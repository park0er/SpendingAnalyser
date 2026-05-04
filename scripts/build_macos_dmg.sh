#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET_ARCH="${BUILD_TARGET_ARCH:-$(uname -m)}"

version_gt() {
  awk -v left="$1" -v right="$2" '
    BEGIN {
      split(left, a, ".")
      split(right, b, ".")
      for (i = 1; i <= 3; i++) {
        av = (a[i] == "" ? 0 : a[i]) + 0
        bv = (b[i] == "" ? 0 : b[i]) + 0
        if (av > bv) exit 0
        if (av < bv) exit 1
      }
      exit 1
    }
  '
}

python_cmd_output() {
  local expected_arch="$1"
  local python_path="$2"
  shift 2

  if [ "$expected_arch" = "x86_64" ]; then
    arch -x86_64 "$python_path" "$@"
  else
    "$python_path" "$@"
  fi
}

python_struct_module() {
  local expected_arch="$1"
  local python_path="$2"

  python_cmd_output "$expected_arch" "$python_path" - <<'PY'
import glob
import os
import sysconfig

dest = sysconfig.get_config_var("DESTSHARED") or ""
matches = glob.glob(os.path.join(dest, "_struct*.so"))
print(matches[0] if matches else "")
PY
}

mach_o_min_version() {
  otool -l "$1" 2>/dev/null | awk '
    /LC_BUILD_VERSION/ { build = 1 }
    build && /minos/ { print $2; exit }
    /LC_VERSION_MIN_MACOSX/ { legacy = 1 }
    legacy && /version/ { print $2; exit }
  '
}

is_supported_python_version() {
  case "$1" in
    3.9|3.10|3.11|3.12) return 0 ;;
    *) return 1 ;;
  esac
}

is_compatible_build_python() {
  local expected_arch="$1"
  local max_macos_version="$2"
  local python_path="$3"
  local actual_arch python_version struct_module min_version

  [ -x "$python_path" ] || return 1

  actual_arch="$(python_cmd_output "$expected_arch" "$python_path" -c 'import platform; print(platform.machine())' 2>/dev/null || true)"
  [ "$actual_arch" = "$expected_arch" ] || return 1

  python_version="$(python_cmd_output "$expected_arch" "$python_path" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  is_supported_python_version "$python_version" || return 1

  struct_module="$(python_struct_module "$expected_arch" "$python_path" 2>/dev/null || true)"
  [ -n "$struct_module" ] && [ -f "$struct_module" ] || return 1

  min_version="$(mach_o_min_version "$struct_module")"
  [ -n "$min_version" ] || return 1
  if version_gt "$min_version" "$max_macos_version"; then
    return 1
  fi

  return 0
}

select_build_python() {
  local expected_arch="$1"
  local max_macos_version="$2"
  shift 2
  local candidate

  for candidate in "$@"; do
    if is_compatible_build_python "$expected_arch" "$max_macos_version" "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

case "$TARGET_ARCH" in
  arm64)
    ELECTRON_ARCH="arm64"
    EXPECTED_PY_ARCH="arm64"
    VENV_DIR=".venv-build-arm64"
    MACOS_COMPATIBILITY_VERSION="${MACOS_COMPATIBILITY_VERSION_ARM64:-${MACOS_COMPATIBILITY_VERSION:-14.0}}"
    BUILD_PYTHON="${PYTHON_BUILD_ARM64:-${PYTHON_BUILD:-/usr/bin/python3}}"
    PYTHON_CMD=("$BUILD_PYTHON")
    VENV_PYTHON_CMD=("$VENV_DIR/bin/python")
    ;;
  x64|x86_64|amd64)
    ELECTRON_ARCH="x64"
    EXPECTED_PY_ARCH="x86_64"
    VENV_DIR=".venv-build-x64"
    MACOS_COMPATIBILITY_VERSION="${MACOS_COMPATIBILITY_VERSION_X64:-${MACOS_COMPATIBILITY_VERSION:-12.0}}"
    if [ -n "${PYTHON_BUILD_X64:-${PYTHON_BUILD:-}}" ]; then
      BUILD_PYTHON="${PYTHON_BUILD_X64:-${PYTHON_BUILD:-}}"
    else
      BUILD_PYTHON="$(select_build_python "$EXPECTED_PY_ARCH" "$MACOS_COMPATIBILITY_VERSION" \
        "$HOME/opt/anaconda3/bin/python3" \
        "/opt/anaconda3/bin/python3" \
        "/usr/local/anaconda3/bin/python3" \
        "/usr/local/bin/python3.12" \
        "/usr/local/bin/python3.11" \
        "/usr/local/bin/python3.10" \
        "/usr/local/bin/python3.9" \
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
        "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3" \
        "/Library/Frameworks/Python.framework/Versions/3.9/bin/python3" \
        "/usr/local/bin/python3" \
        "/usr/bin/python3")" || {
        echo "No compatible x64 Python found for macOS $MACOS_COMPATIBILITY_VERSION packaging." >&2
        echo "Set PYTHON_BUILD_X64 to a Python 3.9-3.12 x86_64 runtime whose stdlib supports macOS $MACOS_COMPATIBILITY_VERSION or older." >&2
        exit 1
      }
    fi
    PYTHON_CMD=(arch -x86_64 "$BUILD_PYTHON")
    VENV_PYTHON_CMD=(arch -x86_64 "$VENV_DIR/bin/python")
    ;;
  *)
    echo "Unsupported BUILD_TARGET_ARCH: $TARGET_ARCH" >&2
    exit 1
    ;;
esac

if [ "$EXPECTED_PY_ARCH" = "x86_64" ] && ! is_compatible_build_python "$EXPECTED_PY_ARCH" "$MACOS_COMPATIBILITY_VERSION" "$BUILD_PYTHON"; then
  echo "Selected x64 Python is not compatible with macOS $MACOS_COMPATIBILITY_VERSION packaging: $BUILD_PYTHON" >&2
  echo "Use Python 3.9-3.12 x86_64 with stdlib Mach-O min version <= $MACOS_COMPATIBILITY_VERSION." >&2
  exit 1
fi

echo "Building $ELECTRON_ARCH package with Python: $BUILD_PYTHON"
echo "Checking packaged Mach-O files against macOS <= $MACOS_COMPATIBILITY_VERSION"

BUILD_ARCH="$("${PYTHON_CMD[@]}" -c 'import platform; print(platform.machine())')"
if [ "$BUILD_ARCH" != "$EXPECTED_PY_ARCH" ]; then
  echo "Python architecture mismatch: expected $EXPECTED_PY_ARCH, got $BUILD_ARCH" >&2
  exit 1
fi

PYTHON_FINGERPRINT="$("${PYTHON_CMD[@]}" - <<'PY'
import os
import sys
import sysconfig

print(os.path.realpath(sys.executable))
print(sys.version)
print(sys.base_prefix)
print(sysconfig.get_config_var("DESTSHARED") or "")
PY
)"

CURRENT_ARCH=""
if [ -x "$VENV_DIR/bin/python" ]; then
  CURRENT_ARCH="$("${VENV_PYTHON_CMD[@]}" -c 'import platform; print(platform.machine())')"
fi

CURRENT_FINGERPRINT=""
if [ -f "$VENV_DIR/.build-python-fingerprint" ]; then
  CURRENT_FINGERPRINT="$(cat "$VENV_DIR/.build-python-fingerprint")"
fi

if [ ! -x "$VENV_DIR/bin/python" ] || [ "$CURRENT_ARCH" != "$BUILD_ARCH" ] || [ "$CURRENT_FINGERPRINT" != "$PYTHON_FINGERPRINT" ]; then
  rm -rf "$VENV_DIR"
  "${PYTHON_CMD[@]}" -m venv "$VENV_DIR"
  printf '%s\n' "$PYTHON_FINGERPRINT" > "$VENV_DIR/.build-python-fingerprint"
fi

"${VENV_PYTHON_CMD[@]}" -m pip install --upgrade pip
"${VENV_PYTHON_CMD[@]}" -m pip install --upgrade --force-reinstall --only-binary=:all: -r requirements.txt pyinstaller

rm -rf build/backend build/pyinstaller
if [ "${CLEAN_RELEASE:-1}" = "1" ]; then
  rm -rf release
fi
npm run frontend:build
"${VENV_PYTHON_CMD[@]}" -m PyInstaller packaging/backend.spec --noconfirm --distpath build/backend --workpath build/pyinstaller
scripts/check_macos_binary_compat.sh build/backend/spending-backend "$MACOS_COMPATIBILITY_VERSION"
xattr -cr node_modules/electron 2>/dev/null || true
xattr -cr build/backend 2>/dev/null || true
file build/backend/spending-backend/spending-backend
CSC_IDENTITY_AUTO_DISCOVERY=false npx electron-builder --mac dmg "--$ELECTRON_ARCH"

if [ "$ELECTRON_ARCH" = "arm64" ]; then
  APP_DIR="release/mac-arm64/SpendingAnalyser.app"
else
  APP_DIR="release/mac/SpendingAnalyser.app"
fi
scripts/check_macos_binary_compat.sh "$APP_DIR" "$MACOS_COMPATIBILITY_VERSION"
