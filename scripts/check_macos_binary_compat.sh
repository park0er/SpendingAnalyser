#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:?usage: $0 <path> <max-macos-version>}"
MAX_VERSION="${2:?usage: $0 <path> <max-macos-version>}"

if [ ! -e "$ROOT" ]; then
  echo "Compatibility check path does not exist: $ROOT" >&2
  exit 1
fi

if ! command -v otool >/dev/null 2>&1; then
  echo "otool is required for macOS binary compatibility checks" >&2
  exit 1
fi

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

mach_o_min_version() {
  otool -l "$1" 2>/dev/null | awk '
    /LC_BUILD_VERSION/ { build = 1 }
    build && /minos/ { print $2; exit }
    /LC_VERSION_MIN_MACOSX/ { legacy = 1 }
    legacy && /version/ { print $2; exit }
  '
}

tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

while IFS= read -r -d '' file_path; do
  if ! file "$file_path" | grep -q 'Mach-O'; then
    continue
  fi

  min_version="$(mach_o_min_version "$file_path")"
  if [ -n "$min_version" ]; then
    if version_gt "$min_version" "$MAX_VERSION"; then
      printf '%s\t%s\n' "$min_version" "$file_path" >> "$tmpfile"
    fi
  fi
done < <(find "$ROOT" -type f -print0) || true

if [ -s "$tmpfile" ]; then
  echo "Found macOS binaries that require newer than macOS $MAX_VERSION:" >&2
  sort -r "$tmpfile" | sed -n '1,80p' >&2
  exit 1
fi

echo "macOS binary compatibility OK: $ROOT <= $MAX_VERSION"
