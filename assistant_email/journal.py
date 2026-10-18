"""Journal de bord : ~/Library/Application Support/AssistantEmail/journal.log (utile pour diagnostiquer)."""
from __future__ import annotations

import time
import traceback

from . import config


def ecrire(message: str) -> None:
    try:
        path = config.app_home() / "journal.log"
        if path.exists() and path.stat().st_size > 500000:   # évite un fichier qui grossit sans fin
            path.write_text(path.read_text(errors="ignore")[-100000:])
        with path.open("a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def erreur(contexte: str) -> None:
    ecrire("ERREUR %s\n%s" % (contexte, traceback.format_exc()))
