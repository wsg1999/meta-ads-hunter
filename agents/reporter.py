"""
REPORTER v3 — Google Sheets con:
  - Enlace directo a Meta Ads Library del anunciante
  - Colores por días activo (verde=fresquísimo, amarillo=reciente, naranja=moderado)
  - Colores por score
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

HEADERS_WINNERS = [
    "Fecha", "Producto", "Marca", "Categoría",
    "Nombre anunciante", "Ver anuncios en Meta",
    "Tipo anuncio", "Score /10", "Días activo",
    "Gasto/día (USD)", "Variaciones", "Países",
    "Precio venta (MXN)", "Costo est. (MXN)", "Margen %",
    "Ángulo de venta", "Por qué es ganador", "Tendencia",
    "Calidad /10", "Señales dropshipping", "Señales marca real",
    "Keyword origen", "País origen",
]

HEADERS_REJECTED = [
    "Fecha", "Producto", "Marca", "Categoría",
    "Motivo rechazo", "Categoría rechazo",
    "Tipo anuncio", "Score", "Keyword origen",
]

HEADERS_LOG = [
    "Fecha", "Hora", "Keywords",
    "Scrapeados", "Analizados", "Aprobados", "Descartados",
    "Tipos", "Notas",
]

COLOR_DIAS_FRESCO   = {"red": 0.565, "green": 0.933, "blue": 0.565}  # verde  ≤7d
COLOR_DIAS_RECIENTE = {"red": 0.984, "green": 0.933, "blue": 0.459}  # amarillo 8-15d
COLOR_DIAS_MODERADO = {"red": 1.0,   "green": 0.737, "blue": 0.318}  # naranja 16-25d
COLOR_DIAS_ANTIGUO  = {"red": 0.957, "green": 0.490, "blue": 0.490}  # rojo >25d

COLOR_SCORE_TOP  = {"red": 0.204, "green": 0.780, "blue": 0.349}  # verde oscuro 9-10
COLOR_SCORE_ALTO = {"red": 0.565, "green": 0.933, "blue": 0.565}  # verde claro  7-8
COLOR_SCORE_MED  = {"red": 0.984, "green": 0.933, "blue": 0.459}  # amarillo     5-6
COLOR_SCORE_BAJO = {"red": 0.957, "green": 0.490, "blue": 0.490}  # rojo         <5

def get_color_dias(d):
    if d <= 7:  return COLOR_DIAS_FRESCO
    if d <= 15: return COLOR_DIAS_RECIENTE
    if d <= 25: return COLOR_DIAS_MODERADO
    return COLOR_DIAS_ANTIGUO

def get_color_score(s):
    if s >= 9: return COLOR_SCORE_TOP
    if s >= 7: return COLOR_SCORE_ALTO
    if s >= 5: return COLOR_SCORE_MED
    return COLOR_SCORE_BAJO

def build_meta_url(nombre: str, pais: str = "MX") -> str:
    nombre_enc = nombre.replace(" ", "+")
    return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais}&search_type=page&q={nombre_enc}"

def connect_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON no definida")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_or_create_tab(sheet, name, headers):
    try:
        ws = sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(name, rows=2000, cols=max(len(headers), 10))
        ws.append_row(headers)
        ws.format("1:1", {"textFormat": {"bold": True}})
    if not ws.get_all_values():
        ws.append_row(headers)
    return ws

async def save_to_sheets(winners, rejected, log_lines, config):
    print("📊 [REPORTER] Conectando a Google Sheets...")
    try:
        sheet = connect_sheet()
    except Exception as e:
        print(f"⚠️  [REPORTER] Error: {e}")
        return

    tab_names       = config.get("sheets", {})
    tab_winners     = tab_names.get("tab_winners",     "Ganadores")
    tab_descartados = tab_names.get("tab_descartados", "Descartados")
    tab_log         = tab_names.get("tab_log",         "Log diario")
    now   = datetime.now()
    today = now.strftime("%Y-%m-%d %H:%M")

    # ── Ganadores ──────────────────────────────────────────────────
    ws_win = get_or_create_tab(sheet, tab_winners, HEADERS_WINNERS)
    if winners:
        existing  = ws_win.get_all_values()
        start_row = len(existing) + 1
        rows_win  = []
        fmt_reqs  = []

        for i, p in enumerate(winners):
            dias  = int(p.get("dias_activo", 30))
            score = int(p.get("score", 5))
            nombre_anunciante = p.get("nombre_anunciante", p.get("marca", ""))
            pais_origen       = p.get("pais_origen", "MX")
            url_meta          = build_meta_url(nombre_anunciante, pais_origen)

            rows_win.append([
                today,
                p.get("nombre", ""),
                p.get("marca", ""),
                p.get("categoria", ""),
                nombre_anunciante,
                url_meta,
                p.get("tipo_anuncio", ""),
                score,
                dias,
                p.get("gasto_dia", ""),
                p.get("variaciones", ""),
                ", ".join(p.get("paises", [])),
                p.get("precio_venta_mxn", ""),
                p.get("costo_estimado_mxn", ""),
                p.get("margen_pct", ""),
                p.get("angulo_venta", ""),
                p.get("por_que_ganador", ""),
                "Sí" if p.get("tendencia") else "No",
                p.get("calidad_contenido", ""),
                ", ".join(p.get("señales_dropshipping", [])),
                ", ".join(p.get("señales_marca_real", [])),
                p.get("keyword_origen", ""),
                pais_origen,
            ])

            sr = start_row + i
            # Color días (col I = índice 8)
            fmt_reqs.append({"repeatCell": {"range": {
                "sheetId": ws_win.id,
                "startRowIndex": sr-1, "endRowIndex": sr,
                "startColumnIndex": 8, "endColumnIndex": 9},
                "cell": {"userEnteredFormat": {"backgroundColor": get_color_dias(dias)}},
                "fields": "userEnteredFormat.backgroundColor"}})
            # Color score (col H = índice 7)
            fmt_reqs.append({"repeatCell": {"range": {
                "sheetId": ws_win.id,
                "startRowIndex": sr-1, "endRowIndex": sr,
                "startColumnIndex": 7, "endColumnIndex": 8},
                "cell": {"userEnteredFormat": {"backgroundColor": get_color_score(score)}},
                "fields": "userEnteredFormat.backgroundColor"}})

        ws_win.append_rows(rows_win, value_input_option="USER_ENTERED")
        if fmt_reqs:
            sheet.batch_update({"requests": fmt_reqs})
        print(f"📊 [REPORTER] {len(rows_win)} ganadores añadidos con colores")

    # ── Descartados ────────────────────────────────────────────────
    ws_rej = get_or_create_tab(sheet, tab_descartados, HEADERS_REJECTED)
    if rejected:
        rows_rej = [[
            today, p.get("nombre",""), p.get("marca",""), p.get("categoria",""),
            p.get("rechazo_motivo",""), p.get("rechazo_categoria",""),
            p.get("tipo_anuncio",""), p.get("score",""), p.get("keyword_origen",""),
        ] for p in rejected]
        ws_rej.append_rows(rows_rej, value_input_option="USER_ENTERED")
        print(f"📊 [REPORTER] {len(rows_rej)} descartados añadidos")

    # ── Log ────────────────────────────────────────────────────────
    ws_log = get_or_create_tab(sheet, tab_log, HEADERS_LOG)
    ws_log.append_row([
        now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
        next((l.replace("Keywords usadas: ","") for l in log_lines if "Keywords" in l), "")[:200],
        next((l for l in log_lines if "scrapeados" in l), ""),
        next((l for l in log_lines if "potenciales" in l), ""),
        len(winners), len(rejected),
        next((l.replace("Tipos aprobados: ","") for l in log_lines if "Tipos" in l), ""),
        " | ".join(log_lines[-3:]),
    ])
    print("📊 [REPORTER] Log actualizado")
