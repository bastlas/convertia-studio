"""Moteur de traitement d'images (Pillow) : décrire, transformer, encoder.

Le module ne dépend pas de Qt : l'interface graphique et la ligne de commande
l'utilisent tel quel.  Les transformations sont appliquées dans cet ordre :
recadrage, rotation, miroir, redimensionnement.
"""

from __future__ import annotations

import io
import os
import tempfile
import time
from dataclasses import dataclass, field

from PIL import Image, ImageOps, UnidentifiedImageError

from . import formats

#: Limite de sécurité pour les aperçus (bords les plus longs).
PREVIEW_MAX_SIDE = 1600


class ImageError(Exception):
    """Erreur de traitement d'image (message destiné à l'utilisateur)."""


@dataclass
class ImageSettings:
    """Réglages de sortie d'une image."""

    crop: tuple | None = None        # (x, y, largeur, hauteur) en pixels source
    width: int | None = None         # largeur cible (None : conserver)
    height: int | None = None        # hauteur cible (None : conserver)
    angle: float = 0.0               # rotation horaire, en degrés
    flip_h: bool = False
    flip_v: bool = False
    quality: int = 85                # 1-100 pour les formats compressés

    def key(self):
        """Empreinte utilisable pour comparer deux jeux de réglages."""
        return (self.crop, self.width, self.height, round(self.angle, 2),
                self.flip_h, self.flip_v, self.quality)


@dataclass
class ImageInfo:
    """Ce que l'on sait d'une image avant traitement."""

    path: str
    width: int
    height: int
    mode: str
    format_name: str
    size: int
    has_alpha: bool = False
    frames: int = 1
    orientation: int = 1
    details: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def title(self):
        return os.path.basename(self.path)

    @property
    def kind_label(self):
        return "Image"

    @property
    def dimensions(self):
        return "%d × %d px" % (self.width, self.height)

    @property
    def size_label(self):
        return human_size(self.size)


def is_image(path):
    """Vrai si l'extension est une image gérée."""
    return formats.is_supported(os.fspath(path) if path else "")


def human_size(size):
    """Taille lisible façon française (« 2,4 Mio »)."""
    size = float(size)
    if size < 1024:
        return "%d o" % round(size)
    for unit in ("Kio", "Mio", "Gio"):
        size /= 1024.0
        if size < 1024 or unit == "Gio":
            text = "%.1f" % size if size < 100 else "%.0f" % size
            return "%s %s" % (text.replace(".", ","), unit)
    return "%.1f Gio" % size


_MODE_LABELS = {
    "1": "noir et blanc",
    "L": "niveaux de gris",
    "LA": "gris + transparence",
    "P": "palette",
    "PA": "palette + transparence",
    "RGB": "RVB",
    "RGBA": "RVB + transparence",
    "CMYK": "CMJN",
    "YCbCr": "YCbCr",
    "I": "entier 32 bits",
    "I;16": "gris 16 bits",
    "F": "flottant 32 bits",
}


def _mode_label(mode):
    return _MODE_LABELS.get(mode, mode)


def _has_alpha(image):
    return image.mode in ("RGBA", "LA", "PA") or (
        image.mode in ("P", "L", "RGB") and "transparency" in image.info)


def describe(path):
    """Analyse rapide d'une image (sans décoder les pixels)."""
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise ImageError("fichier introuvable : %s" % path)
    try:
        with Image.open(path) as image:
            format_name = formats.label_for_pillow(image.format)
            orientation = 1
            try:
                orientation = int(image.getexif().get(0x0112, 1) or 1)
            except Exception:  # noqa: BLE001 - EXIF illisible : tant pis
                orientation = 1
            width, height = image.size
            if orientation in (5, 6, 7, 8):
                width, height = height, width
            mode = image.mode
            alpha = _has_alpha(image)
            frames = int(getattr(image, "n_frames", 1) or 1)
            dpi = image.info.get("dpi")
            icc = bool(image.info.get("icc_profile"))
    except UnidentifiedImageError as error:
        raise ImageError("format d'image non reconnu : %s"
                         % os.path.basename(path)) from error
    except OSError as error:
        raise ImageError("impossible de lire l'image : %s" % error) from error

    size = os.path.getsize(path)
    details = [
        "%s · %d × %d px · %s" % (format_name, width, height, human_size(size)),
        "Mode %s%s" % (_mode_label(mode),
                       " · profil ICC inclus" if icc else ""),
    ]
    if dpi:
        try:
            details.append("Résolution %d × %d ppp" % (round(dpi[0]),
                                                      round(dpi[1])))
        except (TypeError, ValueError, IndexError):
            pass
    if orientation != 1:
        details.append("Orientation EXIF %d appliquée à l'ouverture" % orientation)

    warnings = []
    if frames > 1:
        warnings.append("%d images animées : seule la première sera conservée"
                        % frames)
    if mode in ("I", "I;16", "F"):
        warnings.append("image %s : ramenée à 8 bits par canal"
                        % _mode_label(mode))
    extension = os.path.splitext(path)[1].lower()
    if extension and extension not in formats.INPUT_SUFFIXES:
        warnings.append("extension %s inhabituelle pour une image" % extension)
    if alpha and not formats.is_supported(path):
        warnings.append("transparence détectée")

    return ImageInfo(
        path=path, width=width, height=height, mode=mode,
        format_name=format_name, size=size, has_alpha=alpha,
        frames=frames, orientation=orientation, details=details,
        warnings=warnings)


@dataclass
class LoadedImage:
    """Image décodée prête à être transformée."""

    image: Image.Image
    icc_profile: bytes | None = None
    frames: int = 1
    warnings: list = field(default_factory=list)


def load(path):
    """Décode l'image, applique l'orientation EXIF et normalise le mode."""
    try:
        source = Image.open(path)
    except UnidentifiedImageError as error:
        raise ImageError("format d'image non reconnu : %s"
                         % os.path.basename(path)) from error
    except OSError as error:
        raise ImageError("impossible d'ouvrir l'image : %s" % error) from error

    warnings = []
    try:
        source.load()
        frames = int(getattr(source, "n_frames", 1) or 1)
        icc = source.info.get("icc_profile")
        image = ImageOps.exif_transpose(source)
        if image is source:
            image = source.copy()
    except OSError as error:
        raise ImageError("impossible de décoder l'image : %s" % error) from error
    finally:
        source.close()

    if frames > 1:
        warnings.append("%d images animées : seule la première est conservée"
                        % frames)

    if image.mode in ("P", "PA"):
        image = image.convert("RGBA" if _has_alpha(image) else "RGB")
    elif image.mode in ("I", "I;16", "I;16B", "F"):
        image = image.convert("L")
        warnings.append("image de plus de 8 bits ramenée à 8 bits")
    elif image.mode in ("1", "LA"):
        image = image.convert("RGBA" if image.mode == "LA" else "RGB")

    return LoadedImage(image=image, icc_profile=icc, frames=frames,
                       warnings=warnings)


def _background_tuple(color):
    color = (color or "#FFFFFF").lstrip("#")
    if len(color) == 3:
        color = "".join(part * 2 for part in color)
    try:
        return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def _clamp_crop(image, crop):
    x, y, width, height = (int(round(value)) for value in crop)
    x = max(0, min(x, image.width - 1))
    y = max(0, min(y, image.height - 1))
    width = max(1, min(width, image.width - x))
    height = max(1, min(height, image.height - y))
    return x, y, width, height


def apply_transform(image, settings):
    """Applique recadrage, rotation, miroir puis redimensionnement."""
    result = image

    if settings.crop:
        x, y, width, height = _clamp_crop(result, settings.crop)
        if (x, y, width, height) != (0, 0, result.width, result.height):
            result = result.crop((x, y, x + width, y + height))

    angle = float(settings.angle or 0.0) % 360.0
    if angle:
        steps = round(angle / 90.0)
        if abs(angle - steps * 90.0) < 0.01:
            steps %= 4
            transforms = {
                1: Image.Transpose.ROTATE_270,   # 90° horaire
                2: Image.Transpose.ROTATE_180,
                3: Image.Transpose.ROTATE_90,    # 270° horaire
            }
            if steps:
                result = result.transpose(transforms[steps])
        else:
            if _has_alpha(result):
                fill = (0, 0, 0, 0)
            else:
                fill = _background_tuple(getattr(settings, "background",
                                                 "#FFFFFF"))
            result = result.rotate(-angle, resample=Image.Resampling.BICUBIC,
                                   expand=True, fillcolor=fill)

    if settings.flip_h:
        result = ImageOps.mirror(result)
    if settings.flip_v:
        result = ImageOps.flip(result)

    width = int(settings.width) if settings.width else None
    height = int(settings.height) if settings.height else None
    if width or height:
        if width and height:
            target = (max(1, width), max(1, height))
        elif width:
            target = (max(1, width),
                      max(1, round(result.height * width / result.width)))
        else:
            target = (max(1, round(result.width * height / result.height)),
                      max(1, height))
        if target != result.size:
            result = result.resize(target, Image.Resampling.LANCZOS)

    return result


def _prepare_for_format(image, image_format, background="#FFFFFF"):
    """Adapte le mode au format cible (transparence, CMJN, etc.)."""
    alpha = _has_alpha(image)
    if alpha and image_format.supports_alpha:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        return image
    if alpha:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        base = Image.new("RGBA", image.size,
                         _background_tuple(background) + (255,))
        return Image.alpha_composite(base, image).convert("RGB")
    if image.mode in ("L", "RGB"):
        return image
    return image.convert("RGB")


def encode(image, format_key, quality=85, icc_profile=None,
           background="#FFFFFF"):
    """Encode l'image en mémoire et retourne les octets du fichier."""
    image_format = formats.get_format(format_key)
    prepared = _prepare_for_format(image, image_format, background)
    buffer = io.BytesIO()
    params = {}
    if image_format.key == "jpeg":
        params.update(quality=max(1, min(100, int(quality))), optimize=True,
                      progressive=True)
    elif image_format.key == "webp":
        params.update(quality=max(1, min(100, int(quality))), method=4)
    elif image_format.key == "avif":
        params.update(quality=max(1, min(100, int(quality))))
    elif image_format.key == "png":
        params.update(optimize=True)
    elif image_format.key == "tiff":
        params.update(compression="tiff_deflate")
    if icc_profile and image_format.key in ("jpeg", "png", "webp", "avif"):
        params["icc_profile"] = icc_profile
    try:
        prepared.save(buffer, format=image_format.pillow_format, **params)
    except (OSError, ValueError) as error:
        raise ImageError("encodage %s impossible : %s"
                         % (image_format.label, error)) from error
    return buffer.getvalue()


def render(path, settings, format_key, quality=None, icc_profile=None):
    """Décode, transforme et encode ; renvoie ``(octets, largeur, hauteur)``."""
    loaded = load(path)
    image = apply_transform(loaded.image, settings)
    data = encode(image, format_key,
                  quality if quality is not None else settings.quality,
                  icc_profile=loaded.icc_profile or icc_profile)
    return data, image.width, image.height, loaded.warnings


def preview(path, settings, max_side=PREVIEW_MAX_SIDE, format_key=None):
    """Petit PNG (sans perte) pour l'aperçu graphique.

    ``format_key`` permet de simuler l'aplatissement de la transparence d'un
    format qui ne la gère pas (JPEG, BMP).  Retourne ``(octets, largeur,
    hauteur, avertissements)``.
    """
    loaded = load(path)
    image = apply_transform(loaded.image, settings)
    if max(image.size) > max_side:
        image = image.copy()
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    if format_key:
        image = _prepare_for_format(image, formats.get_format(format_key))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), image.width, image.height, loaded.warnings


def estimate(path, settings, format_key):
    """Poids estimé du fichier final, sans écrire sur le disque."""
    data, width, height, _warnings = render(path, settings, format_key)
    return len(data), width, height


def convert(source, dest, format_key, settings, progress=None):
    """Convertit ``source`` vers ``dest`` et retourne un compte rendu."""
    source = os.fspath(source)
    dest = os.fspath(dest)
    if not os.path.isfile(source):
        raise ImageError("fichier introuvable : %s" % source)
    if os.path.abspath(source) == os.path.abspath(dest):
        raise ImageError("le fichier de sortie ne peut pas être la source")
    directory = os.path.dirname(os.path.abspath(dest))
    if directory and not os.path.isdir(directory):
        raise ImageError("dossier de sortie introuvable : %s" % directory)

    image_format = formats.get_format(format_key)
    started = time.time()
    source_size = os.path.getsize(source)
    _report(progress, 0.05, "lecture de l'image…")
    loaded = load(source)
    _report(progress, 0.3, "application des transformations…")
    image = apply_transform(loaded.image, settings)
    _report(progress, 0.6, "encodage %s…" % image_format.label)
    data = encode(image, format_key, settings.quality,
                  icc_profile=loaded.icc_profile)
    _report(progress, 0.92, "écriture du fichier…")

    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(
            dir=directory or ".", prefix=".convertia-",
            suffix=image_format.extension)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, 0o666 & ~_umask())
        os.replace(temporary, dest)
        temporary = None
    except OSError as error:
        raise ImageError("écriture impossible : %s" % error) from error
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

    _report(progress, 1.0, "terminé")
    size = len(data)
    saved = source_size - size
    return {
        "path": dest,
        "format": image_format,
        "size": size,
        "source_size": source_size,
        "source_width": loaded.image.width,
        "source_height": loaded.image.height,
        "width": image.width,
        "height": image.height,
        "delta": saved,
        "ratio": (size / source_size) if source_size else None,
        "elapsed": time.time() - started,
        "warnings": loaded.warnings,
    }


def delta_label(before, after):
    """Écart de poids lisible : « −75 % », « +3,2 % » ou « ≈ 0 % »."""
    if not before or after is None:
        return "—"
    ratio = after / before
    change = abs(1.0 - ratio) * 100.0
    if change < 0.5:
        return "≈ 0 %"
    sign = "−" if ratio <= 1 else "+"
    if change < 10:
        return "%s%.1f %%" % (sign, change)
    return "%s%d %%" % (sign, round(change))


def default_output_path(source, format_key, directory=None):
    """Nom de sortie proposé, sans écraser la source."""
    image_format = formats.get_format(format_key)
    base, extension = os.path.splitext(os.path.basename(source))
    directory = directory or os.path.dirname(os.path.abspath(source))
    candidate = os.path.join(directory, base + image_format.extension)
    if os.path.abspath(candidate) == os.path.abspath(source):
        candidate = os.path.join(directory, base + "-converti"
                                 + image_format.extension)
    return candidate


def _umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _report(progress, fraction, message):
    if progress:
        progress(max(0.0, min(1.0, fraction)), message)
