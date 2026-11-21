"""Fabrique de projets Audacity synthétiques pour les tests.

Écrit un fichier ``.aup4`` minimal mais conforme : base SQLite (``project``,
``autosave``, ``sampleblocks``) et document au format « binary XML » d'Audacity
(voir :mod:`convertia_studio.audio.project` pour la description du format).

Cela permet de tester le décodage et le mixage sans dépendre d'Audacity ni d'un
projet réel : les échantillons sont connus, donc les résultats attendus aussi.
"""

from __future__ import annotations

import os
import sqlite3
import struct

import numpy as np

APP_ID = 0x41554459  # 'AUDY'

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id    INTEGER PRIMARY KEY,
    dict  BLOB,
    doc   BLOB
);
CREATE TABLE IF NOT EXISTS autosave (
    id    INTEGER PRIMARY KEY,
    dict  BLOB,
    doc   BLOB
);
CREATE TABLE IF NOT EXISTS sampleblocks (
    blockid      INTEGER PRIMARY KEY AUTOINCREMENT,
    sampleformat INTEGER,
    summin       REAL,
    summax       REAL,
    sumrms       REAL,
    summary256   BLOB,
    summary64k   BLOB,
    samples      BLOB
);
"""

FT_CHARSIZE, FT_START, FT_END, FT_STRING = 0, 1, 2, 3
FT_INT, FT_BOOL, FT_FLOAT, FT_NAME = 4, 5, 9, 15

FLOAT32 = 0x0004000F
INT16 = 0x00020001
INT24 = 0x00040001


def _u16(value):
    return struct.pack("<H", value)


def _i32(value):
    return struct.pack("<i", value)


def _utf32(text):
    return text.encode("utf-32-le")


class DocumentWriter:
    """Écrit le couple (dictionnaire, document) au format d'Audacity."""

    def __init__(self):
        self.dictionary = bytearray(bytes([FT_CHARSIZE, 4]))  # 4 octets/caractère
        self.data = bytearray()
        self._names = {}

    def _name_id(self, name):
        if name not in self._names:
            name_id = len(self._names)
            self._names[name] = name_id
            encoded = _utf32(name)
            self.dictionary += bytes([FT_NAME]) + _u16(name_id) + _u16(len(encoded))
            self.dictionary += encoded
        return self._names[name]

    def start(self, name):
        self.data += bytes([FT_START]) + _u16(self._name_id(name))
        return self

    def end(self, name):
        self.data += bytes([FT_END]) + _u16(self._name_id(name))
        return self

    def attr(self, name, value):
        key = self._name_id(name)
        if isinstance(value, bool):
            self.data += bytes([FT_BOOL]) + _u16(key) + bytes([int(value)])
        elif isinstance(value, int):
            self.data += bytes([FT_INT]) + _u16(key) + _i32(value)
        elif isinstance(value, float):
            self.data += bytes([FT_FLOAT]) + _u16(key)
            self.data += struct.pack("<f", value) + _i32(8)
        else:
            encoded = _utf32(str(value))
            self.data += bytes([FT_STRING]) + _u16(key) + _i32(len(encoded))
            self.data += encoded
        return self


def _encode_blocks(samples, sample_format):
    """Découpe un canal en blocs et retourne (blobs, longueurs en échantillons)."""
    if sample_format == FLOAT32:
        payload = np.ascontiguousarray(samples, dtype="<f4")
        blobify = lambda chunk: np.ascontiguousarray(chunk, dtype="<f4").tobytes()
    elif sample_format == INT16:
        blobify = lambda chunk: np.round(np.clip(chunk, -1, 1) * 32767).astype("<i2").tobytes()
        payload = samples
    else:  # int24 stocké en int32
        blobify = lambda chunk: np.round(np.clip(chunk, -1, 1) * 8388607).astype("<i4").tobytes()
        payload = samples
    blobs = []
    step = 256
    for start in range(0, len(payload), step):
        blobs.append(blobify(payload[start:start + step]))
    return blobs


def write_project(path, tracks, rate=44100, sample_format=FLOAT32,
                  document="project"):
    """Crée un projet ``.aup4`` de test.

    ``tracks`` est une liste de dictionnaires ::

        {"name": "Audio 1", "gain": 1.0, "pan": 0.0, "mute": False,
         "solo": False,
         "channels": [
             {"clips": [{"offset": 1.0, "trim_left": 0.0, "trim_right": 0.0,
                         "stretch": 1.0, "envelope": [(1.0, 1.0)],
                         "sequences": [samples_channel_0, samples_channel_1]}]}
         ]}
    """
    if os.path.exists(path):
        os.remove(path)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute("PRAGMA application_id = %d" % APP_ID)
    connection.execute("PRAGMA user_version = %d" % ((4 << 24) | (0 << 16) | (2 << 8) | 1))

    writer = DocumentWriter()
    writer.start("project")
    writer.attr("version", "2.0.0")
    writer.attr("audacityversion", "4.0.2")
    writer.attr("rate", float(rate))

    next_block_id = 1
    for track in tracks:
        for channel_index, channel in enumerate(track.get("channels", [])):
            writer.start("wavetrack")
            writer.attr("name", track.get("name", "Audio"))
            writer.attr("channel", channel_index)
            writer.attr("linked", 3 if channel_index == 0 and
                        len(track.get("channels", [])) > 1 else 0)
            writer.attr("rate", float(rate))
            writer.attr("gain", float(track.get("gain", 1.0)))
            writer.attr("pan", float(track.get("pan", 0.0)))
            writer.attr("mute", bool(track.get("mute", False)))
            writer.attr("solo", bool(track.get("solo", False)))
            writer.attr("sampleformat", sample_format)

            for clip in channel.get("clips", []):
                sequences = clip.get("sequences") or []
                writer.start("waveclip")
                writer.attr("offset", float(clip.get("offset", 0.0)))
                writer.attr("trimLeft", float(clip.get("trim_left", 0.0)))
                writer.attr("trimRight", float(clip.get("trim_right", 0.0)))
                writer.attr("clipStretchRatio", float(clip.get("stretch", 1.0)))
                writer.attr("name", clip.get("name", "clip"))

                for samples in sequences:
                    samples = np.asarray(samples, dtype=np.float32)
                    blobs = _encode_blocks(samples, sample_format)
                    writer.start("sequence")
                    writer.attr("maxsamples", 262144)
                    writer.attr("sampleformat", sample_format)
                    writer.attr("numsamples", int(samples.size))
                    position = 0
                    for blob in blobs:
                        block_id = next_block_id
                        next_block_id += 1
                        connection.execute(
                            "INSERT INTO sampleblocks (blockid, sampleformat, summin,"
                            " summax, sumrms, summary256, summary64k, samples)"
                            " VALUES (?, ?, 0, 0, 0, x'', x'', ?)",
                            (block_id, sample_format, blob))
                        count = len(blob) // (4 if sample_format != INT16 else 2)
                        writer.start("waveblock")
                        writer.attr("start", position)
                        writer.attr("length", count)
                        writer.attr("blockid", block_id)
                        writer.end("waveblock")
                        position += count
                    writer.end("sequence")

                envelope = clip.get("envelope")
                if envelope:
                    writer.start("envelope")
                    writer.attr("numpoints", len(envelope))
                    for when, value in envelope:
                        writer.start("controlpoint")
                        writer.attr("t", float(when))
                        writer.attr("val", float(value))
                        writer.end("controlpoint")
                    writer.end("envelope")

                writer.end("waveclip")
            writer.end("wavetrack")

    writer.end("project")

    for table in ("project", "autosave"):
        connection.execute("DELETE FROM %s" % table)
        if table == document:
            connection.execute("INSERT INTO %s (id, dict, doc) VALUES (1, ?, ?)"
                               % table, (bytes(writer.dictionary), bytes(writer.data)))
        else:
            connection.execute("INSERT INTO %s (id, dict, doc) VALUES (1, ?, NULL)"
                               % table, (bytes(writer.dictionary),))
    connection.commit()
    connection.close()
    return path
