"""
REPORTER v2 — Guarda en Google Sheets con 3 pestañas:
  - Ganadores   : productos aprobados con clasificación drop/marca/IA
  - Descartados : productos rechazados con motivo
  - Log diario  : resumen de cada ejecución
"""
import os, json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")

# ── Cabeceras ──────────────────────────────────────────────────────
HEADERS_WINNERS = [
    "Fecha", "Producto", "Marca", "Categoría",
    "Tipo anuncio",            # dropshipping | marca_real | ia_generico | mixto
    "Señales dropshipping",
    "Señales marca real",
    "Calidad contenido /10",
    "Días activo", "Gasto/día (USD)", "Variaciones",
    "Países", "Precio venta (MXN)", "Costo est. (MXN)", "Margen %",
    "Ángulo de venta", "Por qué es ganador",
    "Tendencia", "Score /10",
    "Keyword origen", "País origen",
]

HEADERS_REJECTED = [
    "Fecha", "Producto", "Marca", "Categoría",
    "Motivo rechazo", "Categoría rechazo",
    "Tipo anuncio detectado",
    "Score original", "Keyword origen",
]

HEADERS_LOG = [
    "Fecha", "Hora inicio", "Keywords usadas",
    "Anuncios scrapeados", "Analizados", "Aprobados", "Descartados",
    "Tipos (drop/marca/ia)", "Notas",
]

# ── Helpers ────────────────────────────────────────────────────────
def get_or_create_tab(sheet, name: str, headers: list):
    try:
        ws = sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(name, rows=2000, cols=len(headers))
        ws.append_row(headers)
        # Formato de cabecera: negrita
        ws.format("1:1", {"textFormat": {"bold": True}})
    vals = ws.get_all_values()
    if not vals:
        ws.append_row(headers)
    return ws

def connect_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON no definida")
    creds = Credentials.from_service_account_info(
        json.loads(creds_json), scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

# ── Función principal ──────────────────────────────────────────────
async def save_to_sheets(
    winners:   list,
    rejected:  list,
    log_lines: list,
    config:    dict,
):
    print(f"📊 [REPORTER] Conectando a Google Sheets...")

    try:
        sheet = connect_sheet()
    except Exception as e:
        print(f"⚠️  [REPORTER] No se pudo conectar: {e}")
        return

    tab_names = config.get("sheets", {})
    tab_winners    = tab_names.get("tab_winners",      "Ganadores")
    tab_descartados = tab_names.get("tab_descartados", "Descartados")
    tab_log        = tab_names.get("tab_log",           "Log diario")

    now = datetime.now()
    today = now.strftime("%Y-%m-%d %H:%M")

    # ── Pestaña Ganadores ──────────────────────────────────────────
    ws_win = get_or_create_tab(sheet, tab_winners, HEADERS_WINNERS)
    if winners:
        rows_win = []
        for p in winners:
            señales_drop  = ", ".join(p.get("señales_dropshipping", []))
            señales_marca = ", ".join(p.get("señales_marca_real", []))
            rows_win.append([
                today,
                p.get("nombre", ""),
                p.get("marca", ""),
                p.get("categoria", ""),
                p.get("tipo_anuncio", ""),
                señales_drop,
                señales_marca,
                p.get("calidad_contenido", ""),
                p.get("dias_activo", ""),
                p.get("gasto_dia", ""),
                p.get("variaciones", ""),
                ", ".join(p.get("paises", [])),
                p.get("precio_venta_mxn", ""),
                p.get("costo_estimado_mxn", ""),
                p.get("margen_pct", ""),
                p.get("angulo_venta", ""),
                p.get("por_que_ganador", ""),
                "Sí" if p.get("tendencia") else "No",
                p.get("score", ""),
                p.get("keyword_origen", ""),
                p.get("pais_origen", ""),
            ])
        ws_win.append_rows(rows_win, value_input_option="USER_ENTERED")
        print(f"📊 [REPORTER] {len(rows_win)} ganadores añadidos a '{tab_winners}'")

    # ── Pestaña Descartados ────────────────────────────────────────
    ws_rej = get_or_create_tab(sheet, tab_descartados, HEADERS_REJECTED)
    if rejected:
        rows_rej = []
        for p in rejected:
            rows_rej.append([
                today,
                p.get("nombre", ""),
                p.get("marca", ""),
                p.get("categoria", ""),
                p.get("rechazo_motivo", ""),
                p.get("rechazo_categoria", ""),
                p.get("tipo_anuncio", ""),
                p.get("score", ""),
                p.get("keyword_origen", ""),
            ])
        ws_rej.append_rows(rows_rej, value_input_option="USER_ENTERED")
        print(f"📊 [REPORTER] {len(rows_rej)} descartados añadidos a '{tab_descartados}'")

    # ── Pestaña Log ────────────────────────────────────────────────
    ws_log = get_or_create_tab(sheet, tab_log, HEADERS_LOG)

    # Extraer métricas del log
    scrapeados = next((l for l in log_lines if "scrapeados" in l), "")
    analizados = next((l for l in log_lines if "potenciales" in l), "")
    tipos_str  = next((l for l in log_lines if "Tipos aprobados" in l), "")
    keywords_str = next((l for l in log_lines if "Keywords usadas" in l), "")

    ws_log.append_row([
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        keywords_str.replace("Keywords usadas: ", "")[:200],
        scrapeados,
        analizados,
        len(winners),
        len(rejected),
        tipos_str.replace("Tipos aprobados: ", ""),
        " | ".join(log_lines[-3:]),
    ])
    print(f"📊 [REPORTER] Log diario actualizado en '{tab_log}'")
