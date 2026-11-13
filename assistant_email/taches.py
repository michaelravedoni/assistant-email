"""Rédactions en tâche de fond : plusieurs peuvent tourner en même temps, chacune avec son avancement."""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import journal

MAX_PARALLELE = 3          # au-delà, les demandes attendent leur tour (ménage le quota de l'abonnement)
_TACHES: Dict[str, "Tache"] = {}
_VERROU = threading.Lock()
_SEMAPHORE = threading.BoundedSemaphore(MAX_PARALLELE)


class Tache:
    def __init__(self, cle: str) -> None:
        self.id = secrets.token_hex(6)
        self.cle = cle                      # identifie la conversation concernée
        self.etat = "attente"               # attente, en_cours, termine, erreur, annule
        self.etape = "En attente d'une place…"
        self.journal: List[Dict[str, Any]] = []
        self.debut = time.time()
        self.fin: Optional[float] = None
        self.resultat: Optional[Dict[str, Any]] = None
        self.erreur = ""
        self.annule = threading.Event()
        self.derniere_activite = time.time()

    def signaler(self, genre: str, texte: str) -> None:
        """genre : etape (étape de préparation), demarrage / sortie / info (venant d'agy)."""
        self.derniere_activite = time.time()
        if genre in ("etape", "demarrage"):
            self.etape = texte
        self.journal.append({"t": round(time.time() - self.debut, 1), "genre": genre, "texte": texte})
        del self.journal[:-30]

    def vue(self) -> Dict[str, Any]:
        fin = self.fin or time.time()
        return {"id": self.id, "cle": self.cle, "etat": self.etat, "etape": self.etape, "duree": round(fin - self.debut, 1),
                "silence": round(time.time() - self.derniere_activite, 1) if self.etat == "en_cours" else 0,
                "journal": self.journal[-6:], "resultat": self.resultat, "erreur": self.erreur}


def demarrer(cle: str, travail: Callable[[Tache], Dict[str, Any]], erreurs: tuple) -> Tache:
    t = Tache(cle)
    with _VERROU:
        for ancien in [k for k, v in _TACHES.items() if v.fin and time.time() - v.fin > 1800]:
            del _TACHES[ancien]          # nettoyage des tâches terminées depuis longtemps
        _TACHES[t.id] = t

    def courir() -> None:
        with _SEMAPHORE:
            if t.annule.is_set():
                t.etat, t.erreur, t.fin = "annule", "Rédaction annulée.", time.time()
                return
            t.etat, t.etape = "en_cours", "Préparation…"
            try:
                t.resultat = travail(t)
                t.etat = "termine"
            except erreurs as exc:
                t.etat = "annule" if t.annule.is_set() else "erreur"
                t.erreur = str(exc.args[0] if isinstance(exc, KeyError) and exc.args else exc)
            except Exception as exc:  # pragma: no cover
                journal.erreur("rédaction")
                t.etat, t.erreur = "erreur", "Erreur inattendue : %s" % exc
            finally:
                t.fin = time.time()
                journal.ecrire("rédaction %s : %s en %.1f s%s" % (t.id, t.etat, t.fin - t.debut,
                                                                  (" (%s)" % t.erreur[:200]) if t.erreur else ""))

    threading.Thread(target=courir, daemon=True).start()
    return t


def lire(tache_id: str) -> Dict[str, Any]:
    t = _TACHES.get(tache_id)
    if t is None:
        raise KeyError("Rédaction introuvable (l'application a peut-être été relancée).")
    return t.vue()


def annuler(tache_id: str) -> Dict[str, Any]:
    t = _TACHES.get(tache_id)
    if t is None:
        raise KeyError("Rédaction introuvable.")
    t.annule.set()
    t.signaler("etape", "Annulation…")
    return {"ok": True}
