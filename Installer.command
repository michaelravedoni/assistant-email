#!/bin/bash
# Installe « Assistant Email » : environnement Python, dépendances et application dans ~/Applications.
# Double-cliquez sur ce fichier dans le Finder.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
HOME_APP="$HOME/Library/Application Support/AssistantEmail"
APP="$HOME/Applications/Assistant Email.app"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mErreur : %s\033[0m\n' "$*"; osascript -e "display alert \"Installation interrompue\" message \"$*\"" >/dev/null 2>&1 || true; exit 1; }

say "Installation d'Assistant Email"

# 1. Python 3.9+ ---------------------------------------------------------------
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  if ! xcode-select -p >/dev/null 2>&1; then
    xcode-select --install >/dev/null 2>&1 || true
    fail "Python est nécessaire. macOS va proposer d'installer les « outils de ligne de commande » : acceptez, puis relancez Installer.command."
  fi
  PY=/usr/bin/python3
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || fail "Python 3.9 ou plus récent est nécessaire."
say "Python : $("$PY" --version) ($PY)"

# 2. Copie du programme ----------------------------------------------------------
mkdir -p "$HOME_APP"
rm -rf "$HOME_APP/app"
mkdir -p "$HOME_APP/app"
cp -R "$SRC/assistant_email" "$SRC/requirements.txt" "$HOME_APP/app/"
xattr -dr com.apple.quarantine "$HOME_APP/app" 2>/dev/null || true

# 3. Environnement et dépendances -----------------------------------------------
if [ ! -x "$HOME_APP/venv/bin/python" ] || ! "$HOME_APP/venv/bin/python" -c 'pass' 2>/dev/null; then
  rm -rf "$HOME_APP/venv"
  "$PY" -m venv "$HOME_APP/venv" || fail "Impossible de créer l'environnement Python."
fi
VPY="$HOME_APP/venv/bin/python"
say "Installation des dépendances (rumps, pywebview)…"
"$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VPY" -m pip install --quiet "rumps>=0.4.0" || fail "Installation de rumps impossible (connexion internet ?)."
"$VPY" -m pip install --quiet "pywebview>=5.0" || echo "pywebview non installé : l'assistant s'ouvrira dans le navigateur."

# 4. Application ----------------------------------------------------------------
say "Création de l'application dans ~/Applications…"
pkill -f -- "-m assistant_email" 2>/dev/null || true
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Assistant Email</string>
  <key>CFBundleDisplayName</key><string>Assistant Email</string>
  <key>CFBundleIdentifier</key><string>com.michaelravedoni.assistant-email</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>icone</string>
  <key>CFBundleExecutable</key><string>AssistantEmail</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSAppleEventsUsageDescription</key><string>Lire le message sélectionné dans Mail pour préparer une réponse.</string>
  <key>NSMicrophoneUsageDescription</key><string>Dicter votre réponse.</string>
  <key>NSSpeechRecognitionUsageDescription</key><string>Dicter votre réponse.</string>
</dict></plist>
PLIST
# Pour que le Dock affiche « Assistant Email » (et non « Python »), le programme Python doit tourner
# depuis l'application elle-même : on en copie l'exécutable dans l'app, puis on vérifie qu'il fonctionne.
BASE=$("$VPY" -c 'import sys; print(sys.base_prefix)')
SITE=$("$VPY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
LAUNCH_PY="$VPY"
PYENV=""
PYBIN="$BASE/Resources/Python.app/Contents/MacOS/Python"
if [ -x "$PYBIN" ]; then
  cp "$PYBIN" "$APP/Contents/MacOS/AssistantEmailPy"
  if PYTHONHOME="$BASE" PYTHONPATH="$HOME_APP/app:$SITE" "$APP/Contents/MacOS/AssistantEmailPy" -c 'import rumps, assistant_email' >/dev/null 2>&1; then
    LAUNCH_PY="$APP/Contents/MacOS/AssistantEmailPy"
    PYENV="export PYTHONHOME=\"$BASE\"; export PYTHONPATH=\"$HOME_APP/app:$SITE\""
    echo "Exécutable intégré à l'application : le Dock affichera « Assistant Email »."
  else
    rm -f "$APP/Contents/MacOS/AssistantEmailPy"
    echo "Exécutable intégré non utilisable ici : le Dock affichera « Python » (sans conséquence sur le reste)."
  fi
fi
cat > "$APP/Contents/MacOS/AssistantEmail" <<LAUNCH
#!/bin/bash
export PYTHONPATH="$HOME_APP/app"
$PYENV
export LANG="\${LANG:-fr_FR.UTF-8}"
cd "$HOME_APP"
exec "$LAUNCH_PY" -m assistant_email >> "$HOME_APP/journal.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/AssistantEmail"
cp "$HOME_APP/app/assistant_email/assets/icone.icns" "$APP/Contents/Resources/icone.icns" 2>/dev/null || true
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
touch "$APP"

# 5. Lancement au démarrage (facultatif) -----------------------------------------
REP=$(osascript -e 'button returned of (display dialog "Lancer Assistant Email automatiquement à l’ouverture de session ?" buttons {"Non", "Oui"} default button "Oui" with title "Assistant Email")' 2>/dev/null || echo "Non")
if [ "$REP" = "Oui" ]; then
  osascript -e "tell application \"System Events\" to delete (every login item whose name is \"Assistant Email\")" >/dev/null 2>&1 || true
  osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP\", hidden:false}" >/dev/null 2>&1 \
    || echo "Ajout au démarrage refusé : vous pourrez l'ajouter dans Réglages Système > Général > Ouverture."
fi

open "$APP"
say "Terminé. L'icône ✉︎ apparaît dans la barre de menus (en haut à droite)."
echo "Vous pouvez fermer cette fenêtre."
