#!/usr/bin/env bash
# Construit l'application Linux (dossier dist/ConvertiaStudio/).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

python3 -m pip install --quiet --upgrade "pyinstaller>=6.10" "numpy>=1.26" \
    "PySide6>=6.6" "Pillow>=11"
python3 build/make_icon.py
python3 -m PyInstaller --noconfirm --clean build/convertia_studio.spec

# ffmpeg n'est pas copié depuis le système : un binaire de distribution dépend
# des bibliothèques de la machine qui l'a produit. L'application utilise le
# ffmpeg du PATH ; les archives de release embarquent un binaire statique
# (voir .github/workflows/build.yml).

cp "${ROOT}/README.md" "${ROOT}/dist/ConvertiaStudio/LISEZ-MOI.md" 2>/dev/null || true
cp -r "${ROOT}/docs" "${ROOT}/dist/ConvertiaStudio/docs" 2>/dev/null || true

echo "Application prête : ${ROOT}/dist/ConvertiaStudio/ConvertiaStudio"
