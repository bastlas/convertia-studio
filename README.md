# Convertia Studio

Application de conversion de médias, avec interface graphique moderne et ligne
de commande. Elle convertit les **projets Audacity** (`.aup3`, `.aup4`, y
compris les fichiers `*unsaved`) et **n'importe quel fichier audio** vers neuf
formats de sortie — sans lancer Audacity.

> **Sections à venir** : une partie « Image » et une partie « Vidéo » sont déjà
> présentes dans la navigation et attendent leur contenu (voir
> [Étendre l'application](#étendre-lapplication)).

![Aperçu de la page Audio](docs/apercu-audio.png)

<sub>Les sections Image et Vidéo sont déjà visibles dans la navigation, avec leur
périmètre à définir : [aperçu](docs/apercu-image.png) · [aperçu](docs/apercu-video.png).</sub>

## Démarrage rapide

| Plateforme | Lancement |
| --- | --- |
| Windows | `ConvertiaStudio.exe` (dossier `dist/ConvertiaStudio-win64/`) |
| Linux / macOS | `python3 convertia_studio.pyw` |
| Ligne de commande | `python3 -m convertia_studio --help` |

Ce qui est nécessaire :

- Python 3.10+ et `numpy` ;
- `PySide6` pour l'interface graphique ;
- `ffmpeg` pour les formats compressés (MP3, MP4, Opus…). Sous Windows,
  `ffmpeg.exe` est livré dans `bin/` à côté de l'exécutable.

## Formats

**En entrée** : projets Audacity `.aup3` / `.aup4` (et `*unsaved`), ou tout
fichier audio ou vidéo contenant de l'audio (WAV, MP3, M4A, FLAC, OGG, Opus,
AIFF, WMA, MP4, MKV, WebM…).

**En sortie** :

| Format | Extension | Type | Réglages |
| --- | --- | --- | --- |
| MP4 · AAC | `.mp4` | compressé | débit (96k → 320k) |
| M4A · AAC | `.m4a` | compressé | débit |
| M4A · ALAC | `.m4a` | sans perte | — |
| MP3 | `.mp3` | compressé | débit |
| OGG · Vorbis | `.ogg` | compressé | débit |
| OPUS | `.opus` | compressé | débit |
| FLAC | `.flac` | sans perte | compression maximale |
| WAV | `.wav` | non compressé | 16 / 24 bits, 32 bits flottant |
| AIFF | `.aiff` | non compressé | 16 / 24 bits, 32 bits flottant |

Tous les formats acceptent une fréquence de sortie imposée (44,1 / 48 / 96 kHz)
et un mixage mono.

## Ligne de commande

```bash
# projet Audacity → MP4 (même nom, à côté du projet)
python3 -m convertia_studio "mon projet.aup4"

# vers MP3 à 320 kb/s, en écrasant la sortie précédente
python3 -m convertia_studio projet.aup4 -f mp3 -b 320k -o podcast.mp3 --force

# n'importe quel fichier audio → Opus mono 64 kb/s
python3 -m convertia_studio interview.wav -f opus -b 64k --mono

# analyser une source sans convertir
python3 -m convertia_studio "mon projet.aup4" --info

# lister les formats disponibles
python3 -m convertia_studio --list-formats
```

Options : `-o/--output`, `-f/--format`, `-b/--bitrate`, `--depth`, `--sample-rate`,
`--mono`, `--info`, `--list-formats`, `-q/--quiet`, `--force`, `--version`.

Depuis l'exécutable Windows (compilé sans console), la ligne de commande reste
accessible en préfixant par `--cli` :

```bat
ConvertiaStudio.exe --cli "C:\projets\mon projet.aup4" -f flac --force
```

## Ce que le mixage restitue

Pour un projet Audacity, l'outil reproduit ce que contient le fichier :

- position et chevauchement des clips (`offset`, `trimLeft`, `trimRight`) ;
- gain de piste et panoramique (loi linéaire d'Audacity, sans atténuation au
  centre), états muet et solo ;
- enveloppes de volume (fade in/out) ;
- pistes mono dupliquées sur les deux canaux, pistes stéréo canal par canal ;
- blocs audio 16 bits, 24 bits et float 32 bits ;
- étirement de clips (`clipStretchRatio`) : traité avec `rubberband`, repli sur
  `atempo`, puis interpolation linéaire en dernier recours — un avertissement
  s'affiche dans le journal ;
- lecture du journal WAL quand le projet est (ou a été) ouvert dans Audacity :
  le projet est copié dans un dossier temporaire pour lire un état cohérent.

## Ce qui n'est pas restitué

- **Effets temps réel** d'Audacity : ils ne sont pas stockés dans le projet
  (seul l'audio d'origine l'est). Pour les inclure : `Fichier → Exporter` dans
  Audacity.
- **Pistes tempo** (`timetrack`) et étiquettes (`labeltrack`) : ignorées.
- **Dithering** : aucune mise en forme du bruit à la conversion 16/24 bits.
- Les crêtes au-delà de 0 dBFS sont écrêtées (sauf WAV/AIFF 32 bits flottant,
  qui conservent le signal tel quel).

## Structure du projet

| Chemin | Rôle |
| --- | --- |
| `convertia_studio/audio/project.py` | décodeur des projets Audacity + mixage |
| `convertia_studio/audio/formats.py` | registre des formats, encodage, écriture WAV/AIFF |
| `convertia_studio/jobs.py` | analyse d'une source et orchestration de la conversion |
| `convertia_studio/ffmpeg_tools.py` | localisation de ffmpeg / ffprobe, analyse des médias |
| `convertia_studio/cli.py` | ligne de commande |
| `convertia_studio/gui/` | interface PySide6 (`app`, `window`, `widgets`, `theme`, `pages/`) |
| `convertia_studio.pyw` | lanceur (fenêtre, ou `--cli` pour la console) |
| `tests/` | tests unitaires + générateur de projets Audacity de test |
| `build/` | recettes PyInstaller, icône, scripts de compilation |
| `scripts/publish_github.sh` | création du dépôt distant et envoi du code |
| `.github/workflows/build.yml` | compilation automatique (Windows + Linux) |
| `dist/` | application compilée (générée) |

## Étendre l'application

La navigation et la structure sont prêtes pour de nouvelles sections :

1. créer une page dans `convertia_studio/gui/pages/` (voir `coming_soon.py`) ;
2. ajouter l'entrée dans `Sidebar.ENTRIES` et le `QStackedWidget` de
   `MainWindow` ;
3. placer la logique métier dans un module dédié (`convertia_studio/video/`,
   `convertia_studio/image/`) et l'exposer via `jobs.py`, comme pour l'audio.

## Publier sur GitHub

Le dépôt local est prêt (branche `main`, premier commit effectué). Il ne reste
qu'à créer le dépôt distant, ce qui demande tes identifiants GitHub :

```bash
# avec GitHub CLI
gh auth login
./scripts/publish_github.sh

# ou avec un jeton personnel (portée « repo »)
GITHUB_TOKEN=ghp_xxx ./scripts/publish_github.sh

# ou, si le dépôt est déjà créé sur github.com
git remote add origin git@github.com:<compte>/convertia-studio.git
git push -u origin main
```

Le workflow `.github/workflows/build.yml` compile automatiquement les versions
Windows et Linux à chaque étiquette `v*` (et à la demande depuis l'onglet
« Actions »).

## Compiler

```bash
# Linux (dossier dist/ConvertiaStudio/ avec ffmpeg copié à côté)
./build/build_linux.sh

# Windows, sur une machine Windows
build\build_windows.bat

# Windows, depuis Linux via Wine (ce qui a produit dist/ConvertiaStudio-win64/)
./build/win/build_exe_wine.sh

# GitHub Actions (Windows + Linux) : .github/workflows/build.yml
```

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

Les tests fabriquent leurs propres projets `.aup4` (via `tests/make_project.py`)
et vérifient le décodage, le mixage (gain, panoramique, mute/solo, enveloppes,
rognage, ancien format stéréo 3.0-3.3, blocs 16/24 bits), les écrivains
WAV/AIFF et la conversion complète.

## Dépannage

| Message | Cause / solution |
| --- | --- |
| « ffmpeg introuvable » | installer ffmpeg, ou le placer dans `bin/` à côté de l'application |
| « journal WAL détecté » | le projet est ouvert dans Audacity ; enregistrer puis fermer pour un instantané stable |
| « document principal vide : lecture de la sauvegarde automatique » | projet jamais enregistré (`.aup4unsaved`) |
| « bloc audio absent de la base » | projet incomplet ou corrompu : le passage devient silencieux |
| « crête à X : écrêtage » | baisser le gain des pistes dans Audacity, ou exporter en WAV 32 bits flottant |

## Licences

- Le code de Convertia Studio : licence MIT (voir `LICENSE`).
- `ffmpeg` embarqué dans la distribution Windows : binaires fournis par
  [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), sous licence LGPL/GPL selon
  les codecs activés. Redistribuer l'exécutable implique de conserver la
  mention de licence d'origine.
