from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_menu_art import sparrow

class SparrowMenu(unittest.TestCase):
    def test_restore_trimming_and_repeated_frames(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'label.png'
            Image.new('RGBA',(2,2),'red').save(path)
            path.with_suffix('.xml').write_text('''<TextureAtlas>
              <SubTexture name="label idle0001" x="0" y="0" width="2" height="2" frameX="-2" frameY="-1" frameWidth="6" frameHeight="4"/>
              <SubTexture name="label idle0000" x="0" y="0" width="2" height="2" frameX="-2" frameY="-1" frameWidth="6" frameHeight="4"/>
            </TextureAtlas>''')
            frames,groups=sparrow(path,1)
            self.assertEqual(groups,{'label idle':[1,0]})
            self.assertEqual(len(frames),2)
            self.assertEqual(frames[0].size,(6,4))
            self.assertEqual(frames[0].getbbox(),(2,1,4,3))
            self.assertEqual(frames[0].tobytes(),frames[1].tobytes())
            with self.assertRaises(ValueError):sparrow(path,100)

if __name__=='__main__':unittest.main()
