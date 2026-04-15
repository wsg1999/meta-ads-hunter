"""
TREND AGENT — Analiza anuncios de marcas grandes para extraer tendencias
No guarda estos productos en el sheet — solo extrae inteligencia de moda
para que el sistema sepa qué buscar en el mercado dropshipping.
"""
import os, json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Marcas grandes a analizar como referencia de tendencia
BIG_BRANDS = [
    "Zara", "Mango", "H&M", "ASOS", "Shein", "Massimo Dutti",
    "Reserved", "Sandro", "COS", "Reformation", "House of CB",
    "Ever Pretty", "Lipsy", "Pull&Bear", "Bershka", "Stradivarius",
    "& Other Stories", "Arket", "Weekday", "Monki"
]

def is_big_brand(nombre_anunciante: str) -> bool:
    """Detecta si un anunciante es una marca grande/reconocida."""
    nombre_lower = nombre_anunciante.lower()
    for brand in BIG_BRANDS:
        if brand.lower() in nombre_lower:
            return True
    return False


async def extract_trend_intelligence(raw_ads: list) -> dict:
    """
    Analiza los anuncios de marcas grandes y extrae:
    - Estilos que están funcionando ahora
    - Colores tendencia
    - Tipos de prendas más anunciadas
    - Ángulos de venta que convierten
    → Esta info se usa para buscar equivalentes en dropshipping
    """
    if not raw_ads:
        return {}

    # Filtrar solo anuncios de marcas reconocidas para análisis de tendencia
    brand_ads = [ad for ad in raw_ads if is_big_brand(ad.get("page_name", ""))]

    if not brand_ads:
        print("🎯 [TREND AGENT] Sin anuncios de marcas grandes para analizar")
        return {}

    print(f"🎯 [TREND AGENT] Analizando {len(brand_ads)} anuncios de marcas grandes...")

    ads_text = ""
    for ad in brand_ads[:20]:
        ads_text += f"\n[{ad.get('page_name','')} - {ad.get('country','')}]: {ad.get('raw_text','')[:200]}\n"

    prompt = f"""Eres experto en tendencias de moda europea. Analiza estos anuncios de marcas grandes y extrae inteligencia de tendencias.

ANUNCIOS DE MARCAS GRANDES (solo para referencia de tendencia):
{ads_text}

Extrae lo que está funcionando AHORA en Europa en moda femenina.

Devuelve este JSON:
{{
  "estilos_trending": ["estilo 1", "estilo 2", "estilo 3", "estilo 4", "estilo 5"],
  "prendas_mas_anunciadas": ["prenda 1", "prenda 2", "prenda 3"],
  "colores_tendencia": ["color 1", "color 2", "color 3"],
  "angulos_venta_efectivos": ["ángulo 1", "ángulo 2", "ángulo 3"],
  "keywords_dropship": ["keyword específica para buscar en dropshipping 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5", "keyword 6", "keyword 7", "keyword 8"],
  "oportunidad_dropship": "descripción de qué producto específico podrías vender ahora mismo aprovechando estas tendencias"
}}

Las keywords_dropship deben ser MUY ESPECÍFICAS para buscar el equivalente dropshippable de estas tendencias — no pongas nombre de marcas grandes.

Solo JSON puro."""

    try:
        r = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip()
        s = raw.find("{")
        e = raw.rfind("}") + 1
        intelligence = json.loads(raw[s:e])
        print(f"🎯 [TREND AGENT] Tendencias extraídas: {intelligence.get('estilos_trending', [])[:3]}")
        print(f"🎯 [TREND AGENT] Keywords dropship generadas: {intelligence.get('keywords_dropship', [])}")
        return intelligence
    except Exception as ex:
        print(f"⚠️  [TREND AGENT] Error: {ex}")
        return {}
