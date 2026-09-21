# -*- coding: utf-8 -*-
"""Pruebas de geometría 15/20×4/5 y de guías de orientación (giros 0/90/180/270)."""
from __future__ import annotations

import sys

import cv2
import numpy as np

from omr_align import (
    CANVAS_H,
    CANVAS_W,
    classify_marker_at,
    draw_fiducial_bgr,
    prepare_mark_maps,
    read_question_answer,
    src_from_fiducials,
    warp_sheet_upright,
    bubble_features,
)
from sheet_pdf import (
    MARKER_DST,
    geometry_to_warped_canvas,
    get_omr_geometry,
)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_geometry_fits_page():
    for nq, na in ((15, 4), (15, 5), (20, 4), (20, 5)):
        g = get_omr_geometry(nq, na)
        _assert(g["num_questions"] == nq, f"{nq}q: num_questions")
        _assert(g["num_alternatives"] == na, f"{nq}q/{na}a: alts")
        _assert(len(g["x_left_mm"]) == na, f"{nq}q/{na}a: x_left")
        _assert(len(g["x_right_mm"]) == na, f"{nq}q/{na}a: x_right")
        mid = (nq + 1) // 2
        _assert(len(g["y_left_mm"]) == mid, f"{nq}q: left rows")
        _assert(len(g["y_right_mm"]) == nq - mid, f"{nq}q: right rows")
        d = g["bubble_diameter_mm"]
        gap = g["bubble_gap_mm"]
        _assert(5.1 <= d <= 8.3, f"{nq}q/{na}a: diámetro {d:.2f} mm")
        _assert(gap >= 1.3, f"{nq}q/{na}a: hueco {gap:.2f} mm")
        # las burbujas caben en la columna
        last_x = g["x_left_mm"][-1] + d / 2.0
        col_end = g["left_col_x_mm"] + g["col_w_mm"]
        _assert(last_x <= col_end + 0.4, f"{nq}q/{na}a: overflow x {last_x:.1f} > {col_end:.1f}")
        # filas caben entre top y bottom
        _assert(g["y_left_mm"][0] < g["questions_top_mm"] + 0.2, "fila 1 sobre el techo")
        _assert(g["y_left_mm"][-1] > g["questions_bottom_mm"] - 0.2, "última fila bajo el piso")
        # 20 preguntas compacta
        if nq == 20:
            _assert(g["compact"] is True, "20q debe compactar cabecera/pie")
            _assert(g["row_h_mm"] >= 11.0, f"20q row_h demasiado bajo: {g['row_h_mm']:.2f}")
        canvas = geometry_to_warped_canvas(g)
        _assert(len(canvas["x_left"]) == na, "canvas x")
        _assert(canvas["bubble_radius"] >= 8, "radio px")
        from omr_processor import overlay_metrics
        ov = overlay_metrics(canvas["bubble_radius"])
        _assert(ov["r"] >= canvas["bubble_radius"], "overlay debe cubrir la burbuja impresa")
        _assert(abs(ov["r"] - canvas["bubble_radius"]) <= 2, "overlay no debe desbordar 2px")
        print(
            f"  OK {nq}q {na}alt  d={d:.2f}mm gap={gap:.2f}mm "
            f"row={g['row_h_mm']:.2f}mm r_px={canvas['bubble_radius']} "
            f"compact={g['compact']}"
        )


def _synthetic_sheet(num_q=20, num_alt=5) -> np.ndarray:
    img = np.full((CANVAS_H, CANVAS_W, 3), 255, np.uint8)
    size = 56
    draw_fiducial_bgr(img, "solid", *MARKER_DST["TL"], size)
    draw_fiducial_bgr(img, "frame", *MARKER_DST["TR"], size)
    draw_fiducial_bgr(img, "circle", *MARKER_DST["BL"], size)
    draw_fiducial_bgr(img, "ell", *MARKER_DST["BR"], size)
    canvas = geometry_to_warped_canvas(get_omr_geometry(num_q, num_alt))
    r = max(8, int(canvas["bubble_radius"] * 0.9))
    for xs, ys in (
        (canvas["x_left"], canvas["y_rows_left"]),
        (canvas["x_right"], canvas["y_rows_right"]),
    ):
        for y in ys:
            for x in xs:
                cv2.circle(img, (int(x), int(round(y))), r, (180, 160, 40), 2, cv2.LINE_AA)
    # título simulado (banda oscura horizontal arriba-izquierda)
    cv2.rectangle(img, (130, 58), (340, 80), (30, 110, 40), -1)
    return img


def _place_on_desk(sheet: np.ndarray, rot90: int, margin: int = 80) -> np.ndarray:
    img = sheet
    for _ in range(rot90 % 4):
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    h, w = img.shape[:2]
    desk = np.full((h + 2 * margin, w + 2 * margin, 3), 210, np.uint8)
    desk[margin : margin + h, margin : margin + w] = img
    return desk


def test_classify_canonical():
    sheet = _synthetic_sheet()
    gray = cv2.cvtColor(sheet, cv2.COLOR_BGR2GRAY)
    expected = {
        "TL": "solid",
        "TR": "frame",
        "BL": "circle",
        "BR": "ell",
    }
    kinds = []
    for name, (x, y) in MARKER_DST.items():
        kind, sc = classify_marker_at(gray, x, y, side=56)
        kinds.append(kind)
        _assert(kind == expected[name], f"{name} esperaba {expected[name]}, obtuvo {kind} (sc={sc:.1f})")
        print(f"  OK {name} → {kind} ({sc:.1f})")
    mapped = src_from_fiducials(
        np.array([MARKER_DST[k] for k in ("TL", "TR", "BR", "BL")], dtype=np.float32),
        [(expected["TL"], 8), (expected["TR"], 8), (expected["BR"], 8), (expected["BL"], 8)],
    )
    _assert(mapped is not None, "src_from_fiducials")


def test_warp_rotations():
    sheet = _synthetic_sheet(20, 5)
    for rot in (0, 1, 2, 3):
        photo = _place_on_desk(sheet, rot)
        warped, meta = warp_sheet_upright(photo)
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        kind_tl, sc_tl = classify_marker_at(gray, 40, 40, side=56)
        kind_tr, _ = classify_marker_at(gray, 760, 40, side=56)
        kind_bl, _ = classify_marker_at(gray, 40, 1090, side=56)
        kind_br, _ = classify_marker_at(gray, 760, 1090, side=56)
        print(
            f"  rot {rot * 90:3d}° method={meta['method']} "
            f"kinds_in={meta.get('fiducial_kinds')} "
            f"out TL/TR/BL/BR={kind_tl}/{kind_tr}/{kind_bl}/{kind_br} "
            f"score={meta['best_score']:.1f}"
        )
        _assert(
            kind_tl == "solid",
            f"rot {rot * 90}°: TL no es sólido ({kind_tl}) method={meta['method']}",
        )
        _assert(kind_tr == "frame", f"rot {rot * 90}°: TR no es marco ({kind_tr})")
        _assert(kind_bl == "circle", f"rot {rot * 90}°: BL no es círculo ({kind_bl})")
        _assert(kind_br == "ell", f"rot {rot * 90}°: BR no es L ({kind_br})")


def _feat(raw, ink, dark, p20, **extra):
    d160 = extra.get("dark160", min(1.0, dark * 1.35 + (0.12 if p20 < 160 else 0.0)))
    f = {
        "raw": float(raw),
        "ink": float(ink),
        "dark_frac": float(dark),
        "p20": float(p20),
        "dark160": float(d160),
        "dark175": float(extra.get("dark175", min(1.0, d160 * 1.15))),
        "ink_soft": float(extra.get("ink_soft", ink * 1.05)),
        "ink_otsu": float(extra.get("ink_otsu", ink)),
        "clahe_dark": float(extra.get("clahe_dark", dark)),
        "core_raw": float(extra.get("core_raw", raw - 2.0)),
        "bg_raw": float(extra.get("bg_raw", min(210.0, raw + 18.0))),
    }
    return f


def _row(*items):
    letters = "ABCDE"
    out = []
    for i, it in enumerate(items):
        out.append((letters[i], it, (100 + i * 70, 400)))
    return out


def test_mark_vote_empty_letters():
    """Letras impresas A/B/C/D, sin pintado → blanco."""
    feats = _row(
        _feat(180, 20.8, 0.054, 181),
        _feat(178, 29.1, 0.075, 181),  # B tiene más tinta impresa
        _feat(180, 24.0, 0.049, 182),
        _feat(179, 26.9, 0.060, 182),
    )
    ans, _, _ = read_question_answer(feats)
    _assert(ans == "-", f"vacío esperaba '-', obtuvo {ans}")
    print("  OK vacío con letras impresas → blanco")


def test_mark_vote_strong_fill():
    feats = _row(
        _feat(179.5, 20.8, 0.054, 181),
        _feat(178.0, 29.1, 0.075, 181),
        _feat(179.8, 24.0, 0.049, 182),
        _feat(141.9, 95.3, 0.527, 109),
    )
    ans, _, _ = read_question_answer(feats)
    _assert(ans == "D", f"relleno fuerte esperaba D, obtuvo {ans}")
    print("  OK relleno oscuro → D")


def test_mark_vote_light_pen():
    """Casos reales que el umbral único mandaba a blanco (ficha 005)."""
    cases = [
        (
            "C",
            _row(
                _feat(181.3, 21.6, 0.010, 175),
                _feat(181.3, 24.5, 0.004, 174),
                _feat(166.8, 38.5, 0.071, 154, dark160=0.22),
                _feat(183.4, 22.3, 0.000, 176),
            ),
        ),
        (
            "B",
            _row(
                _feat(182.6, 19.8, 0.013, 181),
                _feat(176.0, 43.5, 0.055, 161, dark160=0.18, ink_soft=52.0),
                _feat(183.1, 14.4, 0.003, 177),
                _feat(183.9, 23.4, 0.000, 176),
            ),
        ),
        (
            "A",
            _row(
                _feat(175.3, 50.7, 0.106, 159, dark160=0.24, ink_soft=56.0),
                _feat(180.0, 29.9, 0.008, 171),
                _feat(183.6, 13.3, 0.000, 179),
                _feat(183.4, 23.7, 0.000, 176),
            ),
        ),
        (
            "D",
            _row(
                _feat(180.1, 20.2, 0.044, 181),
                _feat(177.5, 29.4, 0.068, 179),
                _feat(177.1, 22.1, 0.046, 178),
                _feat(165.5, 37.4, 0.182, 150, dark160=0.28),
            ),
        ),
    ]
    for expect, feats in cases:
        ans, _, _ = read_question_answer(feats)
        _assert(ans == expect, f"lápiz claro esperaba {expect}, obtuvo {ans}")
        print(f"  OK lápiz claro → {expect}")


def test_mark_vote_double():
    feats = _row(
        _feat(142.0, 80.0, 0.585, 133),
        _feat(125.7, 90.0, 1.000, 122),
        _feat(175.0, 22.0, 0.060, 178),
        _feat(176.0, 25.0, 0.070, 177),
    )
    ans, _, _ = read_question_answer(feats)
    _assert(ans == "X", f"doble esperaba X, obtuvo {ans}")
    print("  OK doble pintado → X")


def test_mark_jitter_offset_scribble():
    """Pintado 12 px a la derecha del centro: el jitter debe encontrarlo."""
    img = np.full((120, 120), 190, np.uint8)
    cv2.circle(img, (60, 60), 22, 170, 2)  # anillo impreso
    # raya de lápiz descentrada (como Q01 D de la ficha 005)
    cv2.circle(img, (72, 64), 8, 110, -1)
    maps = prepare_mark_maps(img)
    f = bubble_features(img, maps["adaptive"], (60, 60), radius=22, maps=maps)
    _assert(f["ink"] >= 34.0 or f["dark_frac"] >= 0.10 or f["dark160"] >= 0.16,
            f"jitter no encontró la raya: {f}")
    empty = np.full((120, 120), 190, np.uint8)
    cv2.circle(empty, (60, 60), 22, 170, 2)
    cv2.putText(empty, "B", (52, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 90, 1, cv2.LINE_AA)
    maps_e = prepare_mark_maps(empty)
    fe = bubble_features(empty, maps_e["adaptive"], (60, 60), radius=22, maps=maps_e)
    marked_row = _row(fe, fe, fe, f)
    # reescribir letras reales
    marked_row = [
        ("A", fe, (60, 60)),
        ("B", fe, (60, 60)),
        ("C", fe, (60, 60)),
        ("D", f, (60, 60)),
    ]
    ans, _, _ = read_question_answer(marked_row)
    _assert(ans == "D", f"offset scribble esperaba D, obtuvo {ans} f={f} fe={fe}")
    print(f"  OK jitter offset → D (dark={f['dark_frac']:.3f} ink={f['ink']:.1f})")


def test_pdf_builds():
    from sheet_pdf import build_sheet_pdf

    for nq, na in ((15, 4), (20, 5)):
        data, name = build_sheet_pdf(
            "Comunicacion",
            settings={
                "labels": {
                    "nombre": "Apellidos y Nombres",
                    "colegio": "Colegio",
                    "grado": "Grado",
                    "procedencia": "Procedencia",
                },
                "num_questions": nq,
                "num_alternatives": na,
            },
        )
        _assert(data[:4] == b"%PDF", f"{name} no es PDF")
        _assert(len(data) > 2000, f"{name} demasiado pequeño")
        print(f"  OK PDF {nq}q/{na}a {len(data)} bytes")


if __name__ == "__main__":
    tests = [
        ("geometría A5", test_geometry_fits_page),
        ("clasificar guías", test_classify_canonical),
        ("giros 0/90/180/270", test_warp_rotations),
        ("PDF vectorial", test_pdf_builds),
        ("voto vacío/letras", test_mark_vote_empty_letters),
        ("voto relleno fuerte", test_mark_vote_strong_fill),
        ("voto lápiz claro", test_mark_vote_light_pen),
        ("voto doble marca", test_mark_vote_double),
        ("jitter pintado offset", test_mark_jitter_offset_scribble),
    ]
    failed = 0
    for title, fn in tests:
        print(f"\n== {title} ==")
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"  FALLO: {exc}")
    if failed:
        print(f"\n{failed} prueba(s) fallaron.")
        sys.exit(1)
    print("\nTodas las pruebas OK.")
