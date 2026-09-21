# -*- coding: utf-8 -*-
"""
Extrae claves resaltadas en amarillo de los Word en EXAMENES
y las escribe en los Excel de claves del mismo folder.

Uso (proxima vez):
    python extraer_claves.py

Reglas:
    - LECTURA = COMUNICACION
    - Solo se llena desde 2do de primaria en adelante (inicial y 1ro se omiten)
    - 15 preguntas por examen (filas 4-18 de cada Excel)
"""
from __future__ import annotations

import re
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

BASE_DIR = Path(__file__).resolve().parent
EXAMENES_DIR = BASE_DIR / "EXAMENES"
REPORT_PATH = EXAMENES_DIR / "reporte_llenado_claves.txt"
BACKUP_DIR = EXAMENES_DIR / "_backup_claves_previas"

EXPECTED_QUESTIONS = 15
HEADER_ROW = 3
FIRST_DATA_ROW = 4

HIGHLIGHT_OK = {
    "yellow", "green", "cyan", "magenta", "red", "blue",
    "darkyellow", "darkgreen", "darkcyan", "darkmagenta",
    "darkred", "darkblue", "lightgray", "darkgray",
}
YELLOW_FILLS = {
    "FFFF00", "FFFFFF00", "FFFF99", "FFC000", "FFEB9C", "FFF2CC",
    "FFD966", "FFEE99", "FFF59D", "FFFF66", "FFD700", "FFF4B3",
    "FFED8A", "FFE699", "FFFFA6", "FFFF99",
}

# Solo A) B) C) D) — no "C." ni "n(A)" ni "D.P."
OPTION_RE = re.compile(r"(?<!\()([A-Da-d])\s*\)")
WORD_NAME_RE = re.compile(
    r"^(LECTURA|COMUNICACION|COMUNICACIÓN|MATEMATICA|MATEMÁTICA)\s+"
    r"(INICIAL|PRIMARIA|SECUNDARIA)\s+"
    r"(03|04|05|1RO|2DO|3RO|4TO|5TO|6TO)$",
    re.IGNORECASE,
)

NIVEL_EXCEL = {
    ("COMUNICACIÓN", "PRIMARIA", "1RO"): ("CLAVES COMUNICACIÓN PRIMARIA I.xlsx", "1RO"),
    ("COMUNICACIÓN", "PRIMARIA", "2DO"): ("CLAVES COMUNICACIÓN PRIMARIA I.xlsx", "2DO"),
    ("COMUNICACIÓN", "PRIMARIA", "3RO"): ("CLAVES COMUNICACIÓN PRIMARIA I.xlsx", "3RO"),
    ("COMUNICACIÓN", "PRIMARIA", "4TO"): ("CLAVES COMUNICACIÓN PRIMARIA II.xlsx", "4TO"),
    ("COMUNICACIÓN", "PRIMARIA", "5TO"): ("CLAVES COMUNICACIÓN PRIMARIA II.xlsx", "5TO"),
    ("COMUNICACIÓN", "PRIMARIA", "6TO"): ("CLAVES COMUNICACIÓN PRIMARIA II.xlsx", "6TO"),
    ("COMUNICACIÓN", "SECUNDARIA", "1RO"): ("CLAVES COMUNICACIÓN SECUNDARIA.xlsx", "1RO"),
    ("COMUNICACIÓN", "SECUNDARIA", "2DO"): ("CLAVES COMUNICACIÓN SECUNDARIA.xlsx", "2DO"),
    ("COMUNICACIÓN", "SECUNDARIA", "3RO"): ("CLAVES COMUNICACIÓN SECUNDARIA.xlsx", "3RO"),
    ("COMUNICACIÓN", "SECUNDARIA", "4TO"): ("CLAVES COMUNICACIÓN SECUNDARIA.xlsx", "4TO"),
    ("COMUNICACIÓN", "SECUNDARIA", "5TO"): ("CLAVES COMUNICACIÓN SECUNDARIA.xlsx", "5TO"),
    ("MATEMÁTICA", "PRIMARIA", "1RO"): ("CLAVES MATEMÁTICA PRIMARIA I.xlsx", "1RO"),
    ("MATEMÁTICA", "PRIMARIA", "2DO"): ("CLAVES MATEMÁTICA PRIMARIA I.xlsx", "2DO"),
    ("MATEMÁTICA", "PRIMARIA", "3RO"): ("CLAVES MATEMÁTICA PRIMARIA I.xlsx", "3RO"),
    ("MATEMÁTICA", "PRIMARIA", "4TO"): ("CLAVES MATEMÁTICA PRIMARIA II.xlsx", "4TO"),
    ("MATEMÁTICA", "PRIMARIA", "5TO"): ("CLAVES MATEMÁTICA PRIMARIA II.xlsx", "5TO"),
    ("MATEMÁTICA", "PRIMARIA", "6TO"): ("CLAVES MATEMÁTICA PRIMARIA II.xlsx", "6TO"),
    ("MATEMÁTICA", "SECUNDARIA", "1RO"): ("CLAVES MATEMÁTICA SECUNDARIA.xlsx", "1RO"),
    ("MATEMÁTICA", "SECUNDARIA", "2DO"): ("CLAVES MATEMÁTICA SECUNDARIA.xlsx", "2DO"),
    ("MATEMÁTICA", "SECUNDARIA", "3RO"): ("CLAVES MATEMÁTICA SECUNDARIA.xlsx", "3RO"),
    ("MATEMÁTICA", "SECUNDARIA", "4TO"): ("CLAVES MATEMÁTICA SECUNDARIA.xlsx", "4TO"),
    ("MATEMÁTICA", "SECUNDARIA", "5TO"): ("CLAVES MATEMÁTICA SECUNDARIA.xlsx", "5TO"),
}

SKIP_GRADOS = {
    ("INICIAL", "03"),
    ("INICIAL", "04"),
    ("INICIAL", "05"),
    ("PRIMARIA", "1RO"),
}


def q(el, attr):
    return el.get(W + attr) if el is not None else None


def fold(s: str) -> str:
    table = str.maketrans("ÁÉÍÓÚÜáéíóúü", "AEIOUUaeiouu")
    return (s or "").translate(table).upper().strip()


def run_text(r) -> str:
    return "".join(r.xpath(".//w:t/text()", namespaces=NS))


def run_is_marked(r) -> bool:
    hl = r.find(".//w:highlight", NS)
    if hl is not None:
        val = (q(hl, "val") or "").lower()
        if val in HIGHLIGHT_OK:
            return True
    shd = r.find(".//w:shd", NS)
    if shd is not None:
        fill = (q(shd, "fill") or "").upper().replace("#", "")
        if fill in YELLOW_FILLS:
            return True
        if len(fill) == 8 and fill.startswith("FF"):
            fill = fill[2:]
        if fill in {x[-6:] if len(x) == 8 else x for x in YELLOW_FILLS}:
            return True
    return False


def load_numbering(zfile) -> dict:
    if "word/numbering.xml" not in zfile.namelist():
        return {}
    numbering = etree.fromstring(zfile.read("word/numbering.xml"))
    abstracts = {}
    for absn in numbering.findall("w:abstractNum", NS):
        aid = q(absn, "abstractNumId")
        levels = {}
        for lvl in absn.findall("w:lvl", NS):
            ilvl = q(lvl, "ilvl") or "0"
            fmt_el = lvl.find("w:numFmt", NS)
            start_el = lvl.find("w:start", NS)
            text_el = lvl.find("w:lvlText", NS)
            levels[ilvl] = {
                "fmt": q(fmt_el, "val") if fmt_el is not None else "",
                "start": int(q(start_el, "val") or "1"),
                "text": q(text_el, "val") if text_el is not None else "",
            }
        abstracts[aid] = levels
    nums = {}
    for num in numbering.findall("w:num", NS):
        nid = q(num, "numId")
        absid = num.find("w:abstractNumId", NS)
        nums[nid] = abstracts.get(q(absid, "val") if absid is not None else None, {})
    return nums


def letter_from_index(idx: int):
    if 1 <= idx <= 26:
        return chr(ord("A") + idx - 1)
    return None


def para_numbering(p, nums, counters):
    numPr = p.find("w:pPr/w:numPr", NS)
    if numPr is None:
        return None, "", None
    nid_el = numPr.find("w:numId", NS)
    ilvl_el = numPr.find("w:ilvl", NS)
    nid = q(nid_el, "val") if nid_el is not None else None
    ilvl = q(ilvl_el, "val") if ilvl_el is not None else "0"
    lvl = nums.get(nid, {}).get(ilvl, {})
    fmt = lvl.get("fmt", "")
    counters[nid][ilvl] += 1
    idx = counters[nid][ilvl]
    letter = letter_from_index(idx) if fmt == "upperLetter" else None
    return nid, fmt, letter


def char_yellow_mask(runs) -> tuple[str, list[bool]]:
    chars = []
    mask = []
    for r in runs:
        t = run_text(r)
        marked = run_is_marked(r)
        for ch in t:
            chars.append(ch)
            mask.append(marked)
    return "".join(chars), mask


def span_is_yellow(mask, start, end) -> bool:
    if start >= end or start >= len(mask):
        return False
    end = min(end, len(mask))
    chunk = mask[start:end]
    return any(chunk)


def options_from_inline(text: str, mask: list[bool]) -> list[dict]:
    spans = list(OPTION_RE.finditer(text))
    if not spans:
        return []
    options = []
    for i, m in enumerate(spans):
        start = m.start()
        end = spans[i + 1].start() if i + 1 < len(spans) else len(text)
        letter = m.group(1).upper()
        opt_text = text[start:end]
        yellow = span_is_yellow(mask, start, end)
        options.append({"letter": letter, "text": opt_text.strip(), "yellow": yellow})
    return options


def parse_word_filename(path: Path):
    stem = fold(path.stem)
    m = WORD_NAME_RE.match(stem)
    if not m:
        return None
    raw_curso, nivel, grado = m.group(1), m.group(2).upper(), m.group(3).upper()
    curso = "COMUNICACIÓN" if fold(raw_curso) in {"LECTURA", "COMUNICACION"} else "MATEMÁTICA"
    return {"curso": curso, "nivel": nivel, "grado": grado, "path": path}


def _letters(options: list[dict]) -> set:
    return {o["letter"] for o in options}


def _is_full_abcd(options: list[dict]) -> bool:
    return {"A", "B", "C", "D"} <= _letters(options)


def _is_keepable_group(options: list[dict]) -> bool:
    """Primaria a veces tiene solo A B C; el resto suele ser A-D."""
    letters = _letters(options)
    return {"A", "B", "C"} <= letters


def extract_question_groups(docx_path: Path) -> list[dict]:
    with zipfile.ZipFile(docx_path) as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
        nums = load_numbering(zf)

    counters = defaultdict(lambda: defaultdict(int))
    groups: list[list[dict]] = []
    current: list[dict] = []

    def flush():
        nonlocal current
        if current:
            groups.append(current)
            current = []

    for p in root.findall(".//w:p", NS):
        runs = p.findall(".//w:r", NS)
        text, mask = char_yellow_mask(runs)
        _nid, fmt, letter_num = para_numbering(p, nums, counters)

        if fmt and "decimal" in (fmt or "") and "PREGUNTA" in (nums.get(_nid, {}).get("0", {}).get("text") or "").upper():
            if _is_full_abcd(current) or (
                current and letter_num is None and _is_keepable_group(current)
            ):
                flush()
            continue

        options = []
        if letter_num in {"A", "B", "C", "D"}:
            options = [{
                "letter": letter_num,
                "text": text.strip(),
                "yellow": any(mask) and bool(text.strip()),
            }]
        else:
            inline = options_from_inline(text, mask)
            if inline:
                options = inline

        if not options:
            if _is_full_abcd(current):
                flush()
            continue

        first_letter = options[0]["letter"]
        if current and first_letter == "A" and "A" in _letters(current):
            flush()
        elif current and _is_full_abcd(current) and len(options) < 2 and first_letter != "A":
            # Texto con un "D)" aislado despues de una pregunta A-D ya completa.
            continue
        current.extend(options)

    flush()

    cleaned = []
    for g in groups:
        if _is_keepable_group(g):
            cleaned.append(g)
    return cleaned


def answer_from_group(options: list[dict]) -> tuple[str | None, str]:
    yellows = [o["letter"] for o in options if o.get("yellow")]
    yellows = list(dict.fromkeys(yellows))
    if len(yellows) == 1:
        return yellows[0], "ok"
    if len(yellows) > 1:
        return None, "ambiguo: se resaltaron " + " y ".join(yellows)
    return None, "sin resaltado amarillo en las alternativas"


def extract_keys_from_docx(docx_path: Path) -> dict:
    groups = extract_question_groups(docx_path)
    keys = []
    issues = []
    for i, opts in enumerate(groups, start=1):
        letter, note = answer_from_group(opts)
        keys.append(letter)
        if letter is None:
            issues.append("Pregunta %d: %s" % (i, note))
        elif note != "ok":
            issues.append("Pregunta %d: %s" % (i, note))

    extra = ""
    if len(keys) > EXPECTED_QUESTIONS:
        extra = "Se detectaron %d bloques de alternativas; se usaran las primeras %d." % (
            len(keys), EXPECTED_QUESTIONS,
        )
        keys = keys[:EXPECTED_QUESTIONS]
        issues = [x for x in issues if _issue_qnum(x) <= EXPECTED_QUESTIONS]
        issues.append(extra)
    elif len(keys) < EXPECTED_QUESTIONS:
        missing = EXPECTED_QUESTIONS - len(keys)
        issues.append(
            "Solo se detectaron %d bloques de alternativas (se esperaban %d). Faltan %d pregunta(s)."
            % (len(keys), EXPECTED_QUESTIONS, missing)
        )
        keys.extend([None] * missing)

    n_ok = sum(1 for k in keys if k)
    if n_ok == 0:
        issues = [
            "No hay alternativas resaltadas en amarillo en este Word. Hay que llenar las 15 claves a mano."
        ]

    return {
        "keys": keys,
        "issues": issues,
        "n_groups": len(groups),
        "n_ok": n_ok,
    }


def _issue_qnum(text: str) -> int:
    m = re.match(r"Pregunta (\d+):", text)
    return int(m.group(1)) if m else 0


def ensure_grade_headers(ws, needed):
    """Completa encabezados de grado vacios (ej. COMUNICACION PRIMARIA II)."""
    existing = {}
    for col in range(2, 12):
        val = ws.cell(HEADER_ROW, col).value
        if val:
            existing[fold(str(val))] = col
    next_col = 2
    while ws.cell(HEADER_ROW, next_col).value or (next_col in existing.values()):
        if ws.cell(HEADER_ROW, next_col).value:
            next_col += 1
            continue
        break
    template = ws.cell(HEADER_ROW, 2)
    for grado in needed:
        key = fold(grado)
        if key in existing:
            continue
        # usa la primera columna vacia a partir de B
        col = None
        for c in range(2, 12):
            if not ws.cell(HEADER_ROW, c).value:
                col = c
                break
        if col is None:
            continue
        cell = ws.cell(HEADER_ROW, col, grado)
        if template.font:
            cell.font = Font(
                name=template.font.name,
                size=template.font.size,
                bold=template.font.bold,
                color=template.font.color,
            )
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if template.border:
            cell.border = Border(
                left=template.border.left,
                right=template.border.right,
                top=template.border.top,
                bottom=template.border.bottom,
            )
        if template.fill:
            cell.fill = PatternFill(
                fill_type=template.fill.fill_type,
                fgColor=template.fill.fgColor,
                bgColor=template.fill.bgColor,
            )
        existing[key] = col
    return existing


def column_for_grado(ws, grado: str) -> int | None:
    target = fold(grado)
    for col in range(2, 12):
        val = ws.cell(HEADER_ROW, col).value
        if val and fold(str(val)) == target:
            return col
    return None


def write_keys_to_excel(xlsx_path: Path, grado: str, keys: list, report_lines: list) -> dict:
    wb = load_workbook(xlsx_path)
    ws = wb.active
    ensure_grade_headers(ws, [grado])
    col = column_for_grado(ws, grado)
    if col is None:
        return {
            "ok": False,
            "filled": 0,
            "error": "No se encontro la columna de grado %s en %s" % (grado, xlsx_path.name),
        }

    filled = 0
    overwritten = []
    skipped = []
    for i, letter in enumerate(keys):
        row = FIRST_DATA_ROW + i
        cell = ws.cell(row, col)
        old = cell.value
        old_s = str(old).strip().upper() if old is not None and str(old).strip() else ""
        if not letter:
            skipped.append(i + 1)
            if old_s:
                cell.value = None
            continue
        if old_s and old_s != letter:
            overwritten.append((i + 1, old_s, letter))
        cell.value = letter
        filled += 1

    wb.save(xlsx_path)
    return {
        "ok": True,
        "filled": filled,
        "overwritten": overwritten,
        "skipped": skipped,
        "column": col,
    }


def backup_excels():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / stamp
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in EXAMENES_DIR.glob("CLAVES *.xlsx"):
        shutil.copy2(f, dest / f.name)
        copied.append(f.name)
    return dest, copied


def main():
    if not EXAMENES_DIR.exists():
        raise SystemExit("No existe la carpeta EXAMENES")

    backup_dir, backed = backup_excels()
    word_files = sorted(EXAMENES_DIR.glob("*.docx"))
    parsed = []
    unknown = []
    for fp in word_files:
        info = parse_word_filename(fp)
        if info:
            parsed.append(info)
        else:
            unknown.append(fp.name)

    results = []
    for info in parsed:
        curso, nivel, grado = info["curso"], info["nivel"], info["grado"]
        item = {
            "file": info["path"].name,
            "curso": curso,
            "nivel": nivel,
            "grado": grado,
            "status": "",
            "keys": [],
            "issues": [],
            "excel": "",
            "notes": [],
        }
        if (nivel, grado) in SKIP_GRADOS:
            item["status"] = "omitido"
            item["notes"].append(
                "Omitido: la lectora optica se usa desde 2do grado de primaria en adelante."
            )
            results.append(item)
            continue

        mapping = NIVEL_EXCEL.get((curso, nivel, grado))
        if not mapping:
            item["status"] = "dificultad"
            item["issues"].append("No hay Excel de destino para %s %s %s" % (curso, nivel, grado))
            results.append(item)
            continue

        xlsx_name, col_grado = mapping
        xlsx_path = EXAMENES_DIR / xlsx_name
        item["excel"] = xlsx_name
        if not xlsx_path.exists():
            item["status"] = "dificultad"
            item["issues"].append("No existe el Excel %s" % xlsx_name)
            results.append(item)
            continue

        extracted = extract_keys_from_docx(info["path"])
        item["keys"] = extracted["keys"]
        item["issues"] = extracted["issues"]
        n_ok = extracted["n_ok"]

        try:
            write = write_keys_to_excel(xlsx_path, col_grado, extracted["keys"], item["notes"])
        except PermissionError:
            item["status"] = "dificultad"
            item["issues"].append(
                "No se pudo guardar %s (cierra el archivo en Excel e intenta de nuevo)." % xlsx_name
            )
            results.append(item)
            continue
        if not write.get("ok"):
            item["status"] = "dificultad"
            item["issues"].append(write.get("error") or "No se pudo escribir el Excel")
            results.append(item)
            continue

        if write.get("overwritten"):
            for qn, old, new in write["overwritten"]:
                item["notes"].append(
                    "Pregunta %d: se reemplazo %s (valor previo del Excel) por %s (Word)."
                    % (qn, old, new)
                )

        if n_ok == EXPECTED_QUESTIONS and not extracted["issues"]:
            item["status"] = "exito"
        elif n_ok == 0:
            item["status"] = "dificultad"
        else:
            item["status"] = "parcial"
            item["issues"].append(
                "Se llenaron %d/%d claves. Las preguntas sin clave quedaron vacias para llenado manual."
                % (n_ok, EXPECTED_QUESTIONS)
            )
        results.append(item)

    write_report(results, backup_dir, backed, unknown)
    print("Listo. Reporte:", REPORT_PATH)
    return results


def write_report(results, backup_dir, backed, unknown):
    lines = []
    lines.append("REPORTE DE LLENADO DE CLAVES")
    lines.append("Fecha: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("Carpeta: %s" % EXAMENES_DIR)
    lines.append("Respaldo de Excel previos: %s" % backup_dir)
    lines.append("")
    lines.append("Resumen")
    lines.append("-" * 60)

    exito = [r for r in results if r["status"] == "exito"]
    parcial = [r for r in results if r["status"] == "parcial"]
    dific = [r for r in results if r["status"] == "dificultad"]
    omit = [r for r in results if r["status"] == "omitido"]

    lines.append("Exito (15/15 claves llenadas): %d" % len(exito))
    lines.append("Parcial (faltan claves, llenar a mano): %d" % len(parcial))
    lines.append("Dificultad (no se pudo llenar): %d" % len(dific))
    lines.append("Omitidos (inicial / 1ro primaria): %d" % len(omit))
    lines.append("")

    def block(title, items, show_keys=True):
        lines.append(title)
        lines.append("=" * 60)
        if not items:
            lines.append("(ninguno)")
            lines.append("")
            return
        for r in items:
            lines.append("%s  [%s %s %s]" % (r["file"], r["curso"], r["nivel"], r["grado"]))
            if r.get("excel"):
                lines.append("  Excel: %s" % r["excel"])
            if show_keys and r.get("keys"):
                compact = " ".join(k if k else "-" for k in r["keys"])
                lines.append("  Claves: %s" % compact)
            for n in r.get("notes") or []:
                lines.append("  Nota: %s" % n)
            for iss in r.get("issues") or []:
                lines.append("  Dificultad: %s" % iss)
            if r["status"] == "dificultad":
                lines.append("  ACCION: llenar este grado MANUALMENTE en el Excel.")
            elif r["status"] == "parcial":
                missing = [str(i + 1) for i, k in enumerate(r.get("keys") or []) if not k]
                if missing:
                    lines.append("  ACCION: llenar a mano las preguntas: %s" % ", ".join(missing))
            lines.append("")

    block("1) LLENADO CON EXITO", exito)
    block("2) LLENADO PARCIAL (revisar / completar a mano)", parcial)
    block("3) DIFICULTADES (llenar a mano)", dific)
    block("4) OMITIDOS", omit, show_keys=False)

    if unknown:
        lines.append("Archivos Word no reconocidos")
        lines.append("=" * 60)
        for name in unknown:
            lines.append("  - %s" % name)
        lines.append("")

    lines.append("Como repetir este proceso la proxima vez")
    lines.append("=" * 60)
    lines.append("1. Copia los Word del examen (claves en amarillo) a la carpeta EXAMENES.")
    lines.append("2. Asegurate de que existan los Excel CLAVES COMUNICACION/MATEMATICA.")
    lines.append("3. Ejecuta:  python extraer_claves.py")
    lines.append("4. Revisa este reporte. Lo que salga como dificultad, llenalo a mano.")
    lines.append("Nota: LECTURA y COMUNICACION se tratan como el mismo curso.")
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
