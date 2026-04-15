"""
DROPSHIP SPECIALIST — Agente especialista en detectar productos de dropshipping chino
Aprende cada día nuevos patrones y señales de productos dropshippables.
Identifica: productos de AliExpress, Temu, proveedores chinos/turcos vendidos en Europa.
"""
import os, json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Señales conocidas de dropshipping chino — se expanden con el aprendizaje diario
DROPSHIP_SIGNALS = {
    "copy_signals": [
        "limited stock", "stock limitado", "oferta por tiempo limitado",
        "envío gratuito", "free shipping", "50% off", "70% descuento",
        "as seen on", "viral", "trending", "solo hoy", "últimas unidades",
        "compra ahora", "buy now", "agotándose", "selling fast",
        "satisfacción garantizada", "devolución fácil", "30 day return",
        "miles de clientes", "thousands of customers", "#1 bestseller",
    ],
    "price_signals": [
        # Precios bajos para moda de calidad media → margen alto
        "€15", "€19", "€24", "€29", "€34", "€39",
        "19.99", "24.99", "29.99", "34.99", "39.99",
    ],
    "supplier_signals": [
        "ships from", "envío desde", "warehouse", "almacén",
        "procesamiento 2-5 días", "entrega 7-15 días",
        "hecho a mano", "handmade", "artesanal",  # A veces usado para esconder origen
    ],
    "brand_signals": [
        # Nombres de marcas genéricas típicas de dropshipping
        "fashion", "style", "boutique", "wear", "chic", "glam", "look",
        "collection", "studio", "store", "shop", "house", "by",
    ]
}

# Proveedores conocidos de dropshipping de moda para mujer
KNOWN_SUPPLIERS = [
    "AliExpress (moda mujer, buscar misma imagen)",
    "Temu (categoría women's clothing)",
    "CJDropshipping (vestidos y conjuntos)",
    "Zendrop (moda europea)",
    "Spocket (proveedores europeos y americanos)",
    "Modalyst (moda premium dropshipping)",
    "Printful (si es ropa con estampados)",
    "HUSTLE GOT REAL (proveedor UK-Europa)",
    "Alibaba (buscar fabricante directo)",
]


def score_dropship_probability(ad_text: str, page_name: str) -> tuple[int, list]:
    """
    Puntúa la probabilidad de que sea dropshipping chino (0-10)
    Devuelve (score, señales_detectadas)
    """
    text = (ad_text + " " + page_name).lower()
    signals_found = []
    score = 5  # Base neutral

    # Señales positivas de dropshipping
    for signal in DROPSHIP_SIGNALS["copy_signals"]:
        if signal.lower() in text:
            signals_found.append(f"copy: '{signal}'")
            score += 0.5

    for signal in DROPSHIP_SIGNALS["supplier_signals"]:
        if signal.lower() in text:
            signals_found.append(f"supplier: '{signal}'")
            score += 1

    for signal in DROPSHIP_SIGNALS["brand_signals"]:
        if signal.lower() in page_name.lower():
            signals_found.append(f"brand genérica: '{signal}'")
            score += 0.3

    # Señales negativas (marca real establecida)
    established_signals = ["official", "oficial", "®", "™", "since 19", "since 20",
                          "founded in", "est.", "flagship"]
    for sig in established_signals:
        if sig.lower() in text:
            score -= 2
            break

    return min(10, max(0, round(score))), signals_found[:5]


async def analyze_dropship_opportunities(raw_ads: list, trend_context: dict = None) -> list:
    """
    Analiza anuncios y detecta oportunidades de dropshipping.
    Devuelve lista de productos dropshippables con análisis completo.
    """
    print(f"🛒 [DROPSHIP] Analizando {len(raw_ads)} anuncios en busca de oportunidades...")

    # Pre-filtrar: solo anuncios con alta probabilidad de dropshipping
    candidates = []
    for ad in raw_ads:
        ds_score, signals = score_dropship_probability(
            ad.get("raw_text", ""), ad.get("page_name", ""))
        if ds_score >= 5:  # Solo los que tienen señales de dropshipping
            ad["dropship_pre_score"] = ds_score
            ad["dropship_signals_pre"] = signals
            candidates.append(ad)

    print(f"🛒 [DROPSHIP] {len(candidates)} candidatos con señales de dropshipping")

    if not candidates:
        candidates = raw_ads[:20]  # Usar todos si no hay candidatos claros

    # Construir contexto para Claude
    ads_ctx = ""
    for i, ad in enumerate(candidates[:25]):
        ads_ctx += f"""
--- Anuncio {i+1} ---
Página: {ad.get('page_name','')} | País: {ad.get('country','')} | Días activo: {ad.get('dias_activo',0)}
Gasto/día est.: ${ad.get('gasto_dia_est',0)} USD | Señales DS pre-detectadas: {ad.get('dropship_signals_pre',[])}
Texto: {ad.get('raw_text','')[:250]}
Web detectada: {ad.get('website_url','')}
"""

    trend_ctx = ""
    if trend_context:
        trend_ctx = f"""
ESTILOS EN TENDENCIA AHORA EN EUROPA (referencia de marcas grandes):
- {', '.join(trend_context.get('estilos_trending', []))}
- Oportunidad: {trend_context.get('oportunidad_dropship', '')}
"""

    prompt = f"""Eres un EXPERTO ABSOLUTO en dropshipping de moda femenina europea. Llevas años identificando productos de proveedores chinos (AliExpress, Temu, CJ, Spocket) que se venden con marca propia en Europa con márgenes de 200-400%.

Tu misión hoy: analizar estos anuncios de Meta Ads en Europa y encontrar los mejores productos para hacer dropshipping de moda femenina elegante (vestidos, conjuntos, monos).

{trend_ctx}

ANUNCIOS A ANALIZAR:
{ads_ctx}

Para cada oportunidad detectada, indica:
- Qué señales te dicen que es dropshipping (copy genérico, precio inflado, sin marca real, imágenes de stock, etc.)
- Dónde encontrar el proveedor
- Cuánto costaría el producto en origen

Devuelve un array JSON con las mejores oportunidades:
[{{
  "nombre": "descripción del producto (ej: Vestido midi drapeado satén negro con abertura)",
  "marca_anunciante": "nombre de la tienda/página en Facebook",
  "categoria": "vestido midi / conjunto dos piezas / etc.",
  "dias_activo": número,
  "gasto_dia_usd": número estimado,
  "pais": "ES/IT/FR/etc.",
  "precio_venta_eur": número,
  "costo_proveedor_eur": número estimado coste AliExpress/Temu,
  "margen_pct": número,
  "señales_dropshipping": ["señal 1", "señal 2", "señal 3"],
  "proveedor_sugerido": "AliExpress / Temu / CJ / etc. — qué buscar exactamente",
  "como_encontrar_proveedor": "busca en AliExpress: '[keywords exactas para buscar el mismo producto]'",
  "angulo_venta": "propuesta de valor del anunciante que funciona",
  "por_que_oportunidad": "razón concreta de 15-20 palabras",
  "score_dropshipping": número 1-10,
  "score_oportunidad": número 1-10,
  "ganador": true si ambos scores >= 6
}}]

Solo JSON puro. Sin texto extra."""

    try:
        r = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=5000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip()
        s, e = raw.find("["), raw.rfind("]") + 1
        products = json.loads(raw[s:e])
        winners = [p for p in products if p.get("ganador") and p.get("score_oportunidad", 0) >= 6]
        print(f"🛒 [DROPSHIP] {len(products)} analizados → {len(winners)} oportunidades reales")
        return winners
    except Exception as ex:
        import re
        print(f"⚠️  [DROPSHIP] Error JSON: {ex} — extrayendo individualmente...")
        products = []
        for match in re.finditer(r'\{[^{}]+\}', raw if 'raw' in dir() else "", re.DOTALL):
            try:
                p = json.loads(match.group())
                if p.get("nombre"):
                    products.append(p)
            except Exception:
                continue
        return [p for p in products if p.get("score_oportunidad", 0) >= 6]
