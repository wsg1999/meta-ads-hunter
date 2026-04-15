"""
SCRAPER v3 — Selectores múltiples + captura de texto completo de página
Si el selector específico de Meta falla (cambian las clases CSS),
usa selectores genéricos alternativos para no quedarse en 0.
"""
import asyncio
from playwright.async_api import async_playwright

META_ADS_URL = "https://www.facebook.com/ads/library/"

# Selectores en orden de preferencia — si Meta cambia sus clases, los alternativos recogen igual
SELECTORS = [
    '[class*="x8iyvax"]',           # Selector principal (clase Meta actual)
    '[class*="_7jyr"]',             # Alternativo 1
    '[data-testid*="ad-"]',        # Alternativo 2 por atributo data
    'div[role="article"]',         # Genérico: artículos
    '.x1lliihq',                   # Otra clase frecuente en Meta
]

def extract_ad_url(card_text, card_element_js):
    """JS para extraer URL directa del anuncio."""
    return """(c) => {
        let ad_url = '', ad_id = '';
        const links = c.querySelectorAll('a[href*="id="]');
        if (links.length > 0) {
            const match = links[0].href.match(/[?&]id=(\\d+)/);
            if (match) { ad_id = match[1]; ad_url = 'https://www.facebook.com/ads/library/?id=' + ad_id; }
        }
        if (!ad_id) {
            const t = c.innerText || '';
            const m = t.match(/Library ID[:\\s]+(\\d+)/i) || t.match(/ID del anuncio[:\\s]+(\\d+)/i);
            if (m) { ad_id = m[1]; ad_url = 'https://www.facebook.com/ads/library/?id=' + ad_id; }
        }
        return { ad_url, ad_id };
    }"""

async def scrape_page(page, keyword, country):
    """Intenta extraer anuncios de una página usando múltiples selectores."""
    ads = []

    for selector in SELECTORS:
        try:
            js = f"""() => {{
                const cards = document.querySelectorAll('{selector}');
                const out = [];
                cards.forEach(c => {{
                    const t = c.innerText || '';
                    if (t.length > 40) {{
                        let ad_url = '', ad_id = '';
                        const links = c.querySelectorAll('a[href*="id="]');
                        if (links.length > 0) {{
                            const match = links[0].href.match(/[?&]id=(\\d+)/);
                            if (match) {{ ad_id = match[1]; ad_url = 'https://www.facebook.com/ads/library/?id=' + ad_id; }}
                        }}
                        if (!ad_id) {{
                            const m = t.match(/Library ID[:\\s]+(\\d+)/i);
                            if (m) {{ ad_id = m[1]; ad_url = 'https://www.facebook.com/ads/library/?id=' + ad_id; }}
                        }}
                        out.push({{ raw_text: t.slice(0, 400), ad_url, ad_id }});
                    }}
                }});
                return out;
            }}"""
            result = await page.evaluate(js)
            if result and len(result) > 0:
                print(f"🕷  [SCRAPER] Selector '{selector}' → {len(result)} anuncios")
                ads = result
                break
        except Exception:
            continue

    # Fallback final: capturar texto visible de toda la página si todo falla
    if not ads:
        try:
            page_text = await page.inner_text("body")
            chunks = [page_text[i:i+350] for i in range(0, min(len(page_text), 3500), 350)]
            ads = [{"raw_text": c, "ad_url": "", "ad_id": ""} for c in chunks if len(c) > 80]
            if ads:
                print(f"🕷  [SCRAPER] Fallback texto página → {len(ads)} fragmentos")
        except Exception as e:
            print(f"🕷  [SCRAPER] Fallback también falló: {e}")

    return ads


async def scrape_meta_ads(keywords: list, countries: list) -> list:
    print("🕷  [SCRAPER] Iniciando Playwright stealth...")
    all_ads = []
    seen_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-MX",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "es-MX,es;q=0.9,en;q=0.8"}
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        kw_sample = keywords[:8]
        co_sample = countries[:3]

        for country in co_sample:
            for keyword in kw_sample:
                print(f"🕷  [SCRAPER] '{keyword}' en {country}...")
                page = await context.new_page()
                try:
                    url = (
                        f"{META_ADS_URL}?active_status=active&ad_type=all"
                        f"&country={country}&q={keyword.replace(' ', '+')}&media_type=all"
                    )
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(3)

                    # Scroll más agresivo para cargar más anuncios
                    for _ in range(5):
                        await page.evaluate("window.scrollBy(0, 600)")
                        await asyncio.sleep(0.8)

                    ads = await scrape_page(page, keyword, country)

                    for ad in ads:
                        uid = hash(ad.get("raw_text", "")[:80])
                        if uid not in seen_ids:
                            seen_ids.add(uid)
                            ad["keyword"] = keyword
                            ad["country"] = country
                            all_ads.append(ad)

                except Exception as e:
                    print(f"⚠️  [SCRAPER] Error '{keyword}' ({country}): {e}")
                finally:
                    await page.close()
                await asyncio.sleep(1.5)

        await browser.close()

    print(f"🕷  [SCRAPER] Total: {len(all_ads)} anuncios únicos")
    return all_ads
