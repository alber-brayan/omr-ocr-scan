"""
Alineación de fichas OMR A5: marcadores, orientación 0/90/180/270,
grilla de burbujas sincronizada con sheet_pdf y lectura de marcas.

Guías 2026.3 (forma única, mismo tamaño):
  TL sólido ■   TR marco ▢   BL círculo ●   BR ele ⌞
Las fichas viejas (TL más grande, 4 cuadrados) siguen funcionando
con el fallback de 4 giros + puntaje.
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
# Orden de destino: TL, TR, BR, BL
FIDUCIAL_KIND_TO_CORNER = {
    "solid": "TL",
    "frame": "TR",
    "ell": "BR",
    "circle": "BL",
}
CORNER_TO_DST_INDEX = {"TL": 0, "TR": 1, "BR": 2, "BL": 3}


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


def draw_fiducial_bgr(img: np.ndarray, kind: str, cx: int, cy: int, size: int, color=(20, 20, 22)) -> None:
    """Dibuja una guía (BGR) para pruebas sintéticas. Y hacia abajo."""
    half = max(4, int(size) // 2)
    cx, cy = int(cx), int(cy)
    if kind == "solid":
        cv2.rectangle(img, (cx - half, cy - half), (cx + half, cy + half), color, -1, cv2.LINE_AA)
    elif kind == "frame":
        cv2.rectangle(img, (cx - half, cy - half), (cx + half, cy + half), color, -1, cv2.LINE_AA)
        inner = max(3, int(size * 0.40))
        cv2.rectangle(
            img,
            (cx - inner // 2, cy - inner // 2),
            (cx + inner // 2, cy + inner // 2),
            (255, 255, 255),
            -1,
            cv2.LINE_AA,
        )
    elif kind == "circle":
        cv2.circle(img, (cx, cy), half, color, -1, cv2.LINE_AA)
    else:  # ell: barra derecha + barra inferior (BR en coords de imagen)
        t = max(3, int(size * 0.38))
        cv2.rectangle(img, (cx + half - t, cy - half), (cx + half, cy + half), color, -1, cv2.LINE_AA)
        cv2.rectangle(img, (cx - half, cy + half - t), (cx + half, cy + half), color, -1, cv2.LINE_AA)


def classify_marker_at(
    gray: np.ndarray, cx: float, cy: float, side: float = 28.0
) -> Tuple[str, float]:
    """
    Clasifica una guía por forma: solid / frame / circle / ell.
    Independiente del giro: silueta del blob oscuro (circularidad, hueco, solidez).
    """
    gray = _gray(gray)
    h, w = gray.shape[:2]
    # Ventana holgada para ver el contorno completo (círculo vs cuadrado).
    half = int(np.clip(max(float(side), 24.0) * 1.15, 22, min(h, w) // 4))
    x1 = int(np.clip(round(cx) - half, 0, w - 1))
    x2 = int(np.clip(round(cx) + half, x1 + 10, w))
    y1 = int(np.clip(round(cy) - half, 0, h - 1))
    y2 = int(np.clip(round(cy) + half, y1 + 10, h))
    patch = gray[y1:y2, x1:x2]
    ph, pw = patch.shape[:2]
    if ph < 10 or pw < 10:
        return "solid", 0.0
    if min(ph, pw) < 40:
        patch = cv2.resize(patch, (56, 56), interpolation=cv2.INTER_CUBIC)
        ph, pw = patch.shape[:2]

    blur = cv2.GaussianBlur(patch, (3, 3), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, hier = cv2.findContours(th, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    scores = {"solid": 0.0, "frame": 0.0, "circle": 0.0, "ell": 0.0}
    if not contours:
        return "solid", 0.0

    pcx, pcy = pw / 2.0, ph / 2.0
    patch_area = float(ph * pw)
    best_i, best_key = -1, 1e18
    for i, cnt in enumerate(contours):
        area = float(cv2.contourArea(cnt))
        if area < 0.04 * patch_area or area > 0.92 * patch_area:
            continue
        bx0, by0, bw0, bh0 = cv2.boundingRect(cnt)
        ar0 = bw0 / float(max(bh0, 1))
        if ar0 < 0.55 or ar0 > 1.85:
            continue
        M = cv2.moments(cnt)
        if M["m00"] <= 0:
            continue
        dx = M["m10"] / M["m00"] - pcx
        dy = M["m01"] / M["m00"] - pcy
        # Preferir blob céntrico y de tamaño medio
        key = (dx * dx + dy * dy) / max(half * half, 1) - 0.15 * (area / patch_area)
        if key < best_key:
            best_key, best_i = key, i
    if best_i < 0:
        # fallback: el de mayor área que no llene el parche
        areas = [(i, float(cv2.contourArea(c))) for i, c in enumerate(contours)]
        areas = [t for t in areas if t[1] < 0.95 * patch_area]
        if not areas:
            return "solid", 0.0
        best_i = max(areas, key=lambda t: t[1])[0]

    cnt = contours[best_i]
    area = float(cv2.contourArea(cnt))
    if area < 20:
        return "solid", 0.0
    peri = float(cv2.arcLength(cnt, True))
    circularity = float(4.0 * math.pi * area / max(peri * peri, 1e-6))
    bx, by, bw, bh = cv2.boundingRect(cnt)
    solidity = area / float(max(bw * bh, 1))
    (_, _), encl_r = cv2.minEnclosingCircle(cnt)
    circle_fill = area / float(max(math.pi * encl_r * encl_r, 1e-6))
    has_hole = False
    if hier is not None and len(hier) > 0:
        child = int(hier[0][best_i][2])
        has_hole = child >= 0

    inner = patch[
        by + max(1, bh // 5) : by + bh - max(1, bh // 5),
        bx + max(1, bw // 5) : bx + bw - max(1, bw // 5),
    ]
    inner_m = float(np.mean(inner)) if inner.size else 128.0

    # Cuadrantes del bounding box del blob (no del parche entero)
    qh, qw = max(1, bh // 2), max(1, bw // 2)
    blob_roi = patch[by : by + bh, bx : bx + bw]
    if blob_roi.size:
        quads = [
            blob_roi[:qh, :qw],
            blob_roi[:qh, qw:],
            blob_roi[qh:, :qw],
            blob_roi[qh:, qw:],
        ]
        qmeans = [float(np.mean(q)) for q in quads if q.size]
    else:
        qmeans = []
    n_bright_quads = sum(1 for m in qmeans if m > 148)
    n_dark_quads = sum(1 for m in qmeans if m < 115)
    q_std = float(np.std(qmeans)) if qmeans else 0.0

    if has_hole or inner_m >= 150:
        scores["frame"] += 8.0
    if inner_m >= 135 and solidity >= 0.50:
        scores["frame"] += 2.5

    if circularity >= 0.80 and circle_fill >= 0.75 and not has_hole:
        scores["circle"] += 8.0 + max(0.0, circularity - 0.80) * 15.0
    if 0.68 <= solidity <= 0.86 and circularity >= 0.78 and inner_m < 140:
        scores["circle"] += 3.0

    if 0.42 <= solidity <= 0.80 and circularity < 0.74 and not has_hole:
        scores["ell"] += 5.5
    if n_bright_quads == 1 and n_dark_quads >= 2:
        scores["ell"] += 5.5
    if q_std >= 28 and n_bright_quads in (1, 2) and inner_m > 70 and not has_hole:
        scores["ell"] += 2.0

    if solidity >= 0.86 and circularity <= 0.87 and inner_m < 135 and not has_hole:
        scores["solid"] += 7.0
    if inner_m < 115 and n_bright_quads == 0 and 0.70 <= circularity <= 0.86:
        scores["solid"] += 3.0
    if not has_hole and solidity >= 0.90 and circularity < 0.84:
        scores["solid"] += 2.5

    kind = max(scores, key=scores.get)
    return kind, float(scores[kind])


def find_marker_candidates(image: np.ndarray) -> List[Tuple[float, float, float, float]]:
    """
    Anclas de esquina (cuadrado, marco, círculo, L).
    Devuelve (cx, cy, area, side) en coords de `image`.
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
    exp_side = 0.048 * min_side  # ~10 mm sobre una ficha que llena el encuadre
    min_s, max_s = 0.012 * min_side, 0.14 * min_side
    min_area, max_area = min_s ** 2 * 0.45, max_s ** 2

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
            if ar < 0.50 or ar > 2.0:
                continue
            solidity = area / float(bw * bh)
            # L ~0.62, círculo ~0.78, sólido ~0.95, marco (anillo) ~0.80
            if solidity < 0.42:
                continue
            side = math.sqrt(area)
            bbox_side = 0.5 * (bw + bh)
            if bbox_side < min_s or bbox_side > max_s:
                continue
            if side < min_s * 0.7 or side > max_s:
                continue
            M = cv2.moments(cnt)
            if M["m00"] <= 0:
                continue
            # Rechazar anillos finos (burbujas OMR huecas): el contorno encierra
            # mucho papel blanco. Las guías sólidas/marco/círculo/L están rellenas.
            roi_g = gray[y : y + bh, x : x + bw]
            mask = np.zeros((bh, bw), dtype=np.uint8)
            cnt_local = cnt.copy()
            cnt_local[:, 0, 0] -= x
            cnt_local[:, 0, 1] -= y
            cv2.drawContours(mask, [cnt_local], -1, 255, -1)
            if mask.size == 0 or int(np.count_nonzero(mask)) < 12:
                continue
            fill_frac = float((roi_g[mask > 0] < 130).mean())
            if fill_frac < 0.38:
                continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            raw.append((cx, cy, area, float(bbox_side)))

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
    def _corner_rank(c):
        cx, cy = c[0], c[1]
        d2 = min(
            cx * cx + cy * cy,
            (cx - w) ** 2 + cy * cy,
            cx * cx + (cy - h) ** 2,
            (cx - w) ** 2 + (cy - h) ** 2,
        )
        return (math.sqrt(d2) / max(min_side, 1.0), abs(c[3] - exp_side), -c[2])

    uniq.sort(key=_corner_rank)
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


def _hough_circles(
    gray: np.ndarray,
    y0: int = 250,
    y1: int = 1000,
    min_radius: int = 8,
    max_radius: int = 26,
) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(12, min_radius),
        param1=55, param2=18, minRadius=min_radius, maxRadius=max_radius,
    )
    if circles is None:
        return np.zeros((0, 3), dtype=np.float32)
    pts = circles[0].astype(np.float32)
    h, w = gray.shape[:2]
    keep = (pts[:, 0] > 70) & (pts[:, 0] < w - 70) & (pts[:, 1] > y0) & (pts[:, 1] < y1)
    return pts[keep]


def _ring_refine(gray: np.ndarray, x: float, y: float, radius: float, search: int = 4) -> Tuple[int, int]:
    """Ajusta el centro al anillo impreso (no a la mancha de lápiz)."""
    h, w = gray.shape[:2]
    x0, y0 = int(round(x)), int(round(y))
    r = max(6, int(round(radius)))
    n = 24
    angs = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    cs, sn = np.cos(angs), np.sin(angs)
    best = (x0, y0)
    best_s = -1e18
    for dy in range(-search, search + 1):
        cy = y0 + dy
        if cy < r or cy >= h - r:
            continue
        for dx in range(-search, search + 1):
            cx = x0 + dx
            if cx < r or cx >= w - r:
                continue
            xs = np.clip(np.round(cx + r * cs).astype(np.int32), 0, w - 1)
            ys = np.clip(np.round(cy + r * sn).astype(np.int32), 0, h - 1)
            ring = gray[ys, xs].astype(np.float32)
            # anillo oscuro = mejor; penaliza si el anillo es irregular (no es círculo)
            s = -float(ring.mean()) - 0.15 * float(ring.std())
            if s > best_s:
                best_s = s
                best = (cx, cy)
    return best


def snap_bubble_center(
    gray: np.ndarray,
    x: float,
    y: float,
    radius: int,
    circ: Optional[np.ndarray] = None,
    search: int = 4,
) -> Tuple[int, int]:
    """
    Centro del círculo IMPRESO: Hough local + micro-ajuste al anillo.
    No sigue el blob de tinta (eso desplazaba el tracking y daba falsos).
    """
    x0, y0 = float(x), float(y)
    r = float(radius or 16)
    if circ is not None and len(circ) > 0:
        d2 = (circ[:, 0] - x0) ** 2 + (circ[:, 1] - y0) ** 2
        j = int(np.argmin(d2))
        # Ajustes reales de Hough están a <5 px; más lejos suele ser un vecino o la raya.
        max_d = max(8.0, r * 0.48)
        if d2[j] <= max_d ** 2:
            x0, y0 = float(circ[j, 0]), float(circ[j, 1])
            if circ.shape[1] >= 3 and circ[j, 2] > 4:
                r = float(circ[j, 2])
    return _ring_refine(gray, x0, y0, r, search=search)


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

    # 2) Círculos en zona de preguntas, dos columnas de filas de 4 o 5
    circ = _hough_circles(gray, 250, 1000)
    n = len(circ)
    score += min(n, 90) * 0.12
    left = circ[circ[:, 0] < 360] if n else circ
    right = circ[circ[:, 0] > 430] if n else circ
    header_c = circ[circ[:, 1] < 250] if n else circ
    score -= min(len(header_c), 12) * 0.8
    if len(left) >= 16:
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
            if 22 <= med <= 80 and float(np.max(np.abs(gaps - med))) <= 18:
                good += 1
        return good

    nL = max(n_regular_rows(left, 4), n_regular_rows(left, 5))
    nR = max(n_regular_rows(right, 4), n_regular_rows(right, 5))
    score += nL * 2.2 + nR * 2.2
    if nL >= 6 and nR >= 5:
        score += 8.0

    # 2b) Formas de guía en las 4 esquinas canónicas (ficha 2026.3)
    corner_kinds = []
    for (x, y) in ((40, 40), (760, 40), (760, 1090), (40, 1090)):
        kind, conf = classify_marker_at(gray, x, y, side=56)
        corner_kinds.append(kind)
    n_unique_kinds = len(set(corner_kinds))
    if n_unique_kinds >= 3:
        expected = ("solid", "frame", "ell", "circle")  # TL TR BR BL
        matched = sum(1 for got, exp in zip(corner_kinds, expected) if got == exp)
        score += matched * 5.5
        if matched == 4:
            score += 8.0
        elif matched <= 1:
            score -= 10.0

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


def classify_four_markers(
    gray: np.ndarray, pts: np.ndarray, sides: Optional[Sequence[float]] = None
) -> List[Tuple[str, float]]:
    """Clasifica 4 puntos de ancla. pts shape (4,2)."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    out: List[Tuple[str, float]] = []
    for i, (x, y) in enumerate(pts):
        side = float(sides[i]) if sides is not None and i < len(sides) else 28.0
        out.append(classify_marker_at(gray, float(x), float(y), side=side))
    return out


def src_from_fiducials(
    pts: np.ndarray, kinds: Sequence[Tuple[str, float]]
) -> Optional[np.ndarray]:
    """
    Reordena 4 puntos a TL, TR, BR, BL según la forma detectada.
    Requiere las 4 formas distintas.
    """
    if len(pts) != 4 or len(kinds) != 4:
        return None
    by_kind: Dict[str, np.ndarray] = {}
    for p, (kind, score) in zip(pts, kinds):
        if score < 2.0:
            continue
        prev = by_kind.get(kind)
        if prev is None:
            by_kind[kind] = np.asarray(p, dtype=np.float32)
    needed = ("solid", "frame", "ell", "circle")
    if any(k not in by_kind for k in needed):
        return None
    ordered = np.array(
        [by_kind["solid"], by_kind["frame"], by_kind["ell"], by_kind["circle"]],
        dtype=np.float32,
    )
    return ordered


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

    src_small = np.asarray(src_small, dtype=np.float32).reshape(4, 2)
    src_cw = _order_clockwise(src_small)
    src_full = src_cw / scale
    work_gray = _gray(work)

    sides_by_src = []
    area_by_src = []
    if cands:
        for p in src_cw:
            best = min(cands, key=lambda c: (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2)
            area_by_src.append(best[2])
            sides_by_src.append(best[3])
    kinds = classify_four_markers(work_gray, src_cw, sides_by_src or None)
    kind_names = [k for k, _ in kinds]
    fid_src = src_from_fiducials(src_cw, kinds)

    best_img = None
    best_score = -1e9
    best_roll = 0
    best_method = method
    scores: List[float] = []

    # Camino principal: las 4 formas identifican TL/TR/BR/BL sin probar giros.
    if fid_src is not None:
        M = cv2.getPerspectiveTransform((fid_src / scale).astype(np.float32), DST_TLTRBRBL)
        warped_f = cv2.warpPerspective(image, M, (CANVAS_W, CANVAS_H))
        sc_f = score_upright_sheet(warped_f) + 16.0
        scores.append(round(float(sc_f), 2))
        best_img, best_score, best_roll, best_method = warped_f, sc_f, 0, "fiducials"
    else:
        scores.append(None)

    for roll in range(4):
        warped = _warp_from_src(image, src_full, roll)
        sc = score_upright_sheet(warped)
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
            best_method = method

    print(
        f"[ALIGN] method={best_method} kinds={kind_names} "
        f"roll={best_roll}*90° scores={scores} best={best_score:.1f}"
    )
    meta = {
        "method": best_method,
        "roll": best_roll,
        "scores": scores,
        "best_score": float(best_score),
        "n_marker_cands": len(cands),
        "fiducial_kinds": kind_names,
        "fiducials_ok": fid_src is not None,
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
    n_alt = len(expected["options"])
    radius = int(expected.get("bubble_radius") or 16)
    ys_all = list(expected.get("y_rows_left") or []) + list(expected.get("y_rows_right") or [])
    if ys_all:
        y0 = max(220, int(min(ys_all) - 50))
        y1 = min(H - 20, int(max(ys_all) + 50))
    else:
        y0, y1 = 250, 1000
    rmin = max(6, int(round(radius * 0.55)))
    rmax = max(radius + 8, min(48, int(round(radius * 1.65))))
    circ = _hough_circles(warped_gray, y0, y1, min_radius=rmin, max_radius=rmax)

    if len(circ) < 12:
        print(f"[OMR] Pocas burbujas Hough ({len(circ)}) → {expected['method']}")
        expected = dict(expected)
        expected["hough_circ"] = circ
        return expected

    matched_radii = []

    def snap_column(x_coords, y_rows):
        max_d = float(max(16.0, radius * 1.15))
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
                    if circ.shape[1] >= 3:
                        matched_radii.append(float(circ[j, 2]))
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
    if matched_radii and len(matched_radii) >= 8:
        measured = int(round(float(np.median(matched_radii))))
        if abs(measured - radius) <= 12:
            radius = max(10, min(42, measured))
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
        "hough_circ": circ,
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


_EMPTY_BUBBLE = {
    "raw": 255.0,
    "ink": 0.0,
    "dark_frac": 0.0,
    "p20": 255.0,
    "dark160": 0.0,
    "dark175": 0.0,
    "ink_soft": 0.0,
    "ink_otsu": 0.0,
    "clahe_dark": 0.0,
    "core_raw": 255.0,
    "bg_raw": 255.0,
}

# Offsets de muestreo paralelo: el lápiz a menudo queda 4–14 px fuera del anillo.
_JITTER_XY = (
    (0, 0),
    (4, 0), (-4, 0), (0, 4), (0, -4),
    (6, 6), (6, -6), (-6, 6), (-6, -6),
    (8, 0), (-8, 0), (0, 8), (0, -8),
    (10, 4), (10, -4), (-10, 4), (-10, -4),
    (4, 10), (-4, 10), (4, -10), (-4, -10),
    (12, 0), (-12, 0), (0, 12), (0, -12),
    (12, 6), (12, -6), (-12, 6), (-12, -6),
)


def prepare_mark_maps(gray: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Mapas de tinta en paralelo (redundancia):
      adaptive      — umbral local actual (anillo/letra)
      adaptive_soft — más sensible a lápiz/bolígrafo claro
      otsu          — global, útil con iluminación pareja
      clahe         — gris con contraste local (fotos lavadas)
    """
    g = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(g, (5, 5), 0)
    adaptive = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15
    )
    adaptive_soft = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 7
    )
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(g)
    return {
        "adaptive": adaptive,
        "adaptive_soft": adaptive_soft,
        "otsu": otsu,
        "clahe": clahe,
    }


def _disk_pixels(img: np.ndarray, cx: int, cy: int, r: int) -> np.ndarray:
    h, w = img.shape[:2]
    x0 = max(0, cx - r)
    y0 = max(0, cy - r)
    x1 = min(w, cx + r + 1)
    y1 = min(h, cy + r + 1)
    if x1 <= x0 or y1 <= y0:
        return np.empty((0,), dtype=img.dtype)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    return img[y0:y1, x0:x1][mask]


def _extract_at(
    gray: np.ndarray,
    thresh: np.ndarray,
    cx: int,
    cy: int,
    radius: int,
    maps: Optional[Dict[str, np.ndarray]] = None,
) -> Dict[str, float]:
    h, w = gray.shape[:2]
    if cx < 4 or cy < 4 or cx >= w - 4 or cy >= h - 4:
        return dict(_EMPTY_BUBBLE)
    inner_r = max(7, int(round(radius * 0.74)))
    core_r = max(5, int(round(radius * 0.48)))
    pix = _disk_pixels(gray, cx, cy, inner_r)
    if pix.size == 0:
        return dict(_EMPTY_BUBBLE)
    ink_pix = _disk_pixels(thresh, cx, cy, inner_r)
    core = _disk_pixels(gray, cx, cy, core_r)
    bg_r1 = max(inner_r + 4, int(round(radius * 1.55)))
    bg_all = _disk_pixels(gray, cx, cy, bg_r1)
    bg_raw = float(np.percentile(bg_all, 70)) if bg_all.size else 255.0

    raw = float(pix.mean())
    p20 = float(np.percentile(pix, 20))
    dark_frac = float((pix < 145).mean())
    dark160 = float((pix < 160).mean())
    dark175 = float((pix < 175).mean())
    ink = float(ink_pix.mean()) if ink_pix.size else 0.0
    core_raw = float(core.mean()) if core.size else raw

    ink_soft = ink
    ink_otsu = ink
    clahe_dark = dark_frac
    if maps:
        soft = maps.get("adaptive_soft")
        if soft is not None:
            sp = _disk_pixels(soft, cx, cy, inner_r)
            if sp.size:
                ink_soft = float(sp.mean())
        otsu = maps.get("otsu")
        if otsu is not None:
            op = _disk_pixels(otsu, cx, cy, inner_r)
            if op.size:
                ink_otsu = float(op.mean())
        clahe = maps.get("clahe")
        if clahe is not None:
            cp = _disk_pixels(clahe, cx, cy, inner_r)
            if cp.size:
                clahe_dark = float((cp < 142).mean())

    return {
        "raw": raw,
        "ink": ink,
        "dark_frac": dark_frac,
        "p20": p20,
        "dark160": dark160,
        "dark175": dark175,
        "ink_soft": ink_soft,
        "ink_otsu": ink_otsu,
        "clahe_dark": clahe_dark,
        "core_raw": core_raw,
        "bg_raw": bg_raw,
    }


def _mark_hint(f: Dict[str, float]) -> float:
    """Qué tan 'pintado' se ve un muestreo (para elegir el jitter)."""
    return (
        float(f.get("dark_frac", 0.0)) * 90.0
        + float(f.get("dark160", 0.0)) * 40.0
        + float(f.get("ink", 0.0)) * 0.55
        + float(f.get("ink_soft", 0.0)) * 0.25
        + max(0.0, 180.0 - float(f.get("raw", 255.0))) * 0.35
        + max(0.0, 165.0 - float(f.get("p20", 255.0))) * 0.25
    )


def bubble_features(
    gray: np.ndarray,
    thresh: np.ndarray,
    center,
    radius: int = 16,
    maps: Optional[Dict[str, np.ndarray]] = None,
) -> Dict[str, float]:
    """
    Extrae features de una burbuja con redundancia espacial:
    muestrea el centro y un jitter paralelo (±4..12 px) y se queda
    con el muestreo más pintado. Lee rayas descentradas sin irse
    al vecino (hueco típico ~70 px).
    """
    h, w = gray.shape[:2]
    x, y = int(round(center[0])), int(round(center[1]))
    if x < 4 or y < 4 or x >= w - 4 or y >= h - 4:
        return dict(_EMPTY_BUBBLE)
    r = max(8, int(radius or 16))
    span = max(6, min(14, int(round(r * 0.62))))
    center_f = _extract_at(gray, thresh, x, y, r, maps)
    best_f = center_f
    best_s = _mark_hint(center_f)
    for dx, dy in _JITTER_XY:
        if dx == 0 and dy == 0:
            continue
        if max(abs(dx), abs(dy)) > span:
            continue
        f = _extract_at(gray, thresh, x + dx, y + dy, r, maps)
        s = _mark_hint(f)
        if s > best_s + 8.0:
            best_s = s
            best_f = f
    return best_f


def _fget(f: Dict[str, float], key: str, default: float) -> float:
    try:
        return float(f.get(key, default))
    except (TypeError, ValueError):
        return default


def read_question_answer(
    feats: List[Tuple[str, Dict[str, float], Tuple[int, int]]],
) -> Tuple[str, Tuple[int, int], str]:
    """
    Decide la marca de una pregunta por voto de detectores en paralelo.

    Canales (redundancia, no un umbral único):
      R1 abs fill   — relleno oscuro claro (peso 2)
      R2 stroke     — rayas/lápiz parcial
      R3 relativo   — más oscuro que las hermanas de la fila
      R4 tinta      — gap de ink / ink_soft / clahe (lápiz claro)

    Hace falta voto >= 2 (o R1 solo). La letra impresa A/B/C/D no basta:
    todas las hermanas la tienen, el gap se anula.
    Devuelve (respuesta, centro_elegido, letra_overlay). '-' blanco, 'X' doble.
    """
    if len(feats) < 2:
        return "-", feats[0][2] if feats else (0, 0), ""

    raws = np.array([_fget(f[1], "raw", 255.0) for f in feats], dtype=np.float32)
    inks = np.array([_fget(f[1], "ink", 0.0) for f in feats], dtype=np.float32)
    darks = np.array([_fget(f[1], "dark_frac", 0.0) for f in feats], dtype=np.float32)
    p20s = np.array([_fget(f[1], "p20", 255.0) for f in feats], dtype=np.float32)
    d160s = np.array([_fget(f[1], "dark160", float(darks[i])) for i, f in enumerate(feats)], dtype=np.float32)
    d175s = np.array([_fget(f[1], "dark175", float(d160s[i])) for i, f in enumerate(feats)], dtype=np.float32)
    softs = np.array([_fget(f[1], "ink_soft", float(inks[i])) for i, f in enumerate(feats)], dtype=np.float32)
    clahes = np.array([_fget(f[1], "clahe_dark", float(darks[i])) for i, f in enumerate(feats)], dtype=np.float32)
    cores = np.array([_fget(f[1], "core_raw", float(raws[i])) for i, f in enumerate(feats)], dtype=np.float32)

    med_raw = float(np.median(raws))
    med_ink = float(np.median(inks))
    med_dark = float(np.median(darks))
    med_d160 = float(np.median(d160s))
    med_soft = float(np.median(softs))
    med_clahe = float(np.median(clahes))
    med_core = float(np.median(cores))
    med_p20 = float(np.median(p20s))

    marked = []
    for i, (letter, f, center) in enumerate(feats):
        raw = float(raws[i])
        ink = float(inks[i])
        dark = float(darks[i])
        p20 = float(p20s[i])
        d160 = float(d160s[i])
        d175 = float(d175s[i])
        ink_soft = float(softs[i])
        clahe_d = float(clahes[i])
        core = float(cores[i])

        gap_raw = med_raw - raw
        gap_ink = ink - med_ink
        gap_dark = dark - med_dark
        gap_d160 = d160 - med_d160
        gap_soft = ink_soft - med_soft
        gap_clahe = clahe_d - med_clahe
        gap_core = med_core - core
        gap_p20 = med_p20 - p20

        # R1: relleno negro absoluto (sigue valiendo si 2–3 hermanas también).
        r1 = (
            raw < 152.0
            or core < 148.0
            or dark >= 0.24
            or d160 >= 0.32
        )
        # R2: raya / pintado parcial (un poco más permisivo que el legado).
        r2 = (
            (dark >= 0.10 and p20 < 162.0 and raw < 180.0)
            or (d160 >= 0.16 and p20 < 166.0 and raw < 184.0)
            or (d175 >= 0.22 and p20 < 168.0 and gap_p20 >= 8.0)
        )
        # R3: destaca frente a las hermanas (iluminación de la fila).
        r3 = (
            (gap_raw >= 12.0 and raw < 186.0)
            or (gap_core >= 10.0 and core < 188.0)
            or (gap_dark >= 0.055 and dark >= 0.07 and p20 < 170.0)
            or (gap_d160 >= 0.07 and d160 >= 0.10)
        )
        # R4: canales de tinta en paralelo — el lápiz claro baja poco el raw
        # pero dispara adaptive/soft. NO umbral absoluto de ink (letra B).
        r4 = (
            (gap_ink >= 12.0 and ink >= 34.0 and raw < 188.0 and p20 < 172.0)
            or (gap_soft >= 14.0 and ink_soft >= 40.0 and raw < 188.0)
            or (gap_clahe >= 0.08 and clahe_d >= 0.12)
        )

        votes = (2 if r1 else 0) + (1 if r2 else 0) + (1 if r3 else 0) + (1 if r4 else 0)
        # Papel casi blanco, sin tinta en ningún canal.
        if raw > 198.0 and d175 < 0.06 and ink < 28.0:
            votes = 0
        # Letra impresa sola: sin gap relativo y sin relleno fuerte.
        if (
            votes
            and not r1
            and gap_ink < 8.0
            and gap_raw < 8.0
            and gap_dark < 0.04
            and gap_soft < 10.0
            and raw > 170.0
        ):
            votes = 0

        is_mark = votes >= 2 or (votes == 1 and r1)
        # Un único detector relativo/tinta, pero claramente el más oscuro.
        if not is_mark and votes == 1 and (r3 or r4):
            if gap_ink >= 18.0 or gap_raw >= 16.0 or gap_d160 >= 0.12:
                is_mark = True

        if is_mark:
            strength = (
                dark * 90.0
                + d160 * 35.0
                + max(0.0, gap_raw)
                + max(0.0, gap_core) * 0.6
                + max(0.0, 180.0 - raw) * 0.4
                + max(0.0, gap_ink) * 0.55
                + max(0.0, gap_soft) * 0.25
                + max(0.0, 155.0 - p20) * 0.25
                + float(votes) * 4.0
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
