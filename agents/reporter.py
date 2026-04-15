"""
REPORTER v4 — 5 pestañas en Google Sheets:
  - Ganadores        : con colores por días y score
  - Top 4 del día    : análisis profundo de los 4 mejores
  - Competidores     : análisis de tiendas web rivales
  - Descartados      : rechazados con motivo
  - Log diario       : historial de ejecuciones
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
    "Nombre anunciante", "Ver anuncios en Meta", "Link directo al anuncio",
    "Tipo anuncio", "Score /10", "Días activo",
    "Gasto/día (USD)", "Variaciones", "Países",
    "Precio venta (MXN)", "Costo est. (MXN)", "Margen %",
    "Ángulo de venta", "Por qué es ganador", "Tendencia",
    "Calidad /10", "Señales dropshipping", "Keyword origen",
]

HEADERS_TOP = [
    "Fecha", "Posición", "Producto", "Marca", "Score /10", "Días activo",
    "Por qué funciona", "Tipo creative probable", "Copy probable",
    "Audiencia probable", "Estrategia de escalado",
    "Cómo replicarlo", "Ángulos alternativos",
    "Productos complementarios", "Riesgo saturación",
    "Ventana de oportunidad", "Replicabilidad /10",
    "Ver anuncios en Meta", "Link directo al anuncio",
]

HEADERS_COMP = [
    "Fecha", "Anunciante", "Producto origen", "Score origen",
    "URL tienda", "Plataforma", "Catálogo estimado", "Rango precios",
    "Tiempo anunciando", "Presupuesto mensual (USD)",
    "Estrategia principal", "Puntos fuertes", "Puntos débiles",
    "Oportunidad para ti", "Productos más anunciados",
    "Nivel amenaza", "Recomendación",
]

HEADERS_REJ = [
    "Fecha", "Producto", "Marca", "Categoría",
    "Motivo rechazo", "Categoría rechazo", "Tipo", "Score", "Keyword",
]

HEADERS_LOG = [
    "Fecha", "Hora", "Keywords", "Scrapeados", "Analizados",
    "Aprobados", "Descartados", "Top ads", "Competidores", "Tipos", "Notas",
]

# ── Colores ─────────────────────────────────────────────────────
C_VERDE_OSC = {"red": 0.204, "green": 0.780, "blue": 0.349}
C_VERDE     = {"red": 0.565, "green": 0.933, "blue": 0.565}
C_AMARILLO  = {"red": 0.984, "green": 0.933, "blue": 0.459}
C_NARANJA   = {"red": 1.0,   "green": 0.737, "blue": 0.318}
C_ROJO      = {"red": 0.957, "green": 0.490, "blue": 0.490}
C_AZUL      = {"red": 0.678, "green": 0.847, "blue": 0.902}

def color_dias(d):
    d = int(d) if str(d).isdigit() else 30
    if d <= 7:  return C_VERDE
    if d <= 15: return C_AMARILLO
    if d <= 25: return C_NARANJA
    return C_ROJO

def color_score(s):
    s = int(s) if str(s).isdigit() else 5
    if s >= 9: return C_VERDE_OSC
    if s >= 7: return C_VERDE
    if s >= 5: return C_AMARILLO
    return C_ROJO

def color_amenaza(nivel):
    return {"alto": C_ROJO, "medio": C_AMARILLO, "bajo": C_VERDE}.get(nivel.lower(), C_AMARILLO)

def build_meta_url(nombre, pais="MX"):
    return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais}&search_type=page&q={nombre.replace(' ', '+')}"

def connect_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

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

def color_cell(ws_id, row, col_start, col_end, color):
    return {"repeatCell": {"range": {
        "sheetId": ws_id,
        "startRowIndex": row-1, "endRowIndex": row,
        "startColumnIndex": col_start, "endColumnIndex": col_end},
        "cell": {"userEnteredFormat": {"backgroundColor": color}},
        "fields": "userEnteredFormat.backgroundColor"}}

async def save_to_sheets(winners, rejected, top_ads, competitors, log_lines, config):
    print("📊 [REPORTER] Conectando...")
    try:
        sheet = connect_sheet()
    except Exception as e:
        print(f"⚠️  [REPORTER] Error: {e}"); return

    cfg         = config.get("sheets", {})
    now         = datetime.now()
    today       = now.strftime("%Y-%m-%d %H:%M")
    fmt_reqs    = []

    # ── 1. GANADORES ──────────────────────────────────────────────
    ws_win = get_or_create_tab(sheet, cfg.get("tab_winners", "Ganadores"), HEADERS_WINNERS)
    if winners:
        start = len(ws_win.get_all_values()) + 1
        rows  = []
        for i, p in enumerate(winners):
            dias  = p.get("dias_activo", 30)
            score = p.get("score", 5)
            anun  = p.get("nombre_anunciante", p.get("marca", ""))
            pais  = p.get("pais_origen", "MX")
            rows.append([
                today, p.get("nombre",""), p.get("marca",""), p.get("categoria",""),
                anun, build_meta_url(anun, pais), p.get("ad_url",""),
                p.get("tipo_anuncio",""), score, dias,
                p.get("gasto_dia",""), p.get("variaciones",""),
                ", ".join(p.get("paises",[])),
                p.get("precio_venta_mxn",""), p.get("costo_estimado_mxn",""), p.get("margen_pct",""),
                p.get("angulo_venta",""), p.get("por_que_ganador",""),
                "Sí" if p.get("tendencia") else "No",
                p.get("calidad_contenido",""),
                ", ".join(p.get("señales_dropshipping",[])),
                p.get("keyword_origen",""),
            ])
            sr = start + i
            fmt_reqs.append(color_cell(ws_win.id, sr, 8, 9, color_score(score)))   # col H score
            fmt_reqs.append(color_cell(ws_win.id, sr, 7, 8, color_dias(dias)))     # col I días — índice ajustado
        ws_win.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"📊 {len(rows)} ganadores añadidos")

    # ── 2. TOP 4 DEL DÍA ─────────────────────────────────────────
    ws_top = get_or_create_tab(sheet, "Top 4 del día", HEADERS_TOP)
    if top_ads:
        start = len(ws_top.get_all_values()) + 1
        rows  = []
        for i, p in enumerate(top_ads):
            anun  = p.get("nombre_anunciante", p.get("marca",""))
            pais  = p.get("pais_origen","MX")
            score = p.get("score", 5)
            rows.append([
                today, i+1,
                p.get("nombre",""), p.get("marca",""), score, p.get("dias_activo",""),
                p.get("por_que_funciona",""),
                p.get("tipo_creative_probable",""),
                p.get("copy_probable",""),
                p.get("audiencia_probable",""),
                p.get("estrategia_escalado",""),
                p.get("como_replicarlo",""),
                " | ".join(p.get("angulos_alternativos",[])),
                " | ".join(p.get("productos_complementarios",[])),
                p.get("riesgo_saturacion",""),
                p.get("ventana_oportunidad",""),
                p.get("puntuacion_replicabilidad",""),
                build_meta_url(anun, pais),
                p.get("ad_url",""),
            ])
            sr = start + i
            fmt_reqs.append(color_cell(ws_top.id, sr, 4, 5, color_score(score)))
        ws_top.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"📊 {len(rows)} top ads añadidos")

    # ── 3. COMPETIDORES ───────────────────────────────────────────
    ws_comp = get_or_create_tab(sheet, "Competidores", HEADERS_COMP)
    if competitors:
        start = len(ws_comp.get_all_values()) + 1
        rows  = []
        for i, c in enumerate(competitors):
            amenaza = c.get("nivel_amenaza","medio")
            rows.append([
                today,
                c.get("anunciante",""), c.get("producto_origen",""), c.get("score_origen",""),
                c.get("url_tienda",""), c.get("plataforma_tienda",""),
                c.get("catalogo_estimado",""), c.get("rango_precios",""),
                c.get("tiempo_anunciando",""), c.get("presupuesto_mensual_estimado",""),
                c.get("estrategia_principal",""),
                " | ".join(c.get("puntos_fuertes",[])),
                " | ".join(c.get("puntos_debiles",[])),
                c.get("oportunidad_para_ti",""),
                " | ".join(c.get("productos_mas_anunciados",[])),
                amenaza,
                c.get("recomendacion",""),
            ])
            sr = start + i
            fmt_reqs.append(color_cell(ws_comp.id, sr, 15, 16, color_amenaza(amenaza)))
        ws_comp.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"📊 {len(rows)} competidores añadidos")

    # ── 4. DESCARTADOS ────────────────────────────────────────────
    ws_rej = get_or_create_tab(sheet, cfg.get("tab_descartados","Descartados"), HEADERS_REJ)
    if rejected:
        rows = [[today, p.get("nombre",""), p.get("marca",""), p.get("categoria",""),
                 p.get("rechazo_motivo",""), p.get("rechazo_categoria",""),
                 p.get("tipo_anuncio",""), p.get("score",""), p.get("keyword_origen","")]
                for p in rejected]
        ws_rej.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"📊 {len(rows)} descartados añadidos")

    # ── 5. LOG ────────────────────────────────────────────────────
    ws_log = get_or_create_tab(sheet, cfg.get("tab_log","Log diario"), HEADERS_LOG)
    ws_log.append_row([
        now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
        next((l.replace("Keywords usadas: ","") for l in log_lines if "Keywords" in l),"")[:150],
        next((l for l in log_lines if "scrapeados" in l),""),
        next((l for l in log_lines if "potenciales" in l),""),
        len(winners), len(rejected), len(top_ads), len(competitors),
        next((l.replace("Tipos aprobados: ","") for l in log_lines if "Tipos" in l),""),
        " | ".join(log_lines[-2:]),
    ])

    # ── Aplicar todos los colores de una vez ──────────────────────
    if fmt_reqs:
        sheet.batch_update({"requests": fmt_reqs})
        print(f"📊 {len(fmt_reqs)} formatos de color aplicados")

    print("✅ [REPORTER] Todo guardado en Google Sheets")
