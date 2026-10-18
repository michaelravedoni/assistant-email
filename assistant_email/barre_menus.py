"""Application de barre de menus macOS (rumps)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import rumps

import webbrowser

from . import action_rapide, config, journal, macos, sauvegarde, server


ICON = Path(__file__).parent / "assets" / "barre_menus@2x.png"


class AssistantApp(rumps.App):
    def __init__(self) -> None:
        if ICON.exists():  # icône « modèle » : suit automatiquement le clair/sombre de la barre de menus
            super().__init__("Assistant Email", icon=str(ICON), template=True, quit_button=None)
        else:
            super().__init__("Assistant Email", title="✉︎", quit_button=None)
        self.srv = server.LocalServer(int(config.load_settings().get("port", 8765))).start()
        self.window: Optional[subprocess.Popen] = None
        self.menu = [
            rumps.MenuItem("Ouvrir l'assistant", callback=lambda _: self.show("")),
            rumps.MenuItem("Répondre au message sélectionné dans Mail", callback=lambda _: self.show("mail")),
            rumps.MenuItem("Répondre au texte copié", callback=lambda _: self.show("presse-papiers")),
            None,
            rumps.MenuItem("Profils et réglages", callback=lambda _: self.show("profils")),
            rumps.MenuItem("Rechercher une mise à jour…", callback=lambda _: self.show("mise-a-jour")),
            None,
            rumps.MenuItem("Quitter", callback=self.quit),
        ]

        self.timer = rumps.Timer(self.surveiller_declencheur, 0.6)
        self.timer.start()

    def surveiller_declencheur(self, _timer) -> None:
        """L'action rapide de Mail dépose un fichier : on ouvre alors l'assistant sur le message sélectionné."""
        self.verifier_fenetre()
        action = action_rapide.lire_declencheur()
        if action:
            self.show(action)

    def show(self, action: str) -> None:
        try:
            self._show(action)
        except Exception:
            journal.erreur("ouverture de la fenêtre (%s)" % action)
            rumps.alert("Assistant Email", "Impossible d'ouvrir la fenêtre. Détails dans :\n%s" % (config.app_home() / "journal.log"))

    def _commande_fenetre(self, url: str):
        if getattr(sys, "frozen", False):
            # Dans l'app empaquetée, sys.executable est l'interpréteur interne : il faut relancer l'exécutable principal.
            principal = Path(sys.executable).parent / "Assistant Email"
            try:
                from Foundation import NSBundle
                principal = Path(NSBundle.mainBundle().executablePath())
            except Exception:
                pass
            return [str(principal), "--fenetre", url]
        return [sys.executable, "-m", "assistant_email.fenetre", url]

    def _show(self, action: str) -> None:
        alive = self.window is not None and self.window.poll() is None
        if alive and server.window_is_open():
            if action:
                server.EVENTS.append(action)
            macos.bring_to_front(self.window.pid)
            return
        if alive:
            self.window.terminate()
        url = self.srv.url(action)
        cmd = self._commande_fenetre(url)
        journal.ecrire("ouverture de la fenêtre : %s" % " ".join(cmd))
        err = (config.app_home() / "fenetre.log").open("w")
        self.window = subprocess.Popen(cmd, stderr=err, stdout=err)
        self.fallback = (self.window, url, time.time())

    def verifier_fenetre(self) -> None:
        """Si la fenêtre se ferme tout de suite (erreur), on le note et on ouvre l'assistant dans le navigateur."""
        fb = getattr(self, "fallback", None)
        if not fb:
            return
        proc, url, t0 = fb
        code = proc.poll()
        if code is None:
            if time.time() - t0 > 6:
                self.fallback = None
            return
        self.fallback = None
        if code != 0 and time.time() - t0 < 6:
            try:
                detail = (config.app_home() / "fenetre.log").read_text(errors="ignore")[-1500:]
            except OSError:
                detail = ""
            journal.ecrire("la fenêtre s'est fermée avec le code %s\n%s" % (code, detail))
            webbrowser.open(url)

    def quit(self, _sender) -> None:
        if self.window is not None and self.window.poll() is None:
            self.window.terminate()
        self.srv.stop()
        rumps.quit_application()


def main() -> int:
    journal.ecrire("démarrage (frozen=%s, exécutable=%s)" % (getattr(sys, "frozen", False), sys.executable))
    sauvegarde.sauvegarder_si_modifie()
    action_rapide.lire_declencheur(age_max=0)     # ignore un déclencheur resté d'une session précédente
    try:
        action_rapide.installer()
    except OSError:
        pass
    try:  # pas d'icône dans le Dock : uniquement la barre de menus
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    try:
        AssistantApp().run()
    except Exception:
        journal.erreur("démarrage de la barre de menus")
        raise
    return 0
