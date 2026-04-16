"""
REPORTER v5 — 5 pestañas en Google Sheets:
  - Ganadores        : con colores por días y score + enlaces spy tools
  - Top 4 del día    : análisis profundo de los 4 mejores
  - Competidores     : análisis de tiendas web rivales
  - Descartados      : rechazados con motivo
  - Log diario       : historial de ejecuciones
"""
import os, json
from datetime import datetime
from urllib.parse import quote
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")

HEADERS_WINNERS = [
    "Fecha", "Producto", "Marca anunciante", "Categoría",
    # ── Columna clave: ver el anuncio en Meta (requiere estar logueado en FB)
    "👁️ Ver anuncio en Meta",
    # ── Spy tools: busca el mismo producto con 1 clic
    "🔍 Buscar en PiPiADS",
    "🛒 Buscar proveedor AliExpress",
    "🛍️ Buscar en Temu",
    "🔎 Google Shopping",
    # ── La tienda del anunciante (si la API la devuelve)
    "🌐 Web anunciante",
    # ── Texto real del anuncio (EU: a veces vacío por GDPR)
    "Texto real del anuncio",
    "Score /10", "Score Dropshipping", "Días activo", "Gasto/día (USD)",
    "País", "Precio venta (EUR)", "Costo proveedor (EUR)", "Margen %",
    "Señales dropshipping", "Cómo encontrar proveedor",
    "Ángulo de venta", "Por qué es oportunidad",
    "Keyword origen",
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

def build_meta_url(nombre, pais="ES"):
    """URL directa con nombre exacto de página — igual que buscar en Meta Ads Library."""
    q = quote(nombre)
    return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais}&search_type=page&q={q}"

def build_pipiads_url(nombre_producto: str) -> str:
    """Busca el producto en PiPiADS (ads de Facebook/TikTok de dropshipping)."""
    q = quote(nombre_producto)
    return f"https://www.pipiads.com/ads/?keyword={q}&ad_platform=facebook&ad_language=es"

def build_aliexpress_url(busqueda: str) -> str:
    """Búsqueda directa del producto en AliExpress para encontrar el proveedor."""
    q = quote(busqueda)
    return f"https://www.aliexpress.com/wholesale?SearchText={q}&sortType=total_tranpro_desc"

def build_temu_url(busqueda: str) -> str:
    """Búsqueda en Temu del producto."""
    q = quote(busqueda)
    return f"https://www.temu.com/search_result.html?search_key={q}"

def build_google_shopping_url(busqueda: str) -> str:
    """Google Shopping para ver quién lo vende y a qué precio."""
    q = quote(busqueda)
    return f"https://www.google.com/search?q={q}&tbm=shop&gl=es&hl=es"

def build_keyword_url(nombre_producto, pais="ES"):
    """URL de búsqueda por keyword en Meta Ads Library."""
    q = quote(nombre_producto)
    return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais}&search_type=keyword_unordered&q={q}"

def connect_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

def get_or_create_tab(sheet, name, headers):
    try:
        ws = sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(name, rows=2000, cols=max(len(headers), 10))
        ws.update("A1", [headers])
        ws.format("1:1", {"textFormat": {"bold": True}})
        return ws

    # Si la pestaña existe, comprueba si los headers son correctos
    existing = ws.get_all_values()
    if not existing:
        ws.update("A1", [headers])
        ws.format("1:1", {"textFormat": {"bold": True}})
    elif existing[0] != headers:
        # Headers incorrectos → borra todo y reescribe con los correctos
        ws.clear()
        ws.update("A1", [headers])
        ws.format("1:1", {"textFormat": {"bold": True}})
        print(f"📊 [REPORTER] Headers de '{name}' actualizados")
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
            pais  = p.get("pais_origen", "ES")
            nombre_producto = p.get("nombre", "")
            keyword = p.get("keyword_origen", p.get("keyword", nombre_producto))

            # ── Construir el término de búsqueda más específico posible ──
            # Combina el nombre del producto con la keyword para mejores resultados
            busqueda_proveedor = p.get("como_encontrar_proveedor", "") or keyword or nombre_producto
            busqueda_spy = nombre_producto or keyword

            # ── Ver el anuncio en Meta (requiere estar logueado en Facebook) ──
            meta_snapshot = (
                p.get("snapshot_url") or
                p.get("ad_url") or
                build_keyword_url(keyword or nombre_producto, pais)
            )

            rows.append([
                today,
                nombre_producto,
                anun,
                p.get("categoria",""),
                # 👁️ Ver anuncio en Meta — clic aquí con Facebook abierto en otro tab
                meta_snapshot,
                # 🔍 PiPiADS — ve quién más anuncia este producto y qué copy usan
                build_pipiads_url(busqueda_spy),
                # 🛒 AliExpress — encuentra el proveedor directamente
                build_aliexpress_url(busqueda_proveedor),
                # 🛍️ Temu — alternativa de proveedor más barato
                build_temu_url(busqueda_spy),
                # 🔎 Google Shopping — ve a qué precio lo venden otros
                build_google_shopping_url(busqueda_spy),
                # 🌐 Web del anunciante (si la API la devuelve — vacío en EU por GDPR)
                p.get("website_url") or p.get("url_web",""),
                # Texto real del anuncio (vacío si Meta no lo devuelve por GDPR)
                p.get("raw_text","")[:400],
                score,
                p.get("score_dropshipping", p.get("score","")),
                dias,
                p.get("gasto_dia_usd", p.get("gasto_dia", p.get("gasto_dia_est",""))),
                p.get("pais", pais),
                p.get("precio_venta_eur", p.get("precio_venta_mxn","")),
                p.get("costo_proveedor_eur", p.get("costo_estimado_eur", p.get("costo_estimado_mxn",""))),
                p.get("margen_pct",""),
                " | ".join(p.get("señales_dropshipping", [])),
                p.get("como_encontrar_proveedor", p.get("proveedor_sugerido","")),
                p.get("angulo_venta",""),
                p.get("por_que_oportunidad", p.get("por_que_ganador","")),
                p.get("keyword_origen", p.get("keyword","")),
            ])
            sr = start + i
            # Columnas (0-indexed): A=0 Fecha, B=1 Producto, C=2 Marca, D=3 Cat
            # E=4 Meta, F=5 PiPiADS, G=6 AliExpress, H=7 Temu, I=8 GoogleShopping
            # J=9 WebAnunciante, K=10 Texto, L=11 Score, M=12 ScoreDrop, N=13 Días...
            fmt_reqs.append(color_cell(ws_win.id, sr, 11, 12, color_score(score)))  # col L: Score /10
            fmt_reqs.append(color_cell(ws_win.id, sr, 13, 14, color_dias(dias)))    # col N: Días activo
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
                p.get("ad_url") or p.get("url_anunciante") or build_meta_url(anun, pais),
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
