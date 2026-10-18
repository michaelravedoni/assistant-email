"""Serveur web local (127.0.0.1 uniquement) qui sert l'interface et l'API JSON."""
from __future__ import annotations

import json
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from . import config, gemini, imap_client, macos, sauvegarde, service, updater

WEB_DIR = Path(__file__).parent / "web"
TOKEN = secrets.token_urlsafe(24)
EVENTS: list = []          # actions envoyées par la barre de menus à la fenêtre ouverte
LAST_POLL = [0.0]          # dernier passage de la fenêtre (horodatage)
KNOWN_ERRORS = (imap_client.ImapError, gemini.GeminiError, macos.MacError, updater.UpdateError, KeyError, ValueError)


def _poll_events(_q: Dict[str, Any]) -> Dict[str, Any]:
    LAST_POLL[0] = time.time()
    out = list(EVENTS)
    del EVENTS[:]
    return {"actions": out}


def window_is_open() -> bool:
    return time.time() - LAST_POLL[0] < 4


def _routes() -> Dict[Tuple[str, str], Callable[[Dict[str, Any]], Any]]:
    return {
        ("GET", "/api/etat"): lambda q: service.state(),
        ("POST", "/api/reglages"): lambda b: service.save_settings(b),
        ("POST", "/api/mise-a-jour/verifier"): lambda b: service.check_update(),
        ("POST", "/api/mise-a-jour/telecharger"): lambda b: service.download_update(b["url"], b["nom"]),
        ("POST", "/api/sauvegarde/exporter"): lambda b: service.export_settings(),
        ("POST", "/api/sauvegarde/importer"): lambda b: service.import_settings(b["chemin"]),
        ("POST", "/api/ouvrir-sauvegardes"): lambda b: macos.open_path(str(sauvegarde.dossier())) or {"ok": True},
        ("POST", "/api/profils"): lambda b: service.save_profile(b),
        ("POST", "/api/profils/supprimer"): lambda b: service.delete_profile(b["id"]) or {"ok": True},
        ("POST", "/api/profils/tester"): lambda b: service.test_profile(b),
        ("POST", "/api/choisir-dossier"): lambda b: {"chemin": macos.choose_folder()},
        ("POST", "/api/choisir-fichier"): lambda b: {"chemin": macos.choose_file()},
        ("POST", "/api/sources"): lambda b: {"sources": service.source_info(b.get("chemins", []))},
        ("GET", "/api/messages"): lambda q: service.list_messages(q["profil"], q.get("dossier", "INBOX"), q.get("filtre", "tous")),
        ("POST", "/api/drapeau"): lambda b: service.set_flag(b["profil"], b.get("dossier", "INBOX"), b["uid"], b["drapeau"], bool(b["valeur"])),
        ("POST", "/api/conversation"): lambda b: service.conversation(b["profil"], b["uid"], b.get("dossier", "INBOX")),
        ("POST", "/api/mail-selection"): lambda b: service.conversation_from_mail_app(b.get("profil")),
        ("GET", "/api/presse-papiers"): lambda q: {"texte": macos.clipboard_text()},
        ("POST", "/api/copier"): lambda b: macos.copy_to_clipboard(b["texte"]) or {"ok": True},
        ("GET", "/api/evenements"): _poll_events,
        ("POST", "/api/generer"): lambda b: service.generate(
            b["profil"], b.get("conversation", ""), b.get("dictee", ""), b.get("objet", ""),
            b.get("brouillon_precedent"), b.get("ajustement")),
        ("POST", "/api/texte-final"): lambda b: {"texte": service.full_text(b["profil"], b["corps"], b.get("citation"))},
        ("POST", "/api/deposer"): lambda b: service.deposit(
            b["profil"], b.get("a", ""), b.get("cc", ""), b.get("objet", ""), b["corps"],
            b.get("in_reply_to", ""), b.get("references", ""), b.get("citation")),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "AssistantEmail"
    routes = _routes()

    def log_message(self, fmt, *args):  # silencieux
        pass

    def _send(self, code: int, payload: Any, ctype: str = "application/json; charset=utf-8") -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Jeton", ""), TOKEN)

    def _handle(self, method: str) -> None:
        url = urlparse(self.path)
        if method == "GET" and url.path in ("/", "/index.html"):
            q = parse_qs(url.query)
            if q.get("t", [""])[0] != TOKEN:
                self._send(403, "Lien expiré : rouvrez l'assistant depuis la barre de menus.".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            page = (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("__JETON__", TOKEN)
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        handler = self.routes.get((method, url.path))
        if handler is None:
            self._send(404, {"erreur": "Introuvable"})
            return
        if not self._authorized():
            self._send(403, {"erreur": "Accès refusé"})
            return
        try:
            if method == "GET":
                arg = {k: v[0] for k, v in parse_qs(url.query).items()}
            else:
                length = int(self.headers.get("Content-Length") or 0)
                arg = json.loads(self.rfile.read(length) or b"{}") if length else {}
            result = handler(arg)
            self._send(200, result if result is not None else {"ok": True})
        except KNOWN_ERRORS as exc:
            msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            self._send(400, {"erreur": str(msg)})
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._send(500, {"erreur": "Erreur inattendue : %s" % exc})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


class LocalServer:
    def __init__(self, port: int = 0):
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # port occupé : port libre
        self.httpd.daemon_threads = True
        self.thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def url(self, action: str = "") -> str:
        return "http://127.0.0.1:%d/?t=%s%s" % (self.port, TOKEN, ("#" + action) if action else "")

    def start(self) -> "LocalServer":
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
