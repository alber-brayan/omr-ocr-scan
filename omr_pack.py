# -*- coding: utf-8 -*-
"""Pack de la app Lectora OMR: manifiesto + salón/curso/fotos."""
from __future__ import annotations

import json
import os
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

SALONES = [
    "Sec 1", "Sec 2", "Sec 3", "Sec 4", "Sec 5",
    "Prim 2", "Prim 3", "Prim 4", "Prim 5", "Prim 6",
]
CURSOS = ["Matematica", "Comunicacion"]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MANIFEST_NAMES = {"manifest.json", "lote.json", "lote.omr.json"}


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


_SALON_MAP = {_key(s): s for s in SALONES}
_SALON_MAP.update({
    "s1": "Sec 1", "s2": "Sec 2", "s3": "Sec 3", "s4": "Sec 4", "s5": "Sec 5",
    "p2": "Prim 2", "p3": "Prim 3", "p4": "Prim 4", "p5": "Prim 5", "p6": "Prim 6",
    "secundaria1": "Sec 1", "primaria3": "Prim 3",
})
_CURSO_MAP = {_key(c): c for c in CURSOS}
_CURSO_MAP.update({
    "mate": "Matematica", "mat": "Matematica", "matematica": "Matematica",
    "comu": "Comunicacion", "comunicacion": "Comunicacion", "lengua": "Comunicacion",
})


def match_salon(name: str) -> Optional[str]:
    return _SALON_MAP.get(_key(name))


def match_curso(name: str) -> Optional[str]:
    return _CURSO_MAP.get(_key(name))


def parse_rel_path(rel: str) -> Optional[Tuple[str, str]]:
    """
    Extrae (salon, curso) de una ruta tipo:
      Ninabamba/Sec 1/Matematica/001.jpg
      Sec 1/Matematica/001.jpg
    """
    parts = [p for p in (rel or "").replace("\\", "/").split("/") if p and p not in (".", "..")]
    if not parts:
        return None
    last = parts[-1]
    if last.lower() in MANIFEST_NAMES:
        return None
    ext = os.path.splitext(last)[1].lower()
    if ext and ext not in IMAGE_EXT:
        return None
    names = parts[:-1] if ext else parts
    for i, p in enumerate(names):
        curso = match_curso(p)
        if curso and i > 0:
            salon = match_salon(names[i - 1])
            if salon:
                return salon, curso
    return None


def load_manifest(root: str) -> Optional[Dict[str, Any]]:
    for dirpath, _dirs, files in os.walk(root):
        for n in files:
            if n.lower() in MANIFEST_NAMES:
                path = os.path.join(dirpath, n)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
    return None


def list_images(folder: str) -> List[str]:
    out = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXT:
            out.append(os.path.join(folder, name))
    return out


def discover_lots(root: str) -> List[Dict[str, Any]]:
    """
    Devuelve lots: [{salon, curso, folder, files, count}]
    Prefiere manifest.json si apunta a carpetas existentes.
    """
    root = os.path.abspath(root)
    manifest = load_manifest(root)
    lots: List[Dict[str, Any]] = []
    seen = set()

    def add(salon: str, curso: str, files: List[str], folder: str = ""):
        key = (salon, curso)
        if key in seen or not files:
            return
        seen.add(key)
        lots.append({
            "salon": salon,
            "curso": curso,
            "folder": folder,
            "files": files,
            "count": len(files),
        })

    if manifest and isinstance(manifest.get("lots"), list):
        for item in manifest["lots"]:
            salon = match_salon(str(item.get("salon") or ""))
            curso = match_curso(str(item.get("curso") or ""))
            folder = str(item.get("folder") or "")
            if not salon or not curso:
                continue
            candidates = []
            if folder:
                candidates.append(os.path.join(root, folder.replace("/", os.sep)))
            candidates.append(os.path.join(root, salon, curso))
            # manifiesto puede estar en un subdirectorio
            for dirpath, dirs, _files in os.walk(root):
                if os.path.basename(dirpath) == curso and match_salon(os.path.basename(os.path.dirname(dirpath))) == salon:
                    candidates.append(dirpath)
            files = []
            used = ""
            for c in candidates:
                imgs = list_images(c)
                if imgs:
                    files = imgs
                    used = c
                    break
            add(salon, curso, files, used)

    # Recorrido por rutas, por si el manifiesto faltó o está incompleto
    for dirpath, _dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        parsed = parse_rel_path(rel.replace("\\", "/") + "/x.jpg")
        if not parsed:
            continue
        salon, curso = parsed
        imgs = [os.path.join(dirpath, f) for f in sorted(files)
                if os.path.splitext(f)[1].lower() in IMAGE_EXT]
        add(salon, curso, imgs, dirpath)

    lots.sort(key=lambda x: (x["salon"], x["curso"]))
    return lots


def safe_extract_zip(zip_path: str, dest: str) -> None:
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            if name.startswith("/") or any(p == ".." for p in name.split("/")):
                continue
            target = os.path.abspath(os.path.join(dest, name))
            if not (target == dest or target.startswith(dest + os.sep)):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
