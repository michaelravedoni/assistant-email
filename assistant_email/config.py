"""Emplacement des données, réglages et profils (fichiers JSON)."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def app_home() -> Path:
    override = os.environ.get("ASSISTANT_EMAIL_HOME")
    if override:
        base = Path(override)
    else:
        base = Path.home() / "Library" / "Application Support" / "AssistantEmail"
    base.mkdir(parents=True, exist_ok=True)
    return base


DEFAULT_SETTINGS: Dict[str, Any] = {
    "gemini_chemin": "",      # vide = détection automatique
    "gemini_modele": "",      # vide = modèle par défaut de Gemini CLI
    "gemini_delai": 240,      # secondes
    "port": 8765,
    "nb_messages": 40,
    "sources_globales": [],   # sources de modèles partagées par tous les profils
    "depot_github": "michaelravedoni/assistant-email",       # « propriétaire/dépôt » où chercher les mises à jour
}

DEFAULT_PROFILE: Dict[str, Any] = {
    "id": "",
    "nom": "",
    "nom_affiche": "",
    "email": "",
    "imap_hote": "mail.infomaniak.com",
    "imap_port": 993,
    "imap_utilisateur": "",
    "dossier_brouillons": "",  # vide = détection automatique
    "adresse": "auto",         # auto | vous | tu
    "registre": "cordial",     # sobre | cordial | chaleureux
    "longueur": "normal",      # concis | normal | detaille
    "ton": "",
    "signature": "",
    "envoyes_nb": 8,           # nb d'emails envoyés récents donnés en exemple de style (0 = aucun)
    "sources_modeles": [],     # [{"chemin": str, "actif": bool}]
    "consignes": "",
    "citer_original": True,
}


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULT_SETTINGS)
    data.update(_read_json(app_home() / "reglages.json", {}))
    return data


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    data = load_settings()
    for key in DEFAULT_SETTINGS:
        if key in values:
            data[key] = values[key]
    for key in ("gemini_delai", "port", "nb_messages"):
        data[key] = int(data[key])
    data["sources_globales"] = clean_sources(data.get("sources_globales"))
    _write_json(app_home() / "reglages.json", data)
    return data


def clean_sources(values: Any) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for v in values if isinstance(values, list) else []:
        if isinstance(v, str):
            v = {"chemin": v}
        path = str((v or {}).get("chemin", "")).strip()
        if path and path not in seen:
            seen.add(path)
            out.append({"chemin": path, "actif": bool(v.get("actif", True))})
    return out


def load_profiles() -> List[Dict[str, Any]]:
    raw = _read_json(app_home() / "profils.json", [])
    profiles = []
    for item in raw if isinstance(raw, list) else []:
        p = dict(DEFAULT_PROFILE)
        p.update(item)
        legacy = p.pop("dossier_modeles", "")  # ancien format : un seul dossier
        if legacy and not p["sources_modeles"]:
            p["sources_modeles"] = [{"chemin": legacy, "actif": True}]
        p["sources_modeles"] = clean_sources(p["sources_modeles"])
        profiles.append(p)
    return profiles


def template_sources(profile: Dict[str, Any]) -> List[str]:
    """Chemins actifs : sources partagées d'abord, puis celles du profil."""
    shared = clean_sources(load_settings().get("sources_globales"))
    return [s["chemin"] for s in shared + profile.get("sources_modeles", []) if s["actif"]]


def get_profile(profile_id: str) -> Dict[str, Any]:
    for p in load_profiles():
        if p["id"] == profile_id:
            return p
    raise KeyError("Profil introuvable : %s" % profile_id)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "profil"


def save_profile(values: Dict[str, Any]) -> Dict[str, Any]:
    profiles = load_profiles()
    profile = dict(DEFAULT_PROFILE)
    existing: Optional[Dict[str, Any]] = None
    if values.get("id"):
        existing = next((p for p in profiles if p["id"] == values["id"]), None)
        if existing:
            profile.update(existing)
    for key in DEFAULT_PROFILE:
        if key in values and key != "id":
            profile[key] = values[key]
    profile.pop("dossier_modeles", None)
    profile["sources_modeles"] = clean_sources(profile["sources_modeles"])
    profile["envoyes_nb"] = max(0, min(30, int(profile["envoyes_nb"] or 0)))
    profile["imap_port"] = int(profile["imap_port"] or 993)
    profile["citer_original"] = bool(profile["citer_original"])
    if not profile["imap_utilisateur"]:
        profile["imap_utilisateur"] = profile["email"]
    if not profile["nom"]:
        profile["nom"] = profile["email"] or "Profil"
    if existing:
        profiles = [profile if p["id"] == existing["id"] else p for p in profiles]
    else:
        profile["id"] = "%s-%s" % (_slug(profile["nom"]), uuid.uuid4().hex[:6])
        profiles.append(profile)
    _write_json(app_home() / "profils.json", profiles)
    return profile


def delete_profile(profile_id: str) -> None:
    profiles = [p for p in load_profiles() if p["id"] != profile_id]
    _write_json(app_home() / "profils.json", profiles)
