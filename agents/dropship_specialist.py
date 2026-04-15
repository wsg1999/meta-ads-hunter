"""
DROPSHIP SPECIALIST v2 — Puntúa y filtra anuncios reales directamente
No genera objetos nuevos. Trabaja con los datos reales de la API.
Preserva: raw_text, snapshot_url, page_url, website_url, page_name — todo intacto.
"""
import os, json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Marcas grandes — solo referencia, se excluyen del sheet
BIG_BRANDS = [
    "zara", "mango", "h&m", "hm", "asos", "shein", "massimo dutti",
    "reserved", "sandro", "cos ", " cos", "reformation", "house of cb",
    "ever pretty", "lipsy", "pull&bear", "bershka", "stradivarius",
    "arket", "weekday", "primark", "uniqlo", "nike ", "adidas",
    "levi", "guess", "calvin klein", "tommy", "ralph lauren",
    "michael kors", "zara.com", "mango.com"
]

# Señales de dropshipping chino / producto replicable
DROPSHIP_SIGNALS = [
    "limited stock", "stock limitado", "oferta", "descuento",
    "envío gratis", "free shipping", "50% off", "70% off",
    "as seen on", "viral", "trending", "solo hoy", "últimas unidades",
    "compra ahora", "buy now", "selling fast", "miles de clientes",
    "satisfacción garantizada", "30 day return", "devolución gratis",
    "fashion", "boutique", "store", "shop", "outlet", "collection",
    "wear", "style", "chic", "glam", "look", "studio"
]


def is_big_brand(page_name: str, raw_text: str) -> bool:
    combined = (page_name + " " + raw_text[:100]).lower()
    return any(b in combined for b in BIG_BRANDS)


def dropship_score(ad: dict) -> tuple:
    """Puntúa de 0-10 la probabilidad de que sea dropshipping replicable."""
    text = (ad.get("raw_text", "") + " " + ad.get("page_name", "")).lower()
    signals = []
    score = 4

    # Señales positivas
    for sig in DROPSHIP_SIGNALS:
        if sig.lower() in text:
            signals.append(sig)
            score += 0.4

    # Buen gasto = está funcionando
    gasto = ad.get("gasto_dia_est", 0) or 0
    if gasto >= 50:  score += 2
    elif gasto >= 20: score += 1

    # Días activo óptimos (entre 3 y 45 días = tendencia activa)
    dias = ad.get("dias_activo", 0) or 0
    if 3 <= dias <= 45: score += 1.5
    elif dias <= 2:     score += 1  # Muy nuevo = oportunidad temprana

    # Penalización si es marca grande
    if is_big_brand(ad.get("page_name",""), ad.get("raw_text","")):
        score -= 5

    return min(10, max(0, round(score))), signals[:4]


async def analyze_dropship_opportunities(raw_ads: list, trend_context: dict = None) -> list:
    """
    Filtra y puntúa los anuncios reales. Devuelve los mejores directamente
    con todos sus datos originales intactos (raw_text, snapshot_url, etc.)
    """
    print(f"🛒 [DROPSHIP] Evaluando {len(raw_ads)} anuncios...")

    # Puntuar y filtrar todos los anuncios
    scored = []
    for ad in raw_ads:
        # Saltar marcas grandes
        if is_big_brand(ad.get("page_name",""), ad.get("raw_text","")):
            continue

        score, signals = dropship_score(ad)
        if score >= 4:
            ad_copy = dict(ad)  # Copia para no modificar el original
            ad_copy["dropship_score_pre"] = score
            ad_copy["señales_detectadas"] = signals
            scored.append(ad_copy)

    # Ordenar por score y tomar los mejores
    scored.sort(key=lambda x: x["dropship_score_pre"], reverse=True)
    top_ads = scored[:25]

    if not top_ads:
        print("🛒 [DROPSHIP] Sin candidatos pre-filtro, usando todos")
        top_ads = raw_ads[:20]

    print(f"🛒 [DROPSHIP] {len(top_ads)} candidatos tras pre-filtro, analizando con IA...")

    # Ahora Claude analiza solo los mejores para enriquecerlos
    ads_ctx = ""
    for i, ad in enumerate(top_ads[:20]):
        ads_ctx += f"""
[{i+1}] Página: {ad.get('page_name','')} | País: {ad.get('country','')} | Días: {ad.get('dias_activo',0)} | Gasto/día: ${ad.get('gasto_dia_est',0)}
Texto: {ad.get('raw_text','')[:200]}
"""

    trend_ctx = ""
    if trend_context:
        trend_ctx = f"Tendencias Europa ahora: {', '.join(trend_context.get('estilos_trending',[]))}"

    prompt = f"""Eres experto en dropshipping de moda femenina europea. {trend_ctx}

Analiza estos anuncios y para cada uno que sea una oportunidad de dropshipping devuelve:
- nombre_producto: descripción del producto (vestido midi negro satén, conjunto blazer beige, etc.)
- categoria: vestido midi / conjunto / mono / blazer / etc.
- precio_venta_eur: precio estimado de venta en euros
- costo_proveedor_eur: coste estimado del proveedor (AliExpress/Temu)
- margen_pct: margen estimado en %
- angulo_venta: qué hace que este anuncio funcione (5-8 palabras)
- como_encontrar_proveedor: qué buscar exactamente en AliExpress/Temu para encontrarlo
- por_que_oportunidad: por qué es una buena oportunidad (10-15 palabras)
- score_oportunidad: 1-10
- indice: el número [X] del anuncio

ANUNCIOS:
{ads_ctx}

Solo los que sean dropshipping real (no marcas grandes registradas).
Devuelve array JSON. Solo JSON puro."""

    try:
        r = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip()
        s, e = raw.find("["), raw.rfind("]") + 1
        enriched = json.loads(raw[s:e])

        # Fusionar análisis de Claude CON los datos originales del anuncio (nunca los perdemos)
        results = []
        for item in enriched:
            idx = item.get("indice", 1) - 1
            if 0 <= idx < len(top_ads):
                original = dict(top_ads[idx])  # Datos originales intactos
                # Añadir análisis de Claude SIN sobreescribir datos originales
                original["nombre"]               = item.get("nombre_producto", original.get("page_name",""))
                original["categoria"]            = item.get("categoria","")
                original["precio_venta_eur"]     = item.get("precio_venta_eur","")
                original["costo_proveedor_eur"]  = item.get("costo_proveedor_eur","")
                original["margen_pct"]           = item.get("margen_pct","")
                original["angulo_venta"]         = item.get("angulo_venta","")
                original["como_encontrar_proveedor"] = item.get("como_encontrar_proveedor","")
                original["por_que_oportunidad"]  = item.get("por_que_oportunidad","")
                original["score_oportunidad"]    = item.get("score_oportunidad", 6)
                original["score"]                = item.get("score_oportunidad", 6)
                original["ganador"]              = item.get("score_oportunidad", 0) >= 6
                original["marca_anunciante"]     = original.get("page_name","")
                original["nombre_anunciante"]    = original.get("page_name","")
                original["keyword_origen"]       = original.get("keyword","")
                original["pais"]                 = original.get("country","")
                results.append(original)

        print(f"🛒 [DROPSHIP] {len(results)} oportunidades de dropshipping encontradas")
        return results

    except Exception as ex:
        import re as re_mod
        print(f"⚠️  [DROPSHIP] Error: {ex} — devolviendo top pre-filtrados")
        # Si falla Claude, devolver los pre-filtrados con datos mínimos
        for ad in top_ads[:10]:
            ad["nombre"]           = ad.get("page_name","")
            ad["categoria"]        = "moda mujer"
            ad["score"]            = ad.get("dropship_score_pre", 5)
            ad["ganador"]          = True
            ad["marca_anunciante"] = ad.get("page_name","")
            ad["nombre_anunciante"]= ad.get("page_name","")
            ad["keyword_origen"]   = ad.get("keyword","")
            ad["pais"]             = ad.get("country","")
        return top_ads[:10]
