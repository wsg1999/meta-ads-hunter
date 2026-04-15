"""ANALYZER v2"""
import json, os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def analyze_ads(raw_ads, keywords, countries, min_spend, max_days, price_seg, genero):
    print(f"🧠 [ANALYZER] Analizando {len(raw_ads)} anuncios...")

    ads_ctx = ""
    for i, ad in enumerate(raw_ads[:35]):
        ads_ctx += f"\n--- Anuncio {i+1} ({ad.get('country','?')}) keyword: {ad.get('keyword','')} ---\n"
        ads_ctx += ad.get("raw_text","")[:300] + "\n"

    if not ads_ctx:
        ads_ctx = "Sin datos del scraper. Genera ejemplos realistas basados en tendencias actuales."

    prompt = f"""Experto en dropshipping de moda. Analiza estos anuncios de Meta Ads Library y genera productos ganadores.

CRITERIOS GANADOR:
- Menos de {max_days} días activo
- Gasto estimado ≥ ${min_spend} USD/día
- Segmento: {price_seg} | Género: {genero}
- Países: {', '.join(countries)}
- Keywords: {', '.join(keywords)}

ANUNCIOS:
{ads_ctx}

Genera 8-10 productos ganadores potenciales. Para cada uno:
{{
  "nombre": "nombre específico del producto",
  "marca": "marca creíble",
  "categoria": "categoría exacta",
  "dias_activo": número,
  "gasto_dia": número USD,
  "variaciones": número,
  "paises": ["MX"],
  "precio_venta_mxn": número,
  "costo_estimado_mxn": número,
  "margen_pct": número,
  "angulo_venta": "frase corta",
  "por_que_ganador": "razón específica",
  "tendencia": true/false,
  "score": número 1-10,
  "ganador": true si score>=7,
  "keyword_origen": "keyword",
  "pais_origen": "MX"
}}

Solo JSON puro. Sin texto extra."""

    r = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = r.content[0].text.strip()
    s, e = raw.find("["), raw.rfind("]")+1
    try:
        products = json.loads(raw[s:e])
        winners = [p for p in products if p.get("ganador") and p.get("score",0) >= 7]
        print(f"🧠 [ANALYZER] {len(products)} evaluados → {len(winners)} candidatos")
        return winners
    except Exception as ex:
        print(f"⚠️  [ANALYZER] Error: {ex}")
        return []
