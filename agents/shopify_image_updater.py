"""
SHOPIFY IMAGE UPDATER v2
Lee la pestaña '📦 Importados', extrae el término de búsqueda en inglés
de la URL de AliExpress, busca imágenes en tiendas Shopify competidoras
y las añade a los productos ya creados en Shopify que no tengan imágenes.

Si no encuentra tienda, usa AliExpress como fuente de imágenes de producto.
"""
import os, json, asyncio, re
import aiohttp
import gspread
from google.oauth2.service_account import Credentials
from urllib.parse import quote, unquote, urlparse, parse_qs

SHOPIFY_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE_URL", "")
SHEET_ID      = os.environ.get("GOOGLE_SHEET_ID", "")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

SKIP_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "amazon.", "ebay.", "google.", "youtube.", "tiktok.",
    "aliexpress", "duckduckgo", "pinterest", "wish.com",
    "dhgate", "made-in-china", "alibaba.com",
]


def connect_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def extract_aliexpress_term(aliexpress_url: str) -> str:
    """Extrae el término de búsqueda en inglés de una URL de AliExpress."""
    if not aliexpress_url or "aliexpress" not in aliexpress_url:
        return ""
    try:
        parsed = urlparse(aliexpress_url)
        params = parse_qs(parsed.query)
        term = params.get("SearchText", [""])[0]
        return unquote(term).strip()
    except Exception:
        return ""


# ── Shopify API ──────────────────────────────────────────────────────────────

async def get_shopify_product_images(session, product_id):
    """Comprueba cuántas imágenes tiene ya el producto en Shopify."""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products/{product_id}/images.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("images", [])
            elif resp.status == 404:
                print(f"⚠️ Producto {product_id} no encontrado en Shopify (404)")
                return None
    except Exception as ex:
        print(f"⚠️ Error obteniendo imágenes de Shopify: {ex}")
    return None


async def delete_all_product_images(session, product_id, existing_images):
    """Elimina todas las imágenes existentes de un producto en Shopify."""
    sh_headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    deleted = 0
    for img in existing_images:
        img_id = img.get("id")
        if not img_id:
            continue
        del_url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products/{product_id}/images/{img_id}.json"
        try:
            async with session.delete(del_url, headers=sh_headers,
                                      timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    deleted += 1
        except Exception as ex:
            print(f"⚠️ Error borrando imagen {img_id}: {ex}")
        await asyncio.sleep(0.3)
    if deleted:
        print(f"🗑️  {deleted} imágenes malas eliminadas del producto {product_id}")
    return deleted


def looks_like_bad_image(src: str) -> bool:
    """Detecta si una imagen de Shopify es en realidad un badge/banner de AliExpress."""
    if not src:
        return False
    src_lower = src.lower()
    # Banners de AliExpress tienen nombres cortos y palabras como sale, choice, etc.
    filename = src_lower.split('/')[-1].split('.')[0].split('?')[0]
    bad_keywords = ['sale', 'choice', 'badge', 'banner', 'icon', 'logo',
                    'coupon', 'free', 'ship', 'secure', 'guarantee', 'hot', 'new']
    if any(kw in filename for kw in bad_keywords):
        return True
    # Nombres muy cortos son sospechosos
    if len(filename) < 10:
        return True
    return False


async def add_images_to_shopify(session, product_id, image_urls,
                                 replace_existing: bool = False,
                                 existing_images: list = None):
    """Añade (o reemplaza) imágenes en un producto de Shopify."""
    sh_headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products/{product_id}.json"

    # Filtrar URLs con protocolos inválidos
    valid_urls = [u for u in image_urls if u.startswith("http")][:6]
    if not valid_urls:
        return False

    # Si hay que reemplazar, borrar primero las malas
    if replace_existing and existing_images:
        await delete_all_product_images(session, product_id, existing_images)

    payload = {
        "product": {
            "id": product_id,
            "images": [{"src": img_url} for img_url in valid_urls]
        }
    }
    try:
        async with session.put(url, json=payload, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status in (200, 201):
                data = await resp.json()
                count = len(data.get("product", {}).get("images", []))
                print(f"✅ {count} imágenes añadidas al producto {product_id}")
                return True
            else:
                text = await resp.text()
                print(f"⚠️ Error Shopify {resp.status}: {text[:300]}")
    except Exception as ex:
        print(f"⚠️ Error añadiendo imágenes: {ex}")
    return False


# ── Competitor store scraper ──────────────────────────────────────────────────

async def scrape_shopify_store(session, store_url: str, search_term: str) -> list:
    """
    Busca el producto en una tienda Shopify via su API JSON pública.
    Devuelve lista de URLs de imágenes.
    """
    try:
        parsed = urlparse(store_url if store_url.startswith("http") else "https://" + store_url)
        root = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return []

    # Intentar con diferentes variantes del término
    terms_to_try = [search_term]
    words = search_term.split()
    if len(words) > 3:
        terms_to_try.append(" ".join(words[:3]))
    if len(words) > 2:
        terms_to_try.append(" ".join(words[:2]))

    for term in terms_to_try:
        if not term.strip():
            continue

        # ── Intento 1: /search/suggest.json ──────────────────────────
        try:
            api_url = f"{root}/search/suggest.json?q={quote(term)}&resources[type]=product&resources[limit]=3"
            async with session.get(api_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = (data.get("resources", {})
                                   .get("results", {})
                                   .get("products", []))
                    if results:
                        handle = results[0].get("handle", "")
                        if handle:
                            prod_url = f"{root}/products/{handle}.json"
                            async with session.get(prod_url, headers=BROWSER_HEADERS,
                                                   timeout=aiohttp.ClientTimeout(total=12)) as presp:
                                if presp.status == 200:
                                    pdata = await presp.json()
                                    imgs = [img["src"].split("?")[0]
                                            for img in pdata.get("product", {}).get("images", [])[:6]
                                            if img.get("src")]
                                    if imgs:
                                        print(f"   ✅ suggest.json '{root}': {len(imgs)} imágenes")
                                        return imgs
        except Exception:
            pass

        # ── Intento 2: /products.json ─────────────────────────────────
        try:
            api_url = f"{root}/products.json?title={quote(term)}&limit=3"
            async with session.get(api_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    products = data.get("products", [])
                    if products:
                        imgs = [img["src"].split("?")[0]
                                for img in products[0].get("images", [])[:6]
                                if img.get("src")]
                        if imgs:
                            print(f"   ✅ products.json '{root}': {len(imgs)} imágenes")
                            return imgs
        except Exception:
            pass

    return []


async def search_and_scrape(session, english_term: str, spanish_name: str) -> list:
    """
    Busca tiendas en DuckDuckGo con múltiples estrategias y prueba cada candidato.
    Usa primero el término inglés (más preciso), luego el nombre español.
    """
    # Construir lista de queries a probar (de más preciso a menos)
    queries = []
    if english_term:
        queries += [
            f'"{english_term}" site:myshopify.com',
            f'{english_term} buy online shopify',
            f'{english_term} women fashion store',
        ]
    if spanish_name:
        queries += [
            f'"{spanish_name[:40]}" comprar tienda online',
            f'{spanish_name.split()[0]} moda mujer tienda',
        ]

    seen_domains = set()

    for query in queries:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
            async with session.get(ddg_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    await asyncio.sleep(2)
                    continue

                text = await resp.text()
                links = re.findall(r'uddg=([^&"]+)', text)

                for raw_link in links[:15]:
                    url = unquote(raw_link)
                    if not url.startswith("http"):
                        continue
                    if any(skip in url for skip in SKIP_DOMAINS):
                        continue

                    # No repetir mismo dominio
                    try:
                        domain = urlparse(url).netloc
                    except Exception:
                        continue
                    if domain in seen_domains:
                        continue
                    seen_domains.add(domain)

                    print(f"   → Probando: {url[:70]}")
                    term = english_term or spanish_name
                    imgs = await scrape_shopify_store(session, url, term)
                    if imgs:
                        return imgs
                    await asyncio.sleep(0.5)

        except Exception as ex:
            print(f"⚠️ DuckDuckGo error: {ex}")

        await asyncio.sleep(1.5)  # pausa entre queries para no ser bloqueado

    return []


async def scrape_aliexpress_images(session, search_term: str) -> list:
    """
    Fallback: obtiene imágenes reales de producto de AliExpress.

    AliExpress carga las fotos de producto con JavaScript, por lo que el HTML
    estático solo contiene banners y badges (Sale, Choice...).

    Estrategia:
    1. Busca en AliExpress y extrae product_ids del JSON embebido en el HTML
    2. Llama a la API pública de AliExpress para obtener imágenes del primer producto
    3. Si no, usa Bing Images (que sí indexa AliExpress con imágenes reales)
    """
    if not search_term:
        return []

    # ── Intento 1: AliExpress embed JSON ─────────────────────────────────────
    try:
        url = (f"https://www.aliexpress.com/wholesale"
               f"?SearchText={quote(search_term)}&SortType=total_tranpro_desc")
        async with session.get(url, headers=BROWSER_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                text = await resp.text()

                # AliExpress embebe datos de producto en JSON dentro del HTML
                # Buscar patrones como: "productId":"123456789","imageUrl":"https://..."
                product_ids = re.findall(r'"productId"\s*:\s*"?(\d{10,})"?', text)
                img_candidates = re.findall(
                    r'"imageUrl"\s*:\s*"(https?://[^"]+alicdn\.com[^"]+)"', text
                )
                # También buscar el patrón de imágenes en el JSON embebido
                img_candidates += re.findall(
                    r'"img"\s*:\s*"(//[^"]+alicdn\.com[^"]+)"', text
                )

                seen = set()
                valid_imgs = []
                for img in img_candidates:
                    # Normalizar protocolo
                    if img.startswith("//"):
                        img = "https:" + img
                    img = img.split("?")[0]
                    img = re.sub(r'_\d+x\d*(?:\.jpg|\.jpeg|\.png|\.webp)$', '.jpg', img)

                    # Filtro clave: el nombre de archivo debe ser un hash largo (≥20 chars)
                    # Las fotos de producto tienen nombres como "Sabcdef123456789.jpg"
                    # Los badges tienen nombres como "sale-icon.png", "choice.webp"
                    filename = img.split('/')[-1].split('.')[0]
                    if len(filename) < 15:
                        continue
                    # Rechazar nombres con palabras legibles (son badges/banners)
                    if re.search(r'(sale|choice|badge|icon|logo|banner|free|ship|coupon|plus|'
                                 r'guarantee|secure|pay|card|return|flag|star|hot|new)',
                                 filename, re.IGNORECASE):
                        continue

                    if img not in seen and img.startswith("http"):
                        seen.add(img)
                        valid_imgs.append(img)
                    if len(valid_imgs) >= 6:
                        break

                if valid_imgs:
                    print(f"✅ [UPDATER] {len(valid_imgs)} imágenes reales de AliExpress JSON")
                    return valid_imgs

                # Si tenemos product_id, intentar obtener fotos via API de producto
                if product_ids:
                    pid = product_ids[0]
                    api_url = f"https://www.aliexpress.com/item/{pid}.json"
                    async with session.get(api_url, headers=BROWSER_HEADERS,
                                           timeout=aiohttp.ClientTimeout(total=10)) as presp:
                        if presp.status == 200:
                            try:
                                pdata = await presp.json(content_type=None)
                                imgs_raw = (pdata.get("pageModule", {})
                                                .get("imagePathList", []))
                                imgs = []
                                for img in imgs_raw[:6]:
                                    if img.startswith("//"):
                                        img = "https:" + img
                                    imgs.append(img.split("?")[0])
                                if imgs:
                                    print(f"✅ [UPDATER] {len(imgs)} imágenes via AliExpress product API")
                                    return imgs
                            except Exception:
                                pass

    except Exception as ex:
        print(f"⚠️ AliExpress HTML error: {ex}")

    # ── Intento 2: Bing Images (indexa AliExpress con las fotos reales) ───────
    try:
        bing_url = (f"https://www.bing.com/images/search"
                    f"?q={quote(search_term + ' aliexpress')}&first=1&count=6")
        async with session.get(bing_url, headers=BROWSER_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                text = await resp.text()
                # Bing embebe las URLs de imagen real en murl= o mediaurl=
                raw = re.findall(r'"murl"\s*:\s*"([^"]+alicdn\.com[^"]+)"', text)
                raw += re.findall(r'mediaurl=([^&"]+alicdn[^&"]+)', text)

                seen = set()
                valid = []
                for img in raw:
                    img = unquote(img).split("?")[0]
                    filename = img.split('/')[-1].split('.')[0]
                    if len(filename) < 15:
                        continue
                    if re.search(r'(sale|choice|badge|icon|logo|banner)',
                                 filename, re.IGNORECASE):
                        continue
                    if img not in seen and img.startswith("http"):
                        seen.add(img)
                        valid.append(img)
                    if len(valid) >= 6:
                        break

                if valid:
                    print(f"✅ [UPDATER] {len(valid)} imágenes via Bing Images")
                    return valid

    except Exception as ex:
        print(f"⚠️ Bing Images error: {ex}")

    print(f"⚠️ No se encontraron imágenes de producto para '{search_term}'")
    return []


async def find_images_for_product(session, product_name: str,
                                   aliexpress_url: str = "",
                                   website_url: str = "") -> list:
    """
    Estrategia en cascada para encontrar imágenes:
    1. URL directa del competidor (si existe en la hoja)
    2. Búsqueda en DuckDuckGo usando término inglés de AliExpress
    3. Búsqueda en DuckDuckGo usando nombre español
    4. Imágenes directas de AliExpress (fallback)
    """
    english_term = extract_aliexpress_term(aliexpress_url)
    if english_term:
        print(f"   📝 Término inglés: '{english_term}'")

    # 1. URL directa del competidor
    if website_url and website_url not in ("", "N/A", "-", "http", "https"):
        print(f"   → URL directa: {website_url[:60]}")
        term = english_term or product_name
        imgs = await scrape_shopify_store(session, website_url, term)
        if imgs:
            return imgs

    # 2 & 3. Búsqueda DuckDuckGo
    print(f"🔍 [UPDATER] Buscando tienda para: '{product_name[:50]}'...")
    imgs = await search_and_scrape(session, english_term, product_name)
    if imgs:
        return imgs

    # 4. Fallback: imágenes de AliExpress
    if english_term:
        print(f"🔍 [UPDATER] Fallback AliExpress: '{english_term}'...")
        imgs = await scrape_aliexpress_images(session, english_term)
        if imgs:
            return imgs

    return []


# ── Main ─────────────────────────────────────────────────────────────────────

async def run_image_updater(max_to_update: int = 5):
    print("=" * 60)
    print("🖼️  [UPDATER] Actualizando imágenes en Shopify...")
    print("=" * 60)

    if not SHOPIFY_TOKEN:
        print("⚠️ Falta SHOPIFY_ACCESS_TOKEN")
        return
    if not SHOPIFY_STORE:
        print("⚠️ Falta SHOPIFY_STORE_URL")
        return

    # Conectar Google Sheets
    try:
        sheet = connect_sheet()
        ws = sheet.worksheet("📦 Importados")
        all_rows = ws.get_all_values()
    except Exception as e:
        print(f"⚠️ Error conectando Sheet: {e}")
        return

    if len(all_rows) < 2:
        print("⚠️ No hay productos en la pestaña Importados")
        return

    headers = all_rows[0]
    rows = all_rows[1:]
    print(f"📋 {len(rows)} filas encontradas en Importados")
    print(f"📋 Columnas: {headers}")

    # Localizar columnas necesarias
    try:
        idx_nombre     = headers.index("Nombre producto Shopify")
        idx_shopify_id = headers.index("Shopify Product ID")
    except ValueError as e:
        print(f"⚠️ Columna no encontrada: {e}")
        return

    # Columnas opcionales
    idx_ali = headers.index("🛒 AliExpress proveedor") if "🛒 AliExpress proveedor" in headers else -1
    idx_web = headers.index("🌐 Web anunciante")       if "🌐 Web anunciante" in headers       else -1
    idx_orig = headers.index("Nombre original (Sheet)") if "Nombre original (Sheet)" in headers  else -1

    print(f"📋 idx_shopify_id={idx_shopify_id}, idx_ali={idx_ali}, idx_web={idx_web}")

    updated  = 0
    skipped  = 0
    no_id    = 0

    async with aiohttp.ClientSession() as session:
        for i, row in enumerate(rows, start=2):  # start=2 porque fila 1 es cabecera
            if updated >= max_to_update:
                break

            # Rellenar fila corta
            while len(row) <= max(idx_nombre, idx_shopify_id):
                row.append("")

            product_id = row[idx_shopify_id].strip() if row[idx_shopify_id] else ""
            nombre     = row[idx_nombre].strip()      if row[idx_nombre]     else ""
            nombre_orig = (row[idx_orig].strip()
                           if idx_orig >= 0 and len(row) > idx_orig else "")
            ali_url    = (row[idx_ali].strip()
                          if idx_ali >= 0 and len(row) > idx_ali else "")
            website    = (row[idx_web].strip()
                          if idx_web >= 0 and len(row) > idx_web else "")

            display_name = nombre or nombre_orig or f"fila {i}"

            # Saltarse filas sin Shopify ID válido
            if not product_id or product_id in ("ERROR", "error", ""):
                print(f"⏭️  [{i}] Sin Shopify ID para '{display_name}', saltando")
                no_id += 1
                continue

            print(f"\n📦 [{i}] '{display_name}' (ID: {product_id})")

            # Ver imágenes actuales
            existing = await get_shopify_product_images(session, product_id)
            if existing is None:
                # Error de API (404 u otro) — saltamos
                skipped += 1
                continue

            # Detectar si las imágenes existentes son "malas" (banners de AliExpress)
            replace_mode = False
            if existing:
                bad_count = sum(1 for img in existing
                                if looks_like_bad_image(img.get("src", "")))
                if bad_count == len(existing):
                    print(f"⚠️  Tiene {len(existing)} imágenes pero son badges/banners → reemplazando")
                    replace_mode = True
                else:
                    print(f"⏭️  Ya tiene {len(existing)} imágenes buenas, saltando")
                    skipped += 1
                    continue

            # Buscar imágenes reales
            imgs = await find_images_for_product(
                session,
                product_name=nombre or nombre_orig,
                aliexpress_url=ali_url,
                website_url=website,
            )

            if not imgs:
                print(f"⚠️ No se encontraron imágenes para '{display_name}'")
                continue

            # Subir a Shopify (reemplazando las malas si las había)
            success = await add_images_to_shopify(
                session, product_id, imgs,
                replace_existing=replace_mode,
                existing_images=existing if replace_mode else None,
            )
            if success:
                updated += 1

            await asyncio.sleep(1)

    print("\n" + "=" * 60)
    print(f"✅ [UPDATER] Completado:")
    print(f"   • {updated} productos actualizados con imágenes")
    print(f"   • {skipped} productos saltados (ya tenían imágenes o error 404)")
    print(f"   • {no_id} filas sin Shopify Product ID")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_image_updater())
