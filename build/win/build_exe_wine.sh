#!/usr/bin/env bash
# Construit l'exécutable Windows de Convertia Studio depuis Linux, via Wine.
#
# Étapes : préfixe Wine isolé → Python 3.12 pour Windows → pip (PyInstaller,
# numpy, PySide6) → PyInstaller avec build/convertia_studio.spec → archive ZIP.
#
# Tout est confiné dans .winbuild/ (ignoré du dépôt) ; rien n'est installé
# sur le système.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${ROOT}/.winbuild"
BUILD="${WORK}/prefix/drive_c/build"
DIST="${ROOT}/dist"
PY_DIR='C:\Python312'
PY="${PY_DIR}\\python.exe"
LOG_PREFIX="[build-win]"

mkdir -p "${WORK}" "${DIST}"

export WINEPREFIX="${WORK}/prefix"
export WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree,mshtml="
export XDG_CACHE_HOME="${WORK}/cache"
export XDG_DATA_HOME="${WORK}/data"
export XDG_CONFIG_HOME="${WORK}/config"
export TMPDIR="${WORK}/tmp"
mkdir -p "${XDG_CACHE_HOME}" "${XDG_DATA_HOME}" "${XDG_CONFIG_HOME}" "${TMPDIR}"

log() { echo "${LOG_PREFIX} $*"; }

# ---------------------------------------------------------------- 1. préfixe
if [ ! -d "${WINEPREFIX}/drive_c/windows" ]; then
    log "initialisation du préfixe Wine…"
    wineboot -i >/dev/null 2>&1 || true
    wineserver -w || true
fi

# ------------------------------------------------------- 2. Python Windows
if [ ! -f "${WINEPREFIX}/drive_c/Python312/python.exe" ]; then
    INSTALLER="${WORK}/python-installer.exe"
    if [ ! -f "${INSTALLER}" ]; then
        log "téléchargement de Python 3.12 pour Windows…"
        curl -sSL -o "${INSTALLER}" \
            "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    fi
    log "installation silencieuse de Python…"
    wine "${INSTALLER}" /quiet InstallAllUsers=0 "TargetDir=${PY_DIR}" \
        Include_pip=1 Include_test=0 Include_doc=0 Include_tcltk=0 \
        Include_launcher=0 Shortcuts=0 >/dev/null 2>&1 || true
    wineserver -w || true
fi
if [ ! -f "${WINEPREFIX}/drive_c/Python312/python.exe" ]; then
    log "ERREUR : Python Windows absent après installation"
    exit 1
fi

# ---------------------------------------------------------------- 3. pip
log "mise à jour de pip…"
wine "${PY}" -m pip install --disable-pip-version-check -q --upgrade pip
log "installation de PyInstaller, numpy et PySide6 (long)…"
wine "${PY}" -m pip install --disable-pip-version-check -q \
    "pyinstaller>=6.10" "numpy>=1.26" "PySide6>=6.6"
wine "${PY}" -m PyInstaller --version

# ------------------------------------------------------ 4. sources + spec
log "copie des sources dans le préfixe…"
mkdir -p "${BUILD}"
rm -rf "${BUILD}/convertia_studio" "${BUILD}/convertia_studio.pyw" \
       "${BUILD}/convertia_studio.spec"
cp -r "${ROOT}/convertia_studio" "${BUILD}/convertia_studio"
cp "${ROOT}/convertia_studio.pyw" "${BUILD}/convertia_studio.pyw"
cp "${ROOT}/build/convertia_studio.spec" "${BUILD}/convertia_studio.spec"
cp "${ROOT}/build/convertia_studio.ico" "${BUILD}/convertia_studio.ico"
find "${BUILD}/convertia_studio" -name '__pycache__' -type d -prune -exec rm -rf {} +

# ffmpeg Windows embarqué (téléchargé au besoin)
FFMPEG_ZIP="${ROOT}/build/win/ffmpeg-win64.zip"
if [ ! -f "${FFMPEG_ZIP}" ] || ! unzip -tq "${FFMPEG_ZIP}" >/dev/null 2>&1; then
    log "téléchargement de ffmpeg pour Windows…"
    curl -sSL -o "${FFMPEG_ZIP}" \
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" || true
fi
rm -rf "${BUILD}/bin"
mkdir -p "${BUILD}/bin"
if [ -f "${FFMPEG_ZIP}" ] && unzip -tq "${FFMPEG_ZIP}" >/dev/null 2>&1; then
    log "extraction de ffmpeg.exe pour Windows…"
    rm -rf "${WORK}/ffmpeg-extract"
    mkdir -p "${WORK}/ffmpeg-extract"
    unzip -q -o "${FFMPEG_ZIP}" -d "${WORK}/ffmpeg-extract"
    find "${WORK}/ffmpeg-extract" -name 'ffmpeg.exe' -exec cp {} "${BUILD}/bin/" \;
    log "ffmpeg embarqué : $(du -h "${BUILD}/bin/ffmpeg.exe" | cut -f1)"
else
    log "archive ffmpeg absente ou incomplète : l'exécutable cherchera ffmpeg dans le PATH"
fi

# ------------------------------------------------------------ 5. PyInstaller
log "lancement de PyInstaller…"
(
    cd "${BUILD}"
    wine "${PY}" -m PyInstaller --noconfirm --clean convertia_studio.spec
)

# ---------------------------------------------------------------- 6. archive
APP_DIR="${BUILD}/dist/ConvertiaStudio"
if [ ! -d "${APP_DIR}" ]; then
    log "ERREUR : dossier dist/ConvertiaStudio absent"
    exit 1
fi
if [ -f "${BUILD}/bin/ffmpeg.exe" ]; then
    mkdir -p "${APP_DIR}/bin"
    cp "${BUILD}/bin/ffmpeg.exe" "${APP_DIR}/bin/"
fi
cp "${ROOT}/README.md" "${APP_DIR}/LISEZ-MOI.md" 2>/dev/null || true
cp -r "${ROOT}/docs" "${APP_DIR}/docs" 2>/dev/null || true

NAME="ConvertiaStudio-$(date +%Y%m%d)-win64"
rm -f "${DIST}/${NAME}.zip"
rm -rf "${DIST}/ConvertiaStudio-win64"
cp -r "${APP_DIR}" "${DIST}/ConvertiaStudio-win64"
( cd "${DIST}" && zip -q -r "${NAME}.zip" ConvertiaStudio-win64 )
log "exécutable prêt : ${DIST}/ConvertiaStudio-win64/ConvertiaStudio.exe"
log "archive         : ${DIST}/${NAME}.zip"
