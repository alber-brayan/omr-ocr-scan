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
# Las coordenadas de burbuja coinciden con el dibujo; TL es más grande para
# orientar fotos rotadas 90/180/270°.
OMR_PROFILE_VERSION = "OMR-A5-SHEET-2026.2"
PAGE_W_MM = 148.0
PAGE_H_MM = 210.0
MARKER_INSET_MM = 5.0
MARKER_BASE_MM = 10.0  # centros: 10 mm desde cada borde
ANCHOR_SIZES_MM = {"TL": 12.0, "TR": 9.0, "BL": 9.0, "BR": 9.0}
ANCHOR_CENTERS_MM = {
    "TL": (MARKER_INSET_MM + MARKER_BASE_MM / 2.0, PAGE_H_MM - MARKER_INSET_MM - MARKER_BASE_MM / 2.0),
    "TR": (PAGE_W_MM - MARKER_INSET_MM - MARKER_BASE_MM / 2.0, PAGE_H_MM - MARKER_INSET_MM - MARKER_BASE_MM / 2.0),
    "BL": (MARKER_INSET_MM + MARKER_BASE_MM / 2.0, MARKER_INSET_MM + MARKER_BASE_MM / 2.0),
    "BR": (PAGE_W_MM - MARKER_INSET_MM - MARKER_BASE_MM / 2.0, MARKER_INSET_MM + MARKER_BASE_MM / 2.0),
}
PAD_X_MM = 14.0
PAD_TOP_MM = 16.0
PAD_BOTTOM_MM = 14.0
HEADER_H_MM = 28.0
FOOTER_H_MM = 18.0
FOOTER_GAP_MM = 3.0
NOTE_H_MM = 4.0
TITLE_DROP_MM = 10.5  # 7 mm línea + 3.5 mm hueco
HEADER_GAP_MM = 3.5
COL_GAP_MM = 6.0
BUBBLE_D_MM = 6.0
BUBBLE_GAP_MM = 2.0
NUM_W_MM = 5.5
BUBBLE_INDENT_MM = 2.2
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


def get_omr_geometry(num_questions: int = 15, num_alternatives: int = 4) -> Dict[str, Any]:
    """Geometría imprimible en mm (origen PDF: esquina inferior izquierda)."""
    num_questions = max(1, int(num_questions))
    num_alternatives = max(2, min(5, int(num_alternatives)))
    mid = (num_questions + 1) // 2
    n_left = mid
    n_right = num_questions - mid
    n_rows = max(n_left, n_right, 1)

    questions_top = PAGE_H_MM - PAD_TOP_MM - TITLE_DROP_MM - HEADER_H_MM - HEADER_GAP_MM
    questions_bottom = PAD_BOTTOM_MM + FOOTER_H_MM + FOOTER_GAP_MM + NOTE_H_MM
    questions_h = questions_top - questions_bottom
    row_h = questions_h / n_rows

    content_left = PAD_X_MM
    content_w = PAGE_W_MM - 2 * PAD_X_MM
    col_w = (content_w - COL_GAP_MM) / 2.0
    left_col_x = content_left
    right_col_x = content_left + col_w + COL_GAP_MM

    # Centro de cada burbuja (igual que el canvas de dibujo)
    step_x = BUBBLE_D_MM + BUBBLE_GAP_MM
    x0 = NUM_W_MM + BUBBLE_INDENT_MM + BUBBLE_D_MM / 2.0
    x_left = [left_col_x + x0 + i * step_x for i in range(num_alternatives)]
    x_right = [right_col_x + x0 + i * step_x for i in range(num_alternatives)]
    y_rows = [questions_top - (i + 0.5) * row_h for i in range(n_rows)]

    return {
        "profile": OMR_PROFILE_VERSION,
        "anchors_mm": dict(ANCHOR_CENTERS_MM),
        "anchor_sizes_mm": dict(ANCHOR_SIZES_MM),
        "bubble_diameter_mm": BUBBLE_D_MM,
        "x_left_mm": x_left,
        "x_right_mm": x_right,
        "y_left_mm": y_rows[:n_left],
        "y_right_mm": y_rows[:n_right],
        "row_h_mm": row_h,
        "questions_top_mm": questions_top,
        "questions_bottom_mm": questions_bottom,
        "left_col_x_mm": left_col_x,
        "right_col_x_mm": right_col_x,
        "col_w_mm": col_w,
        "options": list("ABCDE")[:num_alternatives],
        "num_questions": num_questions,
        "num_alternatives": num_alternatives,
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

    y_left = [float(px_y(y)) for y in geometry["y_left_mm"]]
    y_right = [float(px_y(y)) for y in geometry["y_right_mm"]]
    bubble_r = max(8, int(round(geometry["bubble_diameter_mm"] * 720.0 / span_x / 2.0)))
    return {
        "options": list(geometry["options"]),
        "x_left": [px_x(x) for x in geometry["x_left_mm"]],
        "x_right": [px_x(x) for x in geometry["x_right_mm"]],
        "y_rows_left": y_left,
        "y_rows_right": y_right,
        "y_start_left": y_left[0] if y_left else 345.0,
        "y_start_right": y_right[0] if y_right else y_left[0],
        "y_step": float(y_left[1] - y_left[0]) if len(y_left) > 1 else 78.0,
        "bubble_radius": bubble_r,
        "method": f"profile_{geometry['profile']}",
        "profile": geometry.get("profile", OMR_PROFILE_VERSION),
    }


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
    num_q = int(cfg.get("num_questions") or 15)
    num_alt = int(cfg.get("num_alternatives") or 4)
    options = ["A", "B", "C", "D", "E"][: max(2, min(5, num_alt))]
    geometry = get_omr_geometry(num_q, num_alt)

    buf = io.BytesIO()
    page_w, page_h = A5  # 148mm x 210mm en puntos
    c = canvas.Canvas(buf, pagesize=A5)
    c.setTitle(f"Ficha OMR — {theme['title']}")
    c.setAuthor("OCR OMR SCAN")
    c.setSubject(f"{theme['badge']} | {OMR_PROFILE_VERSION}")

    pad_x = PAD_X_MM * mm
    pad_top = PAD_TOP_MM * mm
    pad_bottom = PAD_BOTTOM_MM * mm

    # Anclas: TL más grande (orientación 90/180/270). Centros fijos a 10 mm del borde.
    c.setFillColor(Color(0.059, 0.090, 0.165))  # #0f172a
    for name, (cx_mm, cy_mm) in geometry["anchors_mm"].items():
        size = geometry["anchor_sizes_mm"][name] * mm
        cx, cy = cx_mm * mm, cy_mm * mm
        c.rect(cx - size / 2.0, cy - size / 2.0, size, size, stroke=0, fill=1)

    content_left = pad_x
    content_right = page_w - pad_x
    content_w = content_right - content_left
    y = page_h - pad_top

    # ——— Título ———
    c.setFillColor(theme["primary_dark"])
    c.setFont("Helvetica-Bold", 12)
    c.drawString(content_left, y - 4 * mm, theme["title"])

    # Badge de área + meta
    badge = f"{theme['badge']}  ·  {num_q} preg. · {num_alt} alt."
    c.setFont("Helvetica-Bold", 7.5)
    tw = c.stringWidth(badge, "Helvetica-Bold", 7.5)
    bx = content_right - tw - 4 * mm
    by = y - 5.5 * mm
    _rounded_rect(
        c, bx - 2 * mm, by - 1.2 * mm, tw + 4 * mm, 4.2 * mm, 2 * mm,
        theme["border"], theme["zebra"], stroke_w=0.8,
    )
    c.setFillColor(theme["primary_dark"])
    c.drawString(bx, by, badge)

    # Línea bajo título
    y -= 7 * mm
    c.setStrokeColor(theme["primary_light"])
    c.setLineWidth(1.6)
    c.line(content_left, y, content_right, y)
    y -= 3.5 * mm

    # ——— Cabecera (identidad) ———
    header_h = 28 * mm
    header_y = y - header_h
    _rounded_rect(
        c, content_left, header_y, content_w, header_h, 2.2 * mm,
        theme["border"], theme["header_bg"], stroke_w=1.3,
    )

    def field_block(fx, fy, fw, label: str):
        c.setFillColor(theme["label"])
        c.setFont("Helvetica-Bold", 7)
        c.drawString(fx, fy + 3.8 * mm, label.upper())
        _draw_dotted_line(c, fx, fy, fx + fw, theme["border"], width=1.1)

    inner_pad = 3.5 * mm
    row_x = content_left + inner_pad
    row_w = content_w - 2 * inner_pad

    # Nombre
    field_block(row_x, header_y + header_h - 9 * mm, row_w, labels.get("nombre", "Apellidos y Nombres"))
    # Colegio + Grado
    col_w = row_w * 0.68
    grad_w = row_w * 0.28
    field_block(row_x, header_y + header_h - 17 * mm, col_w, labels.get("colegio", "Colegio"))
    field_block(row_x + col_w + 0.04 * row_w, header_y + header_h - 17 * mm, grad_w, labels.get("grado", "Grado"))
    # Procedencia
    field_block(row_x, header_y + header_h - 25 * mm, row_w, labels.get("procedencia", "Procedencia"))

    y = header_y - 3.5 * mm

    # ——— Preguntas (2 columnas) ———
    footer_h = 18 * mm
    footer_gap = 3 * mm
    note_h = 4 * mm
    footer_top = pad_bottom + footer_h + footer_gap + note_h
    questions_bottom = footer_top
    questions_top = y
    questions_h = questions_top - questions_bottom

    mid = (num_q + 1) // 2
    col_gap = 6 * mm
    col_w = (content_w - col_gap) / 2
    left_col_x = content_left
    right_col_x = content_left + col_w + col_gap

    left_qs = list(range(1, mid + 1))
    right_qs = list(range(mid + 1, num_q + 1))
    n_rows = max(len(left_qs), len(right_qs), 1)
    row_h = questions_h / n_rows

    bubble_d = BUBBLE_D_MM * mm
    num_w = NUM_W_MM * mm
    bubble_r = bubble_d / 2.0

    def draw_question_column(col_x, qs, x_mm_list, y_mm_list):
        for i, q in enumerate(qs):
            cy = y_mm_list[i] * mm
            row_bottom = cy - row_h * 0.42
            if q % 2 == 0:
                c.setFillColor(theme["zebra"])
                c.roundRect(col_x, row_bottom, col_w, row_h * 0.84, 1.2 * mm, stroke=0, fill=1)

            c.setFillColor(theme["primary_dark"])
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(col_x + num_w, cy - 1.2 * mm, f"{q:02d}")

            for oi, opt in enumerate(options):
                cx = x_mm_list[oi] * mm
                c.setStrokeColor(theme["primary_light"])
                c.setFillColor(white)
                c.setLineWidth(1.35)
                c.circle(cx, cy, bubble_r, stroke=1, fill=1)
                c.setFillColor(theme["bubble_text"])
                c.setFont("Helvetica-Bold", 7.5)
                c.drawCentredString(cx, cy - 1.1 * mm, opt)

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
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(
        page_w / 2,
        pad_bottom * 0.35,
        "Rellene completamente cada círculo con lápiz o lapicero. No use corrector.",
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
