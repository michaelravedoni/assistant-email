"""Petits ponts vers macOS : Apple Mail (AppleScript), presse-papiers, sélecteur de dossier, notifications."""
from __future__ import annotations

import subprocess
import sys
from typing import Optional

IS_MAC = sys.platform == "darwin"

MAIL_SELECTION_SCRIPT = '''
tell application "Mail"
    set sel to selection
    if sel is {} then return ""
    set m to item 1 of sel
    return source of m
end tell
'''


class MacError(Exception):
    pass


def _osascript(script: str, timeout: int = 30) -> str:
    if not IS_MAC:
        raise MacError("Disponible uniquement sur macOS.")
    res = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=timeout)
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace").strip()
        if "-1743" in err or "not allowed" in err.lower() or "autoris" in err.lower():
            raise MacError("macOS bloque l'accès à Mail. Autorisez « Assistant Email » dans Réglages Système "
                           "> Confidentialité et sécurité > Automatisation.")
        if "-128" in err:
            return ""
        raise MacError(err or "Erreur AppleScript.")
    return res.stdout.decode("utf-8", errors="replace")


def mail_selected_source() -> bytes:
    """Source brute du message sélectionné dans Apple Mail."""
    src = _osascript(MAIL_SELECTION_SCRIPT, timeout=60)
    if not src.strip():
        raise MacError("Aucun message sélectionné dans Mail.")
    # AppleScript renvoie des fins de ligne CR : on les normalise.
    return src.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def clipboard_text() -> str:
    if not IS_MAC:
        return ""
    res = subprocess.run(["pbpaste"], capture_output=True, env={"LANG": "fr_FR.UTF-8"})
    return res.stdout.decode("utf-8", errors="replace")


def copy_to_clipboard(text: str) -> None:
    if not IS_MAC:
        raise MacError("Disponible uniquement sur macOS.")
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), env={"LANG": "fr_FR.UTF-8"}, check=True)


def bring_to_front(pid: int) -> None:
    if IS_MAC:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to set frontmost of '
                        '(first process whose unix id is %d) to true' % int(pid)], capture_output=True)


def choose_folder(prompt: str = "Choisissez le dossier de modèles") -> Optional[str]:
    out = _osascript('POSIX path of (choose folder with prompt "%s")' % prompt.replace('"', ""), timeout=600)
    return out.strip() or None


def open_path(path: str) -> None:
    if IS_MAC:
        subprocess.run(["open", path], capture_output=True)


def reveal(path: str) -> None:
    if IS_MAC:
        subprocess.run(["open", "-R", path], capture_output=True)


def choose_file(prompt: str = "Choisissez un fichier de modèle") -> Optional[str]:
    out = _osascript('POSIX path of (choose file with prompt "%s")' % prompt.replace('"', ""), timeout=600)
    return out.strip() or None


def notify(title: str, text: str) -> None:
    if not IS_MAC:
        return
    safe = lambda s: s.replace("\\", "").replace('"', "'")
    subprocess.run(["osascript", "-e", 'display notification "%s" with title "%s"' % (safe(text), safe(title))],
                   capture_output=True)
