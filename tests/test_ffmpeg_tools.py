"""Tests de la sélection ffmpeg / ffprobe (binaire cassé ignoré)."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from unittest import mock

from convertia_studio import ffmpeg_tools


@unittest.skipIf(os.name == "nt", "scripts POSIX dans ce test")
class TestSelectionFfmpeg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        ffmpeg_tools._working_cache.clear()
        self.addCleanup(ffmpeg_tools._working_cache.clear)

    def _script(self, directory, name, exit_code):
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nexit %d\n" % exit_code)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def test_binaire_casse_ignore(self):
        broken_dir = os.path.join(self._tmp.name, "casse")
        good_dir = os.path.join(self._tmp.name, "bon")
        self._script(broken_dir, "ffprobe", 1)
        good = self._script(good_dir, "ffprobe", 0)
        with mock.patch.object(ffmpeg_tools, "_candidate_dirs",
                               return_value=[broken_dir, good_dir]), \
                mock.patch("shutil.which", return_value=None):
            self.assertEqual(ffmpeg_tools._find("ffprobe"), good)

    def test_repli_sur_le_path(self):
        broken_dir = os.path.join(self._tmp.name, "casse")
        path_dir = os.path.join(self._tmp.name, "path")
        self._script(broken_dir, "ffmpeg", 1)
        system = self._script(path_dir, "ffmpeg", 0)
        with mock.patch.object(ffmpeg_tools, "_candidate_dirs",
                               return_value=[broken_dir]), \
                mock.patch("shutil.which", return_value=system):
            self.assertEqual(ffmpeg_tools._find("ffmpeg"), system)

    def test_aucun_binaire_valide(self):
        broken_dir = os.path.join(self._tmp.name, "casse")
        self._script(broken_dir, "ffprobe", 1)
        with mock.patch.object(ffmpeg_tools, "_candidate_dirs",
                               return_value=[broken_dir]), \
                mock.patch("shutil.which", return_value=None):
            self.assertIsNone(ffmpeg_tools._find("ffprobe"))


if __name__ == "__main__":
    unittest.main()
