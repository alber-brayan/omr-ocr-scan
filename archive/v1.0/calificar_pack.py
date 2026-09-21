# -*- coding: utf-8 -*-
"""
Califica un pack exportado por la app (carpeta o ZIP con manifest.json).

Uso:
  python calificar_pack.py "D:\\Descargas\\LectoraOMR\\Ninabamba.zip"
  python calificar_pack.py "D:\\Ninabamba"
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid

from omr_pack import discover_lots, safe_extract_zip


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Arrastra un ZIP o una carpeta sobre CalificarPack.bat")
        print("o: python calificar_pack.py <ruta>")
        return 2
    src = os.path.abspath(argv[0])
    colegio = argv[1] if len(argv) > 1 else "Colegio S/N"
    lugar = argv[2] if len(argv) > 2 else "Lugar S/N"
    if not os.path.exists(src):
        print("No existe:", src)
        return 1

    tmp = None
    root = src
    if os.path.isfile(src) and src.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="omrpack_")
        safe_extract_zip(src, tmp)
        root = tmp

    lots = discover_lots(root)
    if not lots:
        print("No se detectaron salones/cursos en", src)
        return 1

    from omr_processor import process_exam_image, record_confirmed_result

    base = os.path.dirname(os.path.abspath(__file__))
    CONFIG_PATH = os.path.join(base, "configuracion_ejemplo.xlsx")
    REPORT_PATH = os.path.join(base, "reporte_resultados.xlsx")
    BATCH_FOLDER = os.path.join(base, "static", "processed", "batches")
    os.makedirs(BATCH_FOLDER, exist_ok=True)

    from app import build_lote_export_pdf, _lote_filename

    pdf_parent = src if os.path.isdir(src) else os.path.dirname(src)
    pdf_dir = os.path.join(pdf_parent, "PDFs_calificados")
    os.makedirs(pdf_dir, exist_ok=True)
    pack_name = os.path.splitext(os.path.basename(src.rstrip("\\/")))[0]
    print(f"Pack: {pack_name} · {len(lots)} lotes · {sum(l['count'] for l in lots)} fichas")
    print(f"PDFs → {pdf_dir}")
    total = 0
    for lot in lots:
        salon, curso = lot["salon"], lot["curso"]
        batch_id = uuid.uuid4().hex[:12]
        out = os.path.join(BATCH_FOLDER, batch_id)
        os.makedirs(out, exist_ok=True)
        print(f"\n== {salon} / {curso} ({lot['count']}) ==")
        for i, path in enumerate(lot["files"], start=1):
            try:
                r = process_exam_image(
                    image_path=path,
                    salon=salon,
                    curso=curso,
                    colegio=colegio,
                    lugar=lugar,
                    config_path=CONFIG_PATH,
                    output_dir=out,
                    student_index=i,
                    skip_ocr=True,
                )
                record_confirmed_result(
                    salon=salon,
                    curso=curso,
                    colegio=colegio,
                    lugar=lugar,
                    student_id=r.get("student_id"),
                    name=r.get("student_name"),
                    buenas=r.get("buenas"),
                    malas=r.get("malas"),
                    en_blanco=r.get("en_blanco"),
                    score=r.get("puntaje"),
                    hora=r.get("hora_entrega") or "",
                    orden_entrega=r.get("orden_entrega") or r.get("student_id"),
                    answers=r.get("answers") or [],
                    report_path=REPORT_PATH,
                    clave_fingerprint=r.get("clave_fingerprint", ""),
                    clave_id=r.get("clave_id", ""),
                    grado=r.get("grado") or "",
                    graded_at=r.get("graded_at") or "",
                    graded_on_pc=r.get("graded_on_pc") or "",
                )
                total += 1
                print(f"  Est {i:02d}  {r.get('buenas')}B {r.get('malas')}M {r.get('en_blanco')}Bl  {r.get('puntaje')} pts")
            except Exception as exc:
                print(f"  Est {i:02d} ERROR {os.path.basename(path)}: {exc}")
        graded = [
            os.path.join(out, f) for f in sorted(os.listdir(out))
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        if graded:
            meta = {"salon": salon, "curso": curso, "pack_name": pack_name, "count": len(graded)}
            pdf_name = _lote_filename(meta, "pdf")
            pdf_bytes = build_lote_export_pdf(graded, meta=meta, batch_id=batch_id)
            dest = os.path.join(pdf_dir, pdf_name)
            with open(dest, "wb") as fh:
                fh.write(pdf_bytes)
            print(f"  PDF listo: {dest}")
        print(f"  imágenes: static/processed/batches/{batch_id}")
    print(f"\nListo: {total} fichas calificadas.")
    if tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
