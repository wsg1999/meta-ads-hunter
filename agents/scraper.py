"""
SCRAPER v4 — Meta Ads Library API oficial
Sin scraping, sin bloqueos, datos reales siempre.
API gratuita de Meta: https://developers.facebook.com/docs/marketing-api/reference/ads-archive
"""
import os
import asyncio
import aiohttp

META_API_URL = "https://graph.facebook.com/v19.0/ads_archive"

FIELDS = ",".join([
    "id",
    "ad_creation_time",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_descriptions",
    "ad_creative_link_captions",   # Suele contener el dominio de la web
    "ad_snapshot_url",
    "page_id",
    "page_name",
    "funding_entity",
    "impressions",
    "spend",
    "currency",
    "publisher_platforms",
    "languages",
])


def build_ad_url(ad_id: str) -> str:
    return f"https://www.facebook.com/ads/library/?id={ad_id}"


def build_page_url(page_name: str, country: str = "ES", page_id: str = "") -> str:
    """URL directa a todos los anuncios de esa página en Meta Ads Library.
    Si tenemos page_id usamos view_all_page_id — enlace exacto sin ambigüedad."""
    if page_id:
        # view_all_page_id = enlace directo a TODOS los anuncios de esa página específica
        return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id={page_id}"
    # Fallback: buscar por nombre exacto
    from urllib.parse import quote
    q = quote(page_name)
    return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={country}&search_type=page&q={q}"


def parse_spend(spend_obj) -> int:
    """Extrae el gasto diario estimado del objeto spend de la API."""
    if not spend_obj:
        return 0
    try:
        lower = int(spend_obj.get("lower_bound", 0) or 0)
        upper = int(spend_obj.get("upper_bound", lower) or lower)
        return (lower + upper) // 2
    except Exception:
        return 0


def parse_impressions(imp_obj) -> int:
    if not imp_obj:
        return 0
    try:
        lower = int(imp_obj.get("lower_bound", 0) or 0)
        upper = int(imp_obj.get("upper_bound", lower) or lower)
        return (lower + upper) // 2
    except Exception:
        return 0


def days_active(start_time: str) -> int:
    """Calcula cuántos días lleva activo el anuncio."""
    from datetime import datetime, timezone
    if not start_time:
        return 0
    try:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, (now - start).days)
    except Exception:
        return 0


async def fetch_ads_for_keyword(session, keyword: str, country: str, token: str, limit: int = 30) -> list:
    """Llama a la API de Meta para una keyword y país concretos."""
    params = {
        "access_token": token,
        "ad_reached_countries": f'["{country}"]',
        "search_terms": keyword,
        "ad_active_status": "ACTIVE",
        "ad_type": "ALL",
        "fields": FIELDS,
        "limit": limit,
    }
    try:
        async with session.get(META_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"⚠️  [API] Error {resp.status} para '{keyword}' ({country}): {text[:200]}")
                return []
            data = await resp.json()
            ads = data.get("data", [])
            print(f"✅ [API] '{keyword}' en {country} → {len(ads)} anuncios")
            return ads
    except asyncio.TimeoutError:
        print(f"⚠️  [API] Timeout para '{keyword}' ({country})")
        return []
    except Exception as e:
        print(f"⚠️  [API] Error inesperado '{keyword}' ({country}): {e}")
        return []


def extract_website_url(ad: dict) -> str:
    """Extrae la URL de la web del comercio desde los datos del anuncio."""
    # 1. Intentar desde captions (suele ser el dominio)
    captions = ad.get("ad_creative_link_captions", []) or []
    for cap in captions:
        if cap and "." in cap and not "facebook" in cap.lower():
            url = cap.strip()
            if not url.startswith("http"):
                url = "https://" + url
            return url

    # 2. Intentar desde descriptions (a veces contienen el dominio)
    descs = ad.get("ad_creative_link_descriptions", []) or []
    for desc in descs:
        if desc and len(desc) < 60 and "." in desc and " " not in desc.strip():
            return "https://" + desc.strip()

    return ""


def format_ad(ad: dict, keyword: str, country: str) -> dict:
    """Convierte el formato de la API al formato interno del sistema."""
    ad_id       = ad.get("id", "")
    page_name   = ad.get("page_name", ad.get("funding_entity", ""))
    bodies      = ad.get("ad_creative_bodies", []) or []
    titles      = ad.get("ad_creative_link_titles", []) or []
    descs       = ad.get("ad_creative_link_descriptions", []) or []
    captions    = ad.get("ad_creative_link_captions", []) or []

    raw_text = " | ".join(filter(None, [
        page_name,
        " ".join(titles[:2]),
        " ".join(bodies[:2]),
        " ".join(descs[:1]),
        " ".join(captions[:1]),
    ]))[:400]

    website_url = extract_website_url(ad)

    spend_total   = parse_spend(ad.get("spend"))
    dias          = days_active(ad.get("ad_delivery_start_time"))
    gasto_dia_est = (spend_total // max(dias, 1)) if dias > 0 else spend_total

    return {
        "raw_text":       raw_text,
        "ad_id":          ad_id,
        "ad_url":         build_ad_url(ad_id) if ad_id else "",
        "snapshot_url":   ad.get("ad_snapshot_url", ""),
        "page_url":       build_page_url(page_name, country, page_id=ad.get("page_id","")),
        "website_url":    website_url,
        "page_name":      page_name,
        "page_id":        ad.get("page_id", ""),
        "ad_start_date":  ad.get("ad_delivery_start_time", ""),
        "dias_activo":    dias,
        "gasto_total":    spend_total,
        "gasto_dia_est":  gasto_dia_est,
        "impresiones":    parse_impressions(ad.get("impressions")),
        "plataformas":    ad.get("publisher_platforms", []),
        "idiomas":        ad.get("languages", []),
        "snapshot_url":   ad.get("ad_snapshot_url", ""),
        "keyword":        keyword,
        "country":        country,
    }


async def scrape_meta_ads(keywords: list, countries: list) -> list:
    """
    Punto de entrada principal. Usa la API oficial de Meta.
    Si no hay token configurado, avisa y devuelve lista vacía.
    """
    token = os.environ.get("META_ACCESS_TOKEN", "")

    if not token:
        print("⚠️  [API] META_ACCESS_TOKEN no configurado.")
        print("⚠️  Sigue las instrucciones en README para obtener tu token gratuito.")
        return []

    print(f"🔑 [API] Usando Meta Ads Library API oficial...")
    all_ads   = []
    seen_ids  = set()

    kw_sample = keywords[:10]
    co_sample = countries[:5]

    async with aiohttp.ClientSession() as session:
        for country in co_sample:
            for keyword in kw_sample:
                ads_raw = await fetch_ads_for_keyword(session, keyword, country, token)
                for ad in ads_raw:
                    ad_id = ad.get("id", "")
                    uid   = ad_id or hash(ad.get("ad_snapshot_url",""))
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        all_ads.append(format_ad(ad, keyword, country))
                await asyncio.sleep(0.3)   # Respetar rate limits de la API

    print(f"✅ [API] Total: {len(all_ads)} anuncios únicos obtenidos")
    return all_ads
