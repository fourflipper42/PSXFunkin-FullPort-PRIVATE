"""Default-song metadata coverage and instrumental-only audio conversion."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_base_audio import GROUPS, MAPPING, WEEKEND
from build_remix_audio import describe, make_pair


class BaseAudio(unittest.TestCase):
    def test_every_default_song_is_assigned_once(self):
        assigned = [song for songs in GROUPS.values() for song in songs]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), {song for song, _, _ in MAPPING + WEEKEND})

    def test_default_metadata_and_instrumental_only_mix(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            self.skipTest('ffmpeg unavailable')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / 'data/songs/blazin'
            folder = root / 'songs/blazin'
            data.mkdir(parents=True)
            folder.mkdir(parents=True)
            (data / 'blazin-metadata.json').write_text(json.dumps({
                'playData': {'characters': {'player': 'pico-blazin', 'opponent': 'darnell-blazin'}}}))
            (data / 'blazin-chart.json').write_text(json.dumps({
                'scrollSpeed': {'easy': 1.5, 'normal': 2, 'hard': 2.5}}))
            # RIFF input is detected by contents even with the fixture's .ogg name.
            with wave.open(str(folder / 'Inst.ogg'), 'wb') as output:
                output.setparams((2, 2, 37800, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\xe8\x03\xe8\x03' * 3780)
            record = describe(root, 'blazin', 8, 4, variation='')
            self.assertEqual(record['speeds'], [1.5, 2, 2.5])
            self.assertEqual(record['player'], [])
            self.assertEqual(record['opponent'], [])
            full, muted = root / 'full.wav', root / 'muted.wav'
            self.assertEqual(make_pair(ffmpeg, record, full, muted, rate=37800), 3780)
            with wave.open(str(full)) as a, wave.open(str(muted)) as b:
                self.assertEqual(a.getframerate(), 37800)
                self.assertEqual(a.getnchannels(), 2)
                self.assertEqual(a.readframes(3780), b.readframes(3780))
