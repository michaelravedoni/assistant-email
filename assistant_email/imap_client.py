"""Accès IMAP : liste des messages, reconstruction du fil, dépôt d'un brouillon."""
from __future__ import annotations

import imaplib
import re
import ssl
import time
from typing import Any, Dict, List, Optional, Tuple

from . import keychain, messages

LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<delim>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$')
DRAFT_NAMES = ("drafts", "brouillons", "inbox.drafts", "inbox.brouillons", "draft", "entwürfe")
SENT_NAMES = ("sent", "sent messages", "sent items", "envoyés", "messages envoyés",
              "inbox.sent", "éléments envoyés")


class ImapError(Exception):
    pass


def quote_mailbox(name: str) -> str:
    if name.startswith('"'):
        return name
    if re.search(r'[\s"\\(){}%*]', name):
        return '"%s"' % name.replace("\\", "\\\\").replace('"', '\\"')
    return name


def parse_list_line(line: Any) -> Optional[Dict[str, Any]]:
    if isinstance(line, tuple):  # nom de dossier envoyé en littéral
        line = line[0] + b'"' + line[1] + b'"'
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    m = LIST_RE.match(line.strip())
    if not m:
        return None
    name = m.group("name").strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    flags = [f.lower() for f in m.group("flags").split()]
    return {"nom": name, "drapeaux": flags}


def _find_special(folders: List[Dict[str, Any]], flag: str, names: Tuple[str, ...]) -> Optional[str]:
    for f in folders:
        if flag in f["drapeaux"]:
            return f["nom"]
    for wanted in names:
        for f in folders:
            if f["nom"].lower() == wanted:
                return f["nom"]
    return None


class ImapSession:
    def __init__(self, profile: Dict[str, Any], password: Optional[str] = None):
        self.profile = profile
        self.password = password if password is not None else keychain.get_password(profile["id"])
        self.conn: Optional[imaplib.IMAP4] = None
        self._folders: Optional[List[Dict[str, Any]]] = None

    def __enter__(self) -> "ImapSession":
        if not self.password:
            raise ImapError("Aucun mot de passe enregistré pour ce profil. Ouvrez les profils et saisissez-le.")
        try:
            self.conn = imaplib.IMAP4_SSL(self.profile["imap_hote"], int(self.profile["imap_port"]),
                                          ssl_context=ssl.create_default_context())
            self.conn.login(self.profile["imap_utilisateur"] or self.profile["email"], self.password)
        except imaplib.IMAP4.error as exc:
            raise ImapError("Connexion IMAP refusée : %s" % _txt(exc)) from exc
        except OSError as exc:
            raise ImapError("Serveur IMAP injoignable (%s:%s) : %s"
                            % (self.profile["imap_hote"], self.profile["imap_port"], exc)) from exc
        return self

    def __exit__(self, *exc) -> None:
        if self.conn is not None:
            try:
                self.conn.logout()
            except Exception:
                pass

    # -- dossiers -----------------------------------------------------------
    def folders(self) -> List[Dict[str, Any]]:
        if self._folders is None:
            typ, data = self.conn.list()
            if typ != "OK":
                raise ImapError("Impossible de lister les dossiers.")
            self._folders = [f for f in (parse_list_line(l) for l in data if l) if f]
        return self._folders

    def drafts_folder(self) -> str:
        if self.profile.get("dossier_brouillons"):
            return self.profile["dossier_brouillons"]
        found = _find_special(self.folders(), "\\drafts", DRAFT_NAMES)
        if not found:
            raise ImapError("Dossier Brouillons introuvable : indiquez son nom dans le profil.")
        return found

    def sent_folder(self) -> Optional[str]:
        return _find_special(self.folders(), "\\sent", SENT_NAMES)

    def _select(self, folder: str) -> None:
        typ, data = self.conn.select(quote_mailbox(folder), readonly=True)
        if typ != "OK":
            raise ImapError("Dossier inaccessible : %s" % folder)

    # -- lecture ------------------------------------------------------------
    def _search_uids(self, criterion: str) -> List[bytes]:
        typ, data = self.conn.uid("SEARCH", None, criterion)
        return data[0].split() if typ == "OK" and data and data[0] else []

    def recent(self, folder: str = "INBOX", limit: int = 40, filtre: str = "tous") -> Dict[str, Any]:
        """Derniers messages (tous, non lus ou suivis), avec leurs drapeaux, et le nombre de non lus / suivis."""
        self._select(folder)
        unseen = self._search_uids("UNSEEN")
        flagged = self._search_uids("FLAGGED")
        uids = {"non_lus": unseen, "suivis": flagged}.get(filtre) or ([] if filtre in ("non_lus", "suivis") else self._search_uids("ALL"))
        uids = uids[-limit:]
        out: List[Dict[str, Any]] = []
        if uids:
            typ, data = self.conn.uid("FETCH", b",".join(uids).decode(),
                                      "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
            current: Optional[Dict[str, Any]] = None
            for item in data or []:
                if isinstance(item, tuple):
                    m = re.search(rb"UID (\d+)", item[0])
                    if not m:
                        current = None
                        continue
                    d = messages.to_dict(messages.parse_bytes(item[1]))
                    current = {"uid": m.group(1).decode(), "de": d["de"], "objet": d["objet"], "date": d["date"],
                               "horodatage": d["horodatage"], "lu": False, "suivi": False}
                    self._apply_flags(current, item[0])
                    out.append(current)
                elif isinstance(item, bytes) and current is not None:
                    self._apply_flags(current, item)  # certains serveurs envoient FLAGS après l'en-tête
        out.sort(key=lambda x: x["horodatage"], reverse=True)
        return {"messages": out, "non_lus": len(unseen), "suivis": len(flagged)}

    @staticmethod
    def _apply_flags(msg: Dict[str, Any], raw: bytes) -> None:
        m = re.search(rb"FLAGS \(([^)]*)\)", raw)
        if m:
            flags = [f.lower() for f in m.group(1).decode("ascii", "replace").split()]
            msg["lu"] = "\\seen" in flags
            msg["suivi"] = "\\flagged" in flags

    def set_flag(self, folder: str, uid: str, flag: str, value: bool) -> None:
        """flag : « lu » ou « suivi ». Seule écriture faite par l'app sur les messages reçus, et seulement sur demande."""
        imap_flag = {"lu": "\\Seen", "suivi": "\\Flagged"}.get(flag)
        if not imap_flag:
            raise ImapError("Drapeau inconnu : %s" % flag)
        typ, data = self.conn.select(quote_mailbox(folder), readonly=False)
        if typ != "OK":
            raise ImapError("Dossier inaccessible : %s" % folder)
        typ, data = self.conn.uid("STORE", str(uid), "+FLAGS.SILENT" if value else "-FLAGS.SILENT", "(%s)" % imap_flag)
        if typ != "OK":
            raise ImapError("Le serveur a refusé la modification : %s" % _txt(data))

    def fetch(self, folder: str, uid: str) -> Optional[Dict[str, Any]]:
        self._select(folder)
        typ, data = self.conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        for item in data or []:
            if isinstance(item, tuple):
                return messages.to_dict(messages.parse_bytes(item[1]))
        return None

    def search_message_id(self, folder: str, message_id: str) -> List[str]:
        self._select(folder)
        typ, data = self.conn.uid("SEARCH", None, "HEADER", "Message-ID", '"%s"' % message_id)
        if typ != "OK" or not data or not data[0]:
            return []
        return [u.decode() for u in data[0].split()]

    def find_by_message_id(self, message_id: str, folders: List[str]) -> Optional[Dict[str, Any]]:
        for folder in folders:
            for uid in self.search_message_id(folder, message_id):
                found = self.fetch(folder, uid)
                if found:
                    return found
        return None

    def conversation(self, folder: str, uid: str, max_messages: int = 15) -> List[Dict[str, Any]]:
        last = self.fetch(folder, uid)
        if last is None:
            raise ImapError("Message introuvable.")
        return self.expand_thread(last, [folder], max_messages)

    def expand_thread(self, last: Dict[str, Any], folders: List[str], max_messages: int = 15) -> List[Dict[str, Any]]:
        """Retrouve les messages précédents du fil via References / In-Reply-To."""
        search_in = list(dict.fromkeys(["INBOX"] + folders + [f for f in [self.sent_folder()] if f]))
        ids = list(last.get("references") or [])
        if last.get("in_reply_to") and last["in_reply_to"] not in ids:
            ids.append(last["in_reply_to"])
        found: Dict[str, Dict[str, Any]] = {}
        for mid in reversed(ids[-max_messages:]):
            if mid in found or mid == last.get("message_id"):
                continue
            m = self.find_by_message_id(mid, search_in)
            if m:
                found[mid] = m
        thread = sorted(found.values(), key=lambda x: x["horodatage"]) + [last]
        return thread

    def sent_samples(self, limit: int = 8) -> List[str]:
        """Corps (sans citations) des derniers emails envoyés, comme exemples de style."""
        folder = self.sent_folder()
        if not folder or limit <= 0:
            return []
        self._select(folder)
        typ, data = self.conn.uid("SEARCH", None, "ALL")
        uids = data[0].split() if typ == "OK" and data and data[0] else []
        out: List[str] = []
        for uid in reversed(uids[-limit * 4:]):  # on lit large : certains envoyés sont trop courts ou vides
            typ, data = self.conn.uid("FETCH", uid.decode(), "(BODY.PEEK[])")
            for item in data or []:
                if isinstance(item, tuple):
                    text = messages.strip_quoted(messages.body_text(messages.parse_bytes(item[1])))
                    if 40 <= len(text) <= 6000:
                        out.append(text[:1800])
            if len(out) >= limit:
                break
        return out

    # -- écriture -----------------------------------------------------------
    def append_draft(self, raw: bytes) -> str:
        folder = self.drafts_folder()
        typ, data = self.conn.append(quote_mailbox(folder), "(\\Draft \\Seen)",
                                     imaplib.Time2Internaldate(time.time()), raw)
        if typ != "OK":
            raise ImapError("Le serveur a refusé le brouillon : %s" % _txt(data))
        return folder


def _txt(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = b" ".join(v for v in value if isinstance(v, bytes))
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def test_connection(profile: Dict[str, Any], password: Optional[str] = None) -> Dict[str, Any]:
    with ImapSession(profile, password) as s:
        folders = [f["nom"] for f in s.folders()]
        try:
            drafts = s.drafts_folder()
        except ImapError:
            drafts = None
        return {"dossiers": folders, "brouillons": drafts, "envoyes": s.sent_folder()}
