"""Action rapide macOS « Répondre avec l'IA » : apparaît dans Mail › Services et reçoit un raccourci clavier.

L'action ne fait qu'écrire un fichier déclencheur ; l'app de la barre de menus le lit et ouvre l'assistant sur le
message sélectionné dans Mail.
"""
from __future__ import annotations

import plistlib
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from . import config

NOM = "Répondre avec l'IA"
BUNDLE_ID = "com.michaelravedoni.assistant-email"
VERSION_ACTION = 2


def declencheur() -> Path:
    return config.app_home() / "declencheur"


def ecrire_declencheur(action: str = "mail") -> None:
    declencheur().write_text(action, encoding="utf-8")


def lire_declencheur(age_max: float = 30.0) -> Optional[str]:
    """Action demandée par l'action rapide (puis supprimée), ou None. Un fichier trop ancien est ignoré."""
    p = declencheur()
    try:
        fresh = time.time() - p.stat().st_mtime < age_max
        action = p.read_text(encoding="utf-8").strip()
        p.unlink()
    except OSError:
        return None
    return action if fresh and action else None


def _script() -> str:
    return ('echo mail > "$HOME/Library/Application Support/AssistantEmail/declencheur"\n'
            'open -g -b %s 2>/dev/null || open -g -a "Assistant Email" 2>/dev/null\n' % BUNDLE_ID)


def workflow_plists():
    uid = lambda: str(uuid.uuid4()).upper()
    info = {
        "CFBundleName": NOM, "CFBundleIdentifier": "com.michaelravedoni.assistant-email.action",
        "AssistantEmailActionVersion": VERSION_ACTION,
        "NSServices": [{
            "NSMenuItem": {"default": NOM},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.mail"},
        }],
    }
    action = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {"COMMAND_STRING": {}, "CheckedForUserDefaultShell": {}, "inputMethod": {},
                                  "shell": {}, "source": {}},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {"COMMAND_STRING": _script(), "CheckedForUserDefaultShell": True, "inputMethod": 1,
                             "shell": "/bin/zsh", "source": ""},
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False, "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"], "Class Name": "RunShellScriptAction",
        "InputUUID": uid(), "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": uid(), "UUID": uid(), "UnlocalizedApplications": ["Automator"],
        "arguments": {}, "isViewVisible": 1, "location": "309.000000:253.000000",
        "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
    }
    wflow = {
        "AMApplicationBuild": "523", "AMApplicationVersion": "2.10", "AMDocumentVersion": "2",
        "actions": [{"action": action, "isViewVisible": 1}],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {}, "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.nothing", "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 11, "processesInput": 0,
            "serviceApplicationBundleID": "com.apple.mail", "serviceInputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing", "serviceProcessesInput": 0,
            "systemImageName": "NSActionTemplate", "useAutomaticInputType": 0,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }
    return info, wflow


def installer(services_dir: Optional[Path] = None) -> bool:
    """Crée (ou met à jour) l'action rapide. Renvoie True si elle a été écrite."""
    services = services_dir or (Path.home() / "Library" / "Services")
    bundle = services / (NOM + ".workflow")
    info_path = bundle / "Contents" / "Info.plist"
    try:
        if info_path.exists() and plistlib.loads(info_path.read_bytes()).get("AssistantEmailActionVersion") == VERSION_ACTION:
            return False
    except Exception:
        pass
    info, wflow = workflow_plists()
    (bundle / "Contents").mkdir(parents=True, exist_ok=True)
    info_path.write_bytes(plistlib.dumps(info))
    (bundle / "Contents" / "document.wflow").write_bytes(plistlib.dumps(wflow))
    return True


def desinstaller(services_dir: Optional[Path] = None) -> None:
    import shutil
    services = services_dir or (Path.home() / "Library" / "Services")
    shutil.rmtree(services / (NOM + ".workflow"), ignore_errors=True)
