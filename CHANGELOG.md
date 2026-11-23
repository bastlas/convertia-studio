# Journal des versions

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
