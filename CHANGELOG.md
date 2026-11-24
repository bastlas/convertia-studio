# Journal des versions

## 2.2.1 — 24 novembre 2026

- **Lanceur Linux `ConvertiaStudio.sh`** : vérifie les bibliothèques Qt
  (xcb-cursor, xcb-icccm, xkbcommon-x11, OpenGL/EGL, fontconfig, dbus…),
  détecte la distribution et propose d'installer les paquets manquants avec
  apt, dnf, pacman ou zypper (sudo, ou pkexec en session graphique), puis
  démarre l'application.
- `./ConvertiaStudio.sh --check` diagnostique sans rien installer ;
  `CONVERTIA_NO_INSTALL=1` désactive l'installation automatique.
- Message explicite si la distribution est trop ancienne (glibc).
- L'archive Linux est désormais compilée sur Ubuntu 22.04 (glibc plus
  ancienne) pour démarrer sur davantage de distributions.
- Le lanceur est inclus dans l'archive et documenté dans le README.

## 2.2.0 — 23 novembre 2026

Traitement d'un **dossier entier** :

- bouton « Traiter un dossier… » dans la barre latérale, ou glisser-déposer
  d'un dossier sur la fenêtre ou une page ;
- analyse du dossier (option « inclure les sous-dossiers »), classement des
  fichiers en images / vidéos / audio, extensions non gérées ignorées ;
- une ligne par famille : nombre de fichiers, poids, format de sortie
  modifiable, rappel des réglages repris de la page correspondante
  (qualité image, CRF et audio vidéo, débit et profondeur audio) ;
- dossier de sortie choisi (par défaut `<dossier>/converti`), arborescence
  conservée, aucun fichier source écrasé (suffixes `-2`, `-3` au besoin) ;
- progression globale et par fichier, journal détaillé, annulation, bilan
  des conversions réussies et des échecs ;
- reprend le correctif Linux 2.1.3 (ffmpeg statique et repli sur le système).

## 2.1.3 — 23 novembre 2026

- Correctif Linux : les binaires ffmpeg / ffprobe de l'archive sont désormais
  **statiques** (plus de dépendance aux bibliothèques de la distribution).
- Un binaire embarqué qui ne démarre pas (bibliothèque manquante, binaire
  cassé) est détecté et ignoré au profit du ffmpeg du `PATH` ; le test est
  mis en cache.
- Message d'erreur explicite quand ffmpeg / ffprobe est introuvable ou
  inutilisable.
- La CI Linux teste maintenant une conversion vidéo complète avec
  l'exécutable et les binaires embarqués.

## 2.1.2 — 23 novembre 2026

Section **Vidéo** complète, et nouveau sélecteur de taille pour l'image :

- analyse des vidéos (durée, dimensions, cadence, codecs, débits, poids) ;
- sorties MP4 · H.264, MP4 · H.265, WebM · VP9 et MKV · H.264, avec détection
  des encodeurs disponibles dans ffmpeg ;
- découpe début / fin, repositionnable depuis la vignette de contrôle ;
- tailles HD, Full HD, 2K, Ultra HD 4K, 8K, portrait, carré ou personnalisées,
  avec ajustement (bandes noires) ou remplissage (rognage) ;
- qualité CRF, vitesse d'encodage, cadence, rotation, vitesse de lecture ;
- audio AAC / Opus, copie sans réencodage ou suppression ;
- vignette à la position choisie, extraction de l'image courante en PNG,
  estimation du poids et comparaison avant / après ;
- glisser-déposer routé selon le type réel du fichier (audio, image, vidéo) ;
- ligne de commande : `--video`, `--crf`, `--start`, `--end`, `--fps`,
  `--speed`, `--fill`, `--no-audio`, `--audio-copy`, `--list-video-formats` ;
- image : la taille se choisit désormais dans un panneau (HD → 8K, carré,
  portrait) ou en dimensions personnalisées ; l'aperçu reflète la compression ;
- tests vidéo et conversions de contrôle dans la CI Windows.

## 2.1.1 — 23 novembre 2026

- L'aperçu reflète la compression : il est encodé dans le format cible (JPEG,
  WebP ou PNG) avec la qualité choisie, ce qui montre les artefacts quand le
  curseur descend.
- L'en-tête de l'aperçu rappelle le format et la qualité simulés.

## 2.1.0 — 23 novembre 2026

Section **Image** complète :

- recadrage interactif à la souris, avec proportions prédéfinies (1:1, 4:3,
  3:2, 16:9, 9:16, originale) ;
- redimensionnement en pixels avec conservation des proportions ;
- rotation 90 / 180 / 270° et miroir horizontal ou vertical ;
- compression JPEG, WebP et AVIF avec curseur de qualité ;
- sorties PNG, TIFF et BMP sans perte, transparence conservée ou aplatie sur
  fond blanc selon le format ;
- aperçu du résultat, bascule avant / après, dimensions et poids estimé en
  direct, comparaison du poids avant / après avec écart en pourcentage ;
- ligne de commande étendue : `-Q/--quality`, `--resize`, `--crop`,
  `--rotate`, `--flip-h`, `--flip-v`, `--list-image-formats` ;
- glisser-déposer routé automatiquement vers la page Audio ou Image ;
- Pillow embarqué dans les distributions Windows et Linux.

## 2.0.0 — 21 novembre 2026

Réécriture complète sous le nom **Convertia Studio**.

- interface graphique PySide6 : thème sombre néon, navigation Audio / Image /
  Vidéo, cartes de format animées, glisser-déposer dans toute la fenêtre,
  progression détaillée et journal coloré ;
- 9 formats de sortie : MP4·AAC, M4A·AAC, M4A·ALAC, MP3, OGG·Vorbis, Opus, FLAC,
  WAV et AIFF, avec débit / profondeur PCM / fréquence / mono ;
- entrées élargies : projets Audacity `.aup4` **et `.aup3`** (y compris
  `*unsaved`), plus tout fichier audio ou vidéo (ffmpeg) ;
- support des anciens projets Audacity 3.0–3.3 (deux séquences dans un clip) ;
- étirement de clips rendu avec `rubberband` (hauteur préservée), replis
  `atempo` puis interpolation ;
- exécutable Windows autonome avec ffmpeg embarqué (Wine + PyInstaller) ;
- ligne de commande complète, tests unitaires et générateur de projets de test.

## 1.0.0 — 15 novembre 2026

Première version, en ligne de commande et Tkinter : conversion d'un unique
`.aup4` vers MP4, WAV ou FLAC.
