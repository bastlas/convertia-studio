#!/usr/bin/env bash
# Étiquette une version et déclenche la publication GitHub.
#
#   ./scripts/release.sh v2.0.1 ["message de l'étiquette"]
#
# Le workflow .github/workflows/build.yml compile alors l'exécutable Windows et
# l'archive Linux, puis crée la Release GitHub avec les fichiers téléchargeables.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

TAG="${1:-}"
MESSAGE="${2:-Convertia Studio ${TAG#v}}"

if [ -z "${TAG}" ]; then
    echo "usage : $0 v2.0.1 [\"message\"]" >&2
    exit 2
fi
if [[ ! "${TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    echo "étiquette invalide : ${TAG} (attendu : v2.0.1)" >&2
    exit 2
fi

VERSION="$(python3 -c 'import re,pathlib; print(re.search(r"__version__\s*=\s*\"([^\"]+)\"", pathlib.Path("convertia_studio/__init__.py").read_text(encoding="utf-8")).group(1))')"
if [ "v${VERSION}" != "${TAG}" ]; then
    echo "incohérence : __version__ = ${VERSION}, étiquette ${TAG}" >&2
    echo "mets à jour convertia_studio/__init__.py (et CHANGELOG.md) avant de publier." >&2
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "l'arbre de travail n'est pas propre : commite (ou remise) les changements d'abord." >&2
    git status --short
    exit 1
fi

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    echo "l'étiquette ${TAG} existe déjà (localement)." >&2
    exit 1
fi

echo "→ envoi de la branche main"
git push origin main

echo "→ création de l'étiquette ${TAG}"
git tag -a "${TAG}" -m "${MESSAGE}"
git push origin "${TAG}"

echo "Terminé : https://github.com/${GITHUB_REPOSITORY:-$(git remote get-url origin | sed -E 's#.*[:/]([^/]+/[^/]+?)(\.git)?$#\1#')}/releases/tag/${TAG}"
echo "La compilation Windows démarre dans l'onglet Actions ; compte une dizaine de minutes."
