"""
SHOPIFY IMAGE UPDATER
Lee la pestaña '📦 Importados', busca imágenes de los competidores
y las añade a los productos ya creados en Shopify que no tengan imágenes.
"""
import os, json, asyncio, re
import aiohttp
import gspread
from google.oauth2.service_account import Credentials
from urllib.parse import quote, unquote

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
}


def connect_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)


async def get_shopify_product_images(session, product_id):
    """Comprueba cuántas imágenes tiene ya el producto en Shopify."""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products/{product_id}/images.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("images", [])
    except Exception as ex:
        print(f"⚠️ Error obteniendo imágenes de Shopify: {ex}")
    return None  # None = error, [] = sin imágenes


async def add_images_to_shopify(session, product_id, image_urls):
    """Añade imágenes a un producto existente en Shopify."""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products/{product_id}.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {
        "product": {
            "id": product_id,
            "images": [{"src": img_url} for img_url in image_urls[:6]]
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
                print(f"⚠️ Error Shopify {resp.status}: {text[:200]}")
    except Exception as ex:
        print(f"⚠️ Error añadiendo imágenes: {ex}")
    return False


async def search_competitor_store(session, product_name):
    """Busca la tienda del competidor en DuckDuckGo."""
    candidates = []
    query = f'"{product_name[:40]}" comprar tienda online'
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        async with session.get(ddg_url, headers=BROWSER_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                text = await resp.text()
                links = re.findall(r'uddg=([^&"]+)', text)
                for link in links[:10]:
                    url = unquote(link)
                    if any(skip in url for skip in [
                        "facebook.com", "instagram.com", "twitter.com",
                        "amazon.", "ebay.", "google.", "youtube.", "tiktok.",
                        "aliexpress", "duckduckgo", "pinterest"
                    ]):
                        continue
                    if url.startswith("http"):
                        candidates.append(url)
                        if len(candidates) >= 5:
                            break
    except Exception as ex:
        print(f"⚠️ DuckDuckGo error: {ex}")
    return candidates


async def scrape_shopify_store(session, store_url, product_name):
    """Busca el producto en una tienda Shopify y devuelve imágenes."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(store_url if store_url.startswith("http") else "https://" + store_url)
        root = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return []

    search_terms = [
        product_name,
        " ".join(product_name.split()[:3]),
        " ".join(product_name.split()[:2]),
    ]

    for term in search_terms:
        if not term.strip():
            continue
        try:
            # Intento 1: search/suggest.json
            api_url = f"{root}/search/suggest.json?q={quote(term)}&resources[type]=product&resources[limit]=3"
            async with session.get(api_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
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
                                                   timeout=aiohttp.ClientTimeout(total=10)) as presp:
                                if presp.status == 200:
                                    pdata = await presp.json()
                                    imgs = [img["src"].split("?")[0]
                                            for img in pdata.get("product", {}).get("images", [])[:6]
                                            if img.get("src")]
                                    if imgs:
                                        print(f"✅ [UPDATER] Imágenes de {root}: {len(imgs)}")
                                        return imgs
        except Exception:
            pass

        try:
            # Intento 2: products.json
            api_url = f"{root}/products.json?title={quote(term)}&limit=3"
            async with session.get(api_url, headers=BROWSER_HEADERS,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    products = data.get("products", [])
                    if products:
                        imgs = [img["src"].split("?")[0]
                                for img in products[0].get("images", [])[:6]
                                if img.get("src")]
                        if imgs:
                            print(f"✅ [UPDATER] products.json de {root}: {len(imgs)}")
                            return imgs
        except Exception:
            pass

    return []


async def find_images_for_product(session, product_name, website_url=""):
    """Busca imágenes del producto buscando tiendas competidoras."""
    # Si tenemos URL directa, usarla primero
    if website_url and website_url not in ("", "N/A", "-"):
        imgs = await scrape_shopify_store(session, website_url, product_name)
        if imgs:
            return imgs

    # Buscar en DuckDuckGo
    print(f"🔍 [UPDATER] Buscando tienda para: '{product_name[:50]}'")
    candidates = await search_competitor_store(session, product_name)

    for url in candidates:
        print(f"   → Probando: {url[:60]}")
        imgs = await scrape_shopify_store(session, url, product_name)
        if imgs:
            return imgs
        await asyncio.sleep(0.5)

    return []


async def run_image_updater(max_to_update: int = 5):
    print("=" * 60)
    print("🖼️  [UPDATER] Actualizando imágenes en Shopify...")
    print("=" * 60)

    if not SHOPIFY_TOKEN:
        print("⚠️ Falta SHOPIFY_ACCESS_TOKEN")
        return

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

    # Índices de columnas necesarias
    try:
        idx_nombre    = headers.index("Nombre producto Shopify")
        idx_shopify_id = headers.index("Shopify Product ID")
    except ValueError as e:
        print(f"⚠️ Columna no encontrada: {e}")
        return

    # Columna web si existe
    idx_web = headers.index("🌐 Web anunciante") if "🌐 Web anunciante" in headers else -1

    updated = 0
    async with aiohttp.ClientSession() as session:
        for row in rows:
            if updated >= max_to_update:
                break

            if len(row) <= max(idx_nombre, idx_shopify_id):
                continue

            product_id = row[idx_shopify_id].strip() if row[idx_shopify_id] else ""
            nombre     = row[idx_nombre].strip() if row[idx_nombre] else ""
            website    = row[idx_web].strip() if idx_web >= 0 and len(row) > idx_web else ""

            if not product_id or product_id in ("", "ERROR"):
                print(f"⏭️  Sin ID de Shopify para '{nombre}', saltando")
                continue

            print(f"\n📦 [UPDATER] Procesando: '{nombre}' (ID: {product_id})")

            # Comprobar si ya tiene imágenes
            existing = await get_shopify_product_images(session, product_id)
            if existing is None:
                print(f"⚠️ Error consultando producto {product_id}")
                continue
            if len(existing) > 0:
                print(f"⏭️  Ya tiene {len(existing)} imágenes, saltando")
                continue

            # Buscar imágenes del competidor
            imgs = await find_images_for_product(session, nombre, website)

            if not imgs:
                print(f"⚠️ No se encontraron imágenes para '{nombre}'")
                continue

            # Actualizar el producto en Shopify
            success = await add_images_to_shopify(session, product_id, imgs)
            if success:
                updated += 1

            await asyncio.sleep(1)

    print("\n" + "=" * 60)
    print(f"✅ [UPDATER] Completado: {updated} productos actualizados con imágenes")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_image_updater())
