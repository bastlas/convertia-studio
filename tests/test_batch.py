"""Tests du traitement par lot (analyse d'un dossier et plan de sortie)."""

from __future__ import annotations

import os
import tempfile
import unittest

from PIL import Image

from convertia_studio import batch
from convertia_studio.image import engine as image_engine


def write_image(path, size=(120, 80), color=(40, 120, 220)):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


class TestBatchScan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        write_image(os.path.join(self.root, "photo.jpg"))
        write_image(os.path.join(self.root, "photo.png"))
        write_image(os.path.join(self.root, "sous", "image.png"))
        with open(os.path.join(self.root, "voix.wav"), "wb") as handle:
            handle.write(b"RIFF")
        with open(os.path.join(self.root, "clip.mp4"), "wb") as handle:
            handle.write(b"\x00")
        with open(os.path.join(self.root, "notes.txt"), "w") as handle:
            handle.write("ignoré")
        os.makedirs(os.path.join(self.root, "converti"), exist_ok=True)
        write_image(os.path.join(self.root, "converti", "ancien.jpg"))

    def test_classify(self):
        self.assertEqual(batch.classify("a.jpg"), "image")
        self.assertEqual(batch.classify("a.PNG"), "image")
        self.assertEqual(batch.classify("a.mkv"), "video")
        self.assertEqual(batch.classify("a.wav"), "audio")
        self.assertEqual(batch.classify("projet.aup4"), "audio")
        self.assertIsNone(batch.classify("a.txt"))

    def test_scan_non_recursif(self):
        result = batch.scan(self.root, recursive=False)
        self.assertEqual(result.count("image"), 2)
        self.assertEqual(result.count("video"), 1)
        self.assertEqual(result.count("audio"), 1)
        self.assertEqual(result.ignored, 1)
        self.assertGreater(result.size, 0)

    def test_scan_recursif_et_exclusion(self):
        output = os.path.join(self.root, "converti")
        result = batch.scan(self.root, recursive=True, exclude=[output])
        self.assertEqual(result.count("image"), 3)   # sous/image.png inclus
        self.assertEqual(result.count("video"), 1)
        self.assertEqual(result.count("audio"), 1)

    def test_destination_directory(self):
        self.assertTrue(batch.destination_directory(self.root)
                        .endswith(os.path.join("", "converti")))


class TestBatchPlan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.output = os.path.join(self.root, "sortie")
        write_image(os.path.join(self.root, "photo.jpg"))
        write_image(os.path.join(self.root, "photo.png"))
        write_image(os.path.join(self.root, "sous", "image.png"))
        self.scan = batch.scan(self.root, recursive=True)
        self.scan_flat = batch.scan(self.root, recursive=False)

    def test_chemins_preserves(self):
        entries = batch.build_entries(
            self.scan, ["image"], {"image": "webp"}, self.root, self.output,
            recursive=True)
        destinations = {os.path.relpath(entry.destination, self.output)
                        for entry in entries}
        self.assertIn("photo.webp", destinations)
        self.assertIn(os.path.join("sous", "image.webp"), destinations)
        self.assertTrue(all(entry.destination.startswith(self.output)
                            for entry in entries))

    def test_collisions_evitees(self):
        entries = batch.build_entries(
            self.scan_flat, ["image"], {"image": "webp"}, self.root,
            self.output, recursive=False)
        names = sorted(os.path.basename(entry.destination) for entry in entries)
        self.assertEqual(names, ["photo-2.webp", "photo.webp"])

    def test_fichier_existant_non_ecrase(self):
        os.makedirs(self.output, exist_ok=True)
        existing = os.path.join(self.output, "photo.webp")
        with open(existing, "wb") as handle:
            handle.write(b"deja la")
        entries = batch.build_entries(
            self.scan_flat, ["image"], {"image": "webp"}, self.root,
            self.output, recursive=False)
        destinations = [entry.destination for entry in entries]
        self.assertNotIn(existing, destinations)
        self.assertTrue(all(destination != existing
                            for destination in destinations))

    def test_conversion_image_reelle(self):
        entries = batch.build_entries(
            self.scan_flat, ["image"], {"image": "jpeg"}, self.root,
            self.output, recursive=False)
        entry = entries[0]
        result = batch.convert_entry(
            entry, image_engine.ImageSettings(quality=70))
        self.assertTrue(os.path.isfile(entry.destination))
        self.assertEqual(result["size"], os.path.getsize(entry.destination))
        self.assertTrue(entry.destination.endswith(".jpg"))

    def test_format_extension(self):
        self.assertEqual(batch.format_extension("image", "webp"), ".webp")
        self.assertEqual(batch.format_extension("video", "webm"), ".webm")
        self.assertEqual(batch.format_extension("audio", "mp3"), ".mp3")


if __name__ == "__main__":
    unittest.main()
