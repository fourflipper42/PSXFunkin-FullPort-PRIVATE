import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/ps1asset')]
from PIL import Image
import psxfunkin_chartc_v2 as chartc
from png_to_tim import encode_tim, decode_tim
from arc_pack import pack_arc
from validate_disc import validate
from build_weekend1_assets import animation_script
from build_weekend1_audio import interleave, sectors


def decode_chart(data):
    offset = struct.unpack_from('<H', data)[0]
    return (list(struct.iter_unpack('<HH', data[2:offset])),
            list(struct.iter_unpack('<HBB', data[offset:])))

class Charts(unittest.TestCase):
    def convert(self, notes, changes=None, events=None, **kwargs):
        return decode_chart(chartc.convert(
            {'notes': {'normal': notes}, 'events': events or []},
            {'timeChanges': changes or [{'t': 0, 'b': 0, 'bpm': 120}]},
            'normal', **kwargs))

    def test_note_lanes_and_sentinels(self):
        sections, notes = self.convert([{'t': 500, 'd': 0}, {'t': 1000, 'd': 7}])
        self.assertEqual(notes, [(48, 0, 0), (96, 7, 0), (65535, 128, 0)])
        self.assertEqual(sections[-1], (65535, 2880))

    def test_sub_step_hold_does_not_create_phantom_tail(self):
        _, notes = self.convert([{'t': 0, 'd': 0, 'l': 1}])
        self.assertEqual(notes, [(0, 0, 0), (65535, 128, 0)])

    def test_hold_crossing_tempo_change(self):
        sections, notes = self.convert([{'t': 500, 'd': 0, 'l': 750}],
            [{'t': 0, 'b': 0, 'bpm': 120}, {'t': 1000, 'b': 2, 'bpm': 240}])
        self.assertEqual([n[0] for n in notes[1:-1]], list(range(60, 145, 12)))
        self.assertEqual(notes[-2][1], 24)
        self.assertEqual(sections[:2], [(96, 2880), (192, 5760)])

    def test_focus_change_inside_measure(self):
        sections, _ = self.convert([], events=[{'t': 250, 'e': 'FocusCamera', 'v': {'char': 1}}])
        self.assertEqual(sections[:2], [(24, 2880), (192, 2880 | 0x8000)])

    def test_missing_beat_is_derived_from_previous_tempo(self):
        changes = chartc.read_time_changes({'timeChanges': [
            {'t': 0, 'bpm': 120}, {'t': 1000, 'bpm': 240}]})
        self.assertEqual(changes[1].beat, 2)
        self.assertEqual(chartc.time_to_beat(1250, changes), 3)

    def test_reject_invalid_lane(self):
        with self.assertRaises(ValueError): self.convert([{'t': 0, 'd': 8}])

    def test_reject_sentinel_note(self):
        with self.assertRaises(ValueError):
            self.convert([{'t': 65535 / 48 * 500, 'd': 0}], section_count=1)

    def test_reject_unrepresentable_bpm(self):
        with self.assertRaises(ValueError):
            self.convert([], [{'t': 0, 'b': 0, 'bpm': 2000}])

    def test_reject_discontinuous_tempo(self):
        with self.assertRaises(ValueError):
            self.convert([], [{'t': 0, 'b': 0, 'bpm': 120}, {'t': 500, 'b': 0, 'bpm': 150}])

    def test_reject_zero_sections(self):
        with self.assertRaises(ValueError): self.convert([], section_count=0)

class Assets(unittest.TestCase):
    def test_opaque_black_survives_both_tim_depths(self):
        for bpp in (4, 8):
            image = Image.new('RGBA', (4, 1), (0, 0, 0, 255))
            image.putpixel((1, 0), (0, 0, 0, 0))
            result = decode_tim(encode_tim(image, bpp))
            self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 255))
            self.assertEqual(result.getpixel((1, 0))[3], 0)

    def test_full_archive_has_terminator(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = [root / f'{i}.tim' for i in range(16)]
            for f in files: f.write_bytes(b'\xff' * 20)
            out = root / 'main.arc'
            pack_arc(out, files)
            data = out.read_bytes()
            self.assertEqual(data[256:272], bytes(16))
            for i in range(16):
                offset = struct.unpack_from('<I', data, i * 16 + 12)[0]
                self.assertEqual(offset % 16, 0)
                self.assertEqual(data[offset:offset + 20], b'\xff' * 20)

    def test_audio_interleave_pads_shorter_channels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = [root / f'{i}.xa' for i in range(8)]
            for i, path in enumerate(paths):
                path.write_bytes(bytes([i + 1]) * 2336 * (2 if i == 0 else 1))
            silence = [bytes([i + 20]) * 2336 for i in range(8)]
            output = root / 'week8.xa'
            self.assertEqual(interleave(output, paths, silence), 16)
            stream = sectors(output)
            self.assertEqual(stream[:8], [bytes([i + 1]) * 2336 for i in range(8)])
            self.assertEqual(stream[8], bytes([1]) * 2336)
            self.assertEqual(stream[9:], silence[1:])

    def test_missing_animation_fails(self):
        with self.assertRaises(ValueError): animation_script([])

class Disc(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.bin = root / 'game.bin'
        self.cue = root / 'game.cue'
        self.bin.write_bytes(bytes(2352 * 2))
        self.cue.write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    def tearDown(self): self.temp.cleanup()
    def test_valid(self): self.assertEqual(validate(self.bin, self.cue)['raw_sectors'], 2)
    def test_oversize(self):
        with self.assertRaises(ValueError): validate(self.bin, self.cue, max_sectors=1)
    def test_partial_sector(self):
        self.bin.write_bytes(b'bad')
        with self.assertRaises(ValueError): validate(self.bin, self.cue)
    def test_wrong_cue_reference(self):
        self.cue.write_text(self.cue.read_text().replace('game.bin', 'missing.bin'))
        with self.assertRaises(ValueError): validate(self.bin, self.cue)

if __name__ == '__main__': unittest.main()
