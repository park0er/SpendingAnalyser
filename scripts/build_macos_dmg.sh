#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET_ARCH="${BUILD_TARGET_ARCH:-$(uname -m)}"
case "$TARGET_ARCH" in
  arm64)
    ELECTRON_ARCH="arm64"
    EXPECTED_PY_ARCH="arm64"
    VENV_DIR=".venv-build-arm64"
    BUILD_PYTHON="${PYTHON_BUILD_ARM64:-${PYTHON_BUILD:-/usr/bin/python3}}"
    PYTHON_CMD=("$BUILD_PYTHON")
    VENV_PYTHON_CMD=("$VENV_DIR/bin/python")
    ;;
  x64|x86_64|amd64)
    ELECTRON_ARCH="x64"
    EXPECTED_PY_ARCH="x86_64"
    VENV_DIR=".venv-build-x64"
    BUILD_PYTHON="${PYTHON_BUILD_X64:-${PYTHON_BUILD:-/usr/bin/python3}}"
    PYTHON_CMD=(arch -x86_64 "$BUILD_PYTHON")
    VENV_PYTHON_CMD=(arch -x86_64 "$VENV_DIR/bin/python")
    ;;
  *)
    echo "Unsupported BUILD_TARGET_ARCH: $TARGET_ARCH" >&2
    exit 1
    ;;
esac

BUILD_ARCH="$("${PYTHON_CMD[@]}" -c 'import platform; print(platform.machine())')"
if [ "$BUILD_ARCH" != "$EXPECTED_PY_ARCH" ]; then
  echo "Python architecture mismatch: expected $EXPECTED_PY_ARCH, got $BUILD_ARCH" >&2
  exit 1
fi

CURRENT_ARCH=""
if [ -x "$VENV_DIR/bin/python" ]; then
  CURRENT_ARCH="$("${VENV_PYTHON_CMD[@]}" -c 'import platform; print(platform.machine())')"
fi

if [ ! -x "$VENV_DIR/bin/python" ] || [ "$CURRENT_ARCH" != "$BUILD_ARCH" ]; then
  rm -rf "$VENV_DIR"
  "${PYTHON_CMD[@]}" -m venv "$VENV_DIR"
fi

"${VENV_PYTHON_CMD[@]}" -m pip install --upgrade pip
"${VENV_PYTHON_CMD[@]}" -m pip install --upgrade --force-reinstall -r requirements.txt pyinstaller

rm -rf build/backend build/pyinstaller
if [ "${CLEAN_RELEASE:-1}" = "1" ]; then
  rm -rf release
fi
npm run frontend:build
"${VENV_PYTHON_CMD[@]}" -m PyInstaller packaging/backend.spec --noconfirm --distpath build/backend --workpath build/pyinstaller
xattr -cr node_modules/electron 2>/dev/null || true
xattr -cr build/backend 2>/dev/null || true
file build/backend/spending-backend/spending-backend
npx electron-builder --mac dmg "--$ELECTRON_ARCH"
