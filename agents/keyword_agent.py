"""
KEYWORD AGENT — Genera keywords de moda automáticamente
Cada día descubre qué está en tendencia y expande la búsqueda
sin que el usuario tenga que hacer nada.
Incluye rotación diaria de categorías para no repetir siempre los mismos anuncios.
"""
import os, json
from datetime import datetime
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Pool completo de categorías — cada día rota a un grupo diferente
KEYWORD_POOL = [
    # Grupo 0 — Vestidos midi elegantes (core de Carlota's)
    ["vestido midi elegante mujer", "vestido midi satinado", "vestido midi con volantes",
     "vestido midi drapeado", "vestido midi asimétrico mujer"],
    # Grupo 1 — Vestidos maxi y largos
    ["vestido maxi elegante mujer", "vestido largo fiesta", "vestido maxi satén mujer",
     "vestido largo drapeado", "vestido maxi lentejuelas"],
    # Grupo 2 — Vestidos de fiesta y gala
    ["vestido fiesta mujer elegante", "vestido gala corsé", "vestido noche encaje mujer",
     "vestido cóctel mujer", "vestido invitada boda elegante"],
    # Grupo 3 — Vestidos con corsé y escote
    ["vestido corsé mujer", "vestido corsé satén", "vestido bustier elegante",
     "vestido escote profundo elegante", "vestido strapless elegante"],
    # Grupo 4 — Conjuntos dos piezas elegantes
    ["conjunto dos piezas elegante mujer", "set blazer pantalón mujer",
     "conjunto chaqueta pantalón mujer", "co-ord elegante mujer", "conjunto sastre mujer"],
    # Grupo 5 — Conjuntos pantalón ancho
    ["conjunto pantalón palazzo mujer", "set top pantalón wide leg",
     "conjunto pantalón fluido elegante", "outfit pantalón ancho mujer elegante",
     "conjunto palazzo satén mujer"],
    # Grupo 6 — Vestidos encaje y tul
    ["vestido encaje mujer elegante", "vestido tul midi mujer", "vestido encaje floral",
     "vestido encaje corsé", "vestido bordado elegante mujer"],
    # Grupo 7 — Monos y jumpsuits
    ["mono elegante mujer", "jumpsuit elegante mujer", "mono satén mujer",
     "mono wide leg mujer", "jumpsuit fiesta mujer"],
    # Grupo 8 — Blazers y abrigos elegantes
    ["blazer elegante mujer", "blazer oversized mujer", "abrigo elegante mujer",
     "blazer crop mujer", "conjunto blazer mujer tendencia"],
    # Grupo 9 — Tendencias Europa primavera
    ["vestido primavera elegante mujer", "moda primavera mujer europea",
     "vestido floral midi elegante", "conjunto primavera mujer sofisticado",
     "vestido lino elegante mujer"],
]

def get_daily_rotation_keywords() -> list:
    """
    Devuelve el grupo de keywords correspondiente al día de hoy.
    Cada día rota al siguiente grupo del pool, garantizando variedad.
    """
    day_of_year = datetime.utcnow().timetuple().tm_yday
    group_index = day_of_year % len(KEYWORD_POOL)
    selected = KEYWORD_POOL[group_index]
    print(f"🔄 [KEYWORD AGENT] Rotación diaria → Grupo {group_index}: {selected}")
    return selected


async def get_auto_keywords(base_keywords: list, countries: list, gender: str) -> list:
    """
    Usa Claude para expandir las keywords del día (rotación diaria) con tendencias actuales
    de moda en los países objetivo.
    """
    print("🔍 [KEYWORD AGENT] Generando keywords automáticas de tendencia...")

    # Combinar base fija + rotación diaria como punto de partida
    daily_kws  = get_daily_rotation_keywords()
    seed_kws   = list(dict.fromkeys(base_keywords + daily_kws))

    paises_str = ", ".join(countries)

    prompt = f"""Eres un experto en tendencias de moda y ecommerce en Latinoamérica y España.

Tu tarea: dado un conjunto de keywords base de moda, genera keywords ADICIONALES que estén
en tendencia AHORA MISMO en estos países: {paises_str}

Keywords de hoy (rotación diaria): {', '.join(seed_kws)}
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
        # Combinar seed del día + keywords generadas por IA, sin duplicados
        all_kws = list(dict.fromkeys(seed_kws + auto_kws))
        print(f"🔍 [KEYWORD AGENT] {len(auto_kws)} keywords IA + rotación diaria → total: {len(all_kws)}")
        return all_kws
    except Exception as e:
        print(f"⚠️  [KEYWORD AGENT] Error: {e} — usando keywords del día")
        return seed_kws
