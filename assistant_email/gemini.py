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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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
            res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, stdin=subprocess.DEVNULL)
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
    # Si l'encodage des arguments n'est pas l'UTF-8 (app lancée sans langue définie), les accents passent par l'entrée standard.
    utf8_args = sys.getfilesystemencoding().lower().replace("-", "") == "utf8"
    if utf8_args and len(prompt.encode("utf-8")) <= MAX_ARG_BYTES:
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


def parse_agy(stdout: str) -> Tuple[str, Dict[str, Any]]:
    """Texte de la réponse et informations utiles (modèle, durée) lues dans l'enveloppe JSON d'agy."""
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
        return stdout.strip(), {}  # sortie texte brute
    status = str(envelope.get("status") or "SUCCESS").upper()
    if envelope.get("error") or status not in ("SUCCESS", "OK"):
        raise GeminiError(_explain("%s : %s" % (status, envelope.get("error") or "réponse vide")))
    info = {}
    for key in ("model", "model_name", "modele"):
        if isinstance(envelope.get(key), str) and envelope[key].strip():
            info["modele"] = envelope[key].strip()
            break
    return str(envelope.get("response") or "").strip(), info


def parse_agy_output(stdout: str) -> str:
    return parse_agy(stdout)[0]


_ENTETES = {"available", "models", "model", "name", "id", "default", "usage", "modèles", "modele", "modèle"}


def list_models(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Modèles proposés par agy (« agy models ») : la liste évolue avec le temps, on la relit à la demande."""
    path = find_gemini(settings.get("gemini_chemin", ""))
    if not path:
        raise GeminiError("Commande « agy » introuvable : indiquez son chemin dans les réglages.")
    if not is_agy(path):
        raise GeminiError("La liste des modèles n'est disponible qu'avec agy.")
    try:
        res = subprocess.run([path, "models"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=45, env=_env_with(path), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GeminiError("« agy models » n'a pas répondu à temps.")
    except OSError as exc:
        raise GeminiError("Impossible de lancer agy : %s" % exc)
    brut = (res.stdout or "").strip()
    if res.returncode != 0 and not brut:
        raise GeminiError(_explain("(code %s) %s" % (res.returncode, res.stderr or "")))
    noms: List[str] = []
    for line in brut.splitlines():
        line = re.sub(r"^[\s\-*•>·]+", "", line.strip())
        token = re.split(r"[\s(,;|]", line, maxsplit=1)[0].strip("`'\"") if line else ""
        if (re.match(r"^[A-Za-z][\w.\-:/]{2,}$", token) and not token.endswith(":")
                and token.lower() not in _ENTETES and token not in noms):
            noms.append(token)
    return {"modeles": noms, "brut": brut[-3000:]}


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


def _fermer(proc: "subprocess.Popen") -> None:
    for flux in (proc.stdout, proc.stderr):
        try:
            flux.close()
        except OSError:
            pass


def _arreter(proc: "subprocess.Popen") -> None:
    proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    _fermer(proc)


class Cancelled(GeminiError):
    pass


def _label(line: str) -> str:
    """Une ligne de sortie d'agy, résumée pour l'affichage (événements JSON ou texte)."""
    line = line.strip()
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except ValueError:
            return ""
        if isinstance(obj, dict):
            name = obj.get("event") or obj.get("type") or ""
            step = obj.get("step") if isinstance(obj.get("step"), dict) else {}
            detail = step.get("type") or obj.get("status") or ""
            return " · ".join(x for x in (str(name), str(detail)) if x)[:120]
        return ""
    return line[:160]


def run_detailed(prompt: str, settings: Dict[str, Any], on_event: Optional[Callable[[str, str], None]] = None,
                 cancel: Optional[threading.Event] = None) -> Tuple[str, Dict[str, Any]]:
    """Lance l'IA et renvoie (texte, infos). on_event(type, texte) signale l'avancement ; cancel l'interrompt."""
    emit = on_event or (lambda kind, text: None)
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
    delai = int(settings.get("gemini_delai", 240))
    workdir = tempfile.mkdtemp(prefix="assistant-email-")  # dossier vide : l'IA n'a rien à lire
    t0 = time.time()
    out: List[str] = []
    err: List[str] = []
    activite = [t0]
    try:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=workdir, env=_env_with(path), text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            raise GeminiError("Impossible de lancer %s : %s" % (os.path.basename(path), exc))
        emit("demarrage", "%s lancé, connexion et chargement…" % os.path.basename(path))

        def ecrire():
            try:
                proc.stdin.write(stdin or "")
            except OSError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        def lire(flux, store, kind):
            try:
                for line in flux:
                    store.append(line)
                    activite[0] = time.time()
                    label = _label(line)
                    if label:
                        emit(kind, label)
            except (ValueError, OSError):      # flux fermé pendant l'arrêt du processus
                pass

        threads = [threading.Thread(target=ecrire, daemon=True),
                   threading.Thread(target=lire, args=(proc.stdout, out, "sortie"), daemon=True),
                   threading.Thread(target=lire, args=(proc.stderr, err, "info"), daemon=True)]
        for t in threads:
            t.start()
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                _arreter(proc)
                raise Cancelled("Rédaction annulée.")
            if time.time() - t0 > delai + 30:
                _arreter(proc)
                raise GeminiError("L'IA n'a pas répondu à temps (%d s). Réessayez ou augmentez le délai dans les "
                                  "réglages." % (delai + 30))
            time.sleep(0.15)
        for t in threads[1:]:
            t.join(timeout=5)
        _fermer(proc)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    stdout, stderr = "".join(out).strip(), "".join(err).strip()
    info: Dict[str, Any] = {"duree": round(time.time() - t0, 1), "commande": os.path.basename(path)}
    if is_agy(path) and stdout:
        text, meta = parse_agy(stdout)
        info.update(meta)
        if proc.returncode == 0 and text:
            return text, info
    if proc.returncode != 0 or not stdout:
        raise GeminiError(_explain("(code %s) %s" % (proc.returncode, (stderr or stdout).strip())))
    return stdout, info


def run(prompt: str, settings: Dict[str, Any]) -> str:
    return run_detailed(prompt, settings)[0]
