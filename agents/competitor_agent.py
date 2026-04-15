"""
COMPETITOR AGENT — Analiza las tiendas web de la competencia
Para cada ganador busca su tienda web, analiza productos, precios,
estrategia y tiempo que llevan anunciando.
"""
import os, json, asyncio
import anthropic
import aiohttp

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def find_store_url(anunciante: str, marca: str) -> str | None:
    """Intenta deducir la URL de la tienda basándose en el nombre — sin scraping."""
    # Construcción heurística de URL a partir del nombre
    nombre_limpio = marca.lower().replace(" ", "").replace("'", "").replace("&", "")
    candidatos = [
        f"https://www.{nombre_limpio}.com",
        f"https://www.{nombre_limpio}.es",
        f"https://{nombre_limpio}.myshopify.com",
    ]
    async with aiohttp.ClientSession() as session:
        for url in candidatos:
            try:
                async with session.head(url, timeout=aiohttp.ClientTimeout(total=5), allow_redirects=True) as resp:
                    if resp.status < 400:
                        return str(resp.url)
            except Exception:
                continue
    return None

async def analyze_competitor(ad: dict) -> dict:
    """
    Analiza la tienda web de un competidor completo.
    """
    anunciante = ad.get("nombre_anunciante", ad.get("marca", ""))
    marca      = ad.get("marca", "")
    producto   = ad.get("nombre", "")
    dias       = ad.get("dias_activo", 0)
    gasto      = ad.get("gasto_dia", 0)
    paises     = ad.get("paises", [])

    print(f"🔎 [COMPETITOR] Analizando tienda de '{anunciante}'...")

    # 1. Buscar URL de la tienda (sin scraping)
    store_url = await find_store_url(anunciante, marca)
    store_data = {}

    if store_url:
        print(f"🔎 [COMPETITOR] Tienda encontrada: {store_url}")
    else:
        print(f"🔎 [COMPETITOR] No se encontró tienda web para '{anunciante}'")

    # 2. Analizar con Claude
    context = f"""
Anunciante: {anunciante}
Producto anunciado: {producto}
Días anunciando: {dias}
Gasto estimado/día: ${gasto} USD
Países: {', '.join(paises)}
URL tienda: {store_url or 'No encontrada'}
Productos visibles en tienda: {', '.join(store_data.get('productos_visibles', [])[:8])}
Precios detectados: {', '.join(store_data.get('precios', [])[:5])}
Texto de la tienda (extracto): {store_data.get('texto', '')[:800]}
"""

    prompt = f"""Eres un experto en ecommerce y análisis de competencia en dropshipping de moda.

Analiza esta tienda competidora basándote en los datos disponibles:

{context}

Genera un análisis competitivo completo en JSON:

{{
  "url_tienda": "{store_url or ''}",
  "plataforma_tienda": "Shopify / WooCommerce / Tienda propia / No encontrada / etc.",
  "catalogo_estimado": "Descripción de qué tipos de productos venden",
  "rango_precios": "Rango de precios que manejan (ej: $300-$1200 MXN)",
  "tiempo_anunciando": "Estimación de cuánto tiempo llevan haciendo publicidad",
  "presupuesto_mensual_estimado": número en USD estimado mensual,
  "estrategia_principal": "Descripción de su estrategia de venta y publicidad",
  "puntos_fuertes": ["punto fuerte 1", "punto fuerte 2", "punto fuerte 3"],
  "puntos_debiles": ["punto débil 1", "punto débil 2"],
  "oportunidad_para_ti": "Cómo puedes competir con ellos o diferenciarte",
  "productos_mas_anunciados": ["producto 1", "producto 2", "producto 3"],
  "nivel_amenaza": "bajo/medio/alto",
  "recomendacion": "Qué deberías hacer ante este competidor"
}}

Si no se encontró la tienda, analiza basándote en los datos del anuncio.
Solo JSON puro. Sin texto extra."""

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw   = response.content[0].text.strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        analysis = json.loads(raw[start:end])
        analysis["anunciante"]       = anunciante
        analysis["producto_origen"]  = producto
        analysis["score_origen"]     = ad.get("score", 0)
        analysis["keyword_origen"]   = ad.get("keyword_origen", "")
        return analysis

    except Exception as e:
        print(f"⚠️  [COMPETITOR] Error analizando '{anunciante}': {e}")
        return {
            "anunciante": anunciante,
            "producto_origen": producto,
            "url_tienda": store_url or "",
            "error": str(e)
        }

async def analyze_competitors(winners: list) -> list:
    """
    Analiza las tiendas de los top competidores (máx 4).
    """
    if not winners:
        return []

    top = sorted(winners, key=lambda x: x.get("score", 0), reverse=True)[:4]
    print(f"🔎 [COMPETITOR AGENT] Analizando {len(top)} tiendas competidoras...")

    results = []
    for ad in top:
        result = await analyze_competitor(ad)
        results.append(result)
        await asyncio.sleep(2)

    print(f"🔎 [COMPETITOR AGENT] {len(results)} tiendas analizadas")
    return results
