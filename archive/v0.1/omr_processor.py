# Pre-load torch DLLs BEFORE cv2/onnxruntime to avoid WinError 1114 DLL conflicts
try:
    import torch
    _TORCH_PRELOADED = True
except (ImportError, OSError):
    _TORCH_PRELOADED = False

import cv2
import numpy as np
import pandas as pd
import os
import json
import urllib.request

WINOCR_AVAILABLE = False
try:
    import winocr
    WINOCR_AVAILABLE = True
    print("[OCR] Windows UWP OCR (winocr) loaded.")
except ImportError:
    print("[OCR] winocr not installed.")

EASYOCR_AVAILABLE = None  # None = not yet checked, True/False = checked
PADDLEOCR_AVAILABLE = None  # Lazy-loaded to avoid DLL conflicts with onnxruntime

# Global flag and model path
MODEL_PATH = "mnist.onnx"
MODEL_AVAILABLE = False
net = None

def download_mnist_model():
    """
    Downloads a tiny MNIST digit classifier in ONNX format if not already present.
    """
    global MODEL_AVAILABLE, net
    if os.path.exists(MODEL_PATH):
        try:
            net = cv2.dnn.readNetFromONNX(MODEL_PATH)
            MODEL_AVAILABLE = True
            print("MNIST ONNX model loaded successfully.")
            return
        except Exception as e:
            print(f"Error loading local model: {e}")
            
    url = "https://github.com/onnx/models/raw/main/validated/vision/classification/mnist/model/mnist-8.onnx"
    try:
        print(f"Downloading MNIST ONNX model from {url}...")
        urllib.request.urlretrieve(url, MODEL_PATH)
        net = cv2.dnn.readNetFromONNX(MODEL_PATH)
        MODEL_AVAILABLE = True
        print("MNIST ONNX model downloaded and loaded successfully.")
    except Exception as e:
        print(f"Could not download MNIST model: {e}. Running in Manual Confirmation mode.")
        MODEL_AVAILABLE = False

# Run model check
download_mnist_model()

def align_coordinate(thresh, x_nom, y_nom, window=20):
    """
    Refines a nominal coordinate by searching for the center of the nearest contour
    in a small window. This handles printing shifts.
    """
    h, w = thresh.shape
    x1 = max(0, x_nom - window)
    x2 = min(w, x_nom + window)
    y1 = max(0, y_nom - window)
    y2 = min(h, y_nom + window)
    
    sub = thresh[y1:y2, x1:x2]
    contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_center = (x_nom, y_nom)
    best_dist = float('inf')
    
    for c in contours:
        area = cv2.contourArea(c)
        if 80 < area < 1000:
            M = cv2.moments(c)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"]) + x1
                cy = int(M["m01"] / M["m00"]) + y1
                dist = (cx - x_nom)**2 + (cy - y_nom)**2
                if dist < best_dist:
                    best_dist = dist
                    best_center = (cx, cy)
    return best_center

def get_bubble_density(thresh, center, radius=9):
    """
    Calculates the mean pixel density inside a circle of a given radius.
    """
    mask = np.zeros(thresh.shape, dtype="uint8")
    cv2.circle(mask, center, radius, 255, -1)
    mean_val = cv2.mean(thresh, mask=mask)[0]
    return mean_val

def preprocess_digit(crop):
    """
    Preprocesses a handwritten digit crop for the MNIST model:
    - Removes box borders by cropping 4px inside.
    - Extracts non-zero pixels (the digit).
    - Resizes to fit in 20x20 maintaining aspect ratio.
    - Centers in a 28x28 black canvas.
    """
    # Crop inside borders to avoid printed outlines
    h_c, w_c = crop.shape
    if h_c > 8 and w_c > 8:
        crop_inner = crop[4:h_c-4, 4:w_c-4]
    else:
        crop_inner = crop.copy()
        
    coords = cv2.findNonZero(crop_inner)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        # Extract only the digit region
        digit = crop_inner[y:y+h, x:x+w]
        
        # Resize to max 20px
        if w > h:
            r = 20.0 / w
            dim = (20, int(h * r))
        else:
            r = 20.0 / h
            dim = (int(w * r), 20)
            
        if dim[0] > 0 and dim[1] > 0:
            resized = cv2.resize(digit, dim, interpolation=cv2.INTER_AREA)
            # Center on 28x28 black canvas
            mnist_img = np.zeros((28, 28), dtype="uint8")
            dx = (28 - dim[0]) // 2
            dy = (28 - dim[1]) // 2
            mnist_img[dy:dy+dim[1], dx:dx+dim[0]] = resized
            return mnist_img
            
    return cv2.resize(crop_inner, (28, 28), interpolation=cv2.INTER_AREA)

def classify_digit(crop_gray):
    """
    Predicts a single digit 0-9 from a grayscale crop using the MNIST net.
    """
    global MODEL_AVAILABLE, net
    if not MODEL_AVAILABLE or net is None:
        return ""
        
    try:
        # Preprocess
        mnist_img = preprocess_digit(crop_gray)
        # Feed into DNN
        blob = cv2.dnn.blobFromImage(mnist_img, 1.0/255.0, (28, 28))
        net.setInput(blob)
        preds = net.forward()
        return str(np.argmax(preds[0]))
    except Exception as e:
        print(f"Error classifying digit: {e}")
        return ""

from omr_align import (  # noqa: E402
    imread_bgr,
    detect_corners,
    warp_image,
    warp_sheet_upright,
    detect_omr_grid as detect_omr_grid_align,
    expected_omr_grid,
    bubble_features,
    read_question_answer,
    build_question_coords,
)

def load_template_config():
    """
    Loads coordinate positions from template_config.json.
    """
    config_path = "template_config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    # Default fallback if file is missing
    return {
        "ocr_fields": {
            "numero_orden": [
                {"x": 160, "y": 330, "w": 34, "h": 34},
                {"x": 200, "y": 330, "w": 34, "h": 34}
            ],
            "orden_entrega": [
                {"x": 160, "y": 410, "w": 34, "h": 34},
                {"x": 200, "y": 410, "w": 34, "h": 34}
            ],
            "hora_entrega": [
                {"x": 117, "y": 490, "w": 34, "h": 34},
                {"x": 156, "y": 490, "w": 34, "h": 34},
                {"x": 200, "y": 490, "w": 34, "h": 34},
                {"x": 239, "y": 490, "w": 34, "h": 34}
            ]
        },
        "omr_questions": {
            "y_start": 268,
            "y_step": 33,
            "x_coords": [442, 483, 524, 564, 605],
            "options": ["A", "B", "C", "D", "E"]
        }
    }

import re
import hashlib
import unicodedata

def normalize_key_id(text):
    """
    Normaliza salón/curso para matching robusto:
    - minúsculas, sin acentos, colapsa espacios
    - 'Salón 1' / 'Salon1' / 'salon  1' → 'salon 1'
    - 'Matemática' / 'Matematica' → 'matematica'
    """
    if text is None:
        return ""
    s = str(text).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 'salon1' -> 'salon 1'
    s = re.sub(r"^(salon)(\d+)$", r"\1 \2", s)
    return s

def load_settings_num_questions(default=15):
    """Lee num_questions desde settings_config.json si existe."""
    try:
        if os.path.exists("settings_config.json"):
            with open("settings_config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return int(cfg.get("num_questions", default))
    except Exception:
        pass
    return default

def load_settings_num_alternatives(default=4):
    try:
        if os.path.exists("settings_config.json"):
            with open("settings_config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return int(cfg.get("num_alternatives", default))
    except Exception:
        pass
    return default

def key_fingerprint(keys):
    """
    Huella corta y estable de la clave (para trakear qué clave se usó al calificar).
    Ejemplo: 'CDEA...|15q' → md5 corto.
    """
    payload = "|".join(str(k).upper().strip() for k in keys)
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()[:10]
    return f"{digest}:{len(keys)}q"

def extract_keys_from_row(row, num_questions=None):
    """Extrae Q1..Qn de una fila de Excel de forma ordenada y limpia."""
    if num_questions is None:
        num_questions = load_settings_num_questions(15)
    keys = []
    for i in range(1, num_questions + 1):
        col = f"Q{i}"
        if col not in row.index:
            # intentar variantes
            found = None
            for c in row.index:
                if str(c).strip().upper() == col:
                    found = c
                    break
            if found is None:
                raise ValueError(f"Falta columna {col} en la hoja Claves.")
            col = found
        val = str(row[col]).upper().strip()
        if val in ("NAN", "NONE", ""):
            val = "-"
        keys.append(val)
    return keys

def validate_answer_key(keys, num_alternatives=None):
    """
    Valida una clave: letras válidas, sin vacíos, longitud correcta.
    Devuelve (ok: bool, warnings: list[str]).
    """
    if num_alternatives is None:
        num_alternatives = load_settings_num_alternatives(4)
    valid_letters = set(list("ABCDE")[:num_alternatives])
    warnings = []
    if not keys:
        return False, ["Clave vacía."]
    for i, k in enumerate(keys, start=1):
        if k in ("-", "", "NAN"):
            warnings.append(f"Q{i} sin respuesta definida.")
        elif k not in valid_letters:
            warnings.append(
                f"Q{i}='{k}' no es válida para {num_alternatives} alternativas "
                f"(permitidas: {', '.join(sorted(valid_letters))})."
            )
    ok = len([w for w in warnings if "no es válida" in w]) == 0
    return ok, warnings

def get_student_name(config_path, salon, student_id):
    """
    Looks up student name by ID and salon in the Excel file.
    """
    if not os.path.exists(config_path):
        return f"Estudiante ID {student_id}"
    try:
        df = pd.read_excel(config_path, sheet_name="Alumnos")
        df['ID_Estudiante'] = df['ID_Estudiante'].astype(str).str.zfill(2)
        df['Salon'] = df['Salon'].astype(str)
        df['_salon_norm'] = df['Salon'].map(normalize_key_id)
        salon_n = normalize_key_id(salon)
        
        match = df[(df['ID_Estudiante'] == str(student_id).zfill(2)) & (df['_salon_norm'] == salon_n)]
        if not match.empty:
            return match.iloc[0]['Nombre']
    except Exception as e:
        print(f"Error reading students from Excel: {e}")
    return f"Desconocido (Nº {student_id})"

def get_answer_key(config_path, salon, curso, num_questions=None):
    """
    Lee la clave correcta para salón+curso.
    Matching normalizado (acentos/espacios/mayúsculas).
    Devuelve lista de letras Q1..Qn.
    """
    meta = get_answer_key_meta(config_path, salon, curso, num_questions=num_questions)
    return meta["keys"]

def get_answer_key_meta(config_path, salon, curso, num_questions=None):
    """
    Igual que get_answer_key pero con metadatos de trakeo:
    keys, fingerprint, salon/curso resueltos, warnings de validación.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No se encontró el archivo de configuración en: {config_path}")

    if num_questions is None:
        num_questions = load_settings_num_questions(15)

    salon = canonicalize_salon(salon)

    df = pd.read_excel(config_path, sheet_name="Claves")
    df['Salon'] = df['Salon'].astype(str).map(canonicalize_salon)
    df['Curso'] = df['Curso'].astype(str)
    df['_salon_norm'] = df['Salon'].map(normalize_key_id)
    df['_curso_norm'] = df['Curso'].map(normalize_key_id)

    salon_n = normalize_key_id(salon)
    curso_n = normalize_key_id(curso)

    match = df[(df['_salon_norm'] == salon_n) & (df['_curso_norm'] == curso_n)]
    if match.empty:
        # ayuda: listar claves disponibles
        available = sorted({
            f"{r['Salon']} / {r['Curso']}"
            for _, r in df.iterrows()
        })
        raise ValueError(
            f"No se encontró la clave para el salón '{salon}' y curso '{curso}'. "
            f"Disponibles: {', '.join(available[:12])}"
            + ("..." if len(available) > 12 else "")
        )

    row = match.iloc[0]
    keys = extract_keys_from_row(row, num_questions=num_questions)
    ok, warnings = validate_answer_key(keys)
    fp = key_fingerprint(keys)

    return {
        "keys": keys,
        "fingerprint": fp,
        "salon_resolved": str(row["Salon"]),
        "curso_resolved": str(row["Curso"]),
        "num_questions": len(keys),
        "valid": ok,
        "warnings": warnings,
        "key_id": f"{normalize_key_id(row['Salon'])}|{normalize_key_id(row['Curso'])}|{fp}"
    }

def list_all_keys_summary(config_path):
    """Resumen de todas las claves para el panel de trakeo."""
    if not os.path.exists(config_path):
        return []
    df = pd.read_excel(config_path, sheet_name="Claves")
    num_q = load_settings_num_questions(15)
    summaries = []
    for _, row in df.iterrows():
        try:
            keys = extract_keys_from_row(row, num_questions=num_q)
            ok, warnings = validate_answer_key(keys)
            summaries.append({
                "Salon": str(row.get("Salon", "")),
                "Curso": str(row.get("Curso", "")),
                "keys": keys,
                "fingerprint": key_fingerprint(keys),
                "valid": ok,
                "warnings": warnings,
                "preview": " ".join(f"{i+1}:{k}" for i, k in enumerate(keys[:8])) +
                           (" ..." if len(keys) > 8 else "")
            })
        except Exception as e:
            summaries.append({
                "Salon": str(row.get("Salon", "")),
                "Curso": str(row.get("Curso", "")),
                "keys": [],
                "fingerprint": "",
                "valid": False,
                "warnings": [str(e)],
                "preview": ""
            })
    return summaries

_paddle_ocr_engine = None
_easyocr_reader = None

def get_paddleocr_engine():
    global _paddle_ocr_engine, PADDLEOCR_AVAILABLE
    # Lazy import check
    if PADDLEOCR_AVAILABLE is None:
        try:
            from paddleocr import PaddleOCR as _PaddleOCR
            PADDLEOCR_AVAILABLE = True
            print("[OCR] PaddleOCR module found.")
        except ImportError:
            PADDLEOCR_AVAILABLE = False
            print("[OCR] PaddleOCR not installed (expected on Python 3.14+).")
    if not PADDLEOCR_AVAILABLE:
        return None
    if _paddle_ocr_engine is None:
        try:
            from paddleocr import PaddleOCR as _PaddleOCR
            _paddle_ocr_engine = _PaddleOCR(use_angle_cls=True, lang="es", show_log=False)
            print("[OCR] PaddleOCR engine initialized.")
        except Exception as e:
            print(f"[OCR] PaddleOCR init error: {e}")
            PADDLEOCR_AVAILABLE = False
    return _paddle_ocr_engine

def get_easyocr_reader():
    global _easyocr_reader, EASYOCR_AVAILABLE
    # Lazy import check — avoids DLL conflict with onnxruntime at load time
    if EASYOCR_AVAILABLE is None:
        try:
            import easyocr as _easyocr_mod
            EASYOCR_AVAILABLE = True
            print("[OCR] EasyOCR module found.")
        except (ImportError, OSError) as e:
            EASYOCR_AVAILABLE = False
            print(f"[OCR] EasyOCR not available: {e}")
    if not EASYOCR_AVAILABLE:
        return None
    if _easyocr_reader is None:
        try:
            import easyocr as _easyocr_mod
            _easyocr_reader = _easyocr_mod.Reader(['es', 'en'], gpu=False, verbose=False)
            print("[OCR] EasyOCR reader initialized (es+en, CPU).")
        except Exception as e:
            print(f"[OCR] EasyOCR init error: {e}")
            EASYOCR_AVAILABLE = False
    return _easyocr_reader

def preprocess_header_for_ocr(header_crop):
    """
    Preprocesado clásico (CLAHE + dilate) — se usa como una de varias variantes.
    """
    if len(header_crop.shape) == 3:
        gray = cv2.cvtColor(header_crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = header_crop.copy()
    upscaled = cv2.resize(gray, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(upscaled)
    inverted = cv2.bitwise_not(enhanced)
    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(inverted, kernel, iterations=1)
    result = cv2.bitwise_not(dilated)
    normalized = cv2.normalize(result, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
    return normalized

def _to_bgr(img):
    if img is None:
        return img
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img

def build_ocr_variants(crop, scale=3.0):
    """
    Genera variantes de preprocesado. Empíricamente:
    - raw / up3: mejor para texto a lápiz en cabecera
    - raw footer: excelente para dígitos de orden/hora
    """
    variants = []
    if crop is None or crop.size == 0:
        return variants
    variants.append(("raw", crop.copy()))
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop.copy()
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    variants.append(("up3", up))
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(up)
    variants.append(("clahe", clahe))
    blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
    sharp = cv2.addWeighted(clahe, 1.8, blur, -0.8, 0)
    variants.append(("sharp", sharp))
    return variants

# Etiquetas impresas de la ficha → campo destino
_LABEL_FIELD_PATTERNS = [
    (r"apellid|nombres?", "nombre"),
    (r"colegi[oa]", "colegio"),
    (r"procedenc", "procedencia"),
    (r"grado", "grado"),
    (r"n[°ºo]?\s*orden|orden", "numero_orden"),
    (r"hora", "hora_entrega"),
]

_LABEL_NOISE_RE = re.compile(
    r"apellid|nombres?|colegi|procedenc|grado|orden|hora|buenas|malas|blanco|n[°ºo]|puntaje|pts\b|\(\+|\(-\d",
    re.IGNORECASE
)

def _is_label_token(text):
    t = (text or "").strip().lower()
    if not t:
        return True
    if _LABEL_NOISE_RE.search(t) and len(t) <= 24:
        return True
    # tokens casi solo de puntuación
    if re.fullmatch(r"[:|/\-.,;_'\"`~]+", t):
        return True
    return False

def _match_label_field(text):
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    for pattern, field in _LABEL_FIELD_PATTERNS:
        if re.search(pattern, t):
            return field
    return None

def clean_ocr_text(text, field_name=""):
    """Limpieza / correcciones típicas de OCR sobre lápiz."""
    if not text:
        return ""
    s = str(text).strip()
    s = s.replace("|", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip(" :.-")
    # basura del panel de puntaje superpuesto
    s = re.sub(r"(?i)\b(buenas|malas|blancos?|puntaje|pts)\b[^ ]*", " ", s)
    s = re.sub(r"\(\+\d+\)|\(-\d+\)", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" :.-")
    # quitar restos de etiquetas pegadas
    s = re.sub(
        r"(?i)\b(apellidos?\s*y\s*nombres?|colegio|procedencia|grado|n[°ºo]?\s*orden|hora)\b\s*:?",
        "",
        s
    ).strip(" :.-")

    # En contexto alfabético, 1→I / 0→O (MAR1SCAL → MARISCAL)
    if field_name in ("nombre", "colegio", "procedencia"):
        def _fix_digit_letter(m):
            ch = m.group(0)
            return {"0": "O", "1": "I", "5": "S", "8": "B"}.get(ch, ch)
        s = re.sub(r"(?<=[A-Za-zÁÉÍÓÚÑáéíóúñ])[0158](?=[A-Za-zÁÉÍÓÚÑáéíóúñ])", _fix_digit_letter, s)
        s = re.sub(r"(?<=[A-Za-zÁÉÍÓÚÑáéíóúñ])[0158]\b", _fix_digit_letter, s)

    if field_name == "grado":
        s = s.upper().replace("0", "O").replace(" ", "")
        s = re.sub(r"[^A-Z0-9°º]", "", s)
        m = re.search(r"([1-6])(RO|DO|TO|NO|ERO|TO|°|º)?", s)
        if m:
            s = m.group(0)

    if field_name == "colegio":
        # quitar restos de OCR de etiqueta
        s = re.sub(r"(?i)^\s*col[eé]gio\s*:?\s*", "", s).strip()
        s = re.sub(r"(?i)^\s*colcglo\s*:?\s*", "", s).strip()

    if field_name == "procedencia":
        s = re.sub(r"(?i)^\s*procedencia\s*:?\s*", "", s).strip()
        # capitalizar razonable
        if s and s.isupper() or (s and s.lower() == s):
            s = s.title() if len(s) > 3 else s.upper()
        # 1→I / 0→O ya aplicado; arreglar finales tipo AYACUCHo
        if re.search(r"[a-z]$", s) and s[:-1].isupper():
            s = s.upper()

    if field_name == "nombre":
        s = re.sub(r"(?i)^\s*apellidos?\s*(y\s*)?nombres?\s*:?\s*", "", s).strip()
        # si el OCR metió el colegio al inicio, cortar palabras en mayúsculas raras sueltas
        s = re.sub(r"[@#$%&*]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()

    if field_name in ("numero_orden", "orden_entrega"):
        digits = re.sub(r"\D", "", s)
        s = digits.lstrip("0") or digits  # conserva "0" si todo es cero
        if len(s) > 3:
            s = s[:3]

    if field_name == "hora_entrega":
        s = s.replace(".", ":").replace(";", ":").replace(",", ":")
        s = re.sub(r"[^\d:]", "", s)
        m = re.search(r"(\d{1,2}):?(\d{2})", s)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                s = f"{hh:02d}:{mm:02d}"
            else:
                s = ""  # hora imposible → vacío (el usuario corrige)
        else:
            digits = re.sub(r"\D", "", s)
            if len(digits) == 3:
                s = f"0{digits[0]}:{digits[1:]}"
            elif len(digits) == 4:
                s = f"{digits[:2]}:{digits[2:]}"
            else:
                s = ""

    return s.strip()

def _score_field_candidate(text, conf, field_name):
    """Puntúa candidatos OCR: prioriza confianza, longitud útil y caracteres limpios."""
    if not text:
        return -1.0
    t = text.strip()
    if _is_label_token(t):
        return -1.0
    # penalizar basura
    alnum = sum(ch.isalnum() for ch in t)
    if alnum == 0:
        return -1.0
    ratio = alnum / max(len(t), 1)
    length_bonus = min(len(t), 24) * 0.02
    conf_f = float(conf) if conf is not None else 0.2
    score = conf_f * 2.0 + length_bonus + ratio
    if field_name in ("numero_orden", "hora_entrega") and re.search(r"\d", t):
        score += 0.5
    if field_name == "hora_entrega" and ":" in t:
        score += 0.4
    return score

def _run_easyocr_words(reader, image_bgr, allowlist=None, min_conf=0.08):
    """Ejecuta EasyOCR y devuelve lista de dicts {text, conf, cx, cy, x1, y1, x2, y2}."""
    words = []
    if reader is None or image_bgr is None or image_bgr.size == 0:
        return words
    kwargs = {"detail": 1, "paragraph": False}
    if allowlist:
        kwargs["allowlist"] = allowlist
    try:
        ocr_results = reader.readtext(image_bgr, **kwargs)
    except TypeError:
        # easyocr viejo sin allowlist
        ocr_results = reader.readtext(image_bgr, detail=1, paragraph=False)
    except Exception as e:
        print(f"[OCR] EasyOCR readtext error: {e}")
        return words

    for item in ocr_results:
        if not item or len(item) < 3:
            continue
        bbox, text, conf = item[0], item[1], item[2]
        text = (text or "").strip()
        if not text or float(conf) < min_conf:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x1, x2 = float(min(xs)), float(max(xs))
        y1, y2 = float(min(ys)), float(max(ys))
        words.append({
            "text": text,
            "conf": float(conf),
            "cx": (x1 + x2) / 2.0,
            "cy": (y1 + y2) / 2.0,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2
        })
    return words

def _run_winocr_words(image_bgr):
    words = []
    if not WINOCR_AVAILABLE:
        return words
    try:
        if len(image_bgr.shape) == 3:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_bgr
        ocr_res = winocr.recognize_cv2_sync(gray, lang="es-ES")
        for line in ocr_res.get("lines", []):
            line_text = (line.get("text") or "").strip()
            # prefer word-level if available
            line_words = line.get("words") or []
            if line_words:
                for word in line_words:
                    rect = word.get("bounding_rect", {}) or {}
                    text = (word.get("text") or "").strip()
                    if not text:
                        continue
                    x = float(rect.get("x", 0))
                    y = float(rect.get("y", 0))
                    w = float(rect.get("width", 0))
                    h = float(rect.get("height", 0))
                    words.append({
                        "text": text,
                        "conf": 0.55,
                        "cx": x + w / 2.0,
                        "cy": y + h / 2.0,
                        "x1": x, "y1": y, "x2": x + w, "y2": y + h
                    })
            elif line_text:
                words.append({
                    "text": line_text,
                    "conf": 0.5,
                    "cx": 0, "cy": 0, "x1": 0, "y1": 0, "x2": 0, "y2": 0
                })
    except Exception as e:
        print(f"[OCR] WinOCR error: {e}")
    return words

def assign_fields_by_labels(words, image_width=700):
    """
    Asigna texto manuscrito a campos usando anclas de etiquetas impresas.
    Para cada etiqueta detectada, toma tokens en la misma línea (Y) a la derecha.
    """
    results = {
        "nombre": "",
        "colegio": "",
        "grado": "",
        "procedencia": "",
        "numero_orden": "",
        "hora_entrega": ""
    }
    if not words:
        return results

    labels = []
    content = []
    for w in words:
        field = _match_label_field(w["text"])
        if field:
            labels.append({**w, "field": field})
        elif not _is_label_token(w["text"]):
            content.append(w)

    # Si no hay etiquetas, fallback por filas (Y)
    if not labels:
        content_sorted = sorted(content, key=lambda w: (w["cy"], w["cx"]))
        rows = []
        for w in content_sorted:
            if not rows or abs(w["cy"] - rows[-1][0]["cy"]) > 22:
                rows.append([w])
            else:
                rows[-1].append(w)
        row_fields = ["nombre", "colegio", "procedencia"]
        for idx, row in enumerate(rows[:3]):
            row = sorted(row, key=lambda w: w["cx"])
            results[row_fields[idx]] = " ".join(w["text"] for w in row).strip()
        return results

    # Para cada etiqueta, recolectar contenido a la derecha en la misma línea
    y_tol = 28
    field_candidates = {k: [] for k in results}

    for lab in labels:
        same_line = [
            w for w in content
            if abs(w["cy"] - lab["cy"]) <= y_tol and w["cx"] > lab["x1"] + 8
        ]
        # no cruzar hacia otra etiqueta a la derecha en la misma línea
        right_labels = [
            o for o in labels
            if o is not lab and abs(o["cy"] - lab["cy"]) <= y_tol and o["cx"] > lab["cx"]
        ]
        next_x = min((o["x1"] for o in right_labels), default=image_width + 50)
        same_line = [w for w in same_line if w["cx"] < next_x - 4]
        same_line.sort(key=lambda w: w["cx"])
        if same_line:
            text = " ".join(w["text"] for w in same_line).strip()
            conf = float(np.mean([w["conf"] for w in same_line]))
            field_candidates[lab["field"]].append((text, conf))

    for field, cands in field_candidates.items():
        if not cands:
            continue
        best = max(cands, key=lambda c: _score_field_candidate(c[0], c[1], field))
        if _score_field_candidate(best[0], best[1], field) > 0:
            results[field] = best[0]

    return results

def ocr_region_best(reader, crop, field_name="", allowlist=None, variants_scale=2.5):
    """
    OCR de una ROI: prueba varias variantes y elige el mejor candidato.
    """
    best_text, best_score, best_conf = "", -1.0, 0.0
    if crop is None or crop.size == 0:
        return "", 0.0

    for vname, variant in build_ocr_variants(crop, scale=variants_scale):
        img = _to_bgr(variant)
        words = _run_easyocr_words(reader, img, allowlist=allowlist, min_conf=0.05)
        if not words and WINOCR_AVAILABLE:
            words = _run_winocr_words(img)
        if not words:
            continue
        # filtrar etiquetas
        texts = [w for w in words if not _is_label_token(w["text"])]
        if not texts:
            texts = words
        texts.sort(key=lambda w: w["cx"])
        joined = " ".join(w["text"] for w in texts).strip()
        conf = float(np.mean([w["conf"] for w in texts])) if texts else 0.0
        score = _score_field_candidate(joined, conf, field_name)
        if score > best_score:
            best_score, best_text, best_conf = score, joined, conf

    return clean_ocr_text(best_text, field_name), best_conf

def _looks_like_garbage_field(text, field_name):
    """Detecta basura típica de OCR (etiquetas pegadas, símbolos)."""
    if not text:
        return True
    t = text.strip()
    if _is_label_token(t):
        return True
    # demasiados símbolos no alfanuméricos
    alnum = sum(ch.isalnum() or ch.isspace() for ch in t)
    if alnum / max(len(t), 1) < 0.55:
        return True
    # etiquetas pegadas al valor
    low = t.lower()
    if field_name != "nombre" and re.search(r"apellid|nombres", low):
        return True
    if field_name != "colegio" and re.search(r"colegi", low) and len(t) < 16:
        return True
    if field_name == "grado" and re.search(r"colegi|proced|nombre", low):
        return True
    return False

def parse_ocr_header(warped_img, debug_dir=None):
    """
    Extrae campos manuscritos de la ficha alineada (800x1130):

    Cabecera (layout real de fotos):
      - Apellidos y Nombres
      - Colegio
      - Grado | Procedencia

    Pie:
      - N° Orden | Hora

    Estrategia (rápida y robusta):
      1) 2 variantes de cabecera (raw + up3) con asignación por etiquetas
      2) ROI solo si el campo quedó vacío
      3) Pie en RAW con allowlist de dígitos (mejor para orden/hora)
    """
    results = {
        "nombre": "",
        "colegio": "",
        "grado": "",
        "procedencia": "",
        "numero_orden": "",
        "hora_entrega": "",
        "ocr_engine": "none",
        "ocr_confidence": {}
    }

    reader = None
    if EASYOCR_AVAILABLE is not False:
        reader = get_easyocr_reader()

    if reader is None and not WINOCR_AVAILABLE and PADDLEOCR_AVAILABLE is False:
        print("[OCR] No OCR engine available. Skipping header text extraction.")
        return results

    try:
        H, W = warped_img.shape[:2]
        # ROIs desde template_config.json si existen; si no, defaults empíricos
        layout = load_template_config()
        ocr_cfg = layout.get("ocr_fields", {}) if isinstance(layout, dict) else {}

        def _crop_box(box, defaults):
            b = box if isinstance(box, dict) else {}
            x = int(b.get("x", defaults[0]))
            y = int(b.get("y", defaults[1]))
            w = int(b.get("w", defaults[2]))
            h = int(b.get("h", defaults[3]))
            x2, y2 = min(W, x + w), min(H, y + h)
            x, y = max(0, x), max(0, y)
            return warped_img[y:y2, x:x2]

        header = _crop_box(ocr_cfg.get("header"), (45, 40, 710, 135))
        footer = _crop_box(ocr_cfg.get("footer"), (40, 1020, 320, 95))
        if header is None or header.size == 0:
            header = warped_img[40:min(175, H), 45:min(755, W)]
        if footer is None or footer.size == 0:
            footer = warped_img[max(0, 1020):min(H - 5, 1115), 40:min(360, W)]

        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, "ocr_header.jpg"), header)
            cv2.imwrite(os.path.join(debug_dir, "ocr_footer.jpg"), footer)

        engines = []
        field_best = {
            "nombre": ("", -1.0, 0.0),
            "colegio": ("", -1.0, 0.0),
            "grado": ("", -1.0, 0.0),
            "procedencia": ("", -1.0, 0.0),
            "numero_orden": ("", -1.0, 0.0),
            "hora_entrega": ("", -1.0, 0.0),
        }

        # --- 1) Cabecera: raw + up3 (las más útiles en pruebas reales) ---
        header_variants = [("raw", header, 1.0)]
        gray = cv2.cvtColor(header, cv2.COLOR_BGR2GRAY)
        up3 = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        header_variants.append(("up3", up3, 3.0))
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(up3)
        header_variants.append(("clahe", clahe, 3.0))

        for vname, variant, scale in header_variants:
            img = _to_bgr(variant)
            words = _run_easyocr_words(reader, img, min_conf=0.12) if reader else []
            if not words:
                words = _run_winocr_words(img)
                if words:
                    engines.append(f"WinOCR/{vname}")
            else:
                engines.append(f"EasyOCR/{vname}")

            for w in words:
                w["cx"] /= scale
                w["cy"] /= scale
                w["x1"] /= scale
                w["x2"] /= scale
                w["y1"] /= scale
                w["y2"] /= scale

            assigned = assign_fields_by_labels(words, image_width=header.shape[1])
            for field, text in assigned.items():
                cleaned = clean_ocr_text(text, field)
                if _looks_like_garbage_field(cleaned, field):
                    continue
                # conf del contenido de esa línea (no global)
                content = [w for w in words if not _is_label_token(w["text"]) and not _match_label_field(w["text"])]
                conf = float(np.mean([w["conf"] for w in content])) if content else 0.35
                score = _score_field_candidate(cleaned, conf, field)
                if score > field_best[field][1]:
                    field_best[field] = (cleaned, score, conf)

        for field, (text, score, conf) in field_best.items():
            if text and score > 0:
                results[field] = text
                results["ocr_confidence"][field] = round(float(conf), 2)

        # --- 2) ROI solo para campos vacíos o basura ---
        hh, hw = header.shape[:2]
        rois = {
            # recortes a la DERECHA de las etiquetas impresas
            "nombre": header[2:int(hh * 0.38), int(hw * 0.28):],
            "colegio": header[int(hh * 0.30):int(hh * 0.58), int(hw * 0.16):],
            "grado": header[int(hh * 0.55):, int(hw * 0.10):int(hw * 0.40)],
            "procedencia": header[int(hh * 0.55):, int(hw * 0.52):],
        }
        for field, roi in rois.items():
            if debug_dir:
                cv2.imwrite(os.path.join(debug_dir, f"roi_{field}.png"), roi)
            need = (not results[field]) or _looks_like_garbage_field(results[field], field)
            if not need:
                continue
            # Solo raw+upscale ligero del ROI (más limpio y rápido)
            text, conf = "", 0.0
            for scale in (1.0, 2.5):
                crop = roi if scale == 1.0 else cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                words = _run_easyocr_words(reader, _to_bgr(crop), min_conf=0.15) if reader else []
                words = [w for w in words if not _is_label_token(w["text"]) and not _match_label_field(w["text"])]
                if not words:
                    continue
                words.sort(key=lambda w: w["cx"])
                joined = " ".join(w["text"] for w in words).strip()
                cleaned = clean_ocr_text(joined, field)
                if _looks_like_garbage_field(cleaned, field):
                    continue
                c = float(np.mean([w["conf"] for w in words]))
                if c >= conf:
                    text, conf = cleaned, c
            if text:
                results[field] = text
                results["ocr_confidence"][field] = round(conf, 2)

        # --- 3) Pie: RAW first (probado: orden=2, hora=10:25) ---
        if footer is not None and footer.size > 0:
            footer_words = []
            for scale, name in ((1.0, "raw"), (2.0, "up2")):
                crop = footer if scale == 1.0 else cv2.resize(footer, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                words = _run_easyocr_words(
                    reader, _to_bgr(crop),
                    allowlist="0123456789:",
                    min_conf=0.2
                ) if reader else []
                if not words:
                    words = _run_winocr_words(_to_bgr(crop))
                for w in words:
                    w = dict(w)
                    w["cx"] /= scale
                    w["x1"] /= scale
                    w["x2"] /= scale
                    footer_words.append(w)
                if words and name == "raw":
                    engines.append("EasyOCR/footer-raw")
                    break

            # Separar por posición X: izquierda = orden, derecha = hora
            if footer_words:
                footer_words.sort(key=lambda w: w["cx"])
                fw = max(footer.shape[1], 1)
                orden_cands, hora_cands = [], []
                for w in footer_words:
                    t = re.sub(r"\s+", "", w["text"])
                    if not t:
                        continue
                    if ":" in t:
                        hora_cands.append(w)
                    elif re.fullmatch(r"\d{3,4}", t):
                        # 1025 → hora
                        hora_cands.append(w)
                    elif re.fullmatch(r"\d{1,2}", t) and w["cx"] < fw * 0.50:
                        orden_cands.append(w)
                    elif w["cx"] >= fw * 0.40:
                        hora_cands.append(w)
                    else:
                        orden_cands.append(w)

                if orden_cands:
                    best_o = max(orden_cands, key=lambda w: w["conf"])
                    results["numero_orden"] = clean_ocr_text(best_o["text"], "numero_orden")
                    results["ocr_confidence"]["numero_orden"] = round(best_o["conf"], 2)
                if hora_cands:
                    best_h = max(
                        hora_cands,
                        key=lambda w: w["conf"] + (0.35 if ":" in w["text"] else 0)
                    )
                    hora_clean = clean_ocr_text(best_h["text"], "hora_entrega")
                    # rechazar horas imposibles (ej. 70:57)
                    hm = re.match(r"^(\d{1,2}):(\d{2})$", hora_clean)
                    if hm and 0 <= int(hm.group(1)) <= 23 and 0 <= int(hm.group(2)) <= 59:
                        results["hora_entrega"] = hora_clean
                        results["ocr_confidence"]["hora_entrega"] = round(best_h["conf"], 2)
                    elif not results["hora_entrega"]:
                        # guardar crudo solo si no hay nada mejor
                        results["hora_entrega"] = hora_clean
                        results["ocr_confidence"]["hora_entrega"] = round(best_h["conf"] * 0.5, 2)

            # ROI de respaldo pie
            if not results["numero_orden"]:
                orden_roi = footer[:, :int(footer.shape[1] * 0.42)]
                words = _run_easyocr_words(reader, _to_bgr(orden_roi), allowlist="0123456789", min_conf=0.2) if reader else []
                digits = [w for w in words if re.search(r"\d", w["text"])]
                if digits:
                    best = max(digits, key=lambda w: w["conf"])
                    results["numero_orden"] = clean_ocr_text(best["text"], "numero_orden")
                    results["ocr_confidence"]["numero_orden"] = round(best["conf"], 2)
            if not results["hora_entrega"] or not re.match(r"^\d{1,2}:\d{2}$", results["hora_entrega"]):
                hora_roi = footer[:, int(footer.shape[1] * 0.28):]
                words = _run_easyocr_words(reader, _to_bgr(hora_roi), allowlist="0123456789:", min_conf=0.2) if reader else []
                if words:
                    best = max(words, key=lambda w: w["conf"] + (0.3 if ":" in w["text"] else 0))
                    hc = clean_ocr_text(best["text"], "hora_entrega")
                    hm = re.match(r"^(\d{1,2}):(\d{2})$", hc)
                    if hm and 0 <= int(hm.group(1)) <= 23 and 0 <= int(hm.group(2)) <= 59:
                        results["hora_entrega"] = hc
                        results["ocr_confidence"]["hora_entrega"] = round(best["conf"], 2)

        # Limpieza final anti-etiqueta
        for key in ("nombre", "colegio", "grado", "procedencia", "numero_orden", "hora_entrega"):
            results[key] = clean_ocr_text(results[key], key)
            if _looks_like_garbage_field(results[key], key) and key in ("grado",):
                # grado basura → vaciar
                if re.search(r"(?i)colegi|proced|nombre", results[key]):
                    results[key] = re.sub(r"(?i)[^0-9A-Z°º]+", "", results[key].upper())
                    # intentar rescatar patrón 4TO / 5TO / 1RO
                    m = re.search(r"([1-6])\s*(RO|DO|TO|NO|ERO)?", results[key], re.I)
                    results[key] = (m.group(0).upper().replace(" ", "") if m else "")

        results["ocr_engine"] = "+".join(dict.fromkeys(engines)) if engines else "none"
        print(
            f"[OCR] engine={results['ocr_engine']} | "
            f"nombre={results['nombre']!r} colegio={results['colegio']!r} "
            f"grado={results['grado']!r} procedencia={results['procedencia']!r} "
            f"orden={results['numero_orden']!r} hora={results['hora_entrega']!r}"
        )

    except Exception as e:
        import traceback
        print(f"[OCR] Error parsing header: {e}")
        traceback.print_exc()

    return results

def detect_omr_grid(warped_gray, num_questions=15):
    """Grilla OMR sincronizada con la plantilla A5 (sheet_pdf) + snap Hough."""
    return detect_omr_grid_align(warped_gray, num_questions=num_questions)


def _winocr_preprocess_variants(img_bgr):
    """Pocas variantes baratas (CLAHE/OTSU) — cada una ~10-40ms con WinOCR."""
    if img_bgr is None or img_bgr.size == 0:
        return []
    if len(img_bgr.shape) == 3:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_bgr
    up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(up)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [("clahe", clahe), ("otsu", otsu), ("up2", up)]


def _winocr_read(gray_or_bgr):
    if not WINOCR_AVAILABLE:
        return []
    try:
        if len(gray_or_bgr.shape) == 3:
            g = cv2.cvtColor(gray_or_bgr, cv2.COLOR_BGR2GRAY)
        else:
            g = gray_or_bgr
        res = winocr.recognize_cv2_sync(g, lang="es-ES")
        words = []
        for line in res.get("lines", []):
            # prefer words con bbox
            line_words = line.get("words") or []
            if line_words:
                for w in line_words:
                    t = (w.get("text") or "").strip()
                    if not t:
                        continue
                    rect = w.get("bounding_rect", {}) or {}
                    x = float(rect.get("x", 0)); y = float(rect.get("y", 0))
                    ww = float(rect.get("width", 0)); hh = float(rect.get("height", 0))
                    words.append({
                        "text": t, "conf": 0.65,
                        "cx": x + ww / 2, "cy": y + hh / 2,
                        "x1": x, "y1": y, "x2": x + ww, "y2": y + hh
                    })
            else:
                t = (line.get("text") or "").strip()
                if t:
                    words.append({
                        "text": t, "conf": 0.55,
                        "cx": 0, "cy": 0, "x1": 0, "y1": 0, "x2": 0, "y2": 0
                    })
        return words
    except Exception as e:
        print(f"[OCR] WinOCR read err: {e}")
        return []


def parse_ocr_header_fast(warped_img, debug_dir=None):
    """
    OCR RÁPIDO y útil (~0.3–2s):
      1) WinOCR en cabecera completa (CLAHE/OTSU) + asignación por etiquetas
      2) ROIs por campo si faltan datos
      3) Pie para orden/hora si están abajo
      4) UNA sola pasada EasyOCR SOLO si aún faltan nombre y colegio
         (y solo si el reader ya está en memoria, o se fuerza por vacío total)
    """
    results = {
        "nombre": "", "colegio": "", "grado": "", "procedencia": "",
        "numero_orden": "", "hora_entrega": "",
        "ocr_engine": "none", "ocr_confidence": {}
    }
    import time
    global _easyocr_reader
    t0 = time.time()
    engines = []
    try:
        H, W = warped_img.shape[:2]
        layout = load_template_config()
        ocr_cfg = layout.get("ocr_fields", {}) if isinstance(layout, dict) else {}

        def crop_box(key, defaults):
            b = ocr_cfg.get(key, {}) if isinstance(ocr_cfg.get(key), dict) else {}
            x = int(b.get("x", defaults[0])); y = int(b.get("y", defaults[1]))
            w = int(b.get("w", defaults[2])); h = int(b.get("h", defaults[3]))
            return warped_img[max(0, y):min(H, y + h), max(0, x):min(W, x + w)]

        # Diseño nuevo: título arriba; datos manuscritos ~y100–260 (no incluir título)
        header = crop_box("header", (55, 100, 690, 160))
        if header is None or header.size == 0:
            header = warped_img[100:265, 55:745]
        hh, hw = header.shape[:2]

        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, "ocr_header.jpg"), header)

        # --- 1) Cabecera completa con WinOCR (variantes baratas) ---
        best_assigned = {}
        best_score_total = -1
        header_blob = ""
        for vname, variant in _winocr_preprocess_variants(header):
            words = _winocr_read(variant)
            if not words:
                continue
            # coords están en escala 2x → normalizar a header
            for w in words:
                for k in ("cx", "cy", "x1", "x2", "y1", "y2"):
                    w[k] = w[k] / 2.0
            blob = " ".join(w["text"] for w in words)
            if len(blob) > len(header_blob):
                header_blob = blob
            assigned = assign_fields_by_labels(words, image_width=hw)
            score = sum(1 for v in assigned.values() if v and len(v) > 1)
            if score > best_score_total:
                best_score_total = score
                best_assigned = assigned
                engines.append(f"WinOCR/{vname}")

        for field, text in best_assigned.items():
            cleaned = clean_ocr_text(text, field)
            if cleaned and not _looks_like_garbage_field(cleaned, field):
                results[field] = cleaned
                results["ocr_confidence"][field] = 0.65

        # --- 2) ROIs cabecera diseño nuevo (relativo al crop header y≈100–260) ---
        # Fila1 nombre | Fila2 colegio+grado | Fila3 procedencia
        rois = {
            "nombre": header[0:int(hh * 0.38), 0:],
            "colegio": header[int(hh * 0.28):int(hh * 0.68), 0:int(hw * 0.70)],
            "grado": header[int(hh * 0.28):int(hh * 0.68), int(hw * 0.68):],
            "procedencia": header[int(hh * 0.55):, 0:],
        }
        alt_grado = header[int(hh * 0.30):int(hh * 0.70), int(hw * 0.68):]
        alt_proc = header[int(hh * 0.55):, 0:]
        # Orden/hora SOLO del pie
        results["numero_orden"] = ""
        results["hora_entrega"] = ""

        def fill_field_from_roi(field, roi):
            if results.get(field) and not _looks_like_garbage_field(results[field], field):
                return
            best_t, best_c = "", 0.0
            for vname, variant in _winocr_preprocess_variants(roi):
                words = _winocr_read(variant)
                texts = [w["text"] for w in words if not _is_label_token(w["text"]) and not _match_label_field(w["text"])]
                if not texts:
                    continue
                joined = " ".join(texts)
                cleaned = clean_ocr_text(joined, field)
                if cleaned and not _looks_like_garbage_field(cleaned, field):
                    if len(cleaned) >= len(best_t):
                        best_t, best_c = cleaned, 0.7
            if best_t:
                results[field] = best_t
                results["ocr_confidence"][field] = best_c

        for field, roi in rois.items():
            if debug_dir and roi is not None and roi.size:
                cv2.imwrite(os.path.join(debug_dir, f"roi_{field}.png"), roi)
            fill_field_from_roi(field, roi)

        if not results["procedencia"] or _looks_like_garbage_field(results["procedencia"], "procedencia"):
            fill_field_from_roi("procedencia", alt_proc)
        if not results["grado"]:
            fill_field_from_roi("grado", alt_grado)

        # EasyOCR por ROI de cabecera (si está en memoria) — mejora manuscrita
        def _text_quality(s):
            if not s:
                return 0.0
            letters = sum(ch.isalpha() for ch in s)
            bad = sum(ch in "/\\@#$%&*¿¡{}[]<>|" for ch in s)
            return letters - bad * 2 + min(len(s), 20) * 0.1

        # EasyOCR en cabecera SOLO si nombre y colegio están vacíos/basura
        # (cada ROI EasyOCR cuesta ~2–4s; el panel de verificación permite corregir)
        need_header_easy = (
            _easyocr_reader is not None
            and _text_quality(results.get("nombre", "")) < 3
            and _text_quality(results.get("colegio", "")) < 3
        )
        if need_header_easy:
            for field in ("nombre", "colegio", "procedencia"):
                roi = rois.get(field)
                if roi is None or roi.size == 0:
                    continue
                cur = results.get(field, "")
                try:
                    big = cv2.resize(roi, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                    words = _run_easyocr_words(_easyocr_reader, big, min_conf=0.12)
                    words = [w for w in words if not _is_label_token(w["text"]) and not _match_label_field(w["text"])]
                    if not words:
                        continue
                    words.sort(key=lambda w: w["cx"])
                    cleaned = clean_ocr_text(" ".join(w["text"] for w in words), field)
                    if cleaned and _text_quality(cleaned) > _text_quality(cur) + 0.5:
                        results[field] = cleaned
                        results["ocr_confidence"][field] = 0.5
                        engines.append("EasyOCR/header-roi")
                except Exception as e:
                    print(f"[OCR] header ROI EasyOCR err: {e}")

        # --- 3) Pie: Nº Orden + Hora (cajas del diseño nuevo, calibradas testgrok) ---
        orden_box = crop_box("numero_orden_box", (50, 1000, 150, 80))
        hora_box = crop_box("hora_entrega_box", (160, 1000, 200, 80))
        footer = crop_box("footer", (40, 990, 720, 110))
        if debug_dir:
            if orden_box is not None and orden_box.size:
                cv2.imwrite(os.path.join(debug_dir, "roi_orden.png"), orden_box)
            if hora_box is not None and hora_box.size:
                cv2.imwrite(os.path.join(debug_dir, "roi_hora.png"), hora_box)
            if footer is not None and footer.size:
                cv2.imwrite(os.path.join(debug_dir, "ocr_footer.jpg"), footer)

        def _mnist_digits_from_box(box):
            """Segmenta blobs de tinta y clasifica dígitos 0-9 con MNIST (orden L→R)."""
            if not MODEL_AVAILABLE or box is None or box.size == 0:
                return ""
            g = cv2.cvtColor(box, cv2.COLOR_BGR2GRAY) if len(box.shape) == 3 else box.copy()
            # recortar 12% del borde (evita contorno de la caja impresa)
            h, w = g.shape[:2]
            m = max(2, int(min(h, w) * 0.12))
            inner = g[m:h - m, m:w - m]
            if inner.size == 0:
                inner = g
            # realzar lápiz
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(inner)
            _, th = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            # limpiar ruido fino
            th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
            cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            blobs = []
            ih, iw = th.shape[:2]
            for c in cnts:
                x0, y0, bw, bh = cv2.boundingRect(c)
                area = cv2.contourArea(c)
                if area < 30 or bw < 6 or bh < 12:
                    continue
                if bw > iw * 0.85 or bh > ih * 0.95:
                    continue  # borde de caja
                if bh < ih * 0.25:
                    continue
                blobs.append((x0, y0, bw, bh, area))
            blobs.sort(key=lambda b: b[0])
            digits = ""
            for x0, y0, bw, bh, _ in blobs[:5]:
                dig = th[y0:y0 + bh, x0:x0 + bw]
                pad = cv2.copyMakeBorder(dig, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=0)
                d = classify_digit(pad)
                if d:
                    digits += d
            return digits

        def read_footer_box(box, field):
            """OCR de dígitos en cajas del pie (MNIST segmentado + EasyOCR + WinOCR)."""
            if box is None or box.size == 0:
                return ""
            candidates = []

            # 1) MNIST por blobs (mejor para lápiz en cajas)
            mn = _mnist_digits_from_box(box)
            if mn:
                if field == "hora_entrega":
                    # 1025 → 10:25 | 925 → 9:25
                    if len(mn) == 4:
                        candidates.append(f"{mn[:2]}:{mn[2:]}")
                    elif len(mn) == 3:
                        candidates.append(f"0{mn[0]}:{mn[1:]}")
                    elif len(mn) == 2:
                        candidates.append(f"00:{mn}")
                    else:
                        candidates.append(mn)
                else:
                    # orden: preferir 1–2 dígitos; "02"/"03" → sin cero a la izq opcional
                    candidates.append(mn.lstrip("0") or mn)

            # 2) EasyOCR
            if _easyocr_reader is not None:
                for scale in (2.5, 3.0):
                    big = cv2.resize(box, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                    allow = "0123456789" if field == "numero_orden" else "0123456789:"
                    fwords = _run_easyocr_words(_easyocr_reader, big, allowlist=allow, min_conf=0.08)
                    if fwords:
                        fwords.sort(key=lambda w: w["cx"])
                        joined = "".join(w["text"] for w in fwords)
                        t = clean_ocr_text(joined, field)
                        if t:
                            candidates.append(t)

            # 3) WinOCR variantes
            gray = cv2.cvtColor(box, cv2.COLOR_BGR2GRAY) if len(box.shape) == 3 else box.copy()
            up = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(up)
            for v in (clahe, cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]):
                for w in _winocr_read(v):
                    t = clean_ocr_text(w["text"], field)
                    if t:
                        candidates.append(t)

            if not candidates:
                return ""
            if field == "hora_entrega":
                for c in candidates:
                    cc = clean_ocr_text(c, "hora_entrega")
                    if re.match(r"^\d{1,2}:\d{2}$", cc):
                        hh, mm = cc.split(":")
                        if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
                            return f"{int(hh):02d}:{mm}"
                # último recurso: 4 dígitos pegados
                for c in candidates:
                    d = re.sub(r"\D", "", c)
                    if len(d) == 4 and int(d[2:]) <= 59:
                        return f"{d[:2]}:{d[2:]}"
                return ""
            if field == "numero_orden":
                for c in candidates:
                    d = re.sub(r"\D", "", c)
                    if d:
                        return d.lstrip("0") or d
            return candidates[0]

        results["numero_orden"] = read_footer_box(orden_box, "numero_orden") or results["numero_orden"]
        results["hora_entrega"] = read_footer_box(hora_box, "hora_entrega") or results["hora_entrega"]
        if results["numero_orden"] or results["hora_entrega"]:
            engines.append("footer-digits")

        # Respaldo: pie completo izquierda
        if footer is not None and footer.size and (not results["numero_orden"] or not results["hora_entrega"]):
            fw = footer.shape[1]
            left_footer = footer[:, :int(fw * 0.45)]
            if not results["numero_orden"]:
                results["numero_orden"] = read_footer_box(
                    left_footer[:, : left_footer.shape[1] // 2], "numero_orden"
                )
            if not results["hora_entrega"]:
                results["hora_entrega"] = read_footer_box(
                    left_footer[:, left_footer.shape[1] // 2 :], "hora_entrega"
                )

        # --- 4) Regex global sobre texto de cabecera (orden/hora/grado) ---
        # Muy barato y robusto: "N° ORDEN: 3  HORA: 10:21  Grado: 5TO"
        if header_blob:
            m_ord = re.search(r"(?i)(?:n[°ºo.]?\s*orden|orden)\s*:?\s*(\d{1,3})", header_blob)
            if m_ord and not results["numero_orden"]:
                results["numero_orden"] = m_ord.group(1)
                results["ocr_confidence"]["numero_orden"] = 0.8
            m_hora = re.search(r"(?i)(?:hora)\s*:?\s*(\d{1,2}[:.]\d{2})", header_blob)
            if m_hora and not results["hora_entrega"]:
                results["hora_entrega"] = clean_ocr_text(m_hora.group(1), "hora_entrega")
                results["ocr_confidence"]["hora_entrega"] = 0.8
            m_grado = re.search(r"(?i)(?:grado)\s*:?\s*([1-6]\s*(?:ro|do|to|no|ero)?)", header_blob)
            if m_grado and not results["grado"]:
                results["grado"] = clean_ocr_text(m_grado.group(1), "grado")
                results["ocr_confidence"]["grado"] = 0.75
            # también buscar hora suelta tipo 10:21
            if not results["hora_entrega"]:
                m_h2 = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", header_blob)
                if m_h2:
                    results["hora_entrega"] = f"{int(m_h2.group(1)):02d}:{m_h2.group(2)}"
                    results["ocr_confidence"]["hora_entrega"] = 0.7

        # --- 5) EasyOCR SOLO si nombre Y colegio vacíos (evita ~15s de arranque inútil) ---
        # Si el reader ya está en memoria, se puede usar para rellenar huecos.
        # Solo si FALTAN ambos campos críticos; no re-escanear toda la cabecera si ya hay algo.
        need_easy = (not results["nombre"] and not results["colegio"])
        reader = _easyocr_reader
        if need_easy and reader is None:
            # No inicializar EasyOCR en caliente: es la causa de ~10–17s.
            print("[OCR] Skip EasyOCR cold-start (demasiado lento). WinOCR partial results kept.")
        elif need_easy and reader is not None:
            if reader is not None:
                try:
                    words = _run_easyocr_words(reader, header, min_conf=0.12)
                    if words:
                        engines.append("EasyOCR/1pass")
                        assigned = assign_fields_by_labels(words, image_width=hw)
                        for field, text in assigned.items():
                            cleaned = clean_ocr_text(text, field)
                            if not cleaned or _looks_like_garbage_field(cleaned, field):
                                continue
                            # filtrar basura del overlay de puntaje
                            if re.search(r"(?i)puntaje|buenas|malas|blancos|\bpts\b", cleaned):
                                continue
                            cur = results.get(field, "")
                            if (not cur) or _looks_like_garbage_field(cur, field) or len(cleaned) > len(cur) + 2:
                                results[field] = cleaned
                                results["ocr_confidence"][field] = 0.55
                    if (not results["numero_orden"] or not results["hora_entrega"]):
                        footer = crop_box("footer", (40, 1020, 340, 95))
                        if footer is not None and footer.size:
                            fwords = _run_easyocr_words(reader, footer, allowlist="0123456789:", min_conf=0.2)
                            fwords.sort(key=lambda w: w["cx"])
                            fw = footer.shape[1]
                            for w in fwords:
                                t = w["text"].strip()
                                if ":" in t or re.fullmatch(r"\d{3,4}", t):
                                    if not results["hora_entrega"]:
                                        results["hora_entrega"] = clean_ocr_text(t, "hora_entrega")
                                elif re.fullmatch(r"\d{1,2}", t) and w["cx"] < fw * 0.5:
                                    if not results["numero_orden"]:
                                        results["numero_orden"] = clean_ocr_text(t, "numero_orden")
                except Exception as e:
                    print(f"[OCR] EasyOCR 1pass err: {e}")

        # Limpieza final
        for key in ("nombre", "colegio", "grado", "procedencia", "numero_orden", "hora_entrega"):
            results[key] = clean_ocr_text(results[key], key)

        if not engines:
            engines.append("WinOCR-fast" if WINOCR_AVAILABLE else "none")
        results["ocr_engine"] = "+".join(dict.fromkeys(engines))
        dt = time.time() - t0
        print(
            f"[OCR-FAST] {dt*1000:.0f}ms engine={results['ocr_engine']} | "
            f"nombre={results['nombre']!r} colegio={results['colegio']!r} "
            f"proc={results['procedencia']!r} grado={results['grado']!r} "
            f"orden={results['numero_orden']!r} hora={results['hora_entrega']!r}"
        )
    except Exception as e:
        import traceback
        print(f"[OCR-FAST] Error: {e}")
        traceback.print_exc()
    return results


def resize_if_above_megapixels(image, max_megapixels=20.0, target_max_side=2500):
    """
    Solo comprime si la imagen supera max_megapixels (default 20 MPx).
    Por debajo: calidad original intacta (el OMR es rapido).
    Por encima: reduce el lado mayor a target_max_side manteniendo aspecto.
    """
    if image is None:
        return image, {"resized": False, "megapixels": 0.0}
    h, w = image.shape[:2]
    mp = (h * w) / 1_000_000.0
    if mp <= float(max_megapixels):
        return image, {"resized": False, "megapixels": round(mp, 2), "shape": (h, w)}
    m = max(h, w)
    scale = float(target_max_side) / float(m)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    out = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    return out, {
        "resized": True,
        "megapixels": round(mp, 2),
        "shape_in": (h, w),
        "shape_out": (nh, nw),
    }


# Alias por compatibilidad
def resize_image_max(image, max_side=1000):
    # Legacy: no forzar compresion fuerte; solo si > 20 MPx
    return resize_if_above_megapixels(image, max_megapixels=20.0, target_max_side=max(max_side, 2500))[0]


def get_grading_meta():
    """Hora de calificacion + nombre de PC (sistema)."""
    import socket
    from datetime import datetime
    try:
        pc = socket.gethostname()
    except Exception:
        pc = "PC-desconocida"
    now = datetime.now()
    return {
        "graded_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "graded_at_iso": now.isoformat(timespec="seconds"),
        "graded_on_pc": pc,
    }


# Mapeo de salones legacy → nuevos nombres
SALON_DISPLAY_MAP = {
    "Salon 1": "Sec 1", "Salon 2": "Sec 2", "Salon 3": "Sec 3",
    "Salon 4": "Sec 4", "Salon 5": "Sec 5",
    "Salon 6": "Prim 2", "Salon 7": "Prim 3", "Salon 8": "Prim 4",
    "Salon 9": "Prim 5", "Salon 10": "Prim 6",
    # ya nuevos
    "Sec 1": "Sec 1", "Sec 2": "Sec 2", "Sec 3": "Sec 3",
    "Sec 4": "Sec 4", "Sec 5": "Sec 5",
    "Prim 2": "Prim 2", "Prim 3": "Prim 3", "Prim 4": "Prim 4",
    "Prim 5": "Prim 5", "Prim 6": "Prim 6",
}


def canonicalize_salon(salon):
    """Normaliza nombre de seccion/salon al formato actual."""
    s = str(salon or "").strip()
    if s in SALON_DISPLAY_MAP:
        return SALON_DISPLAY_MAP[s]
    # "salon 1" / "SALON 1"
    key = " ".join(s.split())
    for k, v in SALON_DISPLAY_MAP.items():
        if k.lower() == key.lower():
            return v
    return s


def _public_static_url(output_dir, filename):
    """Convierte output_dir local a URL /static/..."""
    norm = os.path.normpath(output_dir).replace("\\", "/")
    # buscar segmento static/ en ruta absoluta o relativa
    lower = norm.lower()
    idx = lower.find("/static/")
    if idx >= 0:
        return norm[idx:] + "/" + filename
    if lower.startswith("static/"):
        return "/" + norm + "/" + filename
    # fallback
    return f"/static/processed/{filename}"


# Tracking visual: BGR, alto contraste (verde / rojo / azul).
COLOR_BIEN = (45, 200, 40)       # verde lima
COLOR_MAL = (40, 40, 245)        # rojo
COLOR_BLANCO = (255, 165, 20)    # azul cielo
COLOR_CLAVE = (40, 170, 255)     # naranja: clave cuando falló
COLOR_HALO = (255, 255, 255)


def _draw_dashed_circle(img, center, radius, color, thickness=2, n_dashes=9):
    cx, cy = int(center[0]), int(center[1])
    for i in range(n_dashes):
        a0 = i * 360.0 / n_dashes
        a1 = a0 + (360.0 / n_dashes) * 0.58
        cv2.ellipse(img, (cx, cy), (radius, radius), 0, a0, a1, color, thickness, cv2.LINE_AA)


def _draw_check(img, center, color, scale=1.0):
    x, y = int(center[0]), int(center[1])
    p1 = (int(x - 7 * scale), int(y + 1 * scale))
    p2 = (int(x - 2 * scale), int(y + 7 * scale))
    p3 = (int(x + 8 * scale), int(y - 7 * scale))
    cv2.line(img, p1, p2, COLOR_HALO, 4, cv2.LINE_AA)
    cv2.line(img, p2, p3, COLOR_HALO, 4, cv2.LINE_AA)
    cv2.line(img, p1, p2, color, 2, cv2.LINE_AA)
    cv2.line(img, p2, p3, color, 2, cv2.LINE_AA)


def _draw_cross(img, center, color, scale=1.0):
    x, y = int(center[0]), int(center[1])
    d = int(7 * scale)
    cv2.line(img, (x - d, y - d), (x + d, y + d), COLOR_HALO, 4, cv2.LINE_AA)
    cv2.line(img, (x - d, y + d), (x + d, y - d), COLOR_HALO, 4, cv2.LINE_AA)
    cv2.line(img, (x - d, y - d), (x + d, y + d), color, 2, cv2.LINE_AA)
    cv2.line(img, (x - d, y + d), (x + d, y - d), color, 2, cv2.LINE_AA)


def _paint_omr_overlays(img, elements):
    """
    Bien   = anillo verde + palomita (lo que marcó el alumno).
    Mal    = anillo rojo + aspa (marca incorrecta o doble).
    Blanco = anillo azul discontinuo sobre la clave no marcada.
    Clave  = anillo naranja fino: respuesta correcta cuando el alumno falló.
    """
    for center, status, _letter in elements:
        c = (int(center[0]), int(center[1]))
        if status == "marked_correct":
            cv2.circle(img, c, 16, COLOR_HALO, 4, cv2.LINE_AA)
            cv2.circle(img, c, 16, COLOR_BIEN, 3, cv2.LINE_AA)
            _draw_check(img, c, COLOR_BIEN)
        elif status == "marked_incorrect":
            cv2.circle(img, c, 16, COLOR_HALO, 4, cv2.LINE_AA)
            cv2.circle(img, c, 16, COLOR_MAL, 3, cv2.LINE_AA)
            _draw_cross(img, c, COLOR_MAL)
        elif status == "blank":
            cv2.circle(img, c, 16, COLOR_HALO, 3, cv2.LINE_AA)
            _draw_dashed_circle(img, c, 16, COLOR_BLANCO, thickness=3)
        elif status == "key_hint":
            cv2.circle(img, c, 12, COLOR_CLAVE, 2, cv2.LINE_AA)


def _paint_score_panel(img, buenas, malas, en_blanco, puntaje):
    """Panel de puntaje + leyenda de colores (abajo derecha, no tapa burbujas)."""
    H, W = img.shape[:2]
    panel_w, panel_h = 268, 168
    px1 = W - panel_w - 22
    py1 = H - panel_h - 36
    px2, py2 = px1 + panel_w, py1 + panel_h
    overlay = img.copy()
    cv2.rectangle(overlay, (px1, py1), (px2, py2), (255, 255, 255), -1)
    cv2.addWeighted(overlay, 0.90, img, 0.10, 0, img)
    cv2.rectangle(img, (px1, py1), (px2, py2), (30, 30, 40), 2, cv2.LINE_AA)

    cv2.putText(img, f"Buenas: {buenas}  (+{buenas * 10})", (px1 + 12, py1 + 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_BIEN, 2, cv2.LINE_AA)
    cv2.putText(img, f"Malas: {malas}  (-{malas * 1})", (px1 + 12, py1 + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_MAL, 2, cv2.LINE_AA)
    cv2.putText(img, f"Blancos: {en_blanco}  (0)", (px1 + 12, py1 + 74),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_BLANCO, 2, cv2.LINE_AA)
    cv2.putText(img, f"PUNTAJE: {puntaje} pts", (px1 + 12, py1 + 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (20, 20, 30), 2, cv2.LINE_AA)

    # Leyenda
    ly = py1 + 128
    items = [
        (COLOR_BIEN, "Bien"),
        (COLOR_MAL, "Mal"),
        (COLOR_BLANCO, "Blanco"),
        (COLOR_CLAVE, "Clave"),
    ]
    x = px1 + 12
    for color, label in items:
        cv2.circle(img, (x + 6, ly), 6, color, -1, cv2.LINE_AA)
        cv2.circle(img, (x + 6, ly), 6, (30, 30, 40), 1, cv2.LINE_AA)
        cv2.putText(img, label, (x + 16, ly + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (40, 40, 50), 1, cv2.LINE_AA)
        x += 64


def process_exam_image(image_path, salon, curso, colegio, lugar, config_path,
                       output_dir="static/processed", student_index=None,
                       skip_ocr=True, max_image_side=2500,
                       max_megapixels=20.0):
    """
    Califica una ficha OMR (sin OCR de nombre/colegio — solo burbujas).

    student_index: 1-based → etiqueta "Est 01", "Est 02", ...
    skip_ocr: True por defecto (flujo rapido en lote).
    max_megapixels: solo comprime si supera este umbral (default 20 MPx).
    """
    import time
    t_all = time.time()
    image = imread_bgr(image_path)
    if image is None:
        raise ValueError("No se pudo cargar la imagen del examen.")

    salon = canonicalize_salon(salon)
    grading_meta = get_grading_meta()

    # 0. Preproceso: SOLO comprimir si > 20 megapixeles
    image, resize_meta = resize_if_above_megapixels(
        image, max_megapixels=max_megapixels, target_max_side=max_image_side
    )
    if resize_meta.get("resized"):
        print(f"[IMG] Comprimida {resize_meta.get('megapixels')}MPx -> {resize_meta.get('shape_out')}")
    else:
        print(f"[IMG] Original conservada ({resize_meta.get('megapixels')} MPx)")
        
    # 1. Localizar ficha, corregir 90/180/270° y warp a 800x1130
    warped, align_meta = warp_sheet_upright(image)
    
    # Pre-process warped image
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    warped_blur = cv2.GaussianBlur(warped_gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        warped_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 51, 15
    )
    
    layout = load_template_config()
    num_questions_cfg = load_settings_num_questions(15)

    # 2. Auto-calibrar grilla OMR
    grid = detect_omr_grid(warped_gray, num_questions=num_questions_cfg)
    options_map = grid["options"]
    detected_alt = len(options_map)
    x_coords_left = grid["x_left"]
    x_coords_right = grid["x_right"]
    y_rows_left = grid.get("y_rows_left")
    y_rows_right = grid.get("y_rows_right")
    y_start_left = grid["y_start_left"]
    y_start_right = grid["y_start_right"]
    y_step = grid["y_step"]
    print(f"[OMR] Layout: {detected_alt} alts via {grid['method']}")

    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(image_path))[0]

    # 3. Sin OCR: etiqueta enumerada Est 01, Est 02, ...
    if student_index is not None:
        try:
            idx = int(student_index)
        except (TypeError, ValueError):
            idx = 1
        num_orden_pred = f"{idx:02d}"
        student_name = f"Est {num_orden_pred}"
    else:
        num_orden_pred = ""
        student_name = "Est --"
    hora_pred = ""
    grado_pred = ""
    # colegio/lugar vienen del formulario (lote), no del OCR
    ocr_header = {
        "nombre": student_name,
        "colegio": colegio,
        "procedencia": lugar,
        "grado": "",
        "numero_orden": num_orden_pred,
        "hora_entrega": "",
        "ocr_engine": "disabled",
        "ocr_confidence": {}
    }
    
    # 4. Claves + lectura OMR
    # Validar claves contra alternativas REALES de la ficha (no solo settings)
    key_meta = get_answer_key_meta(config_path, salon, curso)
    correct_keys = key_meta["keys"]
    num_questions = len(correct_keys)
    # Re-validar con nº de alts detectado en la foto
    ok_keys, key_warns = validate_answer_key(correct_keys, num_alternatives=detected_alt)
    key_meta["valid"] = ok_keys
    key_meta["warnings"] = key_warns
    if key_warns:
        # ASCII-safe print (Windows consoles a veces fallan con acentos → OSError 22)
        try:
            print(f"[CLAVES] warnings {salon}/{curso} ({detected_alt} alts): {key_warns}")
        except Exception:
            print("[CLAVES] warnings (no se pudieron imprimir)")

    question_coords = build_question_coords(grid, num_questions)
    bubble_r = int(grid.get("bubble_radius") or 16)
            
    student_answers = []
    visual_overlay_elements = []

    for q_num in range(1, num_questions + 1):
        q_coords = question_coords.get(q_num)
        if not q_coords:
            student_answers.append("-")
            continue

        feats = []
        for opt_idx, center_coord in enumerate(q_coords):
            if opt_idx >= len(options_map):
                break
            x_nom, y_nom = center_coord
            # Snap corto solo a contorno de burbuja (no a texto del pie)
            aligned_center = align_coordinate(thresh, x_nom, y_nom, window=10)
            # No saltar a letras del pie / garabatos lejanos
            if (aligned_center[0] - x_nom) ** 2 + (aligned_center[1] - y_nom) ** 2 > 14 ** 2:
                aligned_center = (int(x_nom), int(y_nom))
            feat = bubble_features(warped_gray, thresh, aligned_center, radius=bubble_r)
            feats.append((options_map[opt_idx], feat, aligned_center))

        if len(feats) < 2:
            student_answers.append("-")
            continue

        answer, best_center, best_opt = read_question_answer(feats)
        student_answers.append(answer)

        centers_by_letter = {letter: center for letter, _, center in feats}
        correct_opt = correct_keys[q_num - 1]
        if answer == "-":
            if correct_opt in centers_by_letter:
                visual_overlay_elements.append((centers_by_letter[correct_opt], "blank", correct_opt))
        elif answer == "X":
            ranked = sorted(feats, key=lambda t: t[1]["raw"])
            for letter, _, center in ranked[:2]:
                visual_overlay_elements.append((center, "marked_incorrect", letter))
            if correct_opt in centers_by_letter:
                visual_overlay_elements.append((centers_by_letter[correct_opt], "key_hint", correct_opt))
        else:
            if answer in centers_by_letter:
                is_correct = (answer == correct_opt)
                visual_overlay_elements.append((
                    centers_by_letter[answer],
                    "marked_correct" if is_correct else "marked_incorrect",
                    answer,
                ))
            if correct_opt != answer and correct_opt in centers_by_letter:
                visual_overlay_elements.append((centers_by_letter[correct_opt], "key_hint", correct_opt))
 
    # 5. Grading Statistics
    buenas = 0
    malas = 0
    en_blanco = 0
    detailed_results = []
    
    for q_idx in range(num_questions):
        ans = student_answers[q_idx]
        correct = correct_keys[q_idx]
        
        if ans == "-":
            en_blanco += 1
            status = "Blanco"
        elif ans == correct:
            buenas += 1
            status = "Bien"
        else:
            malas += 1
            status = "Mal"
            
        detailed_results.append({
            "pregunta": q_idx + 1,
            "respuesta_alumno": ans,
            "respuesta_correcta": correct,
            "estado": status
        })
        
    puntaje = (buenas * 10) - (malas * 1) + (en_blanco * 0)
    
    # 6. Overlays de tracking: verde=bien, rojo=mal, azul=blanco
    output_image = warped.copy()
    _paint_omr_overlays(output_image, visual_overlay_elements)
    H_out, W_out = output_image.shape[:2]
    _paint_score_panel(output_image, buenas, malas, en_blanco, puntaje)

    # Etiqueta enumerada + meta de sistema (sin OCR)
    tag1 = f"{student_name} | {salon} / {curso} | {buenas}B {malas}M {en_blanco}Bl"
    tag2 = f"Calif: {grading_meta['graded_at']}  PC: {grading_meta['graded_on_pc']}"
    cv2.putText(output_image, tag1[:72], (50, H_out - 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (30, 30, 30), 1, cv2.LINE_AA)
    cv2.putText(output_image, tag2[:72], (50, H_out - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (50, 50, 50), 1, cv2.LINE_AA)
    
    # Nombre de archivo con índice de lote si existe
    if num_orden_pred:
        output_image_filename = f"graded_{num_orden_pred}_{base_name}.jpg"
    else:
        output_image_filename = f"graded_{base_name}.jpg"
    output_image_path = os.path.join(output_dir, output_image_filename)
    cv2.imwrite(output_image_path, output_image)

    elapsed_ms = int((time.time() - t_all) * 1000)
    print(
        f"[PIPELINE] total={elapsed_ms}ms | OMR={detected_alt}alts | "
        f"align={align_meta.get('method')} rot={align_meta.get('roll')} | id={student_name}"
    )
    
    orden_entrega_pred = num_orden_pred

    return {
        "image_filename": base_name,
        "student_id": num_orden_pred,
        "student_name": student_name,
        "colegio": colegio,
        "lugar": lugar,
        "grado": grado_pred,
        "buenas": buenas,
        "malas": malas,
        "en_blanco": en_blanco,
        "puntaje": puntaje,
        "orden_entrega": orden_entrega_pred,
        "hora_entrega": hora_pred,
        "answers": student_answers,
        "detailed_results": detailed_results,
        "graded_image_url": _public_static_url(output_dir, output_image_filename),
        "graded_image_path": output_image_path,
        "num_alternatives": detected_alt,
        "processing_ms": elapsed_ms,
        "omr_grid_method": grid.get("method", ""),
        "align_method": align_meta.get("method", ""),
        "align_rotation": int(align_meta.get("roll", 0)) * 90,
        "resize_meta": resize_meta,
        # --- Meta de calificacion (sistema) ---
        "graded_at": grading_meta["graded_at"],
        "graded_on_pc": grading_meta["graded_on_pc"],
        "salon": salon,
        # --- Trakeo de claves ---
        "clave_id": key_meta.get("key_id", ""),
        "clave_fingerprint": key_meta.get("fingerprint", ""),
        "clave_salon": key_meta.get("salon_resolved", salon),
        "clave_curso": key_meta.get("curso_resolved", curso),
        "clave_keys": correct_keys,
        "clave_valid": key_meta.get("valid", True),
        "clave_warnings": key_meta.get("warnings", []),
        # --- OCR meta (deshabilitado) ---
        "ocr_engine": ocr_header.get("ocr_engine", ""),
        "ocr_confidence": ocr_header.get("ocr_confidence", {}),
        "ocr_fields": {
            "nombre": student_name,
            "colegio": colegio,
            "procedencia": lugar,
            "grado": grado_pred,
            "numero_orden": num_orden_pred,
            "hora_entrega": hora_pred
        }
    }


def record_confirmed_result(salon, curso, colegio, lugar, student_id, name, buenas, malas, en_blanco, score, hora, orden_entrega, answers, report_path="reporte_resultados.xlsx", clave_fingerprint="", clave_id="", grado="", graded_at="", graded_on_pc=""):
    """
    Saves a verified row into the master results Excel sheet under the Lugar/Colegio/Salon structure.
    Incluye fingerprint de la clave, hora de calificacion y PC.
    """
    salon = canonicalize_salon(salon)
    if not graded_at or not graded_on_pc:
        meta = get_grading_meta()
        graded_at = graded_at or meta["graded_at"]
        graded_on_pc = graded_on_pc or meta["graded_on_pc"]
    row_data = {
        "Apellidos y Nombres": name,
        "Colegio": colegio,
        "Lugar": lugar,
        "Grado": grado,
        "Buenas": buenas,
        "Malas": malas,
        "En Blanco": en_blanco,
        "Hora": hora,
        "Orden de Entrega": orden_entrega,
        "Puntaje": score,
        "Salon": salon,
        "Curso": curso,
        "ID_Estudiante": student_id,
        "Clave_Fingerprint": clave_fingerprint or "",
        "Clave_ID": clave_id or "",
        "Fecha_Calificacion": graded_at,
        "PC_Calificacion": graded_on_pc,
    }
    
    # Add question detail indicators
    for i in range(15):
        row_data[f"Q{i+1}"] = answers[i]
        
    df_new = pd.DataFrame([row_data])
    
    # 1. Maintain master list
    master_df = df_new
    if os.path.exists(report_path):
        try:
            try:
                master_df_old = pd.read_excel(report_path, sheet_name="Detalle General")
            except Exception:
                master_df_old = pd.read_excel(report_path)
                
            # Filter duplicates matching student name, classroom, and course
            # ONLY deduplicate if the name is actually detected
            if name and name != "Estudiante No Detectado":
                master_df_old = master_df_old[~((master_df_old["Apellidos y Nombres"] == name) & 
                                                (master_df_old["Salon"] == salon) &
                                                (master_df_old["Curso"] == curso))]
            master_df = pd.concat([master_df_old, df_new], ignore_index=True)
        except Exception as e:
            print(f"Error loading master report: {e}")
            master_df = df_new
            
    # Save workbook
    return _save_excel_workbook(master_df, report_path)

def _save_excel_workbook(master_df, report_path):
    """
    Private helper to normalize and save the master Excel dataframe.
    """
    if master_df.empty:
        # If dataframe is empty, delete the file if it exists
        if os.path.exists(report_path):
            try:
                os.remove(report_path)
            except Exception:
                pass
        return True
        
    try:
        # Normalize types
        master_df['ID_Estudiante'] = master_df['ID_Estudiante'].astype(str).str.zfill(2)
        master_df['Salon'] = master_df['Salon'].astype(str)
        master_df['Curso'] = master_df['Curso'].astype(str)
        master_df['Puntaje'] = master_df['Puntaje'].astype(int)
        master_df['Buenas'] = master_df['Buenas'].astype(int)
        master_df['Malas'] = master_df['Malas'].astype(int)
        master_df['En Blanco'] = master_df['En Blanco'].astype(int)
        
        # Sort
        master_df = master_df.sort_values(by=["Salon", "Curso", "ID_Estudiante"]).reset_index(drop=True)
        
        with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
            # Sheet 1: Detalle General
            master_df.to_excel(writer, sheet_name="Detalle General", index=False)
            
            # Group sheets by Salon (Tab names)
            unique_salones = sorted(master_df["Salon"].unique())
            for s in unique_salones:
                df_salon = master_df[master_df["Salon"] == s].copy()
                cols_to_keep = [
                    "Apellidos y Nombres", "Colegio", "Lugar", "Buenas", "Malas", 
                    "En Blanco", "Hora", "Orden de Entrega", "Puntaje", "Curso"
                ] + [f"Q{i}" for i in range(1, 16)]
                df_salon_write = df_salon[cols_to_keep]
                df_salon_write.to_excel(writer, sheet_name=s, index=False)
                
        print(f"Excel workbook updated successfully: {report_path}")
        return True
    except Exception as e:
        print(f"Could not save Excel file: {e}")
        return False

def delete_confirmed_result(salon, curso, student_id, name, report_path="reporte_resultados.xlsx"):
    """
    Deletes a confirmed student record from the consolidated Excel results sheet.
    """
    if not os.path.exists(report_path):
        return True
        
    try:
        try:
            master_df = pd.read_excel(report_path, sheet_name="Detalle General")
        except Exception:
            master_df = pd.read_excel(report_path)
            
        # Match student_id or name for deletion
        student_id_str = str(student_id).zfill(2) if student_id else ""
        name_str = str(name).strip().lower() if name else ""
        
        # Filter out the specific row
        filtered_df = master_df[~((master_df['Salon'].astype(str) == str(salon)) & 
                                  (master_df['Curso'].astype(str) == str(curso)) & 
                                  ((master_df['ID_Estudiante'].astype(str).str.zfill(2) == student_id_str) | 
                                   (master_df['Apellidos y Nombres'].astype(str).str.strip().str.lower() == name_str)))]
                                   
        return _save_excel_workbook(filtered_df, report_path)
    except Exception as e:
        print(f"Error deleting Excel record: {e}")
        return False

def clear_salon_results(salon, curso, report_path="reporte_resultados.xlsx"):
    """
    Clears all records for the given Salon and Curso.
    """
    if not os.path.exists(report_path):
        return True
        
    try:
        try:
            master_df = pd.read_excel(report_path, sheet_name="Detalle General")
        except Exception:
            master_df = pd.read_excel(report_path)
            
        # Filter out all matching rows
        filtered_df = master_df[~((master_df['Salon'].astype(str) == str(salon)) & 
                                  (master_df['Curso'].astype(str) == str(curso)))]
                                  
        return _save_excel_workbook(filtered_df, report_path)
    except Exception as e:
        print(f"Error clearing Excel records: {e}")
        return False
