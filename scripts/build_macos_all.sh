#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

rm -rf release
CLEAN_RELEASE=0 BUILD_TARGET_ARCH=arm64 bash scripts/build_macos_dmg.sh
CLEAN_RELEASE=0 BUILD_TARGET_ARCH=x64 bash scripts/build_macos_dmg.sh
