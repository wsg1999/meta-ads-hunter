"""
ORCHESTRATOR v3 — Pipeline completo con 7 agentes
"""
import json, asyncio, os
from datetime import datetime

from agents.keyword_agent    import get_auto_keywords
from agents.scraper          import scrape_meta_ads
from agents.analyzer         import analyze_ads
from agents.quality_agent    import classify_and_filter
from agents.top_ads_agent    import analyze_top_ads
from agents.competitor_agent import analyze_competitors
from agents.reporter         import save_to_sheets

CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def run():
    start_time = datetime.now()
    print("=" * 60)
    print(f"🎯 [ORCHESTRATOR] Iniciando — {start_time.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    config         = load_config()
    base_keywords  = config.get("keywords", ["moda mujer"])
    auto_keywords  = config.get("auto_keywords", True)
    countries      = config.get("countries", ["MX"])
    min_spend      = config.get("min_spend_usd_day", 65)
    max_days       = config.get("max_days_active", 30)
    price_seg      = config.get("price_segment", "medio")
    genero         = config.get("gender", "mujer")
    content_filter = config.get("content_filter", {})
    log_entries    = []

    # 1. Keywords
    all_keywords = await get_auto_keywords(base_keywords, countries, genero) if auto_keywords else base_keywords
    log_entries.append(f"Keywords usadas ({len(all_keywords)}): {', '.join(all_keywords)}")

    # 2. Scraper
    raw_ads = await scrape_meta_ads(all_keywords, countries)
    log_entries.append(f"Anuncios scrapeados: {len(raw_ads)}")

    # 3. Analyzer
    analyzed = await analyze_ads(raw_ads, keywords=all_keywords, countries=countries,
                                  min_spend=min_spend, max_days=max_days,
                                  price_seg=price_seg, genero=genero)
    log_entries.append(f"Anuncios analizados → potenciales ganadores: {len(analyzed)}")

    # 4. Quality
    approved, rejected = await classify_and_filter(analyzed, content_filter)
    tipos = {}
    for p in approved:
        t = p.get("tipo_anuncio", "desconocido")
        tipos[t] = tipos.get(t, 0) + 1
    log_entries.append(f"Quality Agent → aprobados: {len(approved)}, rechazados: {len(rejected)}")
    log_entries.append(f"Tipos aprobados: {tipos}")

    # 5. Top Ads
    top_ads = await analyze_top_ads(approved)
    log_entries.append(f"Top ads analizados: {len(top_ads)}")

    # 6. Competitor
    competitors = await analyze_competitors(approved)
    log_entries.append(f"Tiendas competidoras analizadas: {len(competitors)}")

    # 7. Reporter
    elapsed = (datetime.now() - start_time).seconds
    log_entries.append(f"Tiempo total: {elapsed}s")

    await save_to_sheets(
        winners=approved, rejected=rejected,
        top_ads=top_ads, competitors=competitors,
        log_lines=log_entries, config=config,
    )

    print("=" * 60)
    print(f"✅ Completado en {elapsed}s | Ganadores: {len(approved)} | Top: {len(top_ads)} | Competidores: {len(competitors)}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run())
