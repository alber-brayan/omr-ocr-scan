from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import json
import io
import zipfile
import uuid
import pandas as pd
import werkzeug
from omr_processor import (
    process_exam_image, record_confirmed_result, load_template_config,
    delete_confirmed_result, clear_salon_results, get_answer_key_meta,
    list_all_keys_summary, normalize_key_id
)
from sheet_pdf import build_sheet_pdf, resolve_theme

# Rutas absolutas (evita fallos si el CWD del servidor no es la carpeta del proyecto)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

app = Flask(__name__, template_folder='templates', static_folder='static')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
CONFIG_PATH = os.path.join(BASE_DIR, 'configuracion_ejemplo.xlsx')
REPORT_PATH = os.path.join(BASE_DIR, 'reporte_resultados.xlsx')
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'static', 'processed')
BATCH_FOLDER = os.path.join(PROCESSED_FOLDER, 'batches')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(BATCH_FOLDER, exist_ok=True)

# Último lote en memoria (batch_id → lista de rutas de imágenes calificadas)
_LAST_BATCH = {"id": None, "images": [], "meta": {}}


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
        "num_questions": 15
    }
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
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

        # Preserve / default OCR field ROIs (header + footer of real sheets)
        if "ocr_fields" not in layout or "header" not in layout.get("ocr_fields", {}):
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
        layout["mark_threshold"] = layout.get("mark_threshold", 95.0)

        mid = (num_q + 1) // 2
        from sheet_pdf import geometry_to_warped_canvas, get_omr_geometry
        canvas = geometry_to_warped_canvas(get_omr_geometry(int(num_q), int(num_alt)))
        options_list = list(canvas["options"])
        x_coords_left = canvas["x_left"]
        x_coords_right = canvas["x_right"]
        y_start = canvas["y_start_left"]
        y_step = canvas["y_step"]

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
    return render_template('sheet.html', config=config, theme=theme)


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


@app.route('/batch_scan', methods=['POST'])
def batch_scan():
    """
    Procesa un lote de fichas:
    - Redimensiona a max 1000px
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

    results = []
    errors = []
    graded_paths = []

    for i, file in enumerate(files):
        if not file or not file.filename:
            continue
        idx = start_index + i
        filename = werkzeug.utils.secure_filename(file.filename)
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            filename += '.jpg'
        # prefijo de orden para no colisionar nombres
        filename = f"{idx:02d}_{filename}"
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
                output_dir=batch_dir,
                student_index=idx,
                skip_ocr=True,
                max_image_side=2500,
                max_megapixels=20.0
            )
            # Auto-registro en Excel
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
            errors.append({"file": file.filename, "error": str(e), "index": idx})

    _LAST_BATCH["id"] = batch_id
    _LAST_BATCH["images"] = graded_paths
    _LAST_BATCH["meta"] = {
        "salon": salon, "curso": curso, "colegio": colegio, "lugar": lugar,
        "count": len(results)
    }

    return jsonify(_json_safe({
        "batch_id": batch_id,
        "processed": len(results),
        "errors": errors,
        "results": results,
        "download_pdf_url": f"/download_batch_pdf?batch_id={batch_id}",
        "download_pngs_url": f"/download_batch_pngs?batch_id={batch_id}",
    }))


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
    """PDF multipágina con todas las cartillas calificadas del lote."""
    batch_id = request.args.get('batch_id') or _LAST_BATCH.get("id")
    paths = _batch_image_paths(batch_id)
    if not paths:
        return jsonify({"error": "No hay imágenes de lote para descargar."}), 404

    try:
        from PIL import Image
    except ImportError:
        return jsonify({"error": "Falta Pillow (pip install Pillow) para exportar PDF."}), 500

    try:
        pil_images = []
        for p in paths:
            im = Image.open(p)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            else:
                im = im.convert("RGB")
            pil_images.append(im)

        buf = io.BytesIO()
        first, rest = pil_images[0], pil_images[1:]
        first.save(buf, format="PDF", save_all=True, append_images=rest)
        buf.seek(0)
        meta = _LAST_BATCH.get("meta") or {}
        name = f"lote_{meta.get('salon', 'salon')}_{meta.get('curso', 'curso')}_{batch_id}.pdf"
        name = name.replace(" ", "_")
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
        meta = _LAST_BATCH.get("meta") or {}
        name = f"lote_png_{meta.get('salon', 'salon')}_{meta.get('curso', 'curso')}_{batch_id}.zip"
        name = name.replace(" ", "_")
        return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"No se pudo crear el ZIP: {e}"}), 500

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
        for i in range(1, 16):
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
        # Save labels customization file
        with open('settings_config.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        # Automatically update template coordinate vectors for matching bubbles count
        update_template_grid_config(int(data["num_questions"]), int(data["num_alternatives"]))
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": f"No se pudo guardar la configuración: {str(e)}"}), 500

@app.route('/get_keys', methods=['GET'])
def get_keys():
    if not os.path.exists(CONFIG_PATH):
        return jsonify([])
    try:
        df = pd.read_excel(CONFIG_PATH, sheet_name="Claves")
        df = df.fillna("")
        records = df.to_dict(orient="records")
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
        # Convert list of dicts to DataFrame
        keys_df = pd.DataFrame(data)

        # Asegurar columnas Q1..Qn en orden + Salon/Curso
        from omr_processor import load_settings_num_questions, validate_answer_key, extract_keys_from_row, key_fingerprint
        num_q = load_settings_num_questions(15)
        q_cols = [f"Q{i}" for i in range(1, num_q + 1)]
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

        keys_df = pd.DataFrame(cleaned_rows)
        # Orden de columnas estable: Salon, Curso, Q1..Qn
        col_order = ["Salon", "Curso"] + q_cols
        for c in col_order:
            if c not in keys_df.columns:
                keys_df[c] = ""
        keys_df = keys_df[col_order]
        
        # Read students tab first so we don't wipe it out
        students_df = pd.read_excel(CONFIG_PATH, sheet_name="Alumnos")
        
        # Write both back
        with pd.ExcelWriter(CONFIG_PATH, engine="openpyxl") as writer:
            students_df.to_excel(writer, sheet_name="Alumnos", index=False)
            keys_df.to_excel(writer, sheet_name="Claves", index=False)
            
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
