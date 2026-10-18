"""Sauvegarde automatique, export et import des profils et réglages (les mots de passe restent dans le Trousseau)."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__, config

FICHIERS = ("profils.json", "reglages.json")
GARDER = 20


def dossier() -> Path:
    d = config.app_home() / "Sauvegardes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _empreinte() -> str:
    h = hashlib.sha256()
    for name in FICHIERS:
        p = config.app_home() / name
        h.update(p.read_bytes() if p.exists() else b"-")
    return h.hexdigest()


def sauvegarder_si_modifie() -> Optional[Path]:
    """Copie datée des deux fichiers si leur contenu a changé depuis la dernière sauvegarde."""
    if not any((config.app_home() / n).exists() for n in FICHIERS):
        return None
    marque = dossier() / ".derniere"
    actuel = _empreinte()
    if marque.exists() and marque.read_text(encoding="utf-8") == actuel:
        return None
    cible = dossier() / datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 1
    while cible.exists():
        n += 1
        cible = dossier() / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-%d" % n)
    cible.mkdir()
    for name in FICHIERS:
        p = config.app_home() / name
        if p.exists():
            shutil.copy2(p, cible / name)
    marque.write_text(actuel, encoding="utf-8")
    anciennes = sorted(d for d in dossier().iterdir() if d.is_dir())
    for d in anciennes[:-GARDER]:
        shutil.rmtree(d, ignore_errors=True)
    return cible


def exporter(vers: Optional[Path] = None) -> Path:
    vers = vers or (Path.home() / "Downloads" / ("AssistantEmail-reglages-%s.json" % datetime.now().strftime("%Y%m%d")))
    vers.parent.mkdir(parents=True, exist_ok=True)
    data = {"application": "AssistantEmail", "version": __version__, "reglages": config.load_settings(),
            "profils": config.load_profiles()}
    vers.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return vers


def importer(depuis: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(depuis).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Fichier illisible : %s" % exc)
    if data.get("application") != "AssistantEmail" or not isinstance(data.get("profils"), list):
        raise ValueError("Ce fichier n'est pas une sauvegarde d'Assistant Email.")
    sauvegarder_si_modifie()  # l'état actuel reste récupérable
    config._write_json(config.app_home() / "profils.json", data["profils"])
    config._write_json(config.app_home() / "reglages.json", data.get("reglages") or {})
    return {"profils": len(data["profils"])}
