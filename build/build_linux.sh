#!/usr/bin/env bash
# Construit l'application Linux (dossier dist/ConvertiaStudio/).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

python3 -m pip install --quiet --upgrade "pyinstaller>=6.10" "numpy>=1.26" \
    "PySide6>=6.6" "Pillow>=11"
mkdir -p bin
command -v ffmpeg >/dev/null && cp "$(command -v ffmpeg)" bin/ || true
command -v ffprobe >/dev/null && cp "$(command -v ffprobe)" bin/ || true

python3 build/make_icon.py
python3 -m PyInstaller --noconfirm --clean build/convertia_studio.spec

# l'application cherche ffmpeg dans <exe>/bin puis dans le PATH
mkdir -p "${ROOT}/dist/ConvertiaStudio/bin"
[ -f bin/ffmpeg ] && cp bin/ffmpeg "${ROOT}/dist/ConvertiaStudio/bin/" || true
[ -f bin/ffprobe ] && cp bin/ffprobe "${ROOT}/dist/ConvertiaStudio/bin/" || true

cp "${ROOT}/README.md" "${ROOT}/dist/ConvertiaStudio/LISEZ-MOI.md" 2>/dev/null || true
cp -r "${ROOT}/docs" "${ROOT}/dist/ConvertiaStudio/docs" 2>/dev/null || true

echo "Application prête : ${ROOT}/dist/ConvertiaStudio/ConvertiaStudio"
