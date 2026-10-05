#!/usr/bin/env bash
# Build dist/RemindersSys.app and dist/RemindersSys-macOS-<arch>.dmg on macOS.
#   bash packaging/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-dev.txt
python3 packaging/make_icons.py
python3 -m PyInstaller --noconfirm --clean packaging/remindersys.spec

APP=dist/RemindersSys.app
# Ad-hoc signature: required on Apple Silicon and lets macOS remember the
# Calendar/Reminders permission. Replace "-" with a Developer ID to distribute widely.
codesign --force --deep --sign "${CODESIGN_IDENTITY:--}" "$APP"

ARCH=$(uname -m)
STAGING=$(mktemp -d)
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
DMG="dist/RemindersSys-macOS-${ARCH}.dmg"
rm -f "$DMG"
hdiutil create -volname "RemindersSys" -srcfolder "$STAGING" -ov -format UDZO "$DMG"
rm -rf "$STAGING"
echo "Built $DMG"
