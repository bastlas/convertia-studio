"""Tests du décodage des projets Audacity et du mixage.

Lancer avec :  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convertia_studio import jobs  # noqa: E402
from convertia_studio.audio import formats  # noqa: E402
from convertia_studio.audio.project import Project  # noqa: E402
from tests.make_project import (FLOAT32, INT16, INT24,  # noqa: E402
                                write_project)

RATE = 44100


def tone(frequency=440.0, duration=0.25, amplitude=0.5, rate=RATE):
    """Un sinus de durée et d'amplitude connues."""
    times = np.arange(int(duration * rate), dtype=np.float32) / rate
    return (amplitude * np.sin(2 * np.pi * frequency * times)).astype(np.float32)


class ProjectTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def path(self, name="projet.aup4"):
        return os.path.join(self._tmp.name, name)

    def write(self, tracks, **kwargs):
        return write_project(self.path(), tracks, rate=RATE, **kwargs)

    def render(self, **kwargs):
        with Project(self.path()) as project:
            samples, rate = project.render(progress=None, **kwargs)
        return samples, rate


class TestMonoClip(ProjectTestCase):
    def test_position_gain_et_silence(self):
        samples = tone(amplitude=0.5)
        self.write([{
            "name": "voix", "gain": 0.5,
            "channels": [{"clips": [{"offset": 1.0, "sequences": [samples]}]}],
        }])
        mixed, rate = self.render()

        self.assertEqual(rate, RATE)
        start = int(round(1.0 * RATE))
        # silence avant le clip
        self.assertLess(float(np.abs(mixed[:start - 1]).max()), 1e-6)
        # le clip est présent sur les deux canaux, au gain de la piste
        segment = mixed[start:start + samples.size]
        np.testing.assert_allclose(segment[:, 0], samples * 0.5, atol=2e-6)
        np.testing.assert_allclose(segment[:, 1], samples * 0.5, atol=2e-6)

    def test_trim_left_et_right(self):
        samples = np.arange(1000, dtype=np.float32) / 1000.0
        self.write([{
            "name": "voix",
            "channels": [{"clips": [{
                "offset": 0.0, "trim_left": 100 / RATE, "trim_right": 200 / RATE,
                "sequences": [samples]}]}],
        }])
        mixed, _rate = self.render()
        expected = samples[100:800]
        # le debut audible est offset + trimLeft
        start = int(round((100 / RATE) * RATE))
        np.testing.assert_allclose(mixed[start:start + expected.size, 0], expected,
                                   atol=1e-6)
        self.assertLess(float(np.abs(mixed[:start - 1]).max()), 1e-6)

    def test_panoramique_gauche(self):
        samples = tone(amplitude=0.8)
        self.write([{
            "name": "voix", "pan": -1.0,
            "channels": [{"clips": [{"offset": 0.0, "sequences": [samples]}]}],
        }])
        mixed, _rate = self.render()
        segment = mixed[:samples.size]
        self.assertGreater(float(np.abs(segment[:, 0]).max()), 0.5)
        self.assertLess(float(np.abs(segment[:, 1]).max()), 1e-6)

    def test_enveloppe(self):
        samples = np.ones(1000, dtype=np.float32) * 0.5
        self.write([{
            "name": "voix",
            "channels": [{"clips": [{
                "offset": 0.5, "sequences": [samples],
                "envelope": [(0.5, 1.0), (0.5 + 1000 / RATE, 0.5)]}]}],
        }])
        mixed, _rate = self.render()
        start = int(round(0.5 * RATE))
        segment = mixed[start:start + samples.size, 0]
        times = 0.5 + np.arange(samples.size) / RATE
        gain = np.interp(times, [0.5, 0.5 + 1000 / RATE], [1.0, 0.5])
        np.testing.assert_allclose(segment, samples * gain, atol=2e-3)

    def test_muet_et_solo(self):
        first = tone(440.0, amplitude=0.5)
        second = tone(660.0, amplitude=0.5)
        tracks = [
            {"name": "un", "mute": True,
             "channels": [{"clips": [{"offset": 0.0, "sequences": [first]}]}]},
            {"name": "deux", "solo": True,
             "channels": [{"clips": [{"offset": 0.0, "sequences": [second]}]}]},
        ]
        self.write(tracks)
        mixed, _rate = self.render()
        np.testing.assert_allclose(mixed[:second.size, 0], second, atol=2e-6)

        mixed_all, _rate = self.render(respect_mute_solo=False)
        combined = first + second
        np.testing.assert_allclose(mixed_all[:second.size, 0], combined, atol=2e-6)


class TestStereoAndFormats(ProjectTestCase):
    def test_paire_stereo_deux_wavetracks(self):
        left = tone(440.0, amplitude=0.4)
        right = tone(880.0, amplitude=0.4)
        self.write([{
            "name": "musique",
            "channels": [
                {"clips": [{"offset": 0.0, "sequences": [left]}]},
                {"clips": [{"offset": 0.0, "sequences": [right]}]},
            ],
        }])
        mixed, _rate = self.render()
        np.testing.assert_allclose(mixed[:left.size, 0], left, atol=2e-6)
        np.testing.assert_allclose(mixed[:right.size, 1], right, atol=2e-6)

    def test_ancien_format_deux_sequences_dans_un_clip(self):
        left = tone(300.0, amplitude=0.3)
        right = tone(500.0, amplitude=0.3)
        self.write([{
            "name": "stereo 3.3",
            "channels": [{"clips": [{"offset": 0.0, "sequences": [left, right]}]}],
        }])
        mixed, _rate = self.render()
        np.testing.assert_allclose(mixed[:left.size, 0], left, atol=2e-6)
        np.testing.assert_allclose(mixed[:right.size, 1], right, atol=2e-6)

    def test_blocs_int16_et_int24(self):
        samples = tone(440.0, amplitude=0.5)
        for sample_format, tolerance in ((INT16, 1e-3), (INT24, 1e-5), (FLOAT32, 1e-6)):
            with self.subTest(format=hex(sample_format)):
                self.write([{
                    "name": "voix",
                    "channels": [{"clips": [{"offset": 0.0, "sequences": [samples]}]}],
                }], sample_format=sample_format)
                mixed, _rate = self.render()
                np.testing.assert_allclose(mixed[:samples.size, 0], samples,
                                           atol=tolerance)

    def test_sauvegarde_automatique(self):
        samples = tone(amplitude=0.2)
        self.write([{
            "name": "voix",
            "channels": [{"clips": [{"offset": 0.0, "sequences": [samples]}]}],
        }], document="autosave")
        with Project(self.path()) as project:
            self.assertEqual(project.doc_source, "autosave")
            self.assertTrue(any("autosave" in w for w in project.warnings))


class TestPcmWriters(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _decode(self, path, channels=2):
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", path,
                              "-f", "f32le", "-"], capture_output=True).stdout
        return np.frombuffer(out, dtype="<f4").reshape(-1, channels)

    @unittest.skipUnless(formats.ffmpeg_tools.ffmpeg(), "ffmpeg requis")
    def test_wav_et_aiff(self):
        samples = tone(duration=0.1, amplitude=0.6)
        stereo = np.stack([samples, -samples * 0.5], axis=1)
        for key in ("wav", "aiff"):
            for depth, tolerance in (("16", 1e-4), ("24", 1e-6), ("32f", 0.0)):
                with self.subTest(format=key, depth=depth):
                    path = os.path.join(self._tmp.name, "sortie_%s_%s.%s"
                                        % (key, depth, key))
                    formats.write_pcm_file(path, stereo, RATE, key, depth)
                    decoded = self._decode(path)
                    np.testing.assert_allclose(decoded, stereo, atol=tolerance)


class TestJobs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_describe_et_convert(self):
        samples = tone(duration=0.3, amplitude=0.4)
        source = write_project(
            os.path.join(self._tmp.name, "source.aup4"),
            [{"name": "voix", "channels": [
                {"clips": [{"offset": 0.0, "sequences": [samples]}]}]}],
            rate=RATE)
        info = jobs.describe(source)
        self.assertEqual(info.kind, "audacity")
        self.assertAlmostEqual(info.duration, 0.3, places=3)

        if formats.ffmpeg_tools.ffmpeg() is None:
            self.skipTest("ffmpeg requis")
        destination = os.path.join(self._tmp.name, "sortie.mp3")
        result = jobs.convert(source, destination, "mp3", {"bitrate": "192k"})
        self.assertTrue(os.path.isfile(destination))
        self.assertGreater(result["size"], 1000)
        self.assertEqual(result["format"].key, "mp3")

    def test_entree_audio_quelconque(self):
        if formats.ffmpeg_tools.ffmpeg() is None:
            self.skipTest("ffmpeg requis")
        source = os.path.join(self._tmp.name, "bruit.wav")
        formats.write_wav(source, np.stack([tone(), tone()], axis=1), RATE, "16")
        info = jobs.describe(source)
        self.assertEqual(info.kind, "audio")
        self.assertAlmostEqual(info.duration, 0.25, places=2)

        destination = os.path.join(self._tmp.name, "bruit.opus")
        jobs.convert(source, destination, "opus", {"bitrate": "96k"})
        self.assertTrue(os.path.isfile(destination))


if __name__ == "__main__":
    unittest.main()
