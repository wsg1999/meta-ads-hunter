"""
ORCHESTRATOR v2 — Agente principal
Pipeline completo:
  1. Keyword Agent  → expande keywords automáticamente con tendencias
  2. Scraper        → extrae anuncios de Meta Ads Library
  3. Analyzer       → evalúa y puntúa con Claude AI
  4. Quality Agent  → clasifica (drop/marca/IA) y filtra contenido inapropiado
  5. Reporter       → guarda en Google Sheets (ganadores + descartados + log)
"""
import json, asyncio, os
from datetime import datetime

from agents.keyword_agent import get_auto_keywords
from agents.scraper       import scrape_meta_ads
from agents.analyzer      import analyze_ads
from agents.quality_agent import classify_and_filter
from agents.reporter      import save_to_sheets

CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def run():
    start_time = datetime.now()
    print("=" * 60)
    print(f"🎯 [ORCHESTRATOR] Iniciando — {start_time.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    config = load_config()

    base_keywords  = config.get("keywords", ["moda mujer"])
    auto_keywords  = config.get("auto_keywords", True)
    countries      = config.get("countries", ["MX"])
    min_spend      = config.get("min_spend_usd_day", 65)
    max_days       = config.get("max_days_active", 30)
    price_seg      = config.get("price_segment", "medio")
    genero         = config.get("gender", "mujer")
    content_filter = config.get("content_filter", {})

    log_entries = []

    # ── PASO 1: Keyword Agent ──────────────────────────────────────
    if auto_keywords:
        all_keywords = await get_auto_keywords(base_keywords, countries, genero)
    else:
        all_keywords = base_keywords

    log_entries.append(f"Keywords usadas ({len(all_keywords)}): {', '.join(all_keywords)}")
    print(f"🎯 [ORCHESTRATOR] {len(all_keywords)} keywords listas")

    # ── PASO 2: Scraper ────────────────────────────────────────────
    raw_ads = await scrape_meta_ads(all_keywords, countries)
    log_entries.append(f"Anuncios scrapeados: {len(raw_ads)}")

    # ── PASO 3: Analyzer ───────────────────────────────────────────
    analyzed = await analyze_ads(
        raw_ads,
        keywords  = all_keywords,
        countries = countries,
        min_spend = min_spend,
        max_days  = max_days,
        price_seg = price_seg,
        genero    = genero,
    )
    log_entries.append(f"Anuncios analizados → potenciales ganadores: {len(analyzed)}")

    # ── PASO 4: Quality Agent ──────────────────────────────────────
    approved, rejected = await classify_and_filter(analyzed, content_filter)
    log_entries.append(f"Quality Agent → aprobados: {len(approved)}, rechazados: {len(rejected)}")

    # Contar por tipo
    tipos = {}
    for p in approved:
        t = p.get("tipo_anuncio", "desconocido")
        tipos[t] = tipos.get(t, 0) + 1
    log_entries.append(f"Tipos aprobados: {tipos}")

    # ── PASO 5: Reporter ───────────────────────────────────────────
    elapsed = (datetime.now() - start_time).seconds
    log_entries.append(f"Tiempo total: {elapsed}s")

    await save_to_sheets(
        winners   = approved,
        rejected  = rejected,
        log_lines = log_entries,
        config    = config,
    )

    print("=" * 60)
    print(f"✅ [ORCHESTRATOR] Completado en {elapsed}s")
    print(f"   Ganadores guardados : {len(approved)}")
    print(f"   Descartados         : {len(rejected)}")
    print(f"   Breakdown tipos     : {tipos}")
    print("=" * 60)

    return approved, rejected

if __name__ == "__main__":
    asyncio.run(run())
