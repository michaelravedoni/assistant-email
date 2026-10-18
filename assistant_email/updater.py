"""Recherche d'une nouvelle version dans les Releases GitHub (dépôt privé : jeton en lecture, gardé dans le Trousseau)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import __version__

TOKEN_ACCOUNT = "jeton-github"
API = "https://api.github.com"


class UpdateError(Exception):
    pass


def parse_version(v: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:4]) or (0,)


class _SansAutorisationEntreHotes(urllib.request.HTTPRedirectHandler):
    """GitHub redirige les téléchargements vers un autre hôte : il ne faut pas lui renvoyer le jeton."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_SansAutorisationEntreHotes())


def _request(url: str, token: Optional[str], accept: str) -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": "AssistantEmail/" + __version__, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=headers)


def check(depot: str, token: Optional[str] = None) -> Dict[str, Any]:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", depot or ""):
        raise UpdateError("Indiquez le dépôt GitHub (propriétaire/dépôt) dans les Réglages.")
    try:
        with _opener().open(_request("%s/repos/%s/releases/latest" % (API, depot), token, "application/vnd.github+json"), timeout=20) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Aucune version publiée trouvée. Si le dépôt est privé, ajoutez un jeton d'accès dans les Réglages.")
        if exc.code in (401, 403):
            raise UpdateError("Accès refusé par GitHub : vérifiez le jeton d'accès dans les Réglages.")
        raise UpdateError("GitHub a répondu : erreur %s." % exc.code)
    except (OSError, ValueError) as exc:
        raise UpdateError("Impossible de joindre GitHub : %s" % exc)
    latest = str(rel.get("tag_name", ""))
    asset = next((a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".dmg")), None)
    return {"actuelle": __version__, "derniere": latest.lstrip("v"),
            "disponible": parse_version(latest) > parse_version(__version__),
            "notes": rel.get("body") or "", "page": rel.get("html_url", ""),
            "asset_url": asset["url"] if asset else "", "asset_nom": asset["name"] if asset else ""}


def download(asset_url: str, name: str, token: Optional[str] = None, dest_dir: Optional[Path] = None) -> Path:
    if not asset_url.startswith(API + "/repos/"):
        raise UpdateError("Adresse de téléchargement inattendue.")
    dest = (dest_dir or Path.home() / "Downloads") / re.sub(r"[^\w.-]", "_", name or "AssistantEmail.dmg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _opener().open(_request(asset_url, token, "application/octet-stream"), timeout=120) as r, dest.open("wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError("Téléchargement impossible : %s" % exc)
    return dest
