"""Chargement des modèles d'emails et documents d'appui (TXT / Markdown) depuis plusieurs sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
MAX_FILE_CHARS = 12000
MAX_TOTAL_CHARS = 400000
MAX_FILES = 200


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1").strip()
    except OSError:
        return ""


def _files_of(source: Path) -> List[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in EXTENSIONS else []
    if source.is_dir():
        return sorted(p for p in source.rglob("*")
                      if p.is_file() and p.suffix.lower() in EXTENSIONS
                      and not any(part.startswith(".") for part in p.relative_to(source).parts))
    return []


def describe_source(path: str) -> Dict[str, Any]:
    """Pour l'interface : type de source et nombre de fichiers lisibles."""
    p = Path(path).expanduser()
    if not p.exists():
        return {"chemin": path, "type": "absent", "nombre": 0}
    files = _files_of(p)
    return {"chemin": path, "type": "dossier" if p.is_dir() else "fichier", "nombre": len(files),
            "nom": p.name or str(p)}


def load_templates(sources: Iterable[str]) -> List[Dict[str, str]]:
    """Charge les fichiers de toutes les sources ; le nom indique la source pour lever les ambiguïtés."""
    out: List[Dict[str, str]] = []
    seen = set()
    total = 0
    for source in sources:
        if not source:
            continue
        root = Path(source).expanduser()
        for path in _files_of(root):
            real = path.resolve()
            if real in seen:
                continue
            seen.add(real)
            text = _read(path)
            if not text:
                continue
            if len(text) > MAX_FILE_CHARS:
                text = text[:MAX_FILE_CHARS] + "\n[… tronqué …]"
            if total + len(text) > MAX_TOTAL_CHARS or len(out) >= MAX_FILES:
                return out
            total += len(text)
            name = path.name if root.is_file() else str(path.relative_to(root))
            if root.is_dir() and root.name:
                name = root.name + "/" + name
            out.append({"nom": name, "texte": text})
    return out
