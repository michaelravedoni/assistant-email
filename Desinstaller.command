#!/bin/bash
# Supprime l'application et son environnement. Vos profils et modèles sont conservés sauf si vous le demandez.
HOME_APP="$HOME/Library/Application Support/AssistantEmail"
pkill -f -- "-m assistant_email" 2>/dev/null || true
osascript -e 'tell application "System Events" to delete (every login item whose name is "Assistant Email")' >/dev/null 2>&1 || true
rm -rf "$HOME/Applications/Assistant Email.app" "$HOME_APP/app" "$HOME_APP/venv"
REP=$(osascript -e 'button returned of (display dialog "Supprimer aussi les profils et les mots de passe enregistrés ?" buttons {"Garder", "Supprimer"} default button "Garder")' 2>/dev/null || echo "Garder")
if [ "$REP" = "Supprimer" ]; then
  rm -rf "$HOME_APP"
  while security delete-generic-password -s AssistantEmail-IMAP >/dev/null 2>&1; do :; done
fi
echo "Assistant Email a été désinstallé."
