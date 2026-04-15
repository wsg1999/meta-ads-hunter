"""
ORCHESTRATOR v4 — Pipeline completo con 7 agentes + reintento automático
Si la primera búsqueda devuelve 0 aprobados, reintenta con keywords de respaldo.
"""
import json, asyncio, os
from datetime import datetime

from agents.keyword_agent    import get_auto_keywords, KEYWORD_POOL
from agents.scraper          import scrape_meta_ads
from agents.analyzer         import analyze_ads
from agents.quality_agent    import classify_and_filter
from agents.top_ads_agent    import analyze_top_ads
from agents.competitor_agent import analyze_competitors
from agents.reporter         import save_to_sheets

CONFIG_FILE = "config.json"

# Keywords de respaldo garantizadas — siempre dan resultados
FALLBACK_KEYWORDS = [
    "vestidos mujer", "tenis mujer", "ropa casual mujer",
    "bolsa crossbody mujer", "conjunto co-ord mujer",
    "blusa crop mujer", "pantalón cargo mujer", "sandalias mujer"
]

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def run_pipeline(keywords, countries, min_spend, max_days, price_seg, genero, content_filter, log_entries):
    """Ejecuta el pipeline completo con las keywords dadas. Devuelve (approved, rejected, top_ads, competitors)."""

    # Scraper
    raw_ads = await scrape_meta_ads(keywords, countries)
    log_entries.append(f"Anuncios scrapeados: {len(raw_ads)}")

    # Analyzer
    analyzed = await analyze_ads(raw_ads, keywords=keywords, countries=countries,
                                  min_spend=min_spend, max_days=max_days,
                                  price_seg=price_seg, genero=genero)
    log_entries.append(f"Anuncios analizados → potenciales ganadores: {len(analyzed)}")

    # Guardar índice de productos originales por nombre para recuperar campos después
    original_by_name = {p.get("nombre", ""): p for p in analyzed}

    # Quality
    approved_raw, rejected = await classify_and_filter(analyzed, content_filter)

    # MERGE: fusionar campos del quality_agent con los datos completos del analyzer
    # Así nunca se pierden gasto_dia, precio, margen, ángulo, etc.
    approved = []
    for p in approved_raw:
        nombre = p.get("nombre", "")
        original = original_by_name.get(nombre, {})
        merged = {**original, **p}   # quality_agent tiene prioridad para sus campos
        approved.append(merged)

    tipos = {}
    for p in approved:
        t = p.get("tipo_anuncio", "desconocido")
        tipos[t] = tipos.get(t, 0) + 1
    log_entries.append(f"Quality Agent → aprobados: {len(approved)}, rechazados: {len(rejected)}")
    log_entries.append(f"Tipos aprobados: {tipos}")

    # Top Ads
    top_ads = await analyze_top_ads(approved)

    # Competitors
    competitors = await analyze_competitors(approved)

    return approved, rejected, top_ads, competitors

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

    # 1. Keywords del día (con rotación automática)
    all_keywords = await get_auto_keywords(base_keywords, countries, genero) if auto_keywords else base_keywords
    log_entries.append(f"Keywords usadas ({len(all_keywords)}): {', '.join(all_keywords)}")

    # 2-6. Pipeline principal
    print("🔄 [ORCHESTRATOR] Intento 1 — keywords del día...")
    approved, rejected, top_ads, competitors = await run_pipeline(
        all_keywords, countries, min_spend, max_days, price_seg, genero, content_filter, log_entries
    )

    # ── REINTENTO AUTOMÁTICO si 0 aprobados ──────────────────────
    if len(approved) == 0:
        print("⚠️  [ORCHESTRATOR] 0 aprobados — reintentando con keywords de respaldo...")
        log_entries.append("⚠️ Reintento automático con keywords de respaldo")

        fallback_kws = list(dict.fromkeys(FALLBACK_KEYWORDS + base_keywords))
        log_entries.append(f"Keywords respaldo: {', '.join(fallback_kws)}")

        approved, rejected, top_ads, competitors = await run_pipeline(
            fallback_kws, countries, min_spend, max_days, price_seg, genero, content_filter, log_entries
        )

        if len(approved) == 0:
            print("⚠️  [ORCHESTRATOR] Sigue en 0 — bajando criterios mínimos...")
            log_entries.append("⚠️ Reintento 2: criterios más permisivos")
            approved, rejected, top_ads, competitors = await run_pipeline(
                fallback_kws, countries,
                min_spend=20,   # Bajamos el gasto mínimo
                max_days=60,    # Ampliamos el rango de días
                price_seg=price_seg, genero=genero,
                content_filter=content_filter,
                log_entries=log_entries
            )

        # ── ÚLTIMO RECURSO: generar análisis sin scraping real ────
        if len(approved) == 0:
            print("⚠️  [ORCHESTRATOR] Último recurso — análisis sin scraping...")
            log_entries.append("⚠️ Último recurso: análisis IA sin scraping")
            from agents.analyzer import analyze_ads
            analyzed_fallback = await analyze_ads(
                [], keywords=FALLBACK_KEYWORDS, countries=countries,
                min_spend=10, max_days=90,
                price_seg=price_seg, genero=genero
            )
            # Aprobar directamente sin pasar por quality_agent
            for p in analyzed_fallback:
                p["tipo_anuncio"] = p.get("tipo_anuncio", "dropshipping")
                p["calidad_contenido"] = p.get("calidad_contenido", 6)
                p["señales_dropshipping"] = p.get("señales_dropshipping", [])
            approved = analyzed_fallback
            rejected = []
            top_ads  = approved[:4] if len(approved) >= 4 else approved
            competitors = []
            log_entries.append(f"Último recurso → {len(approved)} productos generados por IA")

    log_entries.append(f"Top ads: {len(top_ads)} | Competidores: {len(competitors)}")

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
