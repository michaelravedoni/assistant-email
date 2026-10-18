#!/bin/bash
# Fabrique AssistantEmail-<version>.dmg (fenêtre avec l'app et le raccourci Applications) à partir de dist/.
set -euo pipefail
VERSION="${1:?version}"
APP="dist/Assistant Email.app"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Assistant Email" -srcfolder "$STAGE" -ov -format UDZO "AssistantEmail-$VERSION.dmg"
rm -rf "$STAGE"
echo "AssistantEmail-$VERSION.dmg"
