"""Point d'entrée de l'application empaquetée (py2app)."""
import os
import sys


def _forcer_utf8() -> None:
    """Une app lancée depuis le Finder n'a pas de langue définie : Python bascule alors en ASCII et plante sur les
    accents. On relance une fois l'exécutable principal avec l'UTF-8 forcé (filet de sécurité en plus de Info.plist)."""
    if sys.getfilesystemencoding().lower().replace("-", "") == "utf8" or os.environ.get("AE_UTF8"):
        return
    try:
        from Foundation import NSBundle
        principal = str(NSBundle.mainBundle().executablePath())
        env = dict(os.environ, AE_UTF8="1", PYTHONUTF8="1", LANG="fr_FR.UTF-8", LC_ALL="fr_FR.UTF-8")
        os.execve(principal, [principal] + sys.argv[1:], env)
    except Exception:
        pass


_forcer_utf8()

from assistant_email.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
