#!/usr/bin/env bash
# Publie le projet sur GitHub.
#
# Deux méthodes, dans l'ordre :
#   1. GitHub CLI (recommandé) : `gh auth login` puis ce script ;
#   2. GitHub API + jeton personnel : `GITHUB_TOKEN=ghp_xxx ./scripts/publish_github.sh`
#
# Variables facultatives :
#   REPO_NAME   nom du dépôt (défaut : convertia-studio)
#   REPO_OWNER  compte ou organisation (défaut : compte connecté)
#   VISIBILITY  public (défaut) ou private
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

REPO_NAME="${REPO_NAME:-convertia-studio}"
VISIBILITY="${VISIBILITY:-public}"
DESCRIPTION="Convertia Studio — conversion audio : projets Audacity et fichiers audio vers 9 formats (MP4, MP3, FLAC, WAV…)"

if [ ! -d .git ]; then
    echo "Dépôt git local absent : initialisation…"
    git init -b main
    git add -A
    git commit -m "Convertia Studio 2.0.0" || true
fi

echo "→ vérifications avant envoi"
git status --short || true

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    echo "→ création du dépôt avec GitHub CLI"
    gh repo create "${REPO_NAME}" --"${VISIBILITY}" --source=. --remote=origin \
        --description="${DESCRIPTION}" --push
    gh repo view --web >/dev/null 2>&1 || true
    echo "Terminé : dépôt ${REPO_NAME} publié."
    exit 0
fi

if [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "→ création du dépôt via l'API GitHub"
    OWNER="${REPO_OWNER:-$(curl -sSf -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        https://api.github.com/user | python3 -c 'import json,sys;print(json.load(sys.stdin)["login"])')}"
    curl -sSf -X POST https://api.github.com/user/repos \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -d "{\"name\":\"${REPO_NAME}\",\"description\":\"${DESCRIPTION}\",\"private\":$([ "${VISIBILITY}" = private ] && echo true || echo false)}" \
        >/dev/null || echo "(le dépôt existe peut-être déjà)"
    git remote remove origin 2>/dev/null || true
    git remote add origin "https://github.com/${OWNER}/${REPO_NAME}.git"
    git push -u origin main
    echo "Terminé : https://github.com/${OWNER}/${REPO_NAME}"
    exit 0
fi

cat <<MSG
Aucun identifiant GitHub disponible. Deux possibilités :

  A. GitHub CLI (le plus simple)
       gh auth login
       ./scripts/publish_github.sh

  B. Jeton personnel (Settings → Developer settings → Tokens, portée « repo »)
       GITHUB_TOKEN=ghp_xxx ./scripts/publish_github.sh

  C. À la main, si le dépôt est déjà créé sur github.com
       git remote add origin git@github.com:<compte>/${REPO_NAME}.git
       git push -u origin main
MSG
