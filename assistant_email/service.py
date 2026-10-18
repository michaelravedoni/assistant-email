"""Logique métier, indépendante de l'interface : conversation → prompt → IA → brouillon."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import __version__

from . import brouillon, config, gemini, imap_client, keychain, macos, messages, modeles, prompt, sauvegarde, updater


def public_profile(p: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(p)
    out["mot_de_passe_enregistre"] = bool(keychain.get_password(p["id"]))
    return out


def state() -> Dict[str, Any]:
    settings = config.load_settings()
    profiles = config.load_profiles()
    return {
        "profils": [public_profile(p) for p in profiles],
        "reglages": settings,
        "gemini_trouve": gemini.find_gemini(settings.get("gemini_chemin", "")),
        "version": __version__,
        "jeton_github": bool(keychain.get_password(updater.TOKEN_ACCOUNT)),
        "macos": macos.IS_MAC,
    }


def save_profile(values: Dict[str, Any]) -> Dict[str, Any]:
    password = values.pop("mot_de_passe", None)
    p = config.save_profile(values)
    if password:
        keychain.set_password(p["id"], password)
    sauvegarde.sauvegarder_si_modifie()
    return public_profile(p)


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    token = values.pop("jeton_github", None)
    if token:
        keychain.set_password(updater.TOKEN_ACCOUNT, token)
    out = config.save_settings(values)
    sauvegarde.sauvegarder_si_modifie()
    return out


def check_update() -> Dict[str, Any]:
    s = config.load_settings()
    return updater.check(s.get("depot_github", ""), keychain.get_password(updater.TOKEN_ACCOUNT))


def download_update(asset_url: str, name: str) -> Dict[str, Any]:
    path = updater.download(asset_url, name, keychain.get_password(updater.TOKEN_ACCOUNT))
    macos.open_path(str(path))
    return {"chemin": str(path)}


def export_settings() -> Dict[str, Any]:
    path = sauvegarde.exporter()
    macos.reveal(str(path))
    return {"chemin": str(path)}


def import_settings(path: str) -> Dict[str, Any]:
    return sauvegarde.importer(path)


def delete_profile(profile_id: str) -> None:
    config.delete_profile(profile_id)
    keychain.delete_password(profile_id)


def test_profile(values: Dict[str, Any]) -> Dict[str, Any]:
    profile = dict(config.DEFAULT_PROFILE)
    if values.get("id"):
        try:
            profile.update(config.get_profile(values["id"]))
        except KeyError:
            pass
    profile.update({k: v for k, v in values.items() if k in config.DEFAULT_PROFILE and k != "id"})
    if not profile.get("imap_utilisateur"):
        profile["imap_utilisateur"] = profile.get("email", "")
    pw = values.get("mot_de_passe") or (keychain.get_password(profile["id"]) if profile.get("id") else None)
    return imap_client.test_connection(profile, pw or "")


def source_info(paths: List[str]) -> List[Dict[str, Any]]:
    return [modeles.describe_source(p) for p in paths]


def list_messages(profile_id: str, folder: str = "INBOX", filtre: str = "tous") -> Dict[str, Any]:
    profile = config.get_profile(profile_id)
    limit = int(config.load_settings().get("nb_messages", 40))
    with imap_client.ImapSession(profile) as s:
        return s.recent(folder, limit, filtre)


def set_flag(profile_id: str, folder: str, uid: str, flag: str, value: bool) -> Dict[str, Any]:
    with imap_client.ImapSession(config.get_profile(profile_id)) as s:
        s.set_flag(folder, uid, flag, value)
    return {"ok": True}


def _own_addresses(profile: Dict[str, Any]) -> List[str]:
    return [a for a in (profile.get("email"), profile.get("imap_utilisateur")) if a]


def _package(profile: Optional[Dict[str, Any]], thread: List[Dict[str, Any]], note: str = "") -> Dict[str, Any]:
    own = _own_addresses(profile) if profile else []
    return {
        "profil": profile["id"] if profile else None,
        "messages": thread,
        "texte": messages.conversation_text(thread),
        "reponse": messages.reply_meta(thread[-1], own),
        "note": note,
    }


def conversation(profile_id: str, uid: str, folder: str = "INBOX") -> Dict[str, Any]:
    profile = config.get_profile(profile_id)
    with imap_client.ImapSession(profile) as s:
        thread = s.conversation(folder, uid)
    return _package(profile, thread)


def match_profile(msg: Dict[str, Any], raw_headers: str = "") -> Optional[Dict[str, Any]]:
    addrs = set(messages.recipients_of(msg))
    low_headers = raw_headers.lower()
    for p in config.load_profiles():
        for a in _own_addresses(p):
            if a.lower() in addrs or ("delivered-to: " + a.lower()) in low_headers:
                return p
    for p in config.load_profiles():  # message envoyé par moi
        if any(a.lower() in msg.get("de", "").lower() for a in _own_addresses(p)):
            return p
    return None


def conversation_from_raw(raw: bytes, profile_id: Optional[str] = None) -> Dict[str, Any]:
    parsed = messages.parse_bytes(raw)
    last = messages.to_dict(parsed)
    header_block = raw.split(b"\n\n", 1)[0].decode("utf-8", errors="replace")
    profile = None
    if profile_id:
        profile = config.get_profile(profile_id)
    else:
        profile = match_profile(last, header_block)
    thread = [last]
    note = ""
    if profile and (last.get("references") or last.get("in_reply_to")):
        try:
            with imap_client.ImapSession(profile) as s:
                thread = s.expand_thread(last, ["INBOX"])
        except imap_client.ImapError as exc:
            note = "Messages précédents non récupérés (%s). Seul le message sélectionné est utilisé." % exc
    return _package(profile, thread, note)


def conversation_from_mail_app(profile_id: Optional[str] = None) -> Dict[str, Any]:
    return conversation_from_raw(macos.mail_selected_source(), profile_id)


_SENT_CACHE: Dict[str, Any] = {}


def _sent_examples(profile: Dict[str, Any]) -> List[str]:
    n = int(profile.get("envoyes_nb") or 0)
    if n <= 0:
        return []
    key = "%s:%d" % (profile["id"], n)
    cached = _SENT_CACHE.get(key)
    if cached and time.time() - cached[0] < 900:
        return cached[1]
    with imap_client.ImapSession(profile) as s:
        samples = s.sent_samples(n)
    _SENT_CACHE[key] = (time.time(), samples)
    return samples


def generate(profile_id: str, conversation_text: str, dictation: str, subject_hint: str = "",
             previous_draft: Optional[str] = None, adjustment: Optional[str] = None) -> Dict[str, Any]:
    profile = config.get_profile(profile_id)
    if previous_draft:
        previous_draft = brouillon.remove_signature(profile, previous_draft)
    templates = modeles.load_templates(config.template_sources(profile))
    note = ""
    try:
        examples = _sent_examples(profile)
    except imap_client.ImapError as exc:
        examples, note = [], "Style des envoyés ignoré (%s)." % exc
    text = prompt.build_prompt(profile, conversation_text, dictation, templates, subject_hint,
                               previous_draft, adjustment, examples)
    raw = gemini.run(text, config.load_settings())
    result = prompt.parse_response(raw, subject_hint)
    result["nb_modeles"] = len(templates)
    result["nb_envoyes"] = len(examples)
    result["note"] = note
    if not result["corps"]:
        raise gemini.GeminiError("Réponse de l'IA vide ou illisible :\n" + raw[-1000:])
    result["corps"] = brouillon.add_signature(profile, result["corps"])
    return result


def full_text(profile_id: str, body: str, quote: Optional[Dict[str, Any]] = None) -> str:
    return brouillon.compose_body(config.get_profile(profile_id), body, quote)


def deposit(profile_id: str, to: str, cc: str, subject: str, body: str, in_reply_to: str = "",
            references: str = "", quote: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = config.get_profile(profile_id)
    raw = brouillon.build_draft(profile, to, cc, subject, body, in_reply_to, references, quote)
    with imap_client.ImapSession(profile) as s:
        folder = s.append_draft(raw)
    return {"dossier": folder}
