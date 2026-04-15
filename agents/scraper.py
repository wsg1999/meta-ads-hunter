"""
SCRAPER v2 — igual que v1 pero con mejor manejo de errores
"""
import asyncio
from playwright.async_api import async_playwright

META_ADS_URL = "https://www.facebook.com/ads/library/"

async def scrape_meta_ads(keywords: list, countries: list) -> list:
    print("🕷  [SCRAPER] Iniciando Playwright stealth...")
    all_ads = []
    seen_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-MX",
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        # Limitar a máx 5 keywords × 3 países para no exceder tiempo de GitHub Actions
        kw_sample  = keywords[:8]
        co_sample  = countries[:3]

        for country in co_sample:
            for keyword in kw_sample:
                print(f"🕷  [SCRAPER] '{keyword}' en {country}...")
                page = await context.new_page()
                try:
                    url = (
                        f"{META_ADS_URL}?active_status=active&ad_type=all"
                        f"&country={country}&q={keyword.replace(' ','+')}&media_type=all"
                    )
                    await page.goto(url, wait_until="networkidle", timeout=25000)
                    await asyncio.sleep(2)
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(1)

                    ads = await page.evaluate("""() => {
                        const cards = document.querySelectorAll('[class*="x8iyvax"]');
                        const out = [];
                        cards.forEach(c => {
                            const t = c.innerText || '';
                            if (t.length > 40) {
                                // Intentar obtener el ID del anuncio desde links
                                let ad_url = '';
                                let ad_id  = '';
                                const links = c.querySelectorAll('a[href*="id="]');
                                if (links.length > 0) {
                                    const href  = links[0].href;
                                    const match = href.match(/[?&]id=(\d+)/);
                                    if (match) {
                                        ad_id  = match[1];
                                        ad_url = 'https://www.facebook.com/ads/library/?id=' + ad_id;
                                    }
                                }
                                // Fallback: buscar Library ID en el texto
                                if (!ad_id) {
                                    const m = t.match(/Library ID[:\s]+(\d+)/i) || t.match(/ID del anuncio[:\s]+(\d+)/i);
                                    if (m) {
                                        ad_id  = m[1];
                                        ad_url = 'https://www.facebook.com/ads/library/?id=' + ad_id;
                                    }
                                }
                                out.push({ raw_text: t.slice(0,400), ad_url: ad_url, ad_id: ad_id });
                            }
                        });
                        return out;
                    }""")

                    for ad in ads:
                        ad_id = hash(ad.get("raw_text","")[:80])
                        if ad_id not in seen_ids:
                            seen_ids.add(ad_id)
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
