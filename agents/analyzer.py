"""ANALYZER v3 — Especializado en oportunidades de dropshipping"""
import json, os, re
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Marcas grandes — se usan solo como referencia de tendencia, NO como productos a copiar
BIG_BRANDS_KEYWORDS = [
    "zara", "mango", "h&m", "asos", "shein", "massimo dutti", "reserved",
    "sandro", "cos", "reformation", "house of cb", "ever pretty", "lipsy",
    "pull&bear", "bershka", "stradivarius", "arket", "weekday", "monki",
    "& other stories", "primark", "uniqlo", "nike", "adidas", "levi",
    "guess", "calvin klein", "tommy hilfiger", "ralph lauren", "michael kors"
]

def is_big_brand(text: str) -> bool:
    text_lower = text.lower()
    return any(b in text_lower for b in BIG_BRANDS_KEYWORDS)


async def analyze_ads(raw_ads, keywords, countries, min_spend, max_days, price_seg, genero,
                      trend_intelligence: dict = None):
    print(f"🧠 [ANALYZER] Analizando {len(raw_ads)} anuncios...")

    # Separar anuncios de marcas grandes (referencia) de anuncios dropshippables
    dropship_ads = []
    brand_reference = []

    for ad in raw_ads[:50]:
        page = ad.get("page_name", "")
        text = ad.get("raw_text", "")
        if is_big_brand(page) or is_big_brand(text[:100]):
            brand_reference.append(ad)
        else:
            dropship_ads.append(ad)

    print(f"🧠 [ANALYZER] {len(dropship_ads)} dropshippables, {len(brand_reference)} marcas grandes (referencia)")

    # Construir contexto: primero dropshippables, luego referencia de tendencia
    ads_ctx = ""
    for i, ad in enumerate(dropship_ads[:30]):
        ads_ctx += f"\n--- DROPSHIP {i+1} ({ad.get('country','?')}) [{ad.get('page_name','')}] ---\n"
        ads_ctx += ad.get("raw_text", "")[:250] + "\n"

    trend_ctx = ""
    if trend_intelligence:
        trend_ctx = f"""
TENDENCIAS DETECTADAS EN MARCAS GRANDES (úsalo como referencia de estilo, NO copies estas marcas):
- Estilos trending: {', '.join(trend_intelligence.get('estilos_trending', []))}
- Prendas más anunciadas: {', '.join(trend_intelligence.get('prendas_mas_anunciadas', []))}
- Ángulos de venta efectivos: {', '.join(trend_intelligence.get('angulos_venta_efectivos', []))}
- Oportunidad: {trend_intelligence.get('oportunidad_dropship', '')}
"""

    if not ads_ctx:
        ads_ctx = f"Sin anuncios dropshippables detectados. Genera oportunidades basadas en estas tendencias europeas actuales para vestidos y conjuntos elegantes de mujer."

    pais_principal = countries[0] if countries else "ES"

    prompt = f"""Eres experto en dropshipping de moda femenina europea. Tu cliente tiene una tienda online (Carlota's Collections) y quiere encontrar productos para hacer dropshipping.

OBJETIVO CLARO:
Encuentra productos de marcas PEQUEÑAS o DESCONOCIDAS que:
1. NO sean de marcas grandes/registradas (Zara, Mango, ASOS, etc.)
2. Sean productos genéricos o de marca propia pequeña que se puedan replicar
3. Tengan landing page/creatividad copiable
4. Estén vendiendo bien en Europa ahora mismo (activos, gastando en Meta Ads)
5. Sean vestidos, conjuntos o ropa elegante de mujer (precio €25-65)
6. Tengan márgenes >65% (proveedor chino/turco, venta directa)

{trend_ctx}

ANUNCIOS DROPSHIPPABLES ENCONTRADOS:
{ads_ctx}

IMPORTANTE:
- RECHAZA cualquier producto de Zara, Mango, ASOS, H&M, Shein u otras marcas grandes
- PRIORIZA: marcas desconocidas, tiendas pequeñas, productos sin marca clara, "as seen on social media"
- BUSCA señales de dropshipping: copy genérico, imágenes de stock, nombre de tienda genérico

Genera 8-12 oportunidades de dropshipping. Para cada una devuelve este JSON:
{{
  "nombre": "nombre descriptivo del producto (no la marca)",
  "marca": "nombre de la tienda/página que lo anuncia",
  "categoria": "vestido midi / conjunto dos piezas / vestido fiesta / etc.",
  "dias_activo": número entero,
  "gasto_dia": número entero USD estimado,
  "variaciones": número entero de colores/tallas,
  "paises": ["{pais_principal}"],
  "precio_venta_eur": número entero en euros,
  "costo_estimado_eur": número entero coste proveedor en euros,
  "margen_pct": número entero porcentaje,
  "angulo_venta": "propuesta de valor copiable en 5-8 palabras",
  "por_que_ganador": "por qué es una buena oportunidad de dropshipping en 10-20 palabras",
  "como_replicarlo": "qué proveedor buscar y cómo replicar el producto",
  "tendencia": true si está escalando,
  "score": número 1-10,
  "es_dropshippable": true,
  "ganador": true si score>=6,
  "keyword_origen": "keyword que lo detectó",
  "pais_origen": "{pais_principal}",
  "nombre_anunciante": "nombre exacto de la página en Facebook",
  "url_anunciante": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais_principal}&search_type=page&q=NOMBRE_ANUNCIANTE"
}}

Solo JSON puro. Sin texto extra."""

    r = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = r.content[0].text.strip()
    s, e = raw.find("["), raw.rfind("]") + 1
    try:
        products = json.loads(raw[s:e])
        winners = [p for p in products if p.get("ganador") and p.get("score", 0) >= 6]
        print(f"🧠 [ANALYZER] {len(products)} evaluados → {len(winners)} oportunidades dropshipping")
        return winners
    except Exception as ex:
        print(f"⚠️  [ANALYZER] Error JSON: {ex} — extrayendo individualmente...")
        products = []
        for match in re.finditer(r'\{[^{}]+\}', raw, re.DOTALL):
            try:
                p = json.loads(match.group())
                if p.get("nombre"):
                    products.append(p)
            except Exception:
                continue
        if products:
            winners = [p for p in products if p.get("ganador") and p.get("score", 0) >= 6]
            print(f"🧠 [ANALYZER] Recuperados {len(products)} → {len(winners)} dropshipping")
            return winners
        return []
