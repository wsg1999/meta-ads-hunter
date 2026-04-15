"""
QUALITY AGENT — Agente de calidad y clasificación
Hace DOS cosas:
  1. Detecta si el anuncio es de dropshipping, marca real, o IA genérico
  2. Filtra contenido inapropiado (adulto, violento, engañoso)

Devuelve:
  - approved: lista de anuncios limpios con su clasificación
  - rejected: lista de anuncios descartados con el motivo
"""
import os, json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Señales duras de contenido inapropiado (filtro rápido antes de llamar a la IA)
HARD_BLOCK_WORDS = [
    "xxx", "porn", "sex", "nude", "naked", "onlyfans", "escort",
    "adulto", "desnud", "erótic", "porno", "webcam adult",
    "casino", "apuesta", "crypto guaranteed", "ganar dinero rápido",
    "píldora milagrosa", "pastilla para adelgazar",
]

def quick_block_check(text: str) -> str | None:
    """Revisión rápida sin IA para bloquear contenido obvio."""
    text_lower = text.lower()
    for word in HARD_BLOCK_WORDS:
        if word in text_lower:
            return f"Contenido bloqueado: contiene '{word}'"
    return None

async def classify_and_filter(products: list, content_filter: dict) -> tuple[list, list]:
    """
    Clasifica cada producto y separa aprobados de descartados.
    Retorna (aprobados, descartados)
    """
    print(f"🛡️  [QUALITY AGENT] Evaluando {len(products)} productos...")

    approved = []
    rejected = []

    # --- Filtro rápido primero ---
    for p in products:
        text_to_check = f"{p.get('nombre','')} {p.get('angulo_venta','')} {p.get('por_que_ganador','')}".lower()
        block_reason = quick_block_check(text_to_check)
        if block_reason:
            p["rechazo_motivo"]     = block_reason
            p["rechazo_categoria"]  = "contenido_inapropiado"
            p["tipo_anuncio"]       = "bloqueado"
            rejected.append(p)
        else:
            approved.append(p)  # Pasa al análisis profundo con IA

    print(f"🛡️  [QUALITY AGENT] Filtro rápido: {len(approved)} pasan, {len(rejected)} bloqueados")

    if not approved:
        return [], rejected

    # --- Análisis profundo con Claude ---
    products_json = json.dumps(approved, ensure_ascii=False, indent=2)

    prompt = f"""Eres un experto en ecommerce, dropshipping y publicidad digital. Analiza estos anuncios de moda y clasifícalos.

Para CADA producto debes:

1. CLASIFICAR el tipo de anuncio:
   - "dropshipping": producto genérico revendido, probablemente de AliExpress/Temu/proveedor chino, sin marca establecida
   - "marca_real": marca con identidad propia, presencia en redes, producto propio o exclusivo
   - "ia_generico": copy claramente generado por IA, imágenes de stock, lenguaje genérico y sin personalidad
   - "mixto": tiene elementos de dropshipping pero con branding propio

2. DETECTAR si contiene señales de contenido inapropiado:
   - Imágenes sugestivas o sexualizadas en la descripción
   - Claims falsos o muy exagerados ("pierde 10kg en 3 días")
   - Contenido engañoso o fraudulento
   - Cualquier cosa que no debería aparecer en un negocio de moda legítimo

3. DECIDIR si APROBAR o RECHAZAR:
   - APROBAR: dropshipping, marcas reales, mixtos, ia_generico — TODOS son útiles para el usuario
   - RECHAZAR SOLO: contenido explícitamente adulto, violencia, fraude demostrable ("pierde 10kg en 3 días"), apuestas, crypto
   - IMPORTANTE: ia_generico NO es motivo de rechazo por sí solo. Solo rechaza si además tiene contenido inapropiado.

PRODUCTOS A ANALIZAR:
{products_json}

Devuelve un array JSON donde CADA producto tiene estos campos adicionales:
- "tipo_anuncio": "dropshipping" | "marca_real" | "ia_generico" | "mixto"
- "señales_dropshipping": array de señales detectadas (ej: ["sin marca clara", "precio muy bajo", "copy genérico"])
- "señales_marca_real": array de señales (ej: ["nombre de marca consistente", "estética propia"])
- "calidad_contenido": puntuación del 1 al 10 (10 = contenido muy original y auténtico)
- "aprobado": true o false (usa false MUY raramente, solo para fraude claro o contenido adulto explícito)
- "rechazo_motivo": null si aprobado, o string con el motivo si rechazado
- "rechazo_categoria": null si aprobado, o "contenido_inapropiado" | "claim_falso" | "fraude"

Devuelve SOLO el array JSON. Sin texto. Sin markdown. Sin backticks."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    start = raw.find("[")
    end   = raw.rfind("]") + 1

    try:
        classified = json.loads(raw[start:end])
    except Exception as e:
        print(f"⚠️  [QUALITY AGENT] Error parseando respuesta: {e}")
        # Si falla el parse, aprobar todo con clasificación desconocida
        for p in approved:
            p["tipo_anuncio"]      = "desconocido"
            p["calidad_contenido"] = 5
            p["aprobado"]          = True
        return approved, rejected

    # Separar aprobados y rechazados del análisis IA
    for p in classified:
        if p.get("aprobado", True):
            approved_final_list = approved  # se sobreescribe abajo
            p.pop("aprobado", None)
            approved.append(p) if p not in approved else None
        else:
            p["rechazo_motivo"]    = p.get("rechazo_motivo", "Filtrado por agente de calidad")
            p["rechazo_categoria"] = p.get("rechazo_categoria", "contenido_inapropiado")
            rejected.append(p)

    # Reconstruir listas limpias desde classified
    final_approved = [p for p in classified if p.get("aprobado", True)]
    final_rejected_ia = [p for p in classified if not p.get("aprobado", True)]

    # Unir rechazados del filtro rápido + rechazados por IA
    all_rejected = rejected[:len(rejected)-len(approved)] + final_rejected_ia

    print(f"🛡️  [QUALITY AGENT] Resultado final: {len(final_approved)} aprobados, {len(all_rejected)} rechazados")
    print(f"🛡️  [QUALITY AGENT] Tipos: dropshipping={sum(1 for p in final_approved if p.get('tipo_anuncio')=='dropshipping')}, marca_real={sum(1 for p in final_approved if p.get('tipo_anuncio')=='marca_real')}, ia_generico={sum(1 for p in final_approved if p.get('tipo_anuncio')=='ia_generico')}")

    return final_approved, all_rejected
