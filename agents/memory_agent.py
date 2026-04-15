"""
MEMORY AGENT — Sistema de aprendizaje acumulativo
Lee los ganadores históricos de Google Sheets, extrae patrones,
detecta qué categorías están escalando y genera inteligencia
para que el sistema busque cada día más profundo en los nichos correctos.
"""
import os, json
import anthropic
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def load_winners_history(config: dict) -> list:
    """Lee los últimos 100 ganadores del Google Sheet para aprender de ellos."""
    try:
        creds = Credentials.from_service_account_info(
            json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scopes=SCOPES)
        sheet = gspread.authorize(creds).open_by_key(
            os.environ.get("GOOGLE_SHEET_ID", ""))
        tab_name = config.get("sheets", {}).get("tab_winners", "Ganadores ✓")
        ws = sheet.worksheet(tab_name)
        rows = ws.get_all_records()
        print(f"🧠 [MEMORY] {len(rows)} ganadores históricos cargados")
        return rows[-100:] if len(rows) > 100 else rows
    except Exception as e:
        print(f"⚠️  [MEMORY] No se pudo cargar historial: {e}")
        return []


async def generate_intelligence(winners_history: list, countries: list, genero: str) -> dict:
    """
    Analiza el historial de ganadores y genera:
    1. Categorías en tendencia ascendente
    2. Keywords emergentes no exploradas aún
    3. Nichos con ventana de oportunidad abierta
    4. Señales de productos que van a explotar
    """
    if not winners_history:
        print("🧠 [MEMORY] Sin historial — usando inteligencia base")
        return {
            "trending_categories": ["vestidos mujer", "accesorios moda"],
            "emerging_keywords": ["vestido asimétrico", "top cut-out", "sandalia minimalista"],
            "opportunity_niches": ["moda sostenible", "ropa vintage", "athleisure"],
            "avoid_saturated": [],
            "trend_signals": []
        }

    # Preparar resumen del historial para Claude
    history_summary = []
    for w in winners_history[-50:]:  # Últimos 50 para no sobrecargar el prompt
        history_summary.append({
            "producto": w.get("Producto", ""),
            "categoria": w.get("Categoría", ""),
            "score": w.get("Score /10", ""),
            "dias_activo": w.get("Días activo", ""),
            "margen": w.get("Margen %", ""),
            "tendencia": w.get("Tendencia", ""),
            "por_que_ganador": str(w.get("Por qué es ganador", ""))[:100],
        })

    paises_str = ", ".join(countries)

    prompt = f"""Eres un analista experto en tendencias de moda y dropshipping en Europa ({paises_str}).

Tienes acceso al historial de los últimos ganadores detectados por el sistema:

{json.dumps(history_summary, ensure_ascii=False, indent=2)}

Tu misión: analizar estos datos y generar inteligencia accionable para las próximas búsquedas.

Responde con este JSON exacto:
{{
  "trending_categories": ["lista de 5 categorías que están escalando según el historial"],
  "emerging_keywords": ["10-15 keywords NUEVAS y específicas que NO aparecen en el historial pero son el siguiente paso lógico de lo que está funcionando — busca el nicho antes de que explote"],
  "opportunity_niches": ["3-5 nichos con ventana de oportunidad abierta en Europa ahora mismo"],
  "avoid_saturated": ["categorías que aparecen demasiado en el historial y ya están saturadas"],
  "trend_signals": ["señales específicas de lo que va a ser tendencia en los próximos 30-60 días basándote en los patrones del historial"],
  "first_mover_keywords": ["5-8 keywords ultra-específicas de productos que NADIE está buscando aún pero que tienen potencial — aquí está la curva ascendente"]
}}

Solo JSON. Sin texto extra."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    try:
        intelligence = json.loads(raw[start:end])
        print(f"🧠 [MEMORY] Inteligencia generada: {len(intelligence.get('emerging_keywords',[]))} keywords emergentes, {len(intelligence.get('first_mover_keywords',[]))} first-mover")
        return intelligence
    except Exception as e:
        print(f"⚠️  [MEMORY] Error parseando inteligencia: {e}")
        return {
            "trending_categories": [],
            "emerging_keywords": [],
            "opportunity_niches": [],
            "avoid_saturated": [],
            "trend_signals": [],
            "first_mover_keywords": []
        }


async def get_smart_keywords(base_keywords: list, config: dict, countries: list, genero: str) -> dict:
    """
    Punto de entrada principal del Memory Agent.
    Devuelve keywords inteligentes basadas en el historial + keywords first-mover.
    """
    print("🧠 [MEMORY AGENT] Analizando historial y generando inteligencia...")
    history = load_winners_history(config)
    intelligence = await generate_intelligence(history, countries, genero)

    # Combinar todo en una lista de keywords priorizada
    emerging = intelligence.get("emerging_keywords", [])
    first_mover = intelligence.get("first_mover_keywords", [])
    trending_cats = intelligence.get("trending_categories", [])

    # Prioridad: first_mover > emerging > base > trending_cats
    smart_keywords = list(dict.fromkeys(
        first_mover[:5] +       # Las 5 más innovadoras primero
        emerging[:8] +          # Emergentes detectadas por IA
        base_keywords[:3] +     # Algunas base para no perder el norte
        trending_cats[:3]       # Categorías en tendencia
    ))

    print(f"🧠 [MEMORY] Keywords inteligentes: {smart_keywords[:10]}")
    print(f"🧠 [MEMORY] Señales de tendencia: {intelligence.get('trend_signals', [])}")

    return {
        "keywords": smart_keywords,
        "intelligence": intelligence,
        "history_count": len(history)
    }
