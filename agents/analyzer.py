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

    pais_principal = countries[0] if countries else "ES"

    prompt = f"""Eres experto en moda femenina europea y dropshipping. Trabajas para Carlota's Collections, una tienda española de moda elegante femenina (precio €30-70) que vende principalmente:
- Vestidos midi y maxi elegantes (casual, fiesta, gala)
- Conjuntos de dos piezas (top+pantalón, blazer+pantalón)
- Vestidos con corsé, encaje, satén, lentejuelas, volantes
- Monos elegantes
- Blazers y abrigos de mujer

Tu misión: analizar anuncios de Meta Ads Library en Europa ({', '.join(countries)}) y detectar productos ganadores que:
1. ENCAJEN con el estilo de Carlota's (elegante, sofisticado, mujer 25-45 años)
2. Sean TENDENCIA EMERGENTE — menos de {max_days} días activo o escalando rápido
3. Tengan buen margen para dropshipping (precio venta €30-70, margen >60%)
4. Complementen o mejoren lo que ya vende Carlota's

SCORING DE OPORTUNIDAD:
- Score 9-10: vestido o conjunto elegante, menos de 7 días activo, alto gasto, estilo que encaja perfectamente
- Score 7-8: producto 7-20 días, tendencia clara, margen excelente
- Score 5-6: producto interesante pero ya con cierta competencia
- Ignora: ropa deportiva, calzado de deporte, accesorios básicos, ropa infantil

ANUNCIOS DETECTADOS:
{ads_ctx}

Genera 8-12 productos ganadores. Para cada uno devuelve EXACTAMENTE este JSON:
{{
  "nombre": "nombre específico del producto",
  "marca": "marca o tienda anunciante",
  "categoria": "categoría exacta",
  "dias_activo": número entero,
  "gasto_dia": número entero USD,
  "variaciones": número entero,
  "paises": ["{pais_principal}"],
  "precio_venta_mxn": número entero,
  "costo_estimado_mxn": número entero,
  "margen_pct": número entero,
  "angulo_venta": "propuesta de valor en 5-8 palabras",
  "por_que_ganador": "razón específica de 10-20 palabras",
  "tendencia": true si está escalando,
  "score": número 1-10,
  "ventaja_primer_movimiento": "descripción de por qué es una oportunidad temprana",
  "ganador": true si score>=6,
  "keyword_origen": "keyword que lo detectó",
  "pais_origen": "{pais_principal}",
  "nombre_anunciante": "nombre de la página/marca en Facebook",
  "url_anunciante": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais_principal}&search_type=page&q=NOMBRE_ANUNCIANTE"
}}

En "nombre_anunciante" pon el nombre real de la página de Facebook que anuncia ese producto.
En "url_anunciante" construye la URL de Meta Ads Library con ese nombre para ver todos sus anuncios.

Solo JSON puro. Sin texto extra."""

    r = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = r.content[0].text.strip()
    s, e = raw.find("["), raw.rfind("]")+1
    try:
        products = json.loads(raw[s:e])
        winners = [p for p in products if p.get("ganador") and p.get("score",0) >= 6]
        print(f"🧠 [ANALYZER] {len(products)} evaluados → {len(winners)} candidatos")
        return winners
    except Exception as ex:
        print(f"⚠️  [ANALYZER] Error JSON: {ex} — intentando extraer productos individuales...")
        # Fallback: extraer objetos JSON uno a uno aunque el array esté roto
        import re
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
            print(f"🧠 [ANALYZER] Recuperados {len(products)} productos individuales → {len(winners)} candidatos")
            return winners
        return []
