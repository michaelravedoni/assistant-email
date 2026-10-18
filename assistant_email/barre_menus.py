"""Application de barre de menus macOS (rumps)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import rumps

from . import action_rapide, config, macos, sauvegarde, server


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
        action = action_rapide.lire_declencheur()
        if action:
            self.show(action)

    def show(self, action: str) -> None:
        alive = self.window is not None and self.window.poll() is None
        if alive and server.window_is_open():
            if action:
                server.EVENTS.append(action)
            macos.bring_to_front(self.window.pid)
            return
        if alive:
            self.window.terminate()
        if getattr(sys, "frozen", False):   # app empaquetée : on relance l'app elle-même en mode fenêtre
            cmd = [sys.executable, "--fenetre", self.srv.url(action)]
        else:
            cmd = [sys.executable, "-m", "assistant_email.fenetre", self.srv.url(action)]
        self.window = subprocess.Popen(cmd)

    def quit(self, _sender) -> None:
        if self.window is not None and self.window.poll() is None:
            self.window.terminate()
        self.srv.stop()
        rumps.quit_application()


def main() -> int:
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
    AssistantApp().run()
    return 0
