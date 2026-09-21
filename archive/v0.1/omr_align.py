"""
Alineación de fichas OMR A5: marcadores, orientación 0/90/180/270,
grilla de burbujas sincronizada con sheet_pdf y lectura de marcas.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

CANVAS_W, CANVAS_H = 800, 1130
DST_TLTRBRBL = np.array(
    [[40.0, 40.0], [760.0, 40.0], [760.0, 1090.0], [40.0, 1090.0]],
    dtype=np.float32,
)


def imread_bgr(path: str) -> Optional[np.ndarray]:
    """Lee BGR aplicando orientación EXIF (fotos de celular)."""
    img = cv2.imread(path)
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as pil:
            pil = ImageOps.exif_transpose(pil)
            if pil.mode != "RGB":
                pil = pil.convert("RGB")
            arr = np.array(pil)
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception:
        return img


def expected_omr_grid(num_questions: int = 15, num_alternatives: int = 4) -> Dict[str, Any]:
    try:
        from sheet_pdf import geometry_to_warped_canvas, get_omr_geometry

        return geometry_to_warped_canvas(get_omr_geometry(num_questions, num_alternatives))
    except Exception as exc:
        print(f"[OMR] sheet_pdf geometry fallback: {exc}")
        # Medido sobre la ficha A5 rasterizada (4 alternativas, 15 preguntas)
        y_left = [345.0, 423.0, 501.0, 579.0, 657.0, 735.0, 813.0, 891.0]
        mid = (num_questions + 1) // 2
        n_left, n_right = mid, num_questions - mid
        step = 78.0
        if n_left != 8:
            y_left = [345.0 + i * step for i in range(n_left)]
        y_right = [345.0 + i * step for i in range(n_right)]
        if num_alternatives >= 5:
            x_left = [123, 168, 213, 258, 303]
            x_right = [477, 522, 567, 612, 657]
            options = list("ABCDE")
        else:
            x_left = [123, 168, 213, 258]
            x_right = [477, 522, 567, 612]
            options = list("ABCD")[: max(2, num_alternatives)]
            x_left = x_left[: len(options)]
            x_right = x_right[: len(options)]
        return {
            "options": options,
            "x_left": x_left,
            "x_right": x_right,
            "y_rows_left": y_left[:n_left],
            "y_rows_right": y_right[:n_right],
            "y_start_left": y_left[0],
            "y_start_right": y_right[0] if y_right else y_left[0],
            "y_step": step,
            "bubble_radius": 16,
            "method": "hardcoded_a5_sheet",
        }


def _downscale(image: np.ndarray, max_side: int = 1600) -> Tuple[np.ndarray, float]:
    h, w = image.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return image, 1.0
    scale = max_side / float(m)
    small = cv2.resize(image, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
    return small, scale


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _adaptive_block(h: int, w: int) -> int:
    block = int(round(min(h, w) * 0.045))
    if block % 2 == 0:
        block += 1
    return int(np.clip(block, 31, 101))


def find_marker_candidates(image: np.ndarray) -> List[Tuple[float, float, float, float]]:
    """
    Cuadrados negros de ancla. Devuelve (cx, cy, area, side) en coords de `image`.
    """
    gray = _gray(image)
    h, w = gray.shape[:2]
    min_side = float(min(h, w))
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    block = _adaptive_block(h, w)
    methods = [
        cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 12),
        cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 8),
    ]
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    methods.append(otsu)

    raw: List[Tuple[float, float, float, float]] = []
    exp_side = 0.045 * min_side  # ~10 mm sobre una ficha que llena el encuadre
    min_s, max_s = 0.012 * min_side, 0.14 * min_side
    min_area, max_area = min_s ** 2 * 0.5, max_s ** 2

    for thresh in methods:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            if bh < 1 or bw < 1:
                continue
            ar = bw / float(bh)
            if ar < 0.55 or ar > 1.8:
                continue
            solidity = area / float(bw * bh)
            if solidity < 0.55:
                continue
            side = math.sqrt(area)
            if side < min_s or side > max_s:
                continue
            # El interior del cuadrado debe ser oscuro (no un hueco de letra)
            pad = max(1, int(min(bw, bh) * 0.2))
            roi = gray[y + pad : y + bh - pad, x + pad : x + bw - pad]
            if roi.size == 0:
                continue
            if float(np.mean(roi)) > 110:
                continue
            M = cv2.moments(cnt)
            if M["m00"] <= 0:
                continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            raw.append((cx, cy, area, side))

    # Deduplicar (quedarse con el de mayor área)
    raw.sort(key=lambda t: t[2], reverse=True)
    uniq: List[Tuple[float, float, float, float]] = []
    merge_d2 = (0.025 * min_side) ** 2
    for cand in raw:
        too_close = False
        for u in uniq:
            if (cand[0] - u[0]) ** 2 + (cand[1] - u[1]) ** 2 < merge_d2:
                too_close = True
                break
        if not too_close:
            uniq.append(cand)
    # Preferir tamaños cercanos al ancla esperada
    uniq.sort(key=lambda t: (abs(t[3] - exp_side), -t[2]))
    return uniq[:18]


def _quad_score(pts: np.ndarray, areas: Sequence[float], img_h: int, img_w: int) -> float:
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    hull = cv2.convexHull(pts)
    if hull is None or len(hull) < 4:
        return -1e6
    area = float(cv2.contourArea(hull))
    img_area = float(img_h * img_w)
    if area < 0.08 * img_area:
        return -1e6
    # Ordenar y medir lados
    ordered = _order_clockwise(pts)
    sides = [
        float(np.linalg.norm(ordered[(i + 1) % 4] - ordered[i]))
        for i in range(4)
    ]
    if min(sides) < 20:
        return -1e6
    # A5: lados opuestos similares, aspecto ~0.70 o ~1.41
    r1 = sides[0] / max(sides[2], 1e-6)
    r2 = sides[1] / max(sides[3], 1e-6)
    if r1 > 1:
        r1 = 1.0 / r1
    if r2 > 1:
        r2 = 1.0 / r2
    aspect = (0.5 * (sides[0] + sides[2])) / max(0.5 * (sides[1] + sides[3]), 1e-6)
    a5 = min(abs(aspect - 148 / 210), abs(aspect - 210 / 148), abs(aspect - 1.0) + 0.25)
    size_cv = float(np.std(areas) / (np.mean(areas) + 1e-6))
    # Ángulos no degenerados
    ang_pen = 0.0
    for i in range(4):
        v1 = ordered[i] - ordered[(i - 1) % 4]
        v2 = ordered[(i + 1) % 4] - ordered[i]
        n1 = np.linalg.norm(v1) * np.linalg.norm(v2)
        if n1 < 1e-6:
            ang_pen += 5
            continue
        cos = float(np.clip(np.dot(v1, v2) / n1, -1, 1))
        ang = math.degrees(math.acos(cos))
        ang_pen += abs(ang - 90.0) / 40.0
    score = (
        (area / img_area) * 40.0
        + r1 * 8.0
        + r2 * 8.0
        - a5 * 10.0
        - size_cv * 6.0
        - ang_pen
    )
    return score


def _order_clockwise(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 puntos en sentido horario *en coordenadas de imagen* (Y hacia abajo)."""
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    # Con Y hacia abajo, argsort de atan2 ya recorre el cuadrilátero en horario de pantalla.
    order = np.argsort(ang)
    return pts[order].copy()


def pick_four_markers(
    cands: List[Tuple[float, float, float, float]], h: int, w: int
) -> Optional[np.ndarray]:
    if len(cands) < 4:
        return None
    pool = cands[:12]
    best_pts = None
    best_score = -1e9
    for comb in itertools.combinations(pool, 4):
        pts = np.array([(c[0], c[1]) for c in comb], dtype=np.float32)
        areas = [c[2] for c in comb]
        sc = _quad_score(pts, areas, h, w)
        if sc > best_score:
            best_score = sc
            best_pts = pts
    if best_pts is None or best_score < 0:
        return None
    return best_pts


def find_paper_quad(image: np.ndarray) -> Optional[np.ndarray]:
    gray = _gray(image)
    h, w = gray.shape[:2]
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    block = _adaptive_block(h, w)
    adapt = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 2
    )
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    best = None
    best_area = 0.0
    for mask in (adapt, otsu):
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 0.12 * h * w:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) != 4:
                rect = cv2.minAreaRect(cnt)
                box = cv2.boxPoints(rect)
            else:
                box = approx.reshape(4, 2)
            if area > best_area:
                best_area = area
                best = box.astype(np.float32)
    return best


def _inset_quad(pts: np.ndarray, frac_x: float = 0.0676, frac_y: float = 0.0476) -> np.ndarray:
    """Aproxima centros de ancla (10 mm) desde las esquinas del papel."""
    ordered = _order_clockwise(pts)
    # ordered is CW starting at arbitrary point; use bounding mean
    c = ordered.mean(axis=0)
    out = []
    for p in ordered:
        v = p - c
        # mover hacia el centro ~ fracción del semi-eje
        out.append(p - np.array([v[0] * frac_x * 2.2, v[1] * frac_y * 2.2], dtype=np.float32))
    return np.array(out, dtype=np.float32)


def _hough_circles(gray: np.ndarray, y0: int = 300, y1: int = 940) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=16,
        param1=55, param2=18, minRadius=9, maxRadius=22,
    )
    if circles is None:
        return np.zeros((0, 3), dtype=np.float32)
    pts = circles[0].astype(np.float32)
    h, w = gray.shape[:2]
    keep = (pts[:, 0] > 70) & (pts[:, 0] < w - 70) & (pts[:, 1] > y0) & (pts[:, 1] < y1)
    return pts[keep]


def score_upright_sheet(warped: np.ndarray) -> float:
    """Puntúa si el canvas 800×1130 está derecho (título arriba, 2 columnas)."""
    gray = _gray(warped)
    h, w = gray.shape[:2]
    score = 0.0

    # 1) Anclas oscuras en las 4 esquinas canónicas
    for (x, y) in ((40, 40), (760, 40), (40, 1090), (760, 1090)):
        x1, x2 = max(0, x - 28), min(w, x + 28)
        y1, y2 = max(0, y - 28), min(h, y + 28)
        patch = gray[y1:y2, x1:x2]
        if patch.size == 0:
            continue
        m = float(np.mean(patch))
        if m < 70:
            score += 4.0
        elif m < 110:
            score += 2.0
        elif m > 180:
            score -= 1.5

    # 2) Círculos en zona de preguntas, dos columnas de filas de 4
    circ = _hough_circles(gray, 310, 930)
    n = len(circ)
    score += min(n, 70) * 0.12
    left = circ[circ[:, 0] < 360] if n else circ
    right = circ[circ[:, 0] > 430] if n else circ
    header_c = circ[circ[:, 1] < 290] if n else circ
    score -= min(len(header_c), 12) * 0.8
    if len(left) >= 18:
        score += 6.0
    if len(right) >= 14:
        score += 5.0

    def n_regular_rows(points: np.ndarray, n_alt: int = 4) -> int:
        if points is None or len(points) < n_alt:
            return 0
        order = points[np.argsort(points[:, 1])]
        rows = []
        cur = [order[0]]
        for p in order[1:]:
            if abs(float(p[1]) - float(np.mean([c[1] for c in cur]))) <= 16:
                cur.append(p)
            else:
                rows.append(cur)
                cur = [p]
        rows.append(cur)
        good = 0
        for row in rows:
            xs = sorted(float(p[0]) for p in row)
            if len(xs) < n_alt - 1:
                continue
            if len(xs) > n_alt:
                # ventana más regular de n_alt
                best_std = 1e9
                best = xs[:n_alt]
                for i in range(len(xs) - n_alt + 1):
                    win = xs[i : i + n_alt]
                    g = np.diff(win)
                    std = float(np.std(g))
                    if std < best_std:
                        best_std, best = std, win
                xs = best
            if len(xs) < n_alt - 1:
                continue
            gaps = np.diff(xs)
            med = float(np.median(gaps))
            if 32 <= med <= 70 and float(np.max(np.abs(gaps - med))) <= 16:
                good += 1
        return good

    nL = n_regular_rows(left)
    nR = n_regular_rows(right)
    score += nL * 2.2 + nR * 2.2
    if nL >= 6 and nR >= 5:
        score += 8.0

    # 3) Banda de título (texto horizontal arriba-izquierda)
    band = gray[48:108, 70:430]
    if band.size:
        ink = (band < 140).mean(axis=1)
        if float(np.max(ink)) > 0.06:
            score += 5.0
        # más tinta en filas que en columnas → texto horizontal
        row_e = float(np.std((255 - band).mean(axis=1)))
        col_e = float(np.std((255 - band).mean(axis=0)))
        if row_e > col_e * 1.15:
            score += 3.0
        else:
            score -= 2.0

    # 4) Cabecera: caja redondeada ~y 110–270 con borde
    edges = cv2.Canny(gray[110:280, 60:740], 40, 120)
    if edges.size and float(edges.mean()) > 4:
        score += 2.0

    # 5) Título de color (azul/verde) ARRIBA. Usar canal mínimo para que
    #    el texto cromático se vea negro; ignorar cajas anchas del pie.
    def _title_letters(img: np.ndarray, y0: int, y1: int, x0: int, x1: int) -> Tuple[int, float]:
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            return 0, 0.0
        if crop.ndim == 3:
            dark = np.min(crop, axis=2)
        else:
            dark = crop
        blur = cv2.GaussianBlur(dark, (3, 3), 0)
        _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        nlab, _, stats, _ = cv2.connectedComponentsWithStats(th, 8)
        if nlab <= 1:
            return 0, 0.0
        hs = stats[1:, cv2.CC_STAT_HEIGHT]
        ws = stats[1:, cv2.CC_STAT_WIDTH]
        ar = stats[1:, cv2.CC_STAT_AREA]
        ok = (hs >= 11) & (hs <= 36) & (ws >= 4) & (ws <= 34) & (ar >= 40) & (ar <= 700)
        n = int(np.sum(ok))
        mh = float(np.median(hs[ok])) if n else 0.0
        return n, mh

    src_for_title = warped if warped.ndim == 3 else gray
    n_top, h_top = _title_letters(src_for_title, 38, 125, 55, 430)
    n_bot, h_bot = _title_letters(src_for_title, 1005, 1120, 55, 740)
    if n_top >= n_bot + 2 and n_top >= 4:
        score += 12.0
    elif n_bot >= n_top + 2 and n_bot >= 4:
        score -= 14.0  # título abajo → invertido
    score += min(n_top, 12) * 0.6

    # 6) Números de pregunta 01–08 deben estar a la IZQUIERDA de las burbujas
    #    (x~80–115), no a la derecha. Útil contra espejos.
    left_nums = gray[330:900, 70:125]
    right_nums = gray[330:900, 675:740]
    if left_nums.size and right_nums.size:
        ink_l = float((left_nums < 130).mean())
        ink_r = float((right_nums < 130).mean())
        if ink_l > ink_r + 0.02:
            score += 4.0
        elif ink_r > ink_l + 0.02:
            score -= 6.0

    return score


def _warp_from_src(image: np.ndarray, src_cw: np.ndarray, roll: int) -> np.ndarray:
    src = np.roll(src_cw, roll, axis=0).astype(np.float32)
    M = cv2.getPerspectiveTransform(src, DST_TLTRBRBL)
    return cv2.warpPerspective(image, M, (CANVAS_W, CANVAS_H))


def _largest_anchor_roll(
    src_cw: np.ndarray, areas_by_point: Optional[List[float]]
) -> Optional[int]:
    """Si un ancla es claramente mayor, esa es TL (roll que la pone primero)."""
    if not areas_by_point or len(areas_by_point) != 4:
        return None
    arr = np.array(areas_by_point, dtype=np.float32)
    # Map areas to clockwise-ordered points: we need areas aligned with src_cw
    return None  # se resuelve en warp_sheet_upright con matching


def warp_sheet_upright(image: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Localiza la ficha (anclas o contorno del papel), prueba 4 orientaciones
    y devuelve el canvas 800×1130 derecho.
    """
    work, scale = _downscale(image, 1600)
    wh, ww = work.shape[:2]
    cands = find_marker_candidates(work)
    pts = pick_four_markers(cands, wh, ww)
    method = "markers"
    src_small = pts

    if src_small is None:
        paper = find_paper_quad(work)
        if paper is None:
            raise ValueError(
                "No se detectaron los 4 marcadores de esquina ni el contorno de la ficha. "
                "Fotografía la hoja completa, con las 4 esquinas negras visibles."
            )
        src_small = _inset_quad(paper)
        method = "paper_quad"
        # intentar anclas cerca de cada esquina del papel
        if cands:
            paper_pts = _order_clockwise(paper.reshape(4, 2))
            near = []
            diag = float(np.linalg.norm(paper_pts[0] - paper_pts[2]))
            rad2 = (0.18 * diag) ** 2
            used = set()
            for corner in paper_pts:
                best_i, best_d = -1, 1e18
                for i, cand in enumerate(cands):
                    if i in used:
                        continue
                    d = (cand[0] - corner[0]) ** 2 + (cand[1] - corner[1]) ** 2
                    if d < best_d:
                        best_d, best_i = d, i
                if best_i >= 0 and best_d < rad2:
                    used.add(best_i)
                    near.append(cands[best_i][:2])
            if len(near) == 4:
                src_small = np.array(near, dtype=np.float32)
                method = "markers_near_paper"

    src_small = _order_clockwise(np.asarray(src_small, dtype=np.float32))
    src_full = src_small / scale

    # Áreas de ancla en el mismo orden CW (para TL grande)
    area_by_src = []
    if cands:
        for p in src_small:
            best = min(cands, key=lambda c: (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2)
            area_by_src.append(best[2])

    best_img = None
    best_score = -1e9
    best_roll = 0
    scores = []
    for roll in range(4):
        warped = _warp_from_src(image, src_full, roll)
        sc = score_upright_sheet(warped)
        # Bonus si el ancla más grande cae en TL (índice 0 tras el roll)
        if len(area_by_src) == 4:
            rolled_areas = list(np.roll(np.array(area_by_src), roll))
            largest = max(rolled_areas)
            med = float(np.median(rolled_areas))
            if med > 0 and largest >= 1.28 * med and rolled_areas[0] == largest:
                sc += 7.0
        scores.append(round(float(sc), 2))
        if sc > best_score:
            best_score = sc
            best_img = warped
            best_roll = roll

    print(f"[ALIGN] method={method} roll={best_roll}*90° scores={scores} best={best_score:.1f}")
    meta = {
        "method": method,
        "roll": best_roll,
        "scores": scores,
        "best_score": float(best_score),
        "n_marker_cands": len(cands),
    }
    if best_img is None:
        raise ValueError("No se pudo alinear la ficha.")
    return best_img, meta


def detect_corners(image: np.ndarray):
    """Compat: devuelve (src_pts, dst_pts) ya orientados para warp 800×1130."""
    work, scale = _downscale(image, 1600)
    cands = find_marker_candidates(work)
    pts = pick_four_markers(cands, work.shape[0], work.shape[1])
    if pts is None:
        paper = find_paper_quad(work)
        if paper is None:
            raise ValueError(
                f"No se pudieron detectar suficientes marcadores de esquina. "
                f"Encontrados: {len(cands)}. Se requieren al menos 4."
            )
        pts = _inset_quad(paper)
    src_small = _order_clockwise(np.asarray(pts, dtype=np.float32))
    src_full = src_small / scale
    # Elegir roll con un warp barato sobre la copia pequeña
    best_roll, best_sc = 0, -1e9
    for roll in range(4):
        warped = _warp_from_src(work, src_small, roll)
        sc = score_upright_sheet(warped)
        if sc > best_sc:
            best_sc, best_roll = sc, roll
    src = np.roll(src_full, best_roll, axis=0)
    dst = DST_TLTRBRBL
    return [tuple(map(float, p)) for p in src], [list(map(float, p)) for p in dst]


def warp_image(image: np.ndarray, corners_data) -> np.ndarray:
    src_list, dst_list = corners_data
    src_pts = np.array(src_list, dtype="float32")
    dst_pts = np.array(dst_list, dtype="float32")
    M = cv2.getPerspectiveTransform(src_pts[:4], dst_pts[:4])
    return cv2.warpPerspective(image, M, (CANVAS_W, CANVAS_H))


def _cluster_rows(points: List[Tuple[float, float, float]], y_tol: float = 16.0):
    if not points:
        return []
    points = sorted(points, key=lambda p: p[1])
    rows, cur = [], [points[0]]
    for p in points[1:]:
        if abs(p[1] - float(np.mean([c[1] for c in cur]))) <= y_tol:
            cur.append(p)
        else:
            rows.append(cur)
            cur = [p]
    rows.append(cur)
    return rows


def detect_omr_grid(warped_gray: np.ndarray, num_questions: int = 15) -> Dict[str, Any]:
    """
    Parte de la geometría de sheet_pdf y ajusta con Hough (snap a círculos reales).
    """
    try:
        from omr_processor import load_settings_num_alternatives

        pref_alt = load_settings_num_alternatives(4)
    except Exception:
        pref_alt = 4

    expected = expected_omr_grid(num_questions, pref_alt)
    H, W = warped_gray.shape[:2]
    circ = _hough_circles(warped_gray, 300, 960)
    n_alt = len(expected["options"])
    radius = int(expected.get("bubble_radius") or 16)

    if len(circ) < 12:
        print(f"[OMR] Pocas burbujas Hough ({len(circ)}) → {expected['method']}")
        return expected

    def snap_column(x_coords, y_rows):
        max_d = 18.0
        xs_acc = [[] for _ in x_coords]
        ys_out = []
        matched = 0
        for y in y_rows:
            row_ys = []
            for xi, x in enumerate(x_coords):
                d2 = (circ[:, 0] - x) ** 2 + (circ[:, 1] - y) ** 2
                j = int(np.argmin(d2))
                if d2[j] <= max_d ** 2:
                    cx, cy = float(circ[j, 0]), float(circ[j, 1])
                    xs_acc[xi].append(cx)
                    row_ys.append(cy)
                    matched += 1
            if len(row_ys) >= 2:
                ys_out.append(float(np.median(row_ys)))
            else:
                ys_out.append(float(y))
        xs_out = []
        for xi, x in enumerate(x_coords):
            if len(xs_acc[xi]) >= 3:
                xs_out.append(int(round(float(np.median(xs_acc[xi])))))
            else:
                xs_out.append(int(round(x)))
        # Si el snap desplazó la primera fila hacia la cabecera, descartar
        if ys_out and abs(ys_out[0] - y_rows[0]) > 24:
            return list(x_coords), list(y_rows), 0
        return xs_out, ys_out, matched

    xL, yL, mL = snap_column(expected["x_left"], expected["y_rows_left"])
    xR, yR, mR = snap_column(expected["x_right"], expected["y_rows_right"])
    method = expected["method"]
    if mL + mR >= 20:
        method = f"snap_pdf_{n_alt}alt_m{mL + mR}"
    grid = {
        "options": list(expected["options"]),
        "x_left": xL,
        "x_right": xR,
        "y_rows_left": yL,
        "y_rows_right": yR,
        "y_start_left": yL[0] if yL else expected["y_start_left"],
        "y_start_right": yR[0] if yR else expected["y_start_right"],
        "y_step": float(np.median(np.diff(yL))) if len(yL) > 1 else expected["y_step"],
        "bubble_radius": radius,
        "method": method,
        "hough_matches": int(mL + mR),
    }
    print(
        f"[OMR] Grid {grid['method']}: xL={xL} xR={xR} "
        f"yL0={grid['y_start_left']:.1f} yR0={grid['y_start_right']:.1f} "
        f"step={grid['y_step']:.1f} matches={mL + mR}"
    )
    return grid


def _circle_mask(shape, center, radius) -> np.ndarray:
    mask = np.zeros(shape[:2], dtype=np.uint8)
    cv2.circle(mask, (int(center[0]), int(center[1])), int(radius), 255, -1)
    return mask


def bubble_features(gray: np.ndarray, thresh: np.ndarray, center, radius: int = 16) -> Dict[str, float]:
    h, w = gray.shape[:2]
    x, y = int(center[0]), int(center[1])
    if x < 4 or y < 4 or x >= w - 4 or y >= h - 4:
        return {"raw": 255.0, "ink": 0.0, "dark_frac": 0.0, "p20": 255.0}
    inner_r = max(6, int(round(radius * 0.58)))
    mask = _circle_mask(gray.shape, (x, y), inner_r)
    raw = float(cv2.mean(gray, mask=mask)[0])
    ink = float(cv2.mean(thresh, mask=mask)[0])
    ys, xs = np.where(mask > 0)
    pixels = gray[ys, xs]
    dark_frac = float((pixels < 145).mean()) if pixels.size else 0.0
    p20 = float(np.percentile(pixels, 20)) if pixels.size else 255.0
    return {"raw": raw, "ink": ink, "dark_frac": dark_frac, "p20": p20}


def read_question_answer(
    feats: List[Tuple[str, Dict[str, float], Tuple[int, int]]],
) -> Tuple[str, Tuple[int, int], str]:
    """
    Decide la marca de una pregunta.
    Devuelve (respuesta, centro_elegido, letra_elegida_para_overlay).
    respuesta: 'A'..'E', '-' blanco, 'X' doble.
    """
    if len(feats) < 2:
        return "-", feats[0][2] if feats else (0, 0), ""

    raws = np.array([f[1]["raw"] for f in feats], dtype=np.float32)
    inks = np.array([f[1]["ink"] for f in feats], dtype=np.float32)
    darks = np.array([f[1]["dark_frac"] for f in feats], dtype=np.float32)
    p20s = np.array([f[1]["p20"] for f in feats], dtype=np.float32)

    med_raw = float(np.median(raws))
    med_ink = float(np.median(inks))

    marked = []
    for i, (letter, f, center) in enumerate(feats):
        gap_raw = med_raw - f["raw"]
        gap_ink = f["ink"] - med_ink
        # Absoluto: un relleno negro sigue siéndolo aunque 2–3 hermanas también
        # (el gap de la fila se anula cuando A+B+D están pintadas).
        # NO usar ink absoluto: la letra impresa A/B/C/D dispara umbrales de tinta.
        abs_fill = f["raw"] < 148.0 or f["dark_frac"] >= 0.30
        abs_stroke = f["dark_frac"] >= 0.20 and f["p20"] < 112.0 and f["raw"] < 158.0
        rel = (gap_raw >= 22.0 and f["raw"] < 168.0) or (
            gap_ink >= 28.0 and gap_raw >= 14.0 and f["raw"] < 170.0
        )
        is_mark = abs_fill or abs_stroke or rel
        if f["raw"] > 188.0 or f["dark_frac"] < 0.08:
            is_mark = False
        if is_mark:
            strength = (
                f["dark_frac"] * 90.0
                + max(0.0, gap_raw)
                + max(0.0, 180.0 - f["raw"]) * 0.4
                + max(0.0, gap_ink) * 0.4
                + max(0.0, 140.0 - f["p20"]) * 0.2
            )
            marked.append((strength, letter, center, i))

    if not marked:
        return "-", feats[int(np.argmin(raws))][2], feats[int(np.argmin(raws))][0]

    marked.sort(key=lambda t: t[0], reverse=True)
    if len(marked) >= 2 and marked[1][0] >= 16.0:
        if marked[1][0] >= 0.45 * marked[0][0] or marked[0][0] - marked[1][0] < 14.0:
            return "X", marked[0][2], marked[0][1]
    return marked[0][1], marked[0][2], marked[0][1]


def build_question_coords(grid: Dict[str, Any], num_questions: int) -> Dict[int, List[Tuple[int, int]]]:
    mid = (num_questions + 1) // 2
    coords: Dict[int, List[Tuple[int, int]]] = {}
    xL = grid["x_left"]
    xR = grid["x_right"]
    yL = grid.get("y_rows_left") or []
    yR = grid.get("y_rows_right") or []
    step = float(grid.get("y_step") or 78.0)
    y0l = float(grid.get("y_start_left") or (yL[0] if yL else 345))
    y0r = float(grid.get("y_start_right") or (yR[0] if yR else y0l))
    for qi, q in enumerate(range(1, mid + 1)):
        y = yL[qi] if qi < len(yL) else y0l + qi * step
        coords[q] = [(int(x), int(round(y))) for x in xL]
    for qi, q in enumerate(range(mid + 1, num_questions + 1)):
        y = yR[qi] if qi < len(yR) else y0r + qi * step
        coords[q] = [(int(x), int(round(y))) for x in xR]
    return coords
