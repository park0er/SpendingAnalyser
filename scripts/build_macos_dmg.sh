#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BUILD_PYTHON="${PYTHON_BUILD:-/usr/bin/python3}"
BUILD_ARCH="$("$BUILD_PYTHON" -c 'import platform; print(platform.machine())')"
CURRENT_ARCH=""
if [ -x ".venv-build/bin/python" ]; then
  CURRENT_ARCH="$(.venv-build/bin/python -c 'import platform; print(platform.machine())')"
fi

if [ ! -x ".venv-build/bin/python" ] || [ "$CURRENT_ARCH" != "$BUILD_ARCH" ]; then
  rm -rf .venv-build
  "$BUILD_PYTHON" -m venv .venv-build
fi

.venv-build/bin/python -m pip install --upgrade pip
.venv-build/bin/python -m pip install -r requirements.txt pyinstaller

rm -rf build/backend build/pyinstaller release
npm run frontend:build
.venv-build/bin/pyinstaller packaging/backend.spec --noconfirm --distpath build/backend --workpath build/pyinstaller
xattr -cr node_modules/electron 2>/dev/null || true
xattr -cr build/backend 2>/dev/null || true
npx electron-builder --mac dmg
