"""Tests du moteur vidéo (analyse, vignette, estimation, encodage)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from convertia_studio import ffmpeg_tools
from convertia_studio.video import engine, formats


def have_ffmpeg():
    return ffmpeg_tools.ffmpeg() is not None and ffmpeg_tools.ffprobe() is not None


@unittest.skipUnless(have_ffmpeg(), "ffmpeg et ffprobe requis")
class VideoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.sample = os.path.join(cls._tmp.name, "source.mp4")
        command = [
            ffmpeg_tools.require_ffmpeg(), "-hide_banner", "-loglevel", "error",
            "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", cls.sample,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=120)
        except (OSError, subprocess.SubprocessError):
            completed = None
        if completed is None or completed.returncode != 0 \
                or not os.path.isfile(cls.sample):
            raise unittest.SkipTest("impossible de fabriquer une vidéo de test")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def path(self, name):
        return os.path.join(self._tmp.name, name)

    def test_analyse(self):
        info = engine.describe(self.sample)
        self.assertEqual((info.width, info.height), (320, 240))
        self.assertAlmostEqual(info.duration, 2.0, delta=0.3)
        self.assertAlmostEqual(info.fps, 25.0, delta=0.1)
        self.assertTrue(info.has_audio)
        self.assertIn("H264", info.details[0] + info.details[1])
        self.assertEqual(info.fps_label, "25 i/s")
        self.assertTrue(info.size > 1000)

    def test_formats(self):
        self.assertEqual(len(formats.FORMAT_KEYS), 5)
        self.assertIn("mov", formats.FORMAT_KEYS)
        self.assertEqual(formats.guess_format("film.MOV"), "mov")
        self.assertTrue(formats.is_supported_input("a.mkv"))
        self.assertFalse(formats.is_supported_input("a.png"))
        self.assertTrue(engine.format_supported("mp4"))

    def test_is_video(self):
        self.assertTrue(engine.is_video(self.sample))
        fake = self.path("faux.mp4")
        with open(fake, "wb") as handle:
            handle.write(b"pas une video")
        self.assertFalse(engine.is_video(fake))

    def test_timecode(self):
        self.assertEqual(engine.timecode(0), "00:00")
        self.assertEqual(engine.timecode(83), "01:23")
        self.assertEqual(engine.timecode(3723), "1:02:03")
        self.assertEqual(engine.parse_timecode("1:23"), 83)
        self.assertEqual(engine.parse_timecode("1:02:03"), 3723)
        self.assertEqual(engine.parse_timecode("12.5"), 12.5)
        with self.assertRaises(engine.VideoError):
            engine.parse_timecode("abc")

    def test_vignette(self):
        data = engine.thumbnail(self.sample, 0.6, max_side=160)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertGreater(len(data), 200)

    def test_estimation_varie_avec_la_qualite(self):
        info = engine.describe(self.sample)
        low = engine.estimate_size(info, "mp4", engine.VideoSettings(
            crf=30, width=160, height=120))
        high = engine.estimate_size(info, "mp4", engine.VideoSettings(
            crf=18, width=160, height=120))
        self.assertGreater(low, 0)
        self.assertGreater(high, low)

    def test_commande_attendue(self):
        info = engine.describe(self.sample)
        settings = engine.VideoSettings(
            crf=25, width=160, height=120, fps=25, rotation=90, start=0.5,
            end=1.5, audio_mode="none")
        command = engine.build_command(info, self.path("x.mp4"), "mp4",
                                       settings)
        joined = " ".join(command)
        self.assertIn("scale=160:120", joined)
        self.assertIn("transpose=clock", joined)
        self.assertIn("fps=25", joined)
        self.assertIn("-crf 25", joined)
        self.assertIn("-an", joined)
        self.assertIn("-ss 0.500", joined)

    def test_conversion_mp4_avec_coupe(self):
        destination = self.path("sortie.mp4")
        settings = engine.VideoSettings(
            crf=28, speed="fast", width=160, height=120, start=0.5, end=1.5)
        result = engine.convert(self.sample, destination, "mp4", settings)
        self.assertTrue(os.path.isfile(destination))
        self.assertEqual(result["size"], os.path.getsize(destination))
        self.assertEqual((result["width"], result["height"]), (160, 120))
        self.assertLess(result["duration"], 1.6)
        output = engine.describe(destination)
        self.assertEqual((output.width, output.height), (160, 120))
        self.assertAlmostEqual(output.duration, 1.0, delta=0.4)
        self.assertTrue(output.has_audio)

    def test_conversion_mov(self):
        destination = self.path("sortie.mov")
        settings = engine.VideoSettings(crf=28, speed="fast", width=160,
                                        height=120, start=0.5, end=1.5)
        result = engine.convert(self.sample, destination, "mov", settings)
        self.assertTrue(os.path.isfile(destination))
        output = engine.describe(destination)
        self.assertEqual((output.width, output.height), (160, 120))
        self.assertEqual(output.container, "MOV")
        self.assertTrue(output.has_audio)

    def test_conversion_sans_audio(self):
        destination = self.path("muet.mp4")
        settings = engine.VideoSettings(crf=30, speed="fast", audio_mode="none")
        engine.convert(self.sample, destination, "mp4", settings)
        output = engine.describe(destination)
        self.assertFalse(output.has_audio)

    def test_sortie_par_defaut(self):
        renamed = self.path("source.mp4")
        self.assertTrue(engine.default_output_path(renamed, "mp4")
                        .endswith("source-converti.mp4"))
        self.assertTrue(engine.default_output_path(renamed, "webm")
                        .endswith("source.webm"))

    def test_copie_audio_selon_conteneur(self):
        info = engine.describe(self.sample)
        self.assertTrue(engine.audio_copy_supported(
            info, formats.get_format("mp4")))
        self.assertFalse(engine.audio_copy_supported(
            info, formats.get_format("webm")))


if __name__ == "__main__":
    unittest.main()
