"""Construction de « Assistant Email.app » avec py2app (binaire universel : Intel et Apple Silicon).

    python setup.py py2app          # produit dist/Assistant Email.app
Normalement lancé par GitHub Actions (voir .github/workflows/build.yml), pas à la main.
"""
import re
from pathlib import Path

from setuptools import setup

VERSION = re.search(r'__version__ = "([^"]+)"', Path("assistant_email/__init__.py").read_text()).group(1)

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assistant_email/assets/icone.icns",
    "arch": "universal2",
    "packages": ["assistant_email", "webview", "rumps", "objc", "bottle", "proxy_tools"],
    "includes": ["AppKit", "Foundation", "WebKit", "Quartz", "Security", "PyObjCTools.AppHelper",
                 "typing_extensions"],
    "excludes": ["tkinter", "test", "unittest.mock"],
    "plist": {
        "CFBundleName": "Assistant Email",
        "CFBundleDisplayName": "Assistant Email",
        "CFBundleIdentifier": "com.michaelravedoni.assistant-email",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "© Michael Ravedoni",
        "NSAppleEventsUsageDescription": "Lire le message sélectionné dans Mail pour préparer une réponse.",
        "NSMicrophoneUsageDescription": "Dicter votre réponse.",
        "NSSpeechRecognitionUsageDescription": "Dicter votre réponse.",
        "NSHighResolutionCapable": True,
    },
}

setup(app=["packaging/entry.py"], name="Assistant Email", version=VERSION, options={"py2app": OPTIONS})
