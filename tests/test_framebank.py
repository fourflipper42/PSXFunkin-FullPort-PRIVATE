import ctypes
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/ps1asset'))
from framebank import rle_encode, rle_decode, pack_indices, unpack_indices, encode_images

class FrameBanks(unittest.TestCase):
    def test_lossless_runs_and_literals(self):
        rng = random.Random(804)
        for n in [0,1,2,3,127,128,129,16384]:
            for data in [bytes(n), bytes([127])*n, bytes(rng.randrange(256) for _ in range(n))]:
                self.assertEqual(rle_decode(rle_encode(data), n), data)

    def test_duplicate_frames_retain_timing_entries(self):
        frames=[bytes(16),bytes(range(16)),bytes(16)]
        data=pack_indices(4,4,[0]*256,frames)
        self.assertEqual(unpack_indices(data)[3],frames)
        import struct
        self.assertEqual(struct.unpack_from('<II',data,528),struct.unpack_from('<II',data,544))

    def test_native_decoder_matches_python(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('host C compiler unavailable')
        with tempfile.TemporaryDirectory() as td:
            library=Path(td)/'codec.so'
            subprocess.run([cc,'-std=c99','-shared','-fPIC','-Wall','-Wextra','-Werror',str(ROOT/'overlay/src/framecodec.c'),'-o',str(library)],check=True)
            codec=ctypes.CDLL(str(library)).FrameCodec_Decode
            codec.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint]
            codec.restype=ctypes.c_int
            rng=random.Random(804)
            for size in [1,127,128,129,16384,65536]:
                data=bytes(rng.randrange(16) if rng.random()<.2 else 0 for _ in range(size))
                encoded=rle_encode(data)
                dst=ctypes.create_string_buffer(size)
                self.assertEqual(codec(encoded,len(encoded),dst,size),1)
                self.assertEqual(dst.raw,data)
                self.assertEqual(codec(encoded,len(encoded)-1,dst,size),0)
                self.assertEqual(codec(encoded,len(encoded),dst,size-1),0)

    def test_preserves_frames_and_black(self):
        frame=Image.new('RGBA',(4,4),(0,0,0,255))
        frame.putpixel((0,0),(0,0,0,0))
        data, report=encode_images([frame,frame,frame])
        _,_,palette,frames=unpack_indices(data)
        self.assertEqual(report['frames'],3)
        self.assertEqual(report['frames_dropped'],0)
        self.assertEqual(report['unique_frames'],1)
        self.assertEqual(palette[frames[0][1]],0x8000)
        self.assertEqual(frames[0][0],0)

    def test_reject_truncated_commands(self):
        for data in [b'\x80',b'\x01\x22',b'\xff\x00']:
            with self.assertRaises(ValueError):rle_decode(data,4)

if __name__=='__main__':unittest.main()
