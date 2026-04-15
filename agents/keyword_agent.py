"""
KEYWORD AGENT — Genera keywords de moda automáticamente
Cada día descubre qué está en tendencia y expande la búsqueda
sin que el usuario tenga que hacer nada.
"""
import os, json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def get_auto_keywords(base_keywords: list, countries: list, gender: str) -> list:
    """
    Usa Claude para expandir las keywords base con tendencias actuales
    de moda en los países objetivo.
    """
    print("🔍 [KEYWORD AGENT] Generando keywords automáticas de tendencia...")

    paises_str = ", ".join(countries)

    prompt = f"""Eres un experto en tendencias de moda y ecommerce en Latinoamérica y España.

Tu tarea: dado un conjunto de keywords base de moda, genera keywords ADICIONALES que estén
en tendencia AHORA MISMO en estos países: {paises_str}

Keywords base del usuario: {', '.join(base_keywords)}
Género objetivo: {gender}

Genera entre 8 y 12 keywords adicionales específicas y actuales. Piensa en:
- Tendencias virales de TikTok e Instagram en esos países
- Temporada actual (considera la época del año)
- Estilos que están escalando en Meta Ads ahora
- Subcategorías específicas que venden bien en dropshipping de moda
- Términos en español que usan realmente los compradores

Ejemplos de buenas keywords específicas:
"conjunto co-ord mujer", "vestido crochet playa", "tenis chunky mujer",
"blusa crop bordada", "pantalón cargo mujer", "set deportivo mujer"

Devuelve SOLO un array JSON de strings. Sin texto. Sin markdown.
Ejemplo: ["keyword 1", "keyword 2", "keyword 3"]"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    start = raw.find("[")
    end   = raw.rfind("]") + 1

    try:
        auto_kws = json.loads(raw[start:end])
        # Combinar con las base, eliminar duplicados
        all_kws = list(dict.fromkeys(base_keywords + auto_kws))
        print(f"🔍 [KEYWORD AGENT] {len(auto_kws)} keywords nuevas generadas → total: {len(all_kws)}")
        return all_kws
    except Exception as e:
        print(f"⚠️  [KEYWORD AGENT] Error: {e} — usando solo keywords base")
        return base_keywords
