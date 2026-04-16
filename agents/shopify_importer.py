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


def build_shopify_description(product: dict, ai_description: str) -> str:
    """HTML limpio para la descripción de Shopify."""
    nombre = product.get("Producto", product.get("nombre", ""))
    angulo = product.get("Ángulo de venta", "")
    por_que = product.get("Por qué es oportunidad", "")

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
            "body_html": build_shopify_description(product_data["original"], product_data["descripcion_larga"]),
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


# ── Image Fetching ─────────────────────────────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

async def fetch_aliexpress_images(session: aiohttp.ClientSession, search_term: str) -> list:
    """Busca en AliExpress y devuelve URLs de imágenes del primer resultado."""
    try:
        q = quote(search_term)
        url = f"https://www.aliexpress.com/wholesale?SearchText={q}&SortType=total_tranpro_desc"
        async with session.get(url, headers=BROWSER_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=25),
                               allow_redirects=True) as resp:
            if resp.status != 200:
                print(f"⚠️ [IMG] AliExpress status {resp.status}")
                return []
            text = await resp.text()

            # Intento 1: JSON en window.runParams
            m = re.search(r'window\.runParams\s*=\s*(\{.+?\});\s*window\.__', text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    items = (data.get("data", {})
                                 .get("root", {})
                                 .get("fields", {})
                                 .get("mods", {})
                                 .get("itemList", {})
                                 .get("content", []))
                    imgs = []
                    for item in items[:5]:
                        img = (item.get("image", {}).get("imgUrl") or
                               item.get("item", {}).get("mainImageUrl", ""))
                        if img:
                            if img.startswith("//"):
                                img = "https:" + img
                            imgs.append(img)
                    if imgs:
                        print(f"🖼️ [IMG] {len(imgs)} imágenes de AliExpress (runParams)")
                        return imgs
                except Exception:
                    pass

            # Intento 2: URLs del CDN alicdn.com en el HTML
            raw_imgs = re.findall(
                r'https://ae01\.alicdn\.com/kf/[A-Za-z0-9_\-]+\.[a-z]{3,4}',
                text
            )
            seen, imgs = set(), []
            for img in raw_imgs:
                base = re.sub(r'_\d+x\d+', '', img)
                if base not in seen:
                    seen.add(base)
                    imgs.append(base)
                if len(imgs) >= 5:
                    break
            if imgs:
                print(f"🖼️ [IMG] {len(imgs)} imágenes de AliExpress (CDN regex)")
                return imgs

    except Exception as ex:
        print(f"⚠️ [IMG] Error AliExpress: {ex}")
    return []


async def find_product_images(session: aiohttp.ClientSession, product: dict, ai_content: dict) -> list:
    """Obtiene imágenes del producto de AliExpress."""
    search_term = (
        ai_content.get("busqueda_aliexpress") or
        product.get("Cómo encontrar proveedor", "") or
        product.get("Producto", "")
    )
    if not search_term:
        return []

    imgs = await fetch_aliexpress_images(session, search_term)
    if imgs:
        return imgs

    # Segundo intento con término simplificado (primeras 2 palabras)
    words = search_term.split()
    if len(words) > 2:
        imgs = await fetch_aliexpress_images(session, " ".join(words[:2]))
        if imgs:
            return imgs

    print(f"⚠️ [IMG] Sin imágenes para '{search_term[:50]}'")
    return []


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

            # Buscar imágenes del producto
            print(f"🖼️ [IMPORTER] Buscando imágenes para '{nombre}'...")
            imagenes = await find_product_images(session, product, ai_content)
            ai_content["imagenes"] = imagenes
            await asyncio.sleep(1)  # Pausa entre AliExpress y Shopify

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
