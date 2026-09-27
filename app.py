from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import json
import io
import zipfile
import uuid
import shutil
import pandas as pd
import werkzeug
from omr_pack import discover_lots, safe_extract_zip
from omr_processor import (
    process_exam_image, record_confirmed_result, load_template_config,
    delete_confirmed_result, clear_salon_results, get_answer_key_meta,
    list_all_keys_summary, normalize_key_id,
    load_claves_records, save_claves_records, sanitize_scoring,
)
from sheet_pdf import build_sheet_pdf, resolve_theme, get_omr_geometry

# Rutas absolutas (evita fallos si el CWD del servidor no es la carpeta del proyecto)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

app = Flask(__name__, template_folder='templates', static_folder='static')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
CONFIG_PATH = os.path.join(BASE_DIR, 'configuracion_ejemplo.xlsx')
REPORT_PATH = os.path.join(BASE_DIR, 'reporte_resultados.xlsx')
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'static', 'processed')
BATCH_FOLDER = os.path.join(PROCESSED_FOLDER, 'batches')

PACK_FOLDER = os.path.join(UPLOAD_FOLDER, "packs")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(BATCH_FOLDER, exist_ok=True)
os.makedirs(PACK_FOLDER, exist_ok=True)

# Último lote en memoria (batch_id → lista de rutas de imágenes calificadas)
_LAST_BATCH = {"id": None, "images": [], "meta": {}}

# Créditos del PDF de lote (minimal).
DEVELOPER_INITIALS = "A.B.M.R"
LICENSE_LINE = "Derechos reservados. © 2026 Alberto Brayan."
RIGHTS_LINE = "Todos los derechos reservados"
_LOTE_FONTS = {"ui": "Helvetica", "uib": "Helvetica-Bold", "ready": False}


def _ensure_lote_fonts():
    if _LOTE_FONTS["ready"]:
        return
    _LOTE_FONTS["ready"] = True
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts = os.path.join(windir, "Fonts")
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        segoe = os.path.join(fonts, "segoeui.ttf")
        segoeb = os.path.join(fonts, "segoeuib.ttf")
        if os.path.isfile(segoe):
            pdfmetrics.registerFont(TTFont("LoteUI", segoe))
            _LOTE_FONTS["ui"] = "LoteUI"
        if os.path.isfile(segoeb):
            pdfmetrics.registerFont(TTFont("LoteUIB", segoeb))
            _LOTE_FONTS["uib"] = "LoteUIB"
    except Exception:
        pass


def _draw_lote_footer(c, page_w, footer_h):
    """Franja inferior discreta, debajo de la cartilla."""
    from reportlab.lib.colors import Color
    from reportlab.lib.units import mm

    bg = Color(0.965, 0.965, 0.968)
    line = Color(0.82, 0.82, 0.84)
    ink = Color(0.28, 0.30, 0.33)
    muted = Color(0.48, 0.50, 0.53)
    ui = _LOTE_FONTS["ui"]

    c.setFillColor(bg)
    c.rect(0, 0, page_w, footer_h, stroke=0, fill=1)
    c.setStrokeColor(line)
    c.setLineWidth(0.5)
    c.line(0, footer_h, page_w, footer_h)

    mid = page_w / 2.0
    c.setFont(ui, 7.0)
    c.setFillColor(ink)
    c.drawCentredString(mid, footer_h - 5.2 * mm, f"OCR OMR SCAN  ·  {DEVELOPER_INITIALS}")
    c.setFont(ui, 6.2)
    c.setFillColor(muted)
    c.drawCentredString(mid, footer_h - 9.0 * mm, f"© 2026  ·  {LICENSE_LINE}")


def _draw_lote_credits_page(c, page_w, page_h, meta):
    """Colofón final: blanco, tipografía pequeña, sin adornos."""
    from reportlab.lib.colors import Color, white
    from reportlab.lib.units import mm

    ink = Color(0.22, 0.24, 0.26)
    muted = Color(0.50, 0.52, 0.55)
    line = Color(0.86, 0.86, 0.88)
    ui = _LOTE_FONTS["ui"]
    uib = _LOTE_FONTS["uib"]

    c.setFillColor(white)
    c.rect(0, 0, page_w, page_h, stroke=0, fill=1)

    mid = page_w / 2.0
    cy = page_h * 0.52
    c.setFont(uib, 11)
    c.setFillColor(ink)
    c.drawCentredString(mid, cy + 10 * mm, "OCR OMR SCAN")
    c.setStrokeColor(line)
    c.setLineWidth(0.5)
    c.line(36 * mm, cy + 6 * mm, page_w - 36 * mm, cy + 6 * mm)
    c.setFont(ui, 9)
    c.setFillColor(ink)
    c.drawCentredString(mid, cy - 2 * mm, f"GROK  ·  {DEVELOPER_INITIALS}")
    c.setFont(ui, 8)
    c.setFillColor(ink)
    c.drawCentredString(mid, cy - 8 * mm, RIGHTS_LINE)
    c.setFont(ui, 7.2)
    c.setFillColor(muted)
    c.drawCentredString(mid, cy - 13.5 * mm, "Desarrollo interno. Uso solo con permiso.")

    salon = str((meta or {}).get("salon") or "")
    curso = str((meta or {}).get("curso") or "")
    count = (meta or {}).get("count")
    bits = [p for p in (salon, curso, f"{count} fichas" if count else "") if p]
    if bits:
        c.setFont(ui, 7)
        c.drawCentredString(mid, cy - 22 * mm, "  ·  ".join(bits))

    c.setFont(ui, 6.4)
    c.setFillColor(muted)
    c.drawCentredString(mid, 14 * mm, "© 2026 Alberto Brayan  ·  Derechos reservados")


def build_lote_export_pdf(image_paths, meta=None, batch_id=""):
    """PDF de cartillas calificadas (créditos van en la imagen) + colofón."""
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdfcanvas

    _ensure_lote_fonts()
    meta = meta or {}
    a5_w, a5_h = A5

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A5)
    title = f"Lote calificado — {meta.get('salon', '')} / {meta.get('curso', '')}"
    c.setTitle(title.strip(" —/"))
    c.setAuthor(DEVELOPER_INITIALS)
    c.setCreator("OCR OMR SCAN")
    c.setSubject(LICENSE_LINE)

    for path in image_paths:
        ir = ImageReader(path)
        iw, ih = ir.getSize()
        if iw <= 0 or ih <= 0:
            continue
        img_w = a5_w
        img_h = img_w * (ih / float(iw))
        c.setPageSize((a5_w, img_h))
        c.drawImage(ir, 0, 0, width=img_w, height=img_h, preserveAspectRatio=True, mask="auto")
        c.showPage()

    c.setPageSize((a5_w, a5_h))
    _draw_lote_credits_page(c, a5_w, a5_h, {**meta, "count": meta.get("count") or len(image_paths)})
    c.showPage()
    c.save()
    return buf.getvalue()


def _json_safe(obj):
    """Convierte numpy/paths a tipos JSON-serializables."""
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    return obj

def load_settings_config():
    settings_path = 'settings_config.json'
    default_config = {
        "labels": {
            "nombre": "Apellidos y Nombres",
            "colegio": "Colegio",
            "grado": "Grado",
            "procedencia": "Procedencia"
        },
        "num_alternatives": 4,
        "num_questions": 15,
        "scoring": {"buenas": 10.0, "malas": -1.0, "blanco": 0.0},
        "branding": {"title": "", "logo": ""},
    }
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return default_config
            out = dict(default_config)
            out.update({k: data[k] for k in data if k not in ("labels", "scoring", "branding")})
            if isinstance(data.get("labels"), dict):
                out["labels"] = {**default_config["labels"], **data["labels"]}
            out["scoring"] = sanitize_scoring(data.get("scoring"))
            br = data.get("branding") if isinstance(data.get("branding"), dict) else {}
            out["branding"] = {
                "title": str(br.get("title") or "").strip()[:80],
                "logo": str(br.get("logo") or "").strip(),
            }
            return out
        except Exception:
            pass
    return default_config

def update_template_grid_config(num_q, num_alt):
    """
    Recalibrates OMR grid coordinates in template_config.json when
    questions/options change. Preserves OCR field ROIs if present.
    """
    try:
        layout_path = 'template_config.json'
        layout = {}
        if os.path.exists(layout_path):
            try:
                with open(layout_path, 'r', encoding='utf-8') as f:
                    layout = json.load(f)
            except Exception:
                layout = {}

        layout["mark_threshold"] = layout.get("mark_threshold", 95.0)

        mid = (num_q + 1) // 2
        from sheet_pdf import geometry_to_warped_canvas, get_omr_geometry
        canvas = geometry_to_warped_canvas(get_omr_geometry(int(num_q), int(num_alt)))
        options_list = list(canvas["options"])
        x_coords_left = canvas["x_left"]
        x_coords_right = canvas["x_right"]
        y_start = canvas["y_start_left"]
        y_step = canvas["y_step"]

        if canvas.get("ocr_fields"):
            layout["ocr_fields"] = canvas["ocr_fields"]
        elif "ocr_fields" not in layout or "header" not in layout.get("ocr_fields", {}):
            layout["ocr_fields"] = {
                "header": {"x": 45, "y": 40, "w": 710, "h": 145},
                "nombre": {"x": 180, "y": 45, "w": 560, "h": 40},
                "colegio": {"x": 120, "y": 82, "w": 620, "h": 38},
                "grado": {"x": 100, "y": 118, "w": 200, "h": 40},
                "procedencia": {"x": 400, "y": 118, "w": 340, "h": 40},
                "footer": {"x": 40, "y": 1025, "w": 340, "h": 90},
                "numero_orden_box": {"x": 45, "y": 1035, "w": 110, "h": 70},
                "hora_entrega_box": {"x": 160, "y": 1035, "w": 150, "h": 70}
            }

        layout["omr_questions"] = {
            "left_column": {
                "q_range": [1, mid],
                "x_coords": x_coords_left,
                "y_start": y_start,
                "y_step": y_step,
                "y_rows": canvas.get("y_rows_left"),
            },
            "right_column": {
                "q_range": [mid + 1, num_q],
                "x_coords": x_coords_right,
                "y_start": canvas.get("y_start_right", y_start),
                "y_step": y_step,
                "y_rows": canvas.get("y_rows_right"),
            },
            "options": options_list,
            "profile": canvas.get("profile", ""),
        }
        
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout, f, indent=2)
        print(f"Coordinates grid updated for {num_q} questions and {num_alt} alternatives.")
    except Exception as e:
        print(f"Error updating coordinate grid: {e}")

def _theme_for_template(curso: str | None):
    """Tema visual + colores CSS para sheet.html."""
    t = resolve_theme(curso)

    def _hex(c):
        # reportlab Color → #rrggbb
        return "#{:02x}{:02x}{:02x}".format(
            int(round(c.red * 255)),
            int(round(c.green * 255)),
            int(round(c.blue * 255)),
        )

    return {
        "id": t["id"],
        "title": t["title"],
        "badge": t["badge"],
        "filename": t["filename"],
        "css": {
            "primary": _hex(t["primary"]),
            "primary_dark": _hex(t["primary_dark"]),
            "primary_light": _hex(t["primary_light"]),
            "border": _hex(t["border"]),
            "zebra": _hex(t["zebra"]),
            "header_bg": _hex(t["header_bg"]),
            "label": _hex(t["label"]),
            "bubble_text": _hex(t["bubble_text"]),
        },
    }


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sheet')
def sheet():
    config = load_settings_config()
    curso = request.args.get('curso', 'Comunicacion')
    theme = _theme_for_template(curso)
    nq = max(1, min(20, int(config.get("num_questions") or 15)))
    na = max(2, min(5, int(config.get("num_alternatives") or 4)))
    geo = get_omr_geometry(nq, na)
    return render_template('sheet.html', config=config, theme=theme, geo=geo)


@app.route('/download_sheet_pdf')
def download_sheet_pdf():
    """PDF vectorial A5 de la ficha en blanco (Comunicación o Matemática)."""
    curso = request.args.get('curso', 'Comunicacion')
    try:
        pdf_bytes, filename = build_sheet_pdf(
            curso=curso,
            settings=load_settings_config(),
            base_dir=BASE_DIR,
        )
        buf = io.BytesIO(pdf_bytes)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"No se pudo generar el PDF: {e}"}), 500

@app.route('/scan', methods=['POST'])
def scan():
    if 'image' not in request.files:
        return jsonify({"error": "No se subió ninguna imagen."}), 400
        
    file = request.files['image']
    salon = request.form.get('salon')
    curso = request.form.get('curso')
    colegio = request.form.get('colegio', 'Colegio S/N')
    lugar = request.form.get('lugar', 'Lugar S/N')
    student_index = request.form.get('student_index', '1')
    
    if not file or file.filename == '':
        return jsonify({"error": "Archivo de imagen vacío o inválido."}), 400
        
    if not salon or not curso:
        return jsonify({"error": "Falta información del salón o curso."}), 400
        
    filename = werkzeug.utils.secure_filename(file.filename)
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        filename += '.jpg'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        result = process_exam_image(
            image_path=filepath,
            salon=salon,
            curso=curso,
            colegio=colegio,
            lugar=lugar,
            config_path=CONFIG_PATH,
            output_dir=PROCESSED_FOLDER,
            student_index=student_index,
            skip_ocr=True,
            max_image_side=2500,
            max_megapixels=20.0
        )
        return jsonify(_json_safe(result))
        
    except ValueError as val_err:
        return jsonify({"error": str(val_err)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error en el backend: {str(e)}"}), 500


def _grade_file_list(filepaths, salon, curso, colegio, lugar, batch_dir, start_index=1):
    results = []
    errors = []
    graded_paths = []
    for i, filepath in enumerate(filepaths):
        if not filepath or not os.path.isfile(filepath):
            continue
        idx = start_index + i
        try:
            result = process_exam_image(
                image_path=filepath,
                salon=salon,
                curso=curso,
                colegio=colegio,
                lugar=lugar,
                config_path=CONFIG_PATH,
                output_dir=batch_dir,
                student_index=idx,
                skip_ocr=True,
                max_image_side=2500,
                max_megapixels=20.0
            )
            record_confirmed_result(
                salon=salon,
                curso=curso,
                colegio=colegio,
                lugar=lugar,
                student_id=result.get("student_id"),
                name=result.get("student_name"),
                buenas=result.get("buenas"),
                malas=result.get("malas"),
                en_blanco=result.get("en_blanco"),
                score=result.get("puntaje"),
                hora=result.get("hora_entrega") or "",
                orden_entrega=result.get("orden_entrega") or result.get("student_id"),
                answers=result.get("answers") or [],
                report_path=REPORT_PATH,
                clave_fingerprint=result.get("clave_fingerprint", ""),
                clave_id=result.get("clave_id", ""),
                grado=result.get("grado") or "",
                graded_at=result.get("graded_at") or "",
                graded_on_pc=result.get("graded_on_pc") or "",
            )
            local_graded = result.get("graded_image_path") or os.path.join(
                batch_dir, os.path.basename(result.get("graded_image_url", "").split("/")[-1])
            )
            if os.path.exists(local_graded):
                graded_paths.append(local_graded)
            result["salon"] = salon
            result["curso"] = curso
            results.append(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            errors.append({"file": os.path.basename(filepath), "error": str(e), "index": idx})
    return results, errors, graded_paths


def _lote_filename(meta, ext="pdf"):
    def tok(s):
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s or "").strip()).strip("_")
    salon = tok(meta.get("salon") or "salon")
    curso = tok(meta.get("curso") or "curso")
    pack = tok(meta.get("pack_name") or "")
    base = f"lote_{salon}_{curso}"
    if pack:
        base = f"{pack}_{base}"
    return f"{base}.{ext}"


def _write_batch_meta(batch_dir, meta):
    path = os.path.join(batch_dir, "meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _read_batch_meta(batch_id):
    path = os.path.join(BATCH_FOLDER, batch_id or "", "meta.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    if batch_id and batch_id == _LAST_BATCH.get("id"):
        return dict(_LAST_BATCH.get("meta") or {})
    return {}


def _pdf_extra_dirs(pack_name="", pack_id=""):
    dirs = []
    if pack_id:
        dirs.append(os.path.join(PACK_FOLDER, pack_id, "PDFs_calificados"))
    pack_tok = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (pack_name or "").strip()).strip("_")
    if pack_tok:
        dirs.append(os.path.join(PROCESSED_FOLDER, "pdfs", pack_tok, "PDFs_calificados"))
    return dirs


def _materialize_lote_pdf(batch_id, graded_paths, meta, extra_dirs=None):
    """Genera el PDF al terminar el salón y lo deja en disco (descarga inmediata)."""
    if not graded_paths:
        return None
    name = _lote_filename(meta, "pdf")
    pdf_bytes = build_lote_export_pdf(graded_paths, meta=meta, batch_id=batch_id or "")
    dests = [os.path.join(BATCH_FOLDER, batch_id)]
    for d in extra_dirs or []:
        if d:
            dests.append(d)
    for d in dests:
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "wb") as f:
                f.write(pdf_bytes)
        except Exception:
            import traceback
            traceback.print_exc()
    return name


def _batch_payload(batch_id, salon, curso, colegio, lugar, results, errors, graded_paths, pack_name="", pack_id=""):
    meta = {
        "salon": salon, "curso": curso, "colegio": colegio, "lugar": lugar,
        "count": len(results),
        "pack_name": pack_name or "",
    }
    batch_dir = os.path.join(BATCH_FOLDER, batch_id)
    if os.path.isdir(batch_dir):
        _write_batch_meta(batch_dir, meta)
    pdf_name = None
    if graded_paths:
        pdf_name = _materialize_lote_pdf(
            batch_id, graded_paths, meta, extra_dirs=_pdf_extra_dirs(pack_name, pack_id)
        )
    _LAST_BATCH["id"] = batch_id
    _LAST_BATCH["images"] = graded_paths
    _LAST_BATCH["meta"] = meta
    pdf_name = pdf_name or _lote_filename(meta, "pdf")
    return _json_safe({
        "batch_id": batch_id,
        "processed": len(results),
        "errors": errors,
        "results": results,
        "salon": salon,
        "curso": curso,
        "pdf_name": pdf_name,
        "download_pdf_url": f"/download_batch_pdf?batch_id={batch_id}",
        "download_pngs_url": f"/download_batch_pngs?batch_id={batch_id}",
    })


@app.route('/batch_scan', methods=['POST'])
def batch_scan():
    """
    Procesa un lote de fichas:
    - OMR sin OCR
    - Etiqueta Est 01, Est 02, ...
    - Guarda en Excel (registro)
    - Devuelve lista de imágenes calificadas + batch_id para descargas
    """
    files = request.files.getlist('images') or request.files.getlist('image')
    salon = request.form.get('salon')
    curso = request.form.get('curso')
    colegio = request.form.get('colegio', 'Colegio S/N')
    lugar = request.form.get('lugar', 'Lugar S/N')
    start_index = int(request.form.get('start_index', '1') or 1)

    if not files:
        return jsonify({"error": "No se subieron imágenes."}), 400
    if not salon or not curso:
        return jsonify({"error": "Falta salón o curso."}), 400

    batch_id = uuid.uuid4().hex[:12]
    batch_dir = os.path.join(BATCH_FOLDER, batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    saved = []
    for i, file in enumerate(files):
        if not file or not file.filename:
            continue
        idx = start_index + i
        filename = werkzeug.utils.secure_filename(file.filename)
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            filename += '.jpg'
        filename = f"{idx:02d}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        saved.append(filepath)

    results, errors, graded_paths = _grade_file_list(
        saved, salon, curso, colegio, lugar, batch_dir, start_index=start_index
    )
    pack_name = (request.form.get("pack_name") or "").strip()
    pack_id = (request.form.get("pack_id") or "").strip()
    return jsonify(_batch_payload(
        batch_id, salon, curso, colegio, lugar, results, errors, graded_paths,
        pack_name=pack_name, pack_id=pack_id
    ))


@app.route('/pack_ingest', methods=['POST'])
def pack_ingest():
    """Recibe el ZIP de la app (con manifest.json) y lista los salones detectados."""
    pack = request.files.get('pack') or request.files.get('zip')
    if not pack or not pack.filename:
        return jsonify({"error": "Sube el ZIP exportado por la app."}), 400
    pack_id = uuid.uuid4().hex[:12]
    dest = os.path.join(PACK_FOLDER, pack_id)
    os.makedirs(dest, exist_ok=True)
    tmp = os.path.join(dest, "_pack.zip")
    pack.save(tmp)
    try:
        safe_extract_zip(tmp, dest)
    except zipfile.BadZipFile:
        shutil.rmtree(dest, ignore_errors=True)
        return jsonify({"error": "El archivo no es un ZIP válido."}), 400
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    lots = discover_lots(dest)
    public = [{k: v for k, v in lot.items() if k != "files"} for lot in lots]
    return jsonify({
        "pack_id": pack_id,
        "name": os.path.splitext(pack.filename)[0],
        "lots": public,
        "total": sum(l["count"] for l in public),
    })


@app.route('/pack_grade_lot', methods=['POST'])
def pack_grade_lot():
    """Califica un salón/curso ya extraído de un pack."""
    pack_id = (request.form.get("pack_id") or "").strip()
    salon = request.form.get("salon")
    curso = request.form.get("curso")
    colegio = request.form.get("colegio", "Colegio S/N")
    lugar = request.form.get("lugar", "Lugar S/N")
    if not pack_id or not salon or not curso:
        return jsonify({"error": "Falta pack_id, salón o curso."}), 400
    root = os.path.join(PACK_FOLDER, pack_id)
    if not os.path.isdir(root):
        return jsonify({"error": "Pack no encontrado. Vuelve a subir el ZIP."}), 404
    lots = discover_lots(root)
    match = next((l for l in lots if l["salon"] == salon and l["curso"] == curso), None)
    if not match or not match.get("files"):
        return jsonify({"error": f"No hay fotos en {salon} / {curso}."}), 404
    batch_id = uuid.uuid4().hex[:12]
    batch_dir = os.path.join(BATCH_FOLDER, batch_id)
    os.makedirs(batch_dir, exist_ok=True)
    results, errors, graded_paths = _grade_file_list(
        match["files"], salon, curso, colegio, lugar, batch_dir, start_index=1
    )
    pack_name = (request.form.get("pack_name") or "").strip()
    payload = _batch_payload(
        batch_id, salon, curso, colegio, lugar, results, errors, graded_paths,
        pack_name=pack_name, pack_id=pack_id
    )
    return jsonify(payload)


def _batch_image_paths(batch_id):
    if batch_id and batch_id == _LAST_BATCH.get("id") and _LAST_BATCH.get("images"):
        return [p for p in _LAST_BATCH["images"] if os.path.exists(p)]
    batch_dir = os.path.join(BATCH_FOLDER, batch_id or "")
    if not os.path.isdir(batch_dir):
        return []
    files = sorted([
        os.path.join(batch_dir, f) for f in os.listdir(batch_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])
    return files


@app.route('/download_batch_pdf')
def download_batch_pdf():
    """PDF multipágina con cartillas calificadas, franja de créditos y página final."""
    batch_id = request.args.get('batch_id') or _LAST_BATCH.get("id")
    paths = _batch_image_paths(batch_id)
    if not paths:
        return jsonify({"error": "No hay imágenes de lote para descargar."}), 404

    try:
        meta = _read_batch_meta(batch_id)
        if not meta.get("count"):
            meta["count"] = len(paths)
        name = _lote_filename(meta, "pdf")
        prebuilt = os.path.join(BATCH_FOLDER, batch_id or "", name)
        if os.path.isfile(prebuilt):
            return send_file(prebuilt, as_attachment=True, download_name=name, mimetype="application/pdf")
        pdf_bytes = build_lote_export_pdf(paths, meta=meta, batch_id=batch_id or "")
        buf = io.BytesIO(pdf_bytes)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=name, mimetype="application/pdf")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"No se pudo crear el PDF: {e}"}), 500


@app.route('/download_batch_pngs')
def download_batch_pngs():
    """ZIP con todas las cartillas calificadas en PNG."""
    batch_id = request.args.get('batch_id') or _LAST_BATCH.get("id")
    paths = _batch_image_paths(batch_id)
    if not paths:
        return jsonify({"error": "No hay imágenes de lote para descargar."}), 404

    try:
        from PIL import Image
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                # convertir a PNG en memoria
                im = Image.open(p).convert("RGB")
                png_buf = io.BytesIO()
                im.save(png_buf, format="PNG")
                png_name = os.path.splitext(os.path.basename(p))[0] + ".png"
                zf.writestr(png_name, png_buf.getvalue())
        buf.seek(0)
        meta = _read_batch_meta(batch_id)
        name = _lote_filename(meta, "zip").replace(".zip", "_png.zip")
        if not name.startswith("lote_png") and "png" not in name:
            name = name.replace("lote_", "lote_png_")
        return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"No se pudo crear el ZIP: {e}"}), 500


@app.route('/download_pack_pdfs')
def download_pack_pdfs():
    """ZIP con un PDF por salón/curso, nombres reales (lote_Sec_1_Matematica.pdf)."""
    raw = (request.args.get("ids") or "").strip()
    ids = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if not ids:
        return jsonify({"error": "Faltan batch_id de los salones."}), 400
    used_names = set()
    buf = io.BytesIO()
    written = 0
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for batch_id in ids:
                paths = _batch_image_paths(batch_id)
                if not paths:
                    continue
                meta = _read_batch_meta(batch_id)
                if not meta.get("count"):
                    meta["count"] = len(paths)
                pdf_bytes = build_lote_export_pdf(paths, meta=meta, batch_id=batch_id)
                name = _lote_filename(meta, "pdf")
                if name in used_names:
                    stem, ext = os.path.splitext(name)
                    name = f"{stem}_{batch_id[:6]}{ext}"
                used_names.add(name)
                zf.writestr(name, pdf_bytes)
                written += 1
        if written == 0:
            return jsonify({"error": "No hay PDF para empaquetar."}), 404
        buf.seek(0)
        pack = ""
        if ids:
            pack = str(_read_batch_meta(ids[0]).get("pack_name") or "").strip()
        zip_name = f"{pack}_todos_los_pdfs.zip" if pack else "todos_los_pdfs.zip"
        zip_name = zip_name.replace(" ", "_")
        return send_file(buf, as_attachment=True, download_name=zip_name, mimetype="application/zip")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"No se pudo crear el ZIP de PDFs: {e}"}), 500

@app.route('/confirm', methods=['POST'])
def confirm():
    data = request.json
    if not data:
        return jsonify({"error": "Datos de confirmación vacíos."}), 400
        
    try:
        # Write verified sheet row into Excel consolidated workbook
        success = record_confirmed_result(
            salon=data.get('salon'),
            curso=data.get('curso'),
            colegio=data.get('colegio'),
            lugar=data.get('lugar'),
            student_id=data.get('student_id'),
            name=data.get('student_name'),
            buenas=data.get('buenas'),
            malas=data.get('malas'),
            en_blanco=data.get('en_blanco'),
            score=data.get('puntaje'),
            hora=data.get('hora_entrega'),
            orden_entrega=data.get('orden_entrega'),
            answers=data.get('answers'),
            report_path=REPORT_PATH,
            clave_fingerprint=data.get('clave_fingerprint', ''),
            clave_id=data.get('clave_id', ''),
            grado=data.get('grado', ''),
            graded_at=data.get('graded_at', ''),
            graded_on_pc=data.get('graded_on_pc', ''),
        )
        if success:
            return jsonify({"status": "ok"})
        else:
            return jsonify({"error": "No se pudo escribir en el archivo Excel."}), 500
    except Exception as e:
        return jsonify({"error": f"Error al guardar registro: {str(e)}"}), 500

@app.route('/delete_record', methods=['POST'])
def delete_record():
    data = request.json
    if not data:
        return jsonify({"error": "Datos de eliminación vacíos."}), 400
        
    try:
        success = delete_confirmed_result(
            salon=data.get('salon'),
            curso=data.get('curso'),
            student_id=data.get('student_id'),
            name=data.get('student_name'),
            report_path=REPORT_PATH
        )
        if success:
            return jsonify({"status": "ok"})
        else:
            return jsonify({"error": "No se pudo actualizar el archivo Excel."}), 500
    except Exception as e:
        return jsonify({"error": f"Error al eliminar registro: {str(e)}"}), 500

@app.route('/clear_records', methods=['POST'])
def clear_records():
    data = request.json
    if not data:
        return jsonify({"error": "Datos de limpieza vacíos."}), 400
        
    try:
        success = clear_salon_results(
            salon=data.get('salon'),
            curso=data.get('curso'),
            report_path=REPORT_PATH
        )
        if success:
            return jsonify({"status": "ok"})
        else:
            return jsonify({"error": "No se pudo limpiar el archivo Excel."}), 500
    except Exception as e:
        return jsonify({"error": f"Error al limpiar registros: {str(e)}"}), 500

@app.route('/get_registry', methods=['GET'])
def get_registry():
    if not os.path.exists(REPORT_PATH):
        return jsonify([])
    try:
        df = pd.read_excel(REPORT_PATH, sheet_name="Detalle General")
        df = df.fillna("")
        for i in range(1, 21):
            if f"Q{i}" in df.columns:
                df[f"Q{i}"] = df[f"Q{i}"].astype(str)
        records = df.to_dict(orient="records")
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": f"No se pudo cargar el registro: {str(e)}"}), 500

@app.route('/get_template', methods=['GET'])
def get_template():
    return jsonify(load_template_config())

@app.route('/save_template', methods=['POST'])
def save_template():
    data = request.json
    if not data:
        return jsonify({"error": "Configuración vacía."}), 400
    try:
        with open('template_config.json', 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": f"Error al guardar coordenadas: {str(e)}"}), 500

@app.route('/get_settings', methods=['GET'])
def get_settings():
    return jsonify(load_settings_config())

@app.route('/save_settings', methods=['POST'])
def save_settings():
    data = request.json
    if not data:
        return jsonify({"error": "Configuración de personalización vacía."}), 400
    try:
        current = load_settings_config()
        if isinstance(data.get("labels"), dict):
            current["labels"] = {**current.get("labels", {}), **data["labels"]}
        if "num_questions" in data:
            current["num_questions"] = max(1, min(20, int(data["num_questions"])))
        if "num_alternatives" in data:
            current["num_alternatives"] = max(2, min(5, int(data["num_alternatives"])))
        if "scoring" in data:
            current["scoring"] = sanitize_scoring(data["scoring"])
        if isinstance(data.get("branding"), dict):
            br = current.get("branding") or {"title": "", "logo": ""}
            if "title" in data["branding"]:
                br["title"] = str(data["branding"].get("title") or "").strip()[:80]
            if "logo" in data["branding"]:
                br["logo"] = str(data["branding"].get("logo") or "").strip()
            current["branding"] = br

        nq = max(1, min(20, int(current.get("num_questions") or 15)))
        na = max(2, min(5, int(current.get("num_alternatives") or 4)))
        current["num_questions"] = nq
        current["num_alternatives"] = na
        current["scoring"] = sanitize_scoring(current.get("scoring"))

        with open('settings_config.json', 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

        update_template_grid_config(nq, na)
        return jsonify({"status": "ok", "settings": current})
    except Exception as e:
        return jsonify({"error": f"No se pudo guardar la configuración: {str(e)}"}), 500


BRANDING_DIR = os.path.join(BASE_DIR, "static", "branding")
BRANDING_LOGO = os.path.join(BRANDING_DIR, "logo.png")


@app.route('/upload_logo', methods=['POST'])
def upload_logo():
    """Logo opcional de plantilla: se reduce a un tamaño de encabezado."""
    f = request.files.get("logo") or request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No se envió un archivo de logo."}), 400
    try:
        from PIL import Image
        os.makedirs(BRANDING_DIR, exist_ok=True)
        img = Image.open(f.stream)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        img.thumbnail((160, 96), resample)
        img.save(BRANDING_LOGO, format="PNG", optimize=True)
        rel = "static/branding/logo.png"
        current = load_settings_config()
        br = current.get("branding") or {"title": "", "logo": ""}
        br["logo"] = rel
        current["branding"] = br
        with open(os.path.join(BASE_DIR, "settings_config.json"), "w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2, ensure_ascii=False)
        return jsonify({"status": "ok", "logo": rel, "w": img.size[0], "h": img.size[1]})
    except Exception as e:
        return jsonify({"error": f"No se pudo procesar el logo: {e}"}), 400


@app.route('/delete_logo', methods=['POST'])
def delete_logo():
    try:
        if os.path.isfile(BRANDING_LOGO):
            os.remove(BRANDING_LOGO)
        current = load_settings_config()
        br = current.get("branding") or {"title": "", "logo": ""}
        br["logo"] = ""
        current["branding"] = br
        with open(os.path.join(BASE_DIR, "settings_config.json"), "w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2, ensure_ascii=False)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_keys', methods=['GET'])
def get_keys():
    if not os.path.exists(CONFIG_PATH):
        return jsonify([])
    try:
        records = load_claves_records(CONFIG_PATH)
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": f"Error al cargar las claves: {str(e)}"}), 500

@app.route('/get_key_meta', methods=['GET'])
def get_key_meta():
    """Devuelve la clave activa de un salón/curso con fingerprint y validación."""
    salon = request.args.get('salon', '')
    curso = request.args.get('curso', '')
    if not salon or not curso:
        return jsonify({"error": "Faltan parámetros salon y curso."}), 400
    try:
        meta = get_answer_key_meta(CONFIG_PATH, salon, curso)
        return jsonify(meta)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/get_keys_summary', methods=['GET'])
def get_keys_summary():
    """Resumen de trakeo de todas las claves (10 salones x 2 cursos)."""
    try:
        return jsonify(list_all_keys_summary(CONFIG_PATH))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/save_keys', methods=['POST'])
def save_keys():
    data = request.json
    if not data:
        return jsonify({"error": "Datos de claves vacíos."}), 400
    try:
        from omr_processor import load_settings_num_questions, validate_answer_key, key_fingerprint
        num_q = load_settings_num_questions(15)
        # Normalizar filas
        cleaned_rows = []
        validation_report = []
        for rec in data:
            salon = str(rec.get("Salon", "")).strip()
            curso = str(rec.get("Curso", "")).strip()
            if not salon or not curso:
                continue
            row = {"Salon": salon, "Curso": curso}
            keys = []
            for i in range(1, num_q + 1):
                val = str(rec.get(f"Q{i}", "A")).upper().strip() or "A"
                row[f"Q{i}"] = val
                keys.append(val)
            ok, warnings = validate_answer_key(keys)
            validation_report.append({
                "Salon": salon,
                "Curso": curso,
                "fingerprint": key_fingerprint(keys),
                "valid": ok,
                "warnings": warnings
            })
            cleaned_rows.append(row)

        save_claves_records(CONFIG_PATH, cleaned_rows, num_questions=num_q)
        return jsonify({"status": "ok", "validation": validation_report})
    except Exception as e:
        return jsonify({"error": f"No se pudieron guardar las claves en Excel: {str(e)}"}), 500

@app.route('/download_report')
def download_report():
    if os.path.exists(REPORT_PATH):
        try:
            return send_file(
                REPORT_PATH,
                as_attachment=True,
                download_name='reporte_resultados.xlsx'
            )
        except Exception as e:
            return jsonify({"error": f"No se pudo descargar el archivo: {str(e)}"}), 500
    else:
        return "Aún no se han calificado exámenes. Califica al menos uno para generar el reporte.", 404

@app.errorhandler(Exception)
def _handle_unexpected(e):
    """Siempre devolver JSON (el front no se queda con 'Error al conectar')."""
    import traceback
    traceback.print_exc()
    try:
        msg = str(e)
    except Exception:
        msg = "Error interno"
    return jsonify({"error": f"Error del servidor: {msg}"}), 500


if __name__ == '__main__':
    # debug=False evita doble proceso reloader y errores raros en Windows
    print(f"[APP] BASE_DIR={BASE_DIR}")
    print(f"[APP] CONFIG={CONFIG_PATH} exists={os.path.exists(CONFIG_PATH)}")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
