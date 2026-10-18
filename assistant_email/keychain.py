"""Mots de passe IMAP dans le Trousseau macOS (commande `security`)."""
from __future__ import annotations

import os
import subprocess
from typing import Dict, Optional

SERVICE = "AssistantEmail-IMAP"

# Utilisé par les tests (ASSISTANT_EMAIL_TROUSSEAU=memoire) et hors macOS.
_memory: Dict[str, str] = {}


def _use_memory() -> bool:
    return os.environ.get("ASSISTANT_EMAIL_TROUSSEAU") == "memoire"


def set_password(account: str, password: str) -> None:
    if _use_memory():
        _memory[account] = password
        return
    subprocess.run(
        ["security", "add-generic-password", "-U", "-a", account, "-s", SERVICE,
         "-l", "Assistant Email (%s)" % account, "-w", password],
        check=True, capture_output=True,
    )


def get_password(account: str) -> Optional[str]:
    if _use_memory():
        return _memory.get(account)
    res = subprocess.run(
        ["security", "find-generic-password", "-a", account, "-s", SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        return None
    return res.stdout.rstrip("\n")


def delete_password(account: str) -> None:
    if _use_memory():
        _memory.pop(account, None)
        return
    subprocess.run(
        ["security", "delete-generic-password", "-a", account, "-s", SERVICE],
        capture_output=True,
    )
