"""Tests du moteur d'images (Pillow) : transformations, formats, poids."""

from __future__ import annotations

import os
import random
import tempfile
import unittest

from PIL import Image

from convertia_studio.image import engine, formats


def make_image(path, size=(320, 200), mode="RGB", color=(30, 120, 220)):
    """Crée un dégradé simple (avec transparence optionnelle)."""
    width, height = size
    image = Image.new(mode, size, color)
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            base = (x * 255 // max(1, width - 1),
                    y * 255 // max(1, height - 1), 90)
            if mode == "RGBA":
                pixels[x, y] = base + (255 if x < width // 2 else 80,)
            elif mode == "L":
                pixels[x, y] = (x + y) % 256
            else:
                pixels[x, y] = base
    image.save(path)
    return path


class TestFormats(unittest.TestCase):
    def test_registre_coherent(self):
        keys = [fmt.key for fmt in formats.FORMATS]
        self.assertEqual(len(keys), len(set(keys)))
        extensions = [fmt.extension for fmt in formats.FORMATS]
        self.assertEqual(len(extensions), len(set(extensions)))
        for key in keys:
            self.assertEqual(formats.get_format(key).key, key)

    def test_guess_format(self):
        self.assertEqual(formats.guess_format("photo.JPG"), "jpeg")
        self.assertEqual(formats.guess_format("photo.webp"), "webp")
        self.assertIsNone(formats.guess_format("photo.xyz"))
        self.assertTrue(formats.is_supported("a.PNG"))
        self.assertTrue(formats.is_supported("a.heic"))
        self.assertTrue(formats.is_supported("a.raw"))
        self.assertTrue(engine.is_raw("a.dng"))
        self.assertFalse(engine.is_raw("a.jpg"))
        self.assertFalse(formats.is_supported("a.aup4"))

    def test_human_size(self):
        self.assertEqual(engine.human_size(512), "512 o")
        self.assertEqual(engine.human_size(1536), "1,5 Kio")
        self.assertEqual(engine.human_size(3 * 1024 * 1024), "3,0 Mio")

    def test_delta_label(self):
        self.assertEqual(engine.delta_label(1000, 250), "−75 %")
        self.assertEqual(engine.delta_label(1000, 1250), "+25 %")
        self.assertEqual(engine.delta_label(1000, 1000), "≈ 0 %")
        self.assertEqual(engine.delta_label(1000, 970), "−3,0 %")
        self.assertEqual(engine.delta_label(1000, None), "—")

    def test_formats_disponibles(self):
        self.assertTrue(engine.output_supported("png"))
        self.assertEqual(engine.output_supported("avif"), _feature("avif"))
        self.assertEqual(engine.output_supported("webp"), _feature("webp"))


class TestDescribe(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def path(self, name):
        return os.path.join(self._tmp.name, name)

    def test_describe_png(self):
        source = make_image(self.path("source.png"))
        info = engine.describe(source)
        self.assertEqual((info.width, info.height), (320, 200))
        self.assertEqual(info.format_name, "PNG")
        self.assertEqual(info.size, os.path.getsize(source))
        self.assertFalse(info.has_alpha)
        self.assertIn("320 × 200 px", info.details[0])

    def test_describe_alpha_et_animation(self):
        source = self.path("alpha.png")
        make_image(source, mode="RGBA")
        info = engine.describe(source)
        self.assertTrue(info.has_alpha)

        frames = [Image.new("RGB", (20, 20), (index * 40, 0, 0))
                  for index in range(3)]
        gif = self.path("anim.gif")
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50)
        info = engine.describe(gif)
        self.assertEqual(info.frames, 3)
        self.assertTrue(any("animées" in warning for warning in info.warnings))

    def test_orientation_exif(self):
        source = self.path("exif.jpg")
        image = Image.new("RGB", (60, 30), (200, 80, 20))
        exif = Image.Exif()
        exif[0x0112] = 6          # rotation de 90°
        image.save(source, exif=exif)
        info = engine.describe(source)
        self.assertEqual((info.width, info.height), (30, 60))
        loaded = engine.load(source)
        self.assertEqual(loaded.image.size, (30, 60))

    def test_fichier_absent(self):
        with self.assertRaises(engine.ImageError):
            engine.describe(self.path("absent.png"))


class TestTransformations(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.source = make_image(os.path.join(self._tmp.name, "source.png"),
                                 size=(400, 300))

    def test_recadrage_et_redimensionnement(self):
        settings = engine.ImageSettings(crop=(100, 50, 200, 100),
                                        width=100, height=50)
        data, width, height, _warnings = engine.render(
            self.source, settings, "png")
        self.assertEqual((width, height), (100, 50))

        loaded = engine.load(self.source)
        result = engine.apply_transform(loaded.image, settings)
        self.assertEqual(result.size, (100, 50))
        # le recadrage part bien de x=100, y=50
        expected = loaded.image.crop((100, 50, 300, 150)).resize(
            (100, 50), Image.Resampling.LANCZOS)
        self.assertEqual(list(result.getdata())[0], list(expected.getdata())[0])

    def test_rotation_et_miroir(self):
        settings = engine.ImageSettings(angle=90)
        loaded = engine.load(self.source)
        result = engine.apply_transform(loaded.image, settings)
        self.assertEqual(result.size, (300, 400))
        # rotation horaire : le coin haut-gauche vient du coin bas-gauche
        self.assertEqual(result.getpixel((0, 0)),
                         loaded.image.getpixel((0, 299)))

        mirrored = engine.apply_transform(
            loaded.image, engine.ImageSettings(flip_h=True))
        self.assertEqual(mirrored.getpixel((0, 0)),
                         loaded.image.getpixel((399, 0)))

    def test_dimension_imposee_garde_les_proportions(self):
        loaded = engine.load(self.source)
        result = engine.apply_transform(
            loaded.image, engine.ImageSettings(width=200))
        self.assertEqual(result.size, (200, 150))

    def test_angle_libre_agrandit(self):
        loaded = engine.load(self.source)
        result = engine.apply_transform(
            loaded.image, engine.ImageSettings(angle=30))
        self.assertGreater(result.width, 400)


class TestEncodage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def path(self, name):
        return os.path.join(self._tmp.name, name)

    def _decode(self, data):
        from io import BytesIO

        return Image.open(BytesIO(data))

    def test_formats_sans_perte(self):
        source = make_image(self.path("source.png"), mode="RGBA")
        settings = engine.ImageSettings()
        for key in ("png", "tiff", "webp", "avif"):
            if key == "avif" and not _feature("avif"):
                continue
            data, width, height, _ = engine.render(source, settings, key)
            image = self._decode(data)
            self.assertEqual((width, height), (320, 200))
            self.assertGreater(len(data), 100)
            self.assertIn(image.mode, ("RGB", "RGBA"))

    def test_jpeg_aplatit_la_transparence(self):
        source = self.path("transparent.png")
        Image.new("RGBA", (20, 20), (10, 20, 30, 0)).save(source)
        data, _w, _h, _ = engine.render(source, engine.ImageSettings(), "jpeg")
        image = self._decode(data)
        self.assertEqual(image.mode, "RGB")
        # entièrement transparent : le fond blanc est conservé
        self.assertTrue(all(channel > 240 for channel in image.getpixel((10, 10))))

    def test_qualite_change_le_poids(self):
        source = make_image(self.path("source.jpg"))
        low, _w, _h, _ = engine.render(
            source, engine.ImageSettings(quality=25), "jpeg")
        high, _w, _h, _ = engine.render(
            source, engine.ImageSettings(quality=95), "jpeg")
        self.assertLess(len(low), len(high))

    def test_estimation_egale_au_fichier(self):
        source = make_image(self.path("source.png"), size=(240, 180))
        settings = engine.ImageSettings(width=120, height=90, quality=70)
        estimated, width, height = engine.estimate(source, settings, "jpeg")
        destination = self.path("sortie.jpg")
        result = engine.convert(source, destination, "jpeg", settings)
        self.assertEqual(estimated, result["size"])
        self.assertEqual((result["width"], result["height"]), (120, 90))
        self.assertEqual((width, height), (120, 90))

    def test_convert_ecrit_et_compare(self):
        source = self.path("source.png")
        rng = random.Random(7)
        noise = Image.frombytes("RGB", (400, 300),
                                rng.randbytes(400 * 300 * 3))
        noise.save(source)
        destination = self.path("sortie.webp")
        result = engine.convert(source, destination,
                                "webp", engine.ImageSettings(quality=40))
        self.assertTrue(os.path.isfile(destination))
        self.assertEqual(result["size"], os.path.getsize(destination))
        self.assertEqual(result["source_size"], os.path.getsize(source))
        self.assertLess(result["size"], result["source_size"])
        self.assertLess(result["ratio"], 1.0)

    def test_sortie_par_defaut_ne_remplace_pas_la_source(self):
        source = self.path("photo.png")
        make_image(source)
        self.assertTrue(engine.default_output_path(source, "png")
                        .endswith("photo-converti.png"))
        self.assertTrue(engine.default_output_path(source, "jpeg")
                        .endswith("photo.jpg"))

    def test_heic_entree_sortie(self):
        if not engine.output_supported("heic"):
            self.skipTest("pillow-heif absent")
        source = make_image(self.path("source.png"), size=(320, 200))
        destination = self.path("sortie.heic")
        result = engine.convert(source, destination, "heic",
                                engine.ImageSettings(width=160, height=100,
                                                     quality=80))
        self.assertTrue(os.path.isfile(destination))
        info = engine.describe(destination)
        self.assertEqual(info.format_name, "HEIC")
        self.assertEqual((info.width, info.height), (160, 100))
        loaded = engine.load(destination)
        self.assertEqual(loaded.image.size, (160, 100))
        data, width, height, _ = engine.preview(
            destination, engine.ImageSettings(), format_key="jpeg")
        self.assertEqual((width, height), (160, 100))
        self.assertTrue(data.startswith(b"\xff\xd8"))

    def test_heic_transparence(self):
        if not engine.output_supported("heic"):
            self.skipTest("pillow-heif absent")
        image = Image.new("RGBA", (40, 30), (10, 20, 30, 128))
        data = engine.encode(image, "heic", 80)
        from io import BytesIO

        with Image.open(BytesIO(data)) as decoded:
            self.assertEqual(decoded.mode, "RGBA")

    def test_raw_invalide(self):
        if engine.rawpy is None:
            self.skipTest("rawpy absent")
        fake = self.path("faux.raw")
        with open(fake, "wb") as handle:
            handle.write(b"pas un raw")
        with self.assertRaises(engine.ImageError) as context:
            engine.describe(fake)
        self.assertIn("RAW", str(context.exception))

    def test_apercu_encode_dans_le_format(self):
        source = make_image(self.path("source.png"), size=(300, 200))
        low, width, height, _ = engine.preview(
            source, engine.ImageSettings(quality=15), format_key="jpeg")
        high, _w, _h, _ = engine.preview(
            source, engine.ImageSettings(quality=95), format_key="jpeg")
        self.assertTrue(low.startswith(b"\xff\xd8"))
        self.assertTrue(high.startswith(b"\xff\xd8"))
        self.assertLess(len(low), len(high))
        self.assertEqual((width, height), (300, 200))

    def test_meme_chemin_refuse(self):
        source = make_image(self.path("source.png"))
        with self.assertRaises(engine.ImageError):
            engine.convert(source, source, "png", engine.ImageSettings())


def _feature(name):
    from PIL import features

    return features.check(name)


if __name__ == "__main__":
    unittest.main()
