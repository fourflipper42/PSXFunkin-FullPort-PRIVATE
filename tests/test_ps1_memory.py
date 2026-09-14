import struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from validate_ps1_memory import validate
class MemoryLayout(unittest.TestCase):
 def test_bss_is_included_and_movie_stack_is_reserved(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);exe=p/'game.exe';symbols=p/'symbols.txt'
   data=bytearray(4096);data[:8]=b'PS-X EXE';struct.pack_into('<I',data,16,0x80010000);struct.pack_into('<II',data,24,0x80010000,2048);struct.pack_into('<I',data,48,0x801fff00);exe.write_bytes(data)
   symbols.write_text('80140000 B __bss_end\n')
   self.assertEqual(validate(exe,symbols)['available_stack_bytes'],0xbff00)
   symbols.write_text('80190000 B __bss_end\n')
   with self.assertRaises(ValueError):validate(exe,symbols)
   symbols.write_text('80210000 B __bss_end\n')
   with self.assertRaises(ValueError):validate(exe,symbols)
   symbols.write_text('')
   with self.assertRaises(ValueError):validate(exe,symbols)
