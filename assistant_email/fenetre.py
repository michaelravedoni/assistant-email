"""Fenêtre native (WebKit via pywebview), lancée dans un processus séparé de la barre de menus."""
from __future__ import annotations

import sys


class Api:
    """Fonctions natives appelables depuis la page (window.pywebview.api.…)."""

    def dicter(self) -> bool:
        """Lance la dictée macOS sur le champ qui a le focus (comme Édition › Démarrer la dictation)."""
        try:
            from AppKit import NSApplication
            from PyObjCTools import AppHelper
        except ImportError:
            return False

        def start():
            app = NSApplication.sharedApplication()
            app.activateIgnoringOtherApps_(True)
            app.sendAction_to_from_("startDictation:", None, None)

        AppHelper.callAfter(start)
        return True


def _brand() -> None:
    """Nom et icône de l'app dans le Dock et le menu (sinon : « Python » et la fusée)."""
    try:
        from pathlib import Path
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular, NSImage
        from Foundation import NSBundle, NSProcessInfo
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Assistant Email"
        NSProcessInfo.processInfo().setProcessName_("Assistant Email")
        # l'app est un agent (pas de Dock) : la fenêtre, elle, doit apparaître dans le Dock et le Cmd+Tab
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyRegular)
        icon = Path(__file__).parent / "assets" / "icone.png"
        if icon.exists():
            NSApplication.sharedApplication().setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(str(icon)))
    except Exception:
        pass


def main(url: str) -> int:
    try:
        import webview  # pywebview
    except ImportError:
        import webbrowser
        webbrowser.open(url)
        return 0
    _brand()
    from . import journal
    journal.ecrire("fenêtre : ouverture de %s" % url)
    webview.create_window("Assistant Email", url, js_api=Api(), width=1360, height=880,
                          min_size=(960, 640), text_select=True)
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
