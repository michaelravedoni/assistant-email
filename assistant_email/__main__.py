"""Point d'entrée.

  python -m assistant_email            barre de menus (macOS)
  python -m assistant_email --web      serveur seul + ouverture dans le navigateur (dépannage)
"""
from __future__ import annotations

import sys
import time
import webbrowser


def selftest() -> int:
    """Vérifie que tout ce dont l'app a besoin est présent (utilisé par la construction automatique)."""
    import importlib
    from pathlib import Path
    from . import server
    mods = ["rumps", "webview", "AppKit", "Foundation", "WebKit", "objc"] if sys.platform == "darwin" else []
    for name in mods:
        importlib.import_module(name)
    for f in (server.WEB_DIR / "index.html", Path(__file__).parent / "assets" / "icone.png"):
        assert f.exists(), "fichier manquant : %s" % f
    print("selftest ok")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fenetre" in argv:   # utilisé par l'app empaquetée : fenêtre dans un second processus
        from .fenetre import main as fenetre_main
        return fenetre_main(argv[argv.index("--fenetre") + 1])
    if "--selftest" in argv:
        return selftest()
    if "--web" in argv or sys.platform != "darwin":
        from . import config, server
        srv = server.LocalServer(int(config.load_settings().get("port", 8765))).start()
        print("Assistant Email : %s" % srv.url())
        if "--sans-navigateur" not in argv:
            webbrowser.open(srv.url())
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            srv.stop()
        return 0
    from .barre_menus import main as menubar_main
    return menubar_main()


if __name__ == "__main__":
    sys.exit(main())
