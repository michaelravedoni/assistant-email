"""Appel de l'IA en ligne de commande, sans clé API (abonnement Google déjà connecté).

Commande par défaut : « agy » (Antigravity CLI), en mode headless :
    agy -p "<prompt>" --output-format json
Au-delà d'une certaine taille, le prompt passe par l'entrée standard (--input-format stream-json)
pour ne pas dépasser la limite de longueur d'une ligne de commande macOS.
L'ancienne commande « gemini » (Gemini CLI) reste prise en charge si elle est configurée.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .prompt import INSTRUCTION_COURTE

COMMANDES = ("agy", "gemini")      # ordre de préférence pour la détection automatique
MAX_ARG_BYTES = 150000             # au-delà : prompt envoyé par l'entrée standard


class GeminiError(Exception):
    pass


def _candidate_dirs() -> List[str]:
    home = str(Path.home())
    dirs = [home + "/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", home + "/.npm-global/bin",
            home + "/.volta/bin", home + "/.bun/bin", home + "/Library/pnpm", "/opt/agy", "/usr/bin", "/bin"]
    dirs += sorted(glob.glob(home + "/.nvm/versions/node/*/bin"), reverse=True)
    dirs += sorted(glob.glob(home + "/.fnm/node-versions/*/installation/bin"), reverse=True)
    dirs += sorted(glob.glob(home + "/.asdf/installs/nodejs/*/bin"), reverse=True)
    return dirs


def _env_with(cli_path: Optional[str]) -> Dict[str, str]:
    env = dict(os.environ)
    extra = []
    if cli_path:
        extra.append(str(Path(cli_path).parent))
        extra.append(str(Path(os.path.realpath(cli_path)).parent))
    extra += _candidate_dirs()
    env["PATH"] = os.pathsep.join(list(dict.fromkeys(extra + env.get("PATH", "").split(os.pathsep))))
    env.setdefault("LANG", "fr_FR.UTF-8")
    env["NO_COLOR"] = "1"
    return env


def _which_login_shell(name: str) -> Optional[str]:
    # Une app lancée depuis le Finder n'hérite pas du PATH du terminal : on demande au shell de connexion.
    for args in (["/bin/zsh", "-lc", "command -v " + name], ["/bin/zsh", "-ilc", "command -v " + name],
                 ["/bin/bash", "-lc", "command -v " + name]):
        if not os.path.exists(args[0]):
            continue
        try:
            res = subprocess.run(args, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in reversed(res.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("/") and os.access(line, os.X_OK):
                return line
    return None


def find_gemini(configured: str = "") -> Optional[str]:
    """Chemin de la commande IA : celle des réglages, sinon agy, sinon gemini."""
    if configured:
        p = os.path.expanduser(configured)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        return shutil.which(configured, path=_env_with(None)["PATH"])
    path = _env_with(None)["PATH"]
    for name in COMMANDES:
        found = shutil.which(name, path=path)
        if found:
            return found
    for name in COMMANDES:
        found = _which_login_shell(name)
        if found:
            return found
    return None


def is_agy(path: str) -> bool:
    return not os.path.basename(path).lower().startswith("gemini")


def _agy_command(path: str, prompt: str, settings: Dict[str, Any]) -> Tuple[List[str], Optional[str]]:
    cmd = [path]
    if len(prompt.encode("utf-8")) <= MAX_ARG_BYTES:
        cmd += ["-p", prompt, "--output-format", "json"]
        stdin = None
    else:
        cmd += ["--input-format", "stream-json", "--output-format", "stream-json"]
        stdin = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
    cmd += ["--print-timeout", "%ds" % int(settings.get("gemini_delai", 240))]
    if settings.get("gemini_modele"):
        cmd += ["--model", settings["gemini_modele"]]
    return cmd, stdin


def _find_response(obj: Any) -> Optional[Dict[str, Any]]:
    """Cherche l'objet qui porte « response » (ou une erreur) dans une enveloppe JSON d'agy."""
    if isinstance(obj, dict):
        if "response" in obj or ("status" in obj and "error" in obj):
            return obj
        for key in ("result", "data"):
            found = _find_response(obj.get(key))
            if found:
                return found
    return None


def parse_agy_output(stdout: str) -> str:
    candidates = []
    try:
        candidates.append(json.loads(stdout))
    except ValueError:
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    candidates.append(json.loads(line))
                except ValueError:
                    pass
    envelope = None
    for c in candidates:
        found = _find_response(c)
        if found:
            envelope = found  # on garde le dernier (événement « result » final)
    if envelope is None:
        return stdout.strip()  # sortie texte brute
    status = str(envelope.get("status") or "SUCCESS").upper()
    if envelope.get("error") or status not in ("SUCCESS", "OK"):
        raise GeminiError(_explain("%s : %s" % (status, envelope.get("error") or "réponse vide")))
    return str(envelope.get("response") or "").strip()


def _explain(err: str) -> str:
    low = err.lower()
    hint = ""
    if "auth" in low or "login" in low or "credential" in low or "sign in" in low:
        hint = " Ouvrez un terminal, lancez « agy » une fois et connectez-vous à votre compte Google."
    elif "quota" in low or "429" in low or "rate limit" in low or "resource_exhausted" in low:
        hint = " Quota de l'abonnement atteint, réessayez plus tard."
    elif "model" in low and ("unknown" in low or "invalid" in low or "not found" in low):
        hint = " Modèle inconnu : videz le champ Modèle dans les réglages (liste : « agy models »)."
    return "L'IA a échoué.%s\n%s" % (hint, err.strip()[-1500:])


def run(prompt: str, settings: Dict[str, Any]) -> str:
    path = find_gemini(settings.get("gemini_chemin", ""))
    if not path:
        raise GeminiError("Commande « agy » introuvable. Indiquez son chemin dans les réglages "
                          "(dans un terminal : which agy).")
    if is_agy(path):
        cmd, stdin = _agy_command(path, prompt, settings)
    else:
        cmd = [path] + (["-m", settings["gemini_modele"]] if settings.get("gemini_modele") else [])
        cmd += ["-p", INSTRUCTION_COURTE]
        stdin = prompt
    workdir = tempfile.mkdtemp(prefix="assistant-email-")  # dossier vide : l'IA n'a rien à lire
    try:
        res = subprocess.run(cmd, input=stdin or "", capture_output=True, text=True, cwd=workdir,
                             env=_env_with(path), timeout=int(settings.get("gemini_delai", 240)) + 30)
    except subprocess.TimeoutExpired:
        raise GeminiError("L'IA n'a pas répondu à temps. Réessayez ou augmentez le délai dans les réglages.")
    except OSError as exc:
        raise GeminiError("Impossible de lancer %s : %s" % (os.path.basename(path), exc))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    out = res.stdout.strip()
    if is_agy(path) and out:
        text = parse_agy_output(out)
        if res.returncode == 0 and text:
            return text
    if res.returncode != 0 or not out:
        raise GeminiError(_explain("(code %s) %s" % (res.returncode, (res.stderr or res.stdout or "").strip())))
    return out
