"""
Generador de fichas OMR A5 en PDF vectorial (ReportLab).
Temas:
  - Comunicacion → tonos verdes, título COMUNICACIÓN
  - Matematica   → tonos azules, título MATEMÁTICA
"""
from __future__ import annotations

import io
import os
from typing import Any, Dict, Tuple

from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


# Temas visuales (RGB 0–1)
THEMES: Dict[str, Dict[str, Any]] = {
    "Comunicacion": {
        "id": "Comunicacion",
        "title": "COMUNICACIÓN",
        "badge": "ÁREA: COMUNICACIÓN",
        "primary": Color(0.086, 0.639, 0.290),       # #16a34a
        "primary_dark": Color(0.082, 0.502, 0.239),  # #15803d
        "primary_light": Color(0.133, 0.773, 0.369), # #22c55e
        "border": Color(0.525, 0.937, 0.675),        # #86efac
        "zebra": Color(0.941, 0.992, 0.957),         # #f0fdf4
        "header_bg": Color(0.973, 1.0, 0.984),       # #f8fffb
        "label": Color(0.086, 0.639, 0.290),
        "bubble_text": Color(0.086, 0.396, 0.204),   # #166534
        "hint": Color(0.796, 0.835, 0.882),
        "muted": Color(0.580, 0.639, 0.722),
        "filename": "ficha_comunicacion_a5.pdf",
    },
    "Matematica": {
        "id": "Matematica",
        "title": "MATEMÁTICA",
        "badge": "ÁREA: MATEMÁTICA",
        "primary": Color(0.146, 0.388, 0.922),       # #2563eb
        "primary_dark": Color(0.114, 0.306, 0.847),  # #1d4ed8
        "primary_light": Color(0.376, 0.647, 0.980), # #60a5fa
        "border": Color(0.576, 0.773, 0.992),        # #93c5fd
        "zebra": Color(0.937, 0.965, 1.0),           # #eff6ff
        "header_bg": Color(0.961, 0.976, 1.0),       # #f5f9ff
        "label": Color(0.146, 0.388, 0.922),
        "bubble_text": Color(0.118, 0.227, 0.541),   # #1e3a8a
        "hint": Color(0.796, 0.835, 0.882),
        "muted": Color(0.580, 0.639, 0.722),
        "filename": "ficha_matematica_a5.pdf",
    },
}


# Perfil geométrico compartido con el procesador OpenCV (canvas 800×1130).
# Guías de esquina con FORMA única (no solo tamaño) para girar fotos 90/180/270°:
#   TL sólido ■   TR marco ▢   BL círculo ●   BR ele ⌞
OMR_PROFILE_VERSION = "OMR-A5-SHEET-2026.3"
PAGE_W_MM = 148.0
PAGE_H_MM = 210.0
MARKER_INSET_MM = 5.0
MARKER_SIZE_MM = 10.0  # mismo bounding box en las 4 esquinas
ANCHOR_SIZES_MM = {
    "TL": MARKER_SIZE_MM,
    "TR": MARKER_SIZE_MM,
    "BL": MARKER_SIZE_MM,
    "BR": MARKER_SIZE_MM,
}
ANCHOR_KINDS = {"TL": "solid", "TR": "frame", "BL": "circle", "BR": "ell"}
ANCHOR_CENTERS_MM = {
    "TL": (MARKER_INSET_MM + MARKER_SIZE_MM / 2.0, PAGE_H_MM - MARKER_INSET_MM - MARKER_SIZE_MM / 2.0),
    "TR": (PAGE_W_MM - MARKER_INSET_MM - MARKER_SIZE_MM / 2.0, PAGE_H_MM - MARKER_INSET_MM - MARKER_SIZE_MM / 2.0),
    "BL": (MARKER_INSET_MM + MARKER_SIZE_MM / 2.0, MARKER_INSET_MM + MARKER_SIZE_MM / 2.0),
    "BR": (PAGE_W_MM - MARKER_INSET_MM - MARKER_SIZE_MM / 2.0, MARKER_INSET_MM + MARKER_SIZE_MM / 2.0),
}
# Fallback de constantes (la geometría real sale de _sheet_metrics)
PAD_X_MM = 15.5
PAD_TOP_MM = 15.0
PAD_BOTTOM_MM = 11.0
HEADER_H_MM = 26.0
FOOTER_H_MM = 16.5
FOOTER_GAP_MM = 2.5
NOTE_H_MM = 3.6
TITLE_DROP_MM = 9.5
HEADER_GAP_MM = 3.0
COL_GAP_MM = 5.5
BUBBLE_D_MM = 6.5
BUBBLE_GAP_MM = 2.2
NUM_W_MM = 5.5
BUBBLE_INDENT_MM = 2.0
CANVAS_W, CANVAS_H = 800, 1130
MARKER_DST = {"TL": (40, 40), "TR": (760, 40), "BL": (40, 1090), "BR": (760, 1090)}


def resolve_theme(curso: str | None) -> Dict[str, Any]:
    """Normaliza el nombre del curso a un tema válido."""
    if not curso:
        return THEMES["Comunicacion"]
    key = (
        str(curso)
        .strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    if "matemat" in key:
        return THEMES["Matematica"]
    if "comunic" in key:
        return THEMES["Comunicacion"]
    # alias cortos
    if key in ("mate", "math", "m"):
        return THEMES["Matematica"]
    if key in ("comu", "com", "c", "lengua", "lenguaje"):
        return THEMES["Comunicacion"]
    return THEMES["Comunicacion"]


def _load_settings(base_dir: str | None = None) -> Dict[str, Any]:
    import json

    base = base_dir or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "settings_config.json")
    default = {
        "labels": {
            "nombre": "Apellidos y Nombres",
            "colegio": "Colegio",
            "grado": "Grado",
            "procedencia": "Procedencia",
        },
        "num_alternatives": 4,
        "num_questions": 15,
        "scoring": {"buenas": 10.0, "malas": -1.0, "blanco": 0.0},
        "branding": {"title": "", "logo": ""},
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update({k: data[k] for k in data})
                if "labels" in data:
                    default["labels"] = {**default["labels"], **data["labels"]}
        except Exception:
            pass
    return default


def _fit_bubbles(
    usable_mm: float,
    n_alt: int,
    row_h_mm: float,
) -> Tuple[float, float]:
    """Elige diámetro y hueco para llenar el ancho de columna sin chocar filas."""
    n_alt = max(2, int(n_alt))
    d_max = min(8.2, max(5.2, row_h_mm * 0.56))
    d_min = 5.2
    gap_min, gap_max = 1.35, 4.2
    # Primero un diámetro cómodo, luego reparte el resto en huecos.
    d = min(d_max, max(d_min, (usable_mm - (n_alt - 1) * gap_min) / n_alt))
    rest = usable_mm - n_alt * d
    gap = rest / max(n_alt - 1, 1)
    if gap > gap_max:
        extra = (gap - gap_max) * (n_alt - 1)
        d = min(d_max, d + extra / n_alt)
        gap = (usable_mm - n_alt * d) / max(n_alt - 1, 1)
    if gap < gap_min:
        gap = gap_min
        d = max(d_min, min(d_max, (usable_mm - (n_alt - 1) * gap) / n_alt))
    return float(d), float(gap)


def _sheet_metrics(num_questions: int, num_alternatives: int) -> Dict[str, Any]:
    """Métricas de empaquetado A5: compacta a 20 preguntas / 5 alternativas."""
    nq = max(1, min(20, int(num_questions)))
    na = max(2, min(5, int(num_alternatives)))
    mid = (nq + 1) // 2
    n_left, n_right = mid, nq - mid
    n_rows = max(n_left, n_right, 1)
    compact = n_rows >= 10

    pad_x = 15.5
    pad_top = 15.0
    pad_bottom = 9.4 if compact else 11.0
    header_h = 22.8 if compact else 26.0
    footer_h = 14.2 if compact else 16.5
    footer_gap = 1.8 if compact else 2.5
    note_h = 3.1 if compact else 3.6
    title_drop = 8.2 if compact else 9.5
    header_gap = 2.0 if compact else 3.0
    col_gap = 3.6 if na >= 5 else 5.5
    num_w = 4.8 if na >= 5 else 5.5
    bubble_indent = 1.3 if na >= 5 else 1.8
    right_pad = 1.1 if na >= 5 else 1.6

    questions_top = PAGE_H_MM - pad_top - title_drop - header_h - header_gap
    questions_bottom = pad_bottom + footer_h + footer_gap + note_h
    questions_h = max(questions_top - questions_bottom, 40.0)
    row_h = questions_h / n_rows

    content_left = pad_x
    content_w = PAGE_W_MM - 2 * pad_x
    col_w = (content_w - col_gap) / 2.0
    usable = max(col_w - num_w - bubble_indent - right_pad, 18.0)
    bubble_d, bubble_gap = _fit_bubbles(usable, na, row_h)

    return {
        "num_questions": nq,
        "num_alternatives": na,
        "mid": mid,
        "n_left": n_left,
        "n_right": n_right,
        "n_rows": n_rows,
        "compact": compact,
        "pad_x": pad_x,
        "pad_top": pad_top,
        "pad_bottom": pad_bottom,
        "header_h": header_h,
        "footer_h": footer_h,
        "footer_gap": footer_gap,
        "note_h": note_h,
        "title_drop": title_drop,
        "header_gap": header_gap,
        "col_gap": col_gap,
        "num_w": num_w,
        "bubble_indent": bubble_indent,
        "right_pad": right_pad,
        "questions_top": questions_top,
        "questions_bottom": questions_bottom,
        "questions_h": questions_h,
        "row_h": row_h,
        "content_left": content_left,
        "content_w": content_w,
        "col_w": col_w,
        "left_col_x": content_left,
        "right_col_x": content_left + col_w + col_gap,
        "bubble_d": bubble_d,
        "bubble_gap": bubble_gap,
    }


def get_omr_geometry(num_questions: int = 15, num_alternatives: int = 4) -> Dict[str, Any]:
    """Geometría imprimible en mm (origen PDF: esquina inferior izquierda)."""
    m = _sheet_metrics(num_questions, num_alternatives)
    nq, na = m["num_questions"], m["num_alternatives"]
    n_left, n_right, n_rows = m["n_left"], m["n_right"], m["n_rows"]

    step_x = m["bubble_d"] + m["bubble_gap"]
    x0 = m["num_w"] + m["bubble_indent"] + m["bubble_d"] / 2.0
    x_left = [m["left_col_x"] + x0 + i * step_x for i in range(na)]
    x_right = [m["right_col_x"] + x0 + i * step_x for i in range(na)]
    y_rows = [m["questions_top"] - (i + 0.5) * m["row_h"] for i in range(n_rows)]

    header_top = PAGE_H_MM - m["pad_top"] - m["title_drop"]
    header_bottom = header_top - m["header_h"]
    footer_bottom = m["pad_bottom"] + m["note_h"]
    inner_pad = 3.2
    row_x = m["content_left"] + inner_pad
    row_w = m["content_w"] - 2 * inner_pad
    # 3 filas de cabecera (nombre / colegio+grado / procedencia)
    hdr_row = m["header_h"] / 3.0

    return {
        "profile": OMR_PROFILE_VERSION,
        "anchors_mm": dict(ANCHOR_CENTERS_MM),
        "anchor_sizes_mm": dict(ANCHOR_SIZES_MM),
        "anchor_kinds": dict(ANCHOR_KINDS),
        "bubble_diameter_mm": m["bubble_d"],
        "bubble_gap_mm": m["bubble_gap"],
        "x_left_mm": x_left,
        "x_right_mm": x_right,
        "y_left_mm": y_rows[:n_left],
        "y_right_mm": y_rows[:n_right],
        "row_h_mm": m["row_h"],
        "questions_top_mm": m["questions_top"],
        "questions_bottom_mm": m["questions_bottom"],
        "left_col_x_mm": m["left_col_x"],
        "right_col_x_mm": m["right_col_x"],
        "col_w_mm": m["col_w"],
        "col_gap_mm": m["col_gap"],
        "pad_x_mm": m["pad_x"],
        "pad_top_mm": m["pad_top"],
        "pad_bottom_mm": m["pad_bottom"],
        "header_h_mm": m["header_h"],
        "footer_h_mm": m["footer_h"],
        "title_drop_mm": m["title_drop"],
        "header_gap_mm": m["header_gap"],
        "footer_gap_mm": m["footer_gap"],
        "note_h_mm": m["note_h"],
        "num_w_mm": m["num_w"],
        "bubble_indent_mm": m["bubble_indent"],
        "content_left_mm": m["content_left"],
        "content_w_mm": m["content_w"],
        "compact": m["compact"],
        "n_rows": n_rows,
        "options": list("ABCDE")[:na],
        "num_questions": nq,
        "num_alternatives": na,
        "header_box_mm": (m["content_left"], header_bottom, m["content_w"], m["header_h"]),
        "footer_box_mm": (m["content_left"], footer_bottom, m["content_w"], m["footer_h"]),
        "nombre_box_mm": (row_x, header_top - hdr_row, row_w, hdr_row * 0.85),
        "colegio_box_mm": (row_x, header_top - 2 * hdr_row, row_w * 0.68, hdr_row * 0.85),
        "grado_box_mm": (row_x + row_w * 0.72, header_top - 2 * hdr_row, row_w * 0.28, hdr_row * 0.85),
        "procedencia_box_mm": (row_x, header_bottom, row_w, hdr_row * 0.85),
        "metrics": m,
    }


def geometry_to_warped_canvas(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Proyecta mm de la ficha al canvas canónico 800×1130 (centros de anclas)."""
    anchors = geometry["anchors_mm"]
    left, right = anchors["TL"][0], anchors["TR"][0]
    top, bottom = anchors["TL"][1], anchors["BL"][1]
    span_x = max(right - left, 1e-6)
    span_y = max(top - bottom, 1e-6)

    def px_x(x_mm: float) -> int:
        return int(round(MARKER_DST["TL"][0] + (x_mm - left) * 720.0 / span_x))

    def px_y(y_mm: float) -> float:
        return round(MARKER_DST["TL"][1] + (top - y_mm) * 1050.0 / span_y, 1)

    def box_px(box_mm: Tuple[float, float, float, float]) -> Dict[str, int]:
        x, y, w, h = box_mm
        x1, x2 = px_x(x), px_x(x + w)
        y_top, y_bot = px_y(y + h), px_y(y)
        return {
            "x": int(min(x1, x2)),
            "y": int(round(min(y_top, y_bot))),
            "w": int(abs(x2 - x1)),
            "h": int(round(abs(y_bot - y_top))),
        }

    y_left = [float(px_y(y)) for y in geometry["y_left_mm"]]
    y_right = [float(px_y(y)) for y in geometry["y_right_mm"]]
    bubble_r = max(8, int(round(geometry["bubble_diameter_mm"] * 720.0 / span_x / 2.0)))
    ocr_fields = {
        "header": box_px(geometry["header_box_mm"]),
        "footer": box_px(geometry["footer_box_mm"]),
        "nombre": box_px(geometry["nombre_box_mm"]),
        "colegio": box_px(geometry["colegio_box_mm"]),
        "grado": box_px(geometry["grado_box_mm"]),
        "procedencia": box_px(geometry["procedencia_box_mm"]),
    }
    # Cajas de orden/hora: primeras 2 franjas del pie (~ 1/5.2 y 1.2/5.2)
    fx, fy, fw, fh = geometry["footer_box_mm"]
    ocr_fields["numero_orden_box"] = box_px((fx + 3.2, fy + 2.0, fw * 0.18, fh * 0.62))
    ocr_fields["hora_entrega_box"] = box_px((fx + fw * 0.20, fy + 2.0, fw * 0.22, fh * 0.62))

    return {
        "options": list(geometry["options"]),
        "x_left": [px_x(x) for x in geometry["x_left_mm"]],
        "x_right": [px_x(x) for x in geometry["x_right_mm"]],
        "y_rows_left": y_left,
        "y_rows_right": y_right,
        "y_start_left": y_left[0] if y_left else 345.0,
        "y_start_right": y_right[0] if y_right else y_left[0],
        "y_step": round(float(y_left[1] - y_left[0]), 1) if len(y_left) > 1 else 78.0,
        "bubble_radius": bubble_r,
        "method": f"profile_{geometry['profile']}",
        "profile": geometry.get("profile", OMR_PROFILE_VERSION),
        "anchor_kinds": dict(geometry.get("anchor_kinds") or ANCHOR_KINDS),
        "ocr_fields": ocr_fields,
        "compact": bool(geometry.get("compact")),
        "num_questions": geometry.get("num_questions"),
        "num_alternatives": geometry.get("num_alternatives"),
    }


def draw_fiducial_pdf(c: canvas.Canvas, kind: str, cx: float, cy: float, size: float) -> None:
    """Dibuja una guía de esquina. `cx,cy,size` en puntos PDF."""
    half = size / 2.0
    ink = Color(0.059, 0.090, 0.165)
    c.setFillColor(ink)
    c.setStrokeColor(ink)
    if kind == "solid":
        c.rect(cx - half, cy - half, size, size, stroke=0, fill=1)
    elif kind == "frame":
        c.rect(cx - half, cy - half, size, size, stroke=0, fill=1)
        c.setFillColor(white)
        inner = size * 0.40
        c.rect(cx - inner / 2.0, cy - inner / 2.0, inner, inner, stroke=0, fill=1)
        c.setFillColor(ink)
    elif kind == "circle":
        c.circle(cx, cy, half, stroke=0, fill=1)
    else:  # ell: barra derecha + barra inferior (apunta al contenido desde BR)
        t = size * 0.38
        c.rect(cx + half - t, cy - half, t, size, stroke=0, fill=1)
        c.rect(cx - half, cy - half, size, t, stroke=0, fill=1)


def _rounded_rect(c: canvas.Canvas, x, y, w, h, r, stroke_color, fill_color=None, stroke_w=1.2):
    c.saveState()
    c.setStrokeColor(stroke_color)
    c.setLineWidth(stroke_w)
    if fill_color is not None:
        c.setFillColor(fill_color)
        c.roundRect(x, y, w, h, r, stroke=1, fill=1)
    else:
        c.roundRect(x, y, w, h, r, stroke=1, fill=0)
    c.restoreState()


def _draw_dotted_line(c: canvas.Canvas, x1, y, x2, color: Color, width=1.2):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.setDash(1.2, 1.8)
    c.line(x1, y, x2, y)
    c.restoreState()


def build_sheet_pdf(
    curso: str = "Comunicacion",
    settings: Dict[str, Any] | None = None,
    base_dir: str | None = None,
) -> Tuple[bytes, str]:
    """
    Genera un PDF vectorial A5 de la ficha OMR.
    Returns: (pdf_bytes, filename)
    """
    theme = resolve_theme(curso)
    cfg = settings or _load_settings(base_dir)
    labels = cfg.get("labels") or {}
    num_q = max(1, min(20, int(cfg.get("num_questions") or 15)))
    num_alt = max(2, min(5, int(cfg.get("num_alternatives") or 4)))
    options = ["A", "B", "C", "D", "E"][:num_alt]
    geometry = get_omr_geometry(num_q, num_alt)
    met = geometry["metrics"]
    compact = bool(met["compact"])

    buf = io.BytesIO()
    page_w, page_h = A5  # 148mm x 210mm en puntos
    c = canvas.Canvas(buf, pagesize=A5)
    c.setTitle(f"Ficha OMR — {theme['title']}")
    c.setAuthor("OCR OMR SCAN")
    c.setSubject(f"{theme['badge']} | {OMR_PROFILE_VERSION}")

    pad_x = met["pad_x"] * mm
    pad_top = met["pad_top"] * mm
    pad_bottom = met["pad_bottom"] * mm

    # Guías de orientación: forma única por esquina (sólido / marco / círculo / L).
    for name, (cx_mm, cy_mm) in geometry["anchors_mm"].items():
        size = geometry["anchor_sizes_mm"][name] * mm
        kind = geometry["anchor_kinds"].get(name, "solid")
        draw_fiducial_pdf(c, kind, cx_mm * mm, cy_mm * mm, size)

    content_left = pad_x
    content_right = page_w - pad_x
    content_w = content_right - content_left
    y = page_h - pad_top

    # ——— Título (banda = title_drop, alineada con get_omr_geometry) ———
    title_drop = met["title_drop"] * mm
    brand = cfg.get("branding") if isinstance(cfg.get("branding"), dict) else {}
    brand_title = str(brand.get("title") or "").strip()
    brand_logo = str(brand.get("logo") or "").strip()
    if brand_logo and not os.path.isabs(brand_logo):
        brand_logo = os.path.join(base_dir or os.path.dirname(os.path.abspath(__file__)), brand_logo)
    has_logo = bool(brand_logo and os.path.isfile(brand_logo))
    text_x = content_left
    if has_logo:
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(brand_logo)
            iw, ih = ir.getSize()
            if iw > 0 and ih > 0:
                logo_h = 5.6 * mm
                logo_w = logo_h * (iw / float(ih))
                if logo_w > 14 * mm:
                    logo_w = 14 * mm
                    logo_h = logo_w * (ih / float(iw))
                # Dentro de la banda de título (no empuja cabecera ni burbujas).
                logo_y = y - 3.6 * mm - logo_h * 0.22
                c.drawImage(ir, content_left, logo_y, width=logo_w, height=logo_h, mask="auto", preserveAspectRatio=True)
                text_x = content_left + logo_w + 1.6 * mm
        except Exception:
            has_logo = False
            text_x = content_left
    # El título de área queda en la misma Y de siempre; el branding no mueve la grilla.
    c.setFillColor(theme["primary_dark"])
    c.setFont("Helvetica-Bold", 11 if compact else 12)
    c.drawString(text_x, y - 3.6 * mm, theme["title"])
    if brand_title:
        c.setFillColor(theme.get("muted") or Color(0.35, 0.40, 0.46))
        c.setFont("Helvetica", 6.2 if compact else 6.6)
        c.drawString(text_x, y - 6.4 * mm, brand_title[:48])

    # Badge de área + meta
    badge = f"{theme['badge']}  ·  {num_q} preg. · {num_alt} alt."
    badge_font = 7.0 if compact else 7.5
    c.setFont("Helvetica-Bold", badge_font)
    tw = c.stringWidth(badge, "Helvetica-Bold", badge_font)
    bx = content_right - tw - 4 * mm
    by = y - 5.2 * mm
    _rounded_rect(
        c, bx - 2 * mm, by - 1.2 * mm, tw + 4 * mm, 4.0 * mm, 2 * mm,
        theme["border"], theme["zebra"], stroke_w=0.8,
    )
    c.setFillColor(theme["primary_dark"])
    c.drawString(bx, by, badge)

    # Línea bajo título, luego cabecera
    line_y = y - title_drop + 2.4 * mm
    c.setStrokeColor(theme["primary_light"])
    c.setLineWidth(1.6)
    c.line(content_left, line_y, content_right, line_y)
    y -= title_drop

    # ——— Cabecera (identidad) ———
    header_h = met["header_h"] * mm
    header_y = y - header_h
    _rounded_rect(
        c, content_left, header_y, content_w, header_h, 2.2 * mm,
        theme["border"], theme["header_bg"], stroke_w=1.3,
    )

    lbl_size = 6.4 if compact else 7.0
    name_lift = 7.6 * mm if compact else 9.0 * mm
    mid_lift = 14.4 * mm if compact else 17.0 * mm
    bot_lift = 21.2 * mm if compact else 25.0 * mm

    def field_block(fx, fy, fw, label: str):
        c.setFillColor(theme["label"])
        c.setFont("Helvetica-Bold", lbl_size)
        c.drawString(fx, fy + (3.2 * mm if compact else 3.8 * mm), label.upper())
        _draw_dotted_line(c, fx, fy, fx + fw, theme["border"], width=1.1)

    inner_pad = 3.2 * mm
    row_x = content_left + inner_pad
    row_w = content_w - 2 * inner_pad

    # Nombre
    field_block(row_x, header_y + header_h - name_lift, row_w, labels.get("nombre", "Apellidos y Nombres"))
    # Colegio + Grado
    col_w_hdr = row_w * 0.68
    grad_w = row_w * 0.28
    field_block(row_x, header_y + header_h - mid_lift, col_w_hdr, labels.get("colegio", "Colegio"))
    field_block(row_x + col_w_hdr + 0.04 * row_w, header_y + header_h - mid_lift, grad_w, labels.get("grado", "Grado"))
    # Procedencia
    field_block(row_x, header_y + header_h - bot_lift, row_w, labels.get("procedencia", "Procedencia"))

    y = header_y - met["header_gap"] * mm

    # ——— Preguntas (2 columnas) ———
    footer_h = met["footer_h"] * mm
    footer_gap = met["footer_gap"] * mm
    note_h = met["note_h"] * mm
    footer_top = pad_bottom + footer_h + footer_gap + note_h
    questions_bottom = footer_top
    questions_top = y
    questions_h = questions_top - questions_bottom

    mid = met["mid"]
    col_gap = met["col_gap"] * mm
    col_w = met["col_w"] * mm
    left_col_x = content_left
    right_col_x = met["right_col_x"] * mm

    left_qs = list(range(1, mid + 1))
    right_qs = list(range(mid + 1, num_q + 1))
    n_rows = met["n_rows"]
    row_h = met["row_h"] * mm

    bubble_d = met["bubble_d"] * mm
    num_w = met["num_w"] * mm
    bubble_r = bubble_d / 2.0
    q_font = 8.0 if compact else 9.0
    opt_font = 6.6 if (compact or num_alt >= 5) else 7.5

    def draw_question_column(col_x, qs, x_mm_list, y_mm_list):
        for i, q in enumerate(qs):
            cy = y_mm_list[i] * mm
            row_bottom = cy - row_h * 0.42
            if q % 2 == 0:
                c.setFillColor(theme["zebra"])
                c.roundRect(col_x, row_bottom, col_w, row_h * 0.84, 1.2 * mm, stroke=0, fill=1)

            c.setFillColor(theme["primary_dark"])
            c.setFont("Helvetica-Bold", q_font)
            c.drawRightString(col_x + num_w, cy - 1.2 * mm, f"{q:02d}")

            for oi, opt in enumerate(options):
                cx = x_mm_list[oi] * mm
                c.setStrokeColor(theme["primary_light"])
                c.setFillColor(white)
                c.setLineWidth(1.25 if compact else 1.35)
                c.circle(cx, cy, bubble_r, stroke=1, fill=1)
                c.setFillColor(theme["bubble_text"])
                c.setFont("Helvetica-Bold", opt_font)
                c.drawCentredString(cx, cy - 1.05 * mm, opt)

    draw_question_column(left_col_x, left_qs, geometry["x_left_mm"], geometry["y_left_mm"])
    draw_question_column(right_col_x, right_qs, geometry["x_right_mm"], geometry["y_right_mm"])

    # ——— Pie: Orden / Hora / Buenas / Malas / En blanco ———
    footer_y = pad_bottom + note_h
    _rounded_rect(
        c, content_left, footer_y, content_w, footer_h, 2.2 * mm,
        theme["border"], theme["header_bg"], stroke_w=1.3,
    )

    blocks = ["Nº Orden", "Hora entrega", "Buenas", "Malas", "En blanco"]
    # proporciones similares a CSS grid 1fr 1.2fr 1fr 1fr 1fr
    weights = [1.0, 1.2, 1.0, 1.0, 1.0]
    total_w = sum(weights)
    gap = 2.5 * mm
    usable = content_w - 2 * 3.5 * mm - gap * (len(blocks) - 1)
    bx = content_left + 3.5 * mm
    box_h = 8.5 * mm

    for i, (label, w) in enumerate(zip(blocks, weights)):
        bw = usable * (w / total_w)
        c.setFillColor(theme["label"])
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(bx, footer_y + footer_h - 5 * mm, label.upper())

        box_y = footer_y + 2.2 * mm
        is_score = i >= 2
        stroke = theme["border"] if is_score else theme["primary_light"]
        fill = theme["zebra"] if is_score else white
        dash = is_score
        c.saveState()
        c.setStrokeColor(stroke)
        c.setFillColor(fill)
        c.setLineWidth(1.2)
        if dash:
            c.setDash(2, 1.5)
        c.roundRect(bx, box_y, bw, box_h, 1.4 * mm, stroke=1, fill=1)
        c.restoreState()

        if not is_score:
            c.setFillColor(theme["hint"])
            c.setFont("Helvetica", 7)
            hint = "01–99" if i == 0 else "HH:MM"
            c.drawCentredString(bx + bw / 2, box_y + box_h / 2 - 1.2 * mm, hint)

        bx += bw + gap

    # Nota pie
    c.setFillColor(theme["muted"])
    c.setFont("Helvetica", 6.2 if compact else 6.5)
    c.drawCentredString(
        page_w / 2,
        met["pad_bottom"] * mm * 0.28,
        "Rellene cada círculo. No cubra las 4 guías de esquina (sirven para orientar la foto).",
    )

    # Franja lateral sutil de color (ayuda visual al clasificar pilas)
    c.setFillColor(theme["primary"])
    c.rect(0, 0, 1.8 * mm, page_h, stroke=0, fill=1)
    c.rect(page_w - 1.8 * mm, 0, 1.8 * mm, page_h, stroke=0, fill=1)

    c.showPage()
    c.save()
    return buf.getvalue(), theme["filename"]


if __name__ == "__main__":
    for curso in ("Comunicacion", "Matematica"):
        data, name = build_sheet_pdf(curso)
        out = os.path.join(os.path.dirname(__file__), name)
        with open(out, "wb") as f:
            f.write(data)
        print(f"OK {name} ({len(data)} bytes)")
