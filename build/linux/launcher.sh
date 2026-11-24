#!/usr/bin/env bash
# Lanceur Linux de Convertia Studio.
#
# Vérifie les bibliothèques Qt nécessaires, propose de les installer avec le
# gestionnaire de paquets de la distribution, puis démarre l'application.
#
#   ./ConvertiaStudio.sh              lance la fenêtre
#   ./ConvertiaStudio.sh --cli ...    ligne de commande
#   ./ConvertiaStudio.sh --check      vérifie seulement les dépendances
#
# Variables : CONVERTIA_NO_INSTALL=1 pour ne jamais installer automatiquement.
set -u

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP="$HERE/ConvertiaStudio"
CHECK_ONLY=0
CLI_MODE=0

for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        --cli|--cli=*) CLI_MODE=1 ;;
    esac
done

fail() { printf '%s\n' "$*" >&2; }
info() { printf '%s\n' "$*"; }

# ---------------------------------------------------------------- exécutable
if [ ! -f "$APP" ]; then
    fail "Convertia Studio : exécutable introuvable dans $HERE."
    fail "Décompressez l'archive complète puis relancez ce script."
    exit 1
fi
[ -x "$APP" ] || chmod +x "$APP" 2>/dev/null || true
for extra in "$HERE/bin/ffmpeg" "$HERE/bin/ffprobe"; do
    [ -e "$extra" ] && { [ -x "$extra" ] || chmod +x "$extra" 2>/dev/null || true; }
done

# Vérification de base : glibc, Python embarqué, démarrage de l'application.
core_output="$("$APP" --cli --version 2>&1)"
if [ $? -ne 0 ]; then
    fail "$core_output"
    case "$core_output" in
        *GLIBC_*not\ found*|*"version \`GLIBC"*)
            fail ""
            fail "Cette distribution est trop ancienne pour ce binaire (glibc)."
            fail "Utilisez Ubuntu 22.04 ou plus récent, Debian 12, Fedora 36…"
            fail "ou demandez une compilation adaptée à votre système."
            ;;
    esac
    exit 1
fi

# ---------------------------------------------------------------- distribution
detect_distro() {
    local id="" like=""
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        id="${ID:-}"
        like="${ID_LIKE:-}"
    fi
    case "$id" in
        debian|ubuntu|linuxmint|pop|elementary|zorin|kali|raspbian|neon)
            echo debian; return ;;
        fedora|rhel|centos|rocky|almalinux|ol|nobara)
            echo fedora; return ;;
        arch|manjaro|endeavouros|cachyos|garuda|artix)
            echo arch; return ;;
        opensuse*|suse*|sles)
            echo suse; return ;;
    esac
    case " $like " in
        *debian*|*ubuntu*) echo debian ;;
        *fedora*|*rhel*) echo fedora ;;
        *arch*) echo arch ;;
        *suse*) echo suse ;;
        *) echo unknown ;;
    esac
}

packages_for() {
    case "$1" in
        debian) echo "libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 libegl1 libgl1 libfontconfig1 libdbus-1-3" ;;
        fedora) echo "xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil mesa-libGL mesa-libEGL libxkbcommon-x11 fontconfig dbus-libs" ;;
        arch) echo "xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil mesa libxkbcommon fontconfig dbus" ;;
        suse) echo "libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 libEGL1 libGL1 fontconfig dbus-1" ;;
        *) echo "" ;;
    esac
}

install_command() {
    case "$1" in
        debian) echo "apt-get update && apt-get install -y $2" ;;
        fedora) echo "dnf install -y $2" ;;
        arch) echo "pacman -S --needed --noconfirm $2" ;;
        suse) echo "zypper --non-interactive install $2" ;;
        *) echo "" ;;
    esac
}

# ---------------------------------------------------------------- dépendances
find_missing() {
    local targets=("$APP")
    local library cache loader lib
    while IFS= read -r -d '' library; do
        targets+=("$library")
    done < <(find "$HERE/_internal" -type f \
                  \( -name 'libqxcb.so' -o -name 'libQt6XcbQpa.so*' \
                     -o -name 'libQt6Core.so*' -o -name 'libQt6Gui.so*' \
                     -o -name 'libQt6Widgets.so*' \) -print0 2>/dev/null)

    {
        for library in "${targets[@]}"; do
            ldd "$library" 2>/dev/null
        done | awk '/=> not found/ {print $1}'

        # Bibliothèques chargées par dlopen : présentes dans le cache système ?
        loader="$(command -v ldconfig 2>/dev/null || echo /sbin/ldconfig)"
        cache=""
        [ -x "$loader" ] && cache="$("$loader" -p 2>/dev/null)"
        if [ -n "$cache" ]; then
            for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 \
                       libxcb-keysyms.so.1 libxcb-render-util.so.0 \
                       libxkbcommon.so.0 libxkbcommon-x11.so.0 \
                       libGL.so.1 libEGL.so.1 libfontconfig.so.1 \
                       libdbus-1.so.3; do
                printf '%s\n' "$cache" | grep -q -- "$lib" || printf '%s\n' "$lib"
            done
        fi
    } | sort -u
}

# La ligne de commande n'a pas besoin de Qt (GUI) : on ne vérifie que la fenêtre.
missing=""
if [ "$CLI_MODE" -eq 0 ] || [ "$CHECK_ONLY" -eq 1 ]; then
    missing="$(find_missing)"
fi

if [ -n "$missing" ]; then
    fail "Convertia Studio ne peut pas démarrer : bibliothèques manquantes."
    printf '%s\n' "$missing" | sed 's/^/  - /' >&2

    distro="$(detect_distro)"
    packages="$(packages_for "$distro")"
    if [ -z "$packages" ]; then
        fail ""
        fail "Distribution non reconnue : installez les paquets Qt/X11 de votre"
        fail "distribution (xcb-cursor, xcb-icccm, xcb-image, xcb-keysyms,"
        fail "xkbcommon-x11, OpenGL/EGL, fontconfig, dbus)."
    else
        command_line="$(install_command "$distro" "$packages")"
        fail ""
        fail "Paquets à installer : $packages"
        fail "Commande manuelle : sudo sh -c '$command_line'"
    fi

    if [ "$CHECK_ONLY" -eq 1 ] || [ "${CONVERTIA_NO_INSTALL:-0}" = "1" ]; then
        exit 1
    fi

    # Demande de confirmation (terminal ou boîte de dialogue graphique).
    if [ -t 0 ]; then
        printf 'Installer automatiquement ces paquets ? [O/n] '
        read -r answer || answer="n"
        case "$answer" in n|N|non|no|Non|NON) exit 1 ;; esac
    elif [ -n "$packages" ]; then
        if command -v zenity >/dev/null 2>&1; then
            zenity --question --title="Convertia Studio" \
                   --text="Installer les bibliothèques Qt manquantes ?" \
                || exit 1
        elif command -v kdialog >/dev/null 2>&1; then
            kdialog --title "Convertia Studio" \
                   --yesno "Installer les bibliothèques Qt manquantes ?" \
                || exit 1
        elif [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] \
                || ! command -v pkexec >/dev/null 2>&1; then
            fail ""
            fail "Aucun terminal pour confirmer : relancez ./ConvertiaStudio.sh"
            fail "depuis un terminal."
            exit 1
        fi
        # sinon pkexec affiche sa propre demande d'authentification
    fi

    [ -n "$packages" ] || exit 1

    run_root() {
        if [ "$(id -u)" -eq 0 ]; then
            "$@"
        elif [ -t 0 ] && command -v sudo >/dev/null 2>&1; then
            # terminal : sudo peut demander le mot de passe
            sudo "$@"
        elif command -v pkexec >/dev/null 2>&1; then
            # session graphique : demande d'authentification polkit
            pkexec "$@"
        elif command -v sudo >/dev/null 2>&1; then
            sudo "$@"
        else
            return 127
        fi
    }

    if ! run_root sh -c "$command_line"; then
        fail ""
        fail "L'installation automatique a échoué (droits ou réseau)."
        fail "Exécutez manuellement : sudo sh -c '$command_line'"
        exit 1
    fi

    missing="$(find_missing)"
    if [ -n "$missing" ]; then
        fail "Bibliothèques toujours manquantes après installation :"
        printf '%s\n' "$missing" | sed 's/^/  - /' >&2
        fail "Redémarrez la session si la mise à jour vient d'être installée."
        exit 1
    fi
    info "Dépendances installées."
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    info "Dépendances OK — Convertia Studio peut démarrer."
    exit 0
fi

cd "$HERE" || exit 1
exec "$APP" "$@"
