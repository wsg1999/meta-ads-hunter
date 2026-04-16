"""
SHOPIFY IMPORTER v2
Lee los productos Ganadores del Sheet y los crea en Shopify como borradores.
- Busca imágenes automáticamente en AliExpress (fuente: mismo proveedor)
- Si no hay imagen en AliExpress, intenta con Google Images
- Registra cada importación en la pestaña "📦 Importados"

Requiere en GitHub Secrets:
  SHOPIFY_ACCESS_TOKEN  → token de la app privada de Shopify (shpat_...)
  SHOPIFY_STORE_URL     → tu-tienda.myshopify.com  (sin https://)
"""
import os, json, asyncio, re
import aiohttp
import anthropic
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from urllib.parse import quote

# ── Config ─────────────────────────────────────────────────────────────────────
SHOPIFY_TOKEN    = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_STORE    = os.environ.get("SHOPIFY_STORE_URL", "")   # ej: carlotasmexico.myshopify.com
SHEET_ID         = os.environ.get("GOOGLE_SHEET_ID", "")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Cabeceras de la pestaña de importados
HEADERS_IMPORTADOS = [
    "Fecha importación",
    "Nombre producto Shopify",        # Nombre que le pusimos en la tienda
    "Nombre original (Sheet)",         # Como venía del Ganadores
    "Categoría",
    "Estado Shopify",                  # borrador / publicado / archivado
    "🔗 Ver en Shopify Admin",         # Link directo al producto en tu panel
    "🛒 AliExpress proveedor",         # Link al proveedor sugerido
    "🔍 PiPiADS referencia",           # Para ver el anuncio original
    "Precio venta (EUR)",
    "Costo proveedor (EUR)",
    "Margen %",
    "Días activo original",
    "Score original",
    "País origen anuncio",
    "Marca anunciante original",
    "Keyword origen",
    "Shopify Product ID",              # Para no duplicar
]

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


def connect_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def get_or_create_importados_tab(sheet):
    tab_name = "📦 Importados"
    try:
        ws = sheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(tab_name, rows=2000, cols=len(HEADERS_IMPORTADOS) + 2)
        ws.update("A1", [HEADERS_IMPORTADOS])
        ws.format("1:1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.118, "green": 0.565, "blue": 1.0}
        })
        print("📦 [IMPORTER] Pestaña 'Importados' creada")
    return ws


def already_imported(ws_importados, nombre_original: str) -> bool:
    """Comprueba si ya importamos este producto antes (evita duplicados)."""
    try:
        all_rows = ws_importados.get_all_values()
        for row in all_rows[1:]:  # Skip header
            if len(row) > 2 and row[2].strip().lower() == nombre_original.strip().lower():
                return True
    except Exception:
        pass
    return False


def get_winners_from_sheet(sheet, tab_name="Ganadores ✓", max_rows=10) -> list:
    """Lee los últimos N ganadores del Sheet para importar."""
    try:
        ws = sheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        # Fallback al nombre sin tilde
        try:
            ws = sheet.worksheet("Ganadores")
        except Exception:
            print("⚠️  [IMPORTER] No se encontró la pestaña de Ganadores")
            return []

    all_rows = ws.get_all_values()
    if len(all_rows) < 2:
        return []

    headers = all_rows[0]
    winners = []
    for row in all_rows[1:]:  # Todas las filas
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))
        product = dict(zip(headers, row))
        winners.append(product)

    # Tomar solo los más recientes (últimos max_rows)
    return winners[-max_rows:]


def build_shopify_description(product: dict, ai_description: str,
                               competitor_html: str = "") -> str:
    """
    HTML para la descripción de Shopify.
    Si tenemos descripción del competidor, la usamos como base.
    Si no, usamos la generada por IA.
    """
    angulo = product.get("Ángulo de venta", "")
    por_que = product.get("Por qué es oportunidad", "")

    # Prioridad: descripción real del competidor
    if competitor_html and len(competitor_html) > 100:
        # Limpiar scripts y estilos del HTML del competidor
        competitor_clean = re.sub(r'<script[^>]*>.*?</script>', '', competitor_html, flags=re.DOTALL)
        competitor_clean = re.sub(r'<style[^>]*>.*?</style>', '', competitor_clean, flags=re.DOTALL)
        html = f'<div class="product-description">\n{competitor_clean}\n'
    else:
        html = f"""<div class="product-description">
  <p class="product-intro">{ai_description}</p>
"""
        if angulo:
            html += f'  <p><strong>✨ {angulo}</strong></p>\n'
        if por_que:
            html += f'  <p>{por_que}</p>\n'

    html += """  <ul>
    <li>Envío rápido a toda España</li>
    <li>Devoluciones gratuitas en 30 días</li>
    <li>Pago seguro 100%</li>
  </ul>
</div>"""
    return html


async def generate_shopify_content(product: dict) -> dict:
    """Claude genera título optimizado y descripción para Shopify en español."""
    nombre_raw = product.get("Producto", product.get("nombre", "producto de moda"))
    categoria  = product.get("Categoría", "ropa mujer")
    angulo     = product.get("Ángulo de venta", "")
    proveedor  = product.get("Cómo encontrar proveedor", "")
    precio     = product.get("Precio venta (EUR)", "")

    prompt = f"""Eres el responsable de contenido de Carlota's Collections, tienda española de moda femenina elegante (carlotasmexico.com).
Precio medio de productos: 30-70€. Tono: cercano, femenino, elegante pero accesible.

Producto a publicar en Shopify:
- Nombre original (del anuncio): {nombre_raw}
- Categoría: {categoria}
- Ángulo de venta detectado: {angulo}
- Qué buscar en AliExpress: {proveedor}
- Precio venta estimado: {precio} EUR

Genera en JSON:
{{
  "titulo_shopify": "Título comercial atractivo para la tienda (máx 70 chars, en español, sin emojis)",
  "descripcion_corta": "Descripción de 1-2 frases para el extracto del producto (máx 160 chars)",
  "descripcion_larga": "Descripción de producto de 3-4 párrafos en español, tono Carlota's Collections, destacando ocasiones de uso, materiales, y beneficios. Sin bullet points excesivos.",
  "tags": ["tag1", "tag2", "tag3"],
  "tipo_producto": "Vestidos" | "Conjuntos" | "Monos" | "Blazers" | "Faldas" | "Tops",
  "busqueda_aliexpress": "Términos exactos para buscar el proveedor en AliExpress (en inglés para mejores resultados)"
}}

Solo JSON puro. Sin markdown."""

    try:
        r = client_ai.messages.create(
            model="claude-opus-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip()
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception as ex:
        print(f"⚠️  [IMPORTER] Error generando contenido IA: {ex}")
        return {
            "titulo_shopify": nombre_raw[:70],
            "descripcion_corta": f"Elegante {categoria} para mujer",
            "descripcion_larga": f"Descubre este precioso {nombre_raw}. Perfecto para cualquier ocasión.",
            "tags": [categoria, "moda mujer", "novedades"],
            "tipo_producto": "Vestidos",
            "busqueda_aliexpress": nombre_raw
        }


async def create_shopify_product(session: aiohttp.ClientSession, product_data: dict) -> dict | None:
    """Crea el producto en Shopify como BORRADOR."""
    if not SHOPIFY_TOKEN or not SHOPIFY_STORE:
        print("⚠️  [IMPORTER] Faltan SHOPIFY_ACCESS_TOKEN o SHOPIFY_STORE_URL en Secrets")
        return None

    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }

    payload = {
        "product": {
            "title": product_data["titulo_shopify"],
            "body_html": build_shopify_description(
                product_data["original"],
                product_data["descripcion_larga"],
                product_data.get("descripcion_competidor", "")
            ),
            "vendor": "Carlota's Collections",
            "product_type": product_data.get("tipo_producto", "Vestidos"),
            "tags": ", ".join(product_data.get("tags", [])),
            "status": "draft",   # SIEMPRE borrador — tú decides cuándo publicar
            "variants": [{
                "price": str(product_data.get("precio", "39.99")),
                "requires_shipping": True,
                "taxable": True,
                "inventory_management": None,  # Sin gestión de stock (dropshipping)
                "fulfillment_service": "manual",
            }],
            "metafields": [
                {
                    "namespace": "carlota",
                    "key": "aliexpress_search",
                    "value": product_data.get("busqueda_aliexpress", ""),
                    "type": "single_line_text_field",
                },
                {
                    "namespace": "carlota",
                    "key": "score_original",
                    "value": str(product_data.get("score", "")),
                    "type": "single_line_text_field",
                },
            ]
        }
    }

    # Añadir imágenes si las tenemos
    imagenes = product_data.get("imagenes", [])
    if imagenes:
        payload["product"]["images"] = [{"src": url} for url in imagenes[:5]]
        print(f"🖼️ [IMPORTER] Subiendo {len(imagenes[:5])} imágenes al producto")

    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status in (200, 201):
                data = await resp.json()
                shopify_product = data.get("product", {})
                product_id = shopify_product.get("id", "")
                print(f"✅ [IMPORTER] '{product_data['titulo_shopify']}' → Shopify ID {product_id}")
                return shopify_product
            else:
                text = await resp.text()
                print(f"⚠️  [IMPORTER] Shopify error {resp.status}: {text[:300]}")
                return None
    except Exception as ex:
        print(f"⚠️  [IMPORTER] Error creando producto en Shopify: {ex}")
        return None


def build_aliexpress_url(busqueda: str) -> str:
    q = quote(busqueda)
    return f"https://www.aliexpress.com/wholesale?SearchText={q}&sortType=total_tranpro_desc"

def build_pipiads_url(busqueda: str) -> str:
    q = quote(busqueda)
    return f"https://www.pipiads.com/ads/?keyword={q}&ad_platform=facebook"

def shopify_admin_url(product_id) -> str:
    return f"https://{SHOPIFY_STORE}/admin/products/{product_id}" if SHOPIFY_STORE else ""


# ── Competitor Scraper ────────────────────────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def clean_url(url: str) -> str:
    """Asegura que la URL tiene protocolo."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/")


async def scrape_shopify_store(session: aiohttp.ClientSession,
                                store_url: str,
                                product_name: str) -> dict:
    """
    Intenta obtener el producto de una tienda Shopify usando su API JSON pública.
    Devuelve dict con 'description' (HTML) y 'images' (lista de URLs).
    """
    domain = clean_url(store_url)
    if not domain:
        return {}

    # Quitamos el path para quedarnos solo con el dominio raíz
    from urllib.parse import urlparse
    parsed = urlparse(domain)
    root = f"{parsed.scheme}://{parsed.netloc}"

    search_terms = [
        product_name,
        " ".join(product_name.split()[:3]),   # primeras 3 palabras
        " ".join(product_name.split()[:2]),   # primeras 2 palabras
    ]

    for term in search_terms:
        if not term.strip():
            continue
        try:
            # Shopify public product search API
            api_url = f"{root}/search/suggest.json?q={quote(term)}&resources[type]=product&resources[limit]=3"
            async with session.get(api_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = (data.get("resources", {})
                                   .get("results", {})
                                   .get("products", []))
                    if results:
                        product_handle = results[0].get("handle", "")
                        if product_handle:
                            product_url = f"{root}/products/{product_handle}.json"
                            async with session.get(product_url, headers=BROWSER_HEADERS,
                                                   timeout=aiohttp.ClientTimeout(total=15)) as presp:
                                if presp.status == 200:
                                    pdata = await presp.json()
                                    prod = pdata.get("product", {})
                                    images = [img["src"].split("?")[0]
                                              for img in prod.get("images", [])[:6]
                                              if img.get("src")]
                                    desc = prod.get("body_html", "")
                                    if images:
                                        print(f"✅ [SCRAPER] Shopify API: '{results[0].get('title','')}' — {len(images)} imgs")
                                        return {"description": desc, "images": images,
                                                "title_competitor": results[0].get("title", "")}
        except Exception as ex:
            print(f"⚠️ [SCRAPER] Error Shopify API: {ex}")

    # Fallback: products.json clásico
    for term in search_terms[:2]:
        try:
            api_url = f"{root}/products.json?title={quote(term)}&limit=3"
            async with session.get(api_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    products = data.get("products", [])
                    if products:
                        prod = products[0]
                        images = [img["src"].split("?")[0]
                                  for img in prod.get("images", [])[:6]
                                  if img.get("src")]
                        desc = prod.get("body_html", "")
                        if images:
                            print(f"✅ [SCRAPER] products.json: '{prod.get('title','')}' — {len(images)} imgs")
                            return {"description": desc, "images": images,
                                    "title_competitor": prod.get("title", "")}
        except Exception as ex:
            print(f"⚠️ [SCRAPER] Error products.json: {ex}")

    return {}


async def scrape_generic_store(session: aiohttp.ClientSession,
                                store_url: str,
                                product_name: str) -> dict:
    """
    Para tiendas NO-Shopify: scrapea la página de búsqueda y extrae
    imágenes de producto con regex.
    """
    domain = clean_url(store_url)
    if not domain:
        return {}

    from urllib.parse import urlparse
    parsed = urlparse(domain)
    root = f"{parsed.scheme}://{parsed.netloc}"

    # Intentar búsqueda estándar
    search_urls = [
        f"{root}/search?q={quote(product_name)}",
        f"{root}/buscar?q={quote(product_name)}",
        f"{root}/?s={quote(product_name)}",
    ]
    for s_url in search_urls:
        try:
            async with session.get(s_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=15),
                                   allow_redirects=True) as resp:
                if resp.status != 200:
                    continue
                text = await resp.text()

                # Extraer links de productos en la página de resultados
                product_links = re.findall(
                    r'href="(/(?:products|producto|item|p)/[^"?#]+)"',
                    text
                )
                if not product_links:
                    continue

                # Tomar el primer resultado de producto
                product_path = product_links[0]
                product_page_url = root + product_path
                async with session.get(product_page_url, headers=BROWSER_HEADERS,
                                       timeout=aiohttp.ClientTimeout(total=15)) as presp:
                    if presp.status != 200:
                        continue
                    ptext = await presp.text()

                    # Extraer imágenes (CDN de Shopify o imágenes genéricas de producto)
                    imgs = []
                    # CDN Shopify
                    shopify_imgs = re.findall(
                        r'https://cdn\.shopify\.com/s/files/[^"\'>\s]+\.(?:jpg|jpeg|png|webp)',
                        ptext
                    )
                    for img in shopify_imgs:
                        clean = re.sub(r'_\d+x\d*', '', img).split("?")[0]
                        if clean not in imgs:
                            imgs.append(clean)
                        if len(imgs) >= 6:
                            break

                    if imgs:
                        print(f"✅ [SCRAPER] Genérico: {len(imgs)} imágenes de {root}")
                        return {"images": imgs, "description": ""}
        except Exception as ex:
            print(f"⚠️ [SCRAPER] Error genérico: {ex}")

    return {}


async def search_competitor_store(session: aiohttp.ClientSession,
                                   brand: str,
                                   product_name: str) -> list:
    """
    Busca la tienda del competidor en DuckDuckGo cuando no tenemos la URL directa.
    Devuelve lista de URLs candidatas para probar.
    """
    candidates = []
    query = f'"{product_name[:40]}" comprar tienda online' if not brand else f"{brand} {product_name[:30]} tienda"
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        async with session.get(ddg_url, headers=BROWSER_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                text = await resp.text()
                # Extraer URLs de resultados de búsqueda
                links = re.findall(
                    r'uddg=([^&"]+)',
                    text
                )
                from urllib.parse import unquote
                for link in links[:8]:
                    url = unquote(link)
                    # Filtrar redes sociales, marketplaces y Google
                    if any(skip in url for skip in [
                        "facebook.com", "instagram.com", "twitter.com",
                        "amazon.", "ebay.", "google.", "youtube.", "tiktok.",
                        "aliexpress", "duckduckgo"
                    ]):
                        continue
                    if url.startswith("http"):
                        candidates.append(url)
                        if len(candidates) >= 4:
                            break
    except Exception as ex:
        print(f"⚠️ [SCRAPER] Error DuckDuckGo: {ex}")

    return candidates


async def get_competitor_content(session: aiohttp.ClientSession,
                                  product: dict,
                                  product_name: str) -> dict:
    """
    Punto de entrada del scraper de competidores.
    1. Usa la URL del Sheet si existe
    2. Si no, la busca automáticamente en DuckDuckGo
    """
    website_url = (
        product.get("🌐 Web anunciante", "") or
        product.get("website_url", "") or
        ""
    ).strip()

    brand = (
        product.get("Marca anunciante", "") or
        product.get("Marca", "") or
        ""
    ).strip()

    # ── Caso 1: tenemos URL directa ──────────────────────────────
    if website_url and website_url not in ("", "N/A", "-"):
        print(f"🔍 [SCRAPER] URL directa: {website_url}")
        result = await scrape_shopify_store(session, website_url, product_name)
        if result.get("images"):
            return result
        result = await scrape_generic_store(session, website_url, product_name)
        if result.get("images"):
            return result

    # ── Caso 2: buscamos la tienda automáticamente ───────────────
    # Usar marca si la tenemos, o solo el nombre del producto
    search_query = f"{brand} {product_name}" if brand else product_name
    print(f"🔍 [SCRAPER] Buscando tienda en DuckDuckGo: '{search_query[:50]}'...")
    candidates = await search_competitor_store(session, brand or product_name.split()[0], product_name)

    for candidate_url in candidates:
        print(f"   → Probando: {candidate_url[:60]}")
        result = await scrape_shopify_store(session, candidate_url, product_name)
        if result.get("images"):
            print(f"✅ [SCRAPER] ¡Encontrado en {candidate_url[:50]}!")
            return result
        await asyncio.sleep(0.5)

    print(f"⚠️ [SCRAPER] No se encontró tienda del competidor para '{brand}'")
    return {}


async def run_importer(max_to_import: int = 5):
    """
    Punto de entrada del importador.
    Lee los últimos ganadores del Sheet, genera contenido con IA,
    los crea en Shopify como borradores y registra todo en la pestaña Importados.
    """
    print("=" * 60)
    print("📦 [IMPORTER] Iniciando importación a Shopify...")
    print("=" * 60)

    if not SHOPIFY_TOKEN:
        print("⚠️  [IMPORTER] SHOPIFY_ACCESS_TOKEN no configurado. Saltando importación.")
        print("⚠️  Añade el secret en GitHub: Settings → Secrets → SHOPIFY_ACCESS_TOKEN")
        return

    # Conectar Sheet
    try:
        sheet = connect_sheet()
        ws_importados = get_or_create_importados_tab(sheet)
    except Exception as e:
        print(f"⚠️  [IMPORTER] Error conectando Sheet: {e}")
        return

    # Leer ganadores
    winners = get_winners_from_sheet(sheet, max_rows=20)
    if not winners:
        print("⚠️  [IMPORTER] No hay productos en Ganadores para importar")
        return

    print(f"📦 [IMPORTER] {len(winners)} ganadores encontrados, procesando hasta {max_to_import}...")

    importados = 0
    async with aiohttp.ClientSession() as session:
        for product in winners:
            nombre = product.get("Producto", "").strip()
            if not nombre:
                continue

            # Evitar duplicados
            if already_imported(ws_importados, nombre):
                print(f"⏭️  [IMPORTER] '{nombre}' ya importado, saltando")
                continue

            if importados >= max_to_import:
                print(f"📦 [IMPORTER] Límite de {max_to_import} importaciones alcanzado")
                break

            print(f"📦 [IMPORTER] Procesando: '{nombre}'...")

            # Generar contenido con IA
            ai_content = await generate_shopify_content(product)
            ai_content["original"] = product

            # Extraer precio
            precio_raw = product.get("Precio venta (EUR)", "39.99")
            try:
                precio = float(str(precio_raw).replace("€","").replace(",",".").strip())
            except Exception:
                precio = 39.99
            ai_content["precio"] = precio
            ai_content["score"] = product.get("Score /10", "")

            # Busqueda AliExpress usando el término más específico disponible
            busqueda_ali = (
                ai_content.get("busqueda_aliexpress") or
                product.get("Cómo encontrar proveedor", "") or
                nombre
            )
            ai_content["busqueda_aliexpress"] = busqueda_ali

            # ── Scraping del competidor (imágenes + descripción real) ──
            print(f"🔍 [IMPORTER] Buscando contenido del competidor para '{nombre}'...")
            competitor = await get_competitor_content(session, product, nombre)
            await asyncio.sleep(1)

            # Si obtenemos imágenes del competidor, las usamos
            if competitor.get("images"):
                ai_content["imagenes"] = competitor["images"]
                print(f"✅ [IMPORTER] {len(competitor['images'])} imágenes del competidor")
            else:
                ai_content["imagenes"] = []
                print(f"⚠️ [IMPORTER] Sin imágenes del competidor, importando sin imagen")

            # Si el competidor tiene descripción real, la usamos (en lugar de la generada por IA)
            if competitor.get("description") and len(competitor["description"]) > 100:
                ai_content["descripcion_competidor"] = competitor["description"]
                print(f"✅ [IMPORTER] Usando descripción real del competidor")

            # Crear en Shopify
            shopify_result = await create_shopify_product(session, ai_content)

            # Registrar en pestaña Importados
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            product_id = shopify_result.get("id", "") if shopify_result else "ERROR"
            admin_url  = shopify_admin_url(product_id) if shopify_result else ""

            row = [
                now,
                ai_content.get("titulo_shopify", nombre),          # Nombre en Shopify
                nombre,                                              # Nombre original del Sheet
                product.get("Categoría", ""),
                "borrador" if shopify_result else "error",
                admin_url,                                           # Link Shopify Admin
                build_aliexpress_url(busqueda_ali),                 # AliExpress proveedor
                build_pipiads_url(nombre),                          # PiPiADS referencia
                product.get("Precio venta (EUR)", ""),
                product.get("Costo proveedor (EUR)", ""),
                product.get("Margen %", ""),
                product.get("Días activo", ""),
                product.get("Score /10", ""),
                product.get("País", ""),
                product.get("Marca anunciante", ""),
                product.get("Keyword origen", ""),
                str(product_id),                                    # Shopify ID
            ]

            ws_importados.append_row(row, value_input_option="USER_ENTERED")
            importados += 1

            if shopify_result:
                print(f"✅ [IMPORTER] '{ai_content['titulo_shopify']}' → borrador en Shopify")
            else:
                print(f"⚠️  [IMPORTER] '{nombre}' registrado con error en Sheet")

            await asyncio.sleep(0.5)  # Rate limit Shopify API

    print("=" * 60)
    print(f"✅ [IMPORTER] Completado: {importados} productos importados a Shopify")
    print(f"✅ Revisa tus borradores en: https://{SHOPIFY_STORE}/admin/products?status=draft")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_importer())
