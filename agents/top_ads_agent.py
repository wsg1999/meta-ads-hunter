"""
TOP ADS AGENT — Analiza los 4 mejores anuncios del día en profundidad
Para cada uno genera un análisis completo: copy, creativos, estrategia,
por qué funciona y cómo replicarlo.
"""
import os, json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def analyze_top_ads(winners: list) -> list:
    """
    Toma los 4 mejores ganadores (por score) y los analiza en profundidad.
    """
    if not winners:
        print("⭐ [TOP ADS AGENT] Sin ganadores para analizar")
        return []

    # Ordenar por score y tomar top 4
    top4 = sorted(winners, key=lambda x: x.get("score", 0), reverse=True)[:4]
    print(f"⭐ [TOP ADS AGENT] Analizando top {len(top4)} anuncios del día...")

    results = []
    for ad in top4:
        nombre    = ad.get("nombre", "")
        marca     = ad.get("marca", "")
        anunciante = ad.get("nombre_anunciante", marca)
        angulo    = ad.get("angulo_venta", "")
        tipo      = ad.get("tipo_anuncio", "")
        dias      = ad.get("dias_activo", 0)
        gasto     = ad.get("gasto_dia", 0)
        variaciones = ad.get("variaciones", 0)
        paises    = ad.get("paises", [])
        score     = ad.get("score", 0)

        prompt = f"""Eres un experto en publicidad digital y dropshipping de moda. Analiza en profundidad este anuncio de Meta Ads Library.

DATOS DEL ANUNCIO:
- Producto: {nombre}
- Marca/Anunciante: {anunciante}
- Tipo: {tipo}
- Ángulo de venta: {angulo}
- Días activo: {dias}
- Gasto estimado/día: ${gasto} USD
- Variaciones de creative: {variaciones}
- Países activos: {', '.join(paises)}
- Score ganador: {score}/10

Genera un análisis COMPLETO y ACCIONABLE en JSON con esta estructura exacta:

{{
  "por_que_funciona": "Explicación de 2-3 frases de por qué este anuncio está funcionando bien",
  "tipo_creative_probable": "Tipo de creative que probablemente usa (ej: video UGC, carousel producto, video lifestyle, imagen estática)",
  "copy_probable": "Cómo es el copy del anuncio probablemente (tono, estructura, llamada a la acción)",
  "audiencia_probable": "A quién se dirige exactamente (edad, intereses, comportamiento)",
  "estrategia_escalado": "Cómo está escalando este anuncio (presupuesto, países, variaciones)",
  "como_replicarlo": "Pasos concretos para replicar esta estrategia con un producto similar",
  "angulos_alternativos": ["ángulo alternativo 1", "ángulo alternativo 2", "ángulo alternativo 3"],
  "productos_complementarios": ["producto que podrías vender junto a este 1", "producto complementario 2"],
  "riesgo_saturacion": "bajo/medio/alto",
  "ventana_oportunidad": "Cuánto tiempo estimado queda antes de que este nicho se sature",
  "puntuacion_replicabilidad": número del 1 al 10 (10 = muy fácil de replicar)
}}

Solo JSON puro. Sin texto extra. Sin markdown."""

        try:
            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            analysis = json.loads(raw[start:end])

            # Combinar datos originales con análisis profundo
            result = {**ad, **analysis}
            results.append(result)
            print(f"⭐ [TOP ADS AGENT] '{nombre}' analizado ✓")

        except Exception as e:
            print(f"⚠️  [TOP ADS AGENT] Error analizando '{nombre}': {e}")
            results.append(ad)

    return results
