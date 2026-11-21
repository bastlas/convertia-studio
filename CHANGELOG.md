# Journal des versions

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
