from pathlib import Path
import sys,tempfile,unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_homebrew_disc import prepare
class Manifest(unittest.TestCase):
    def test_serialized_whitespace_does_not_change_preparation(self):
        for ending in ('/>',' />'):
            with tempfile.TemporaryDirectory() as td:
                path=Path(td)/'disc.xml'
                path.write_text('<iso_project><track><license file="licensea.dat"'+ending+'<directory_tree><file name="story.fbk" source="iso/menu/story.fbk" /></directory_tree></track></iso_project>')
                prepare(path);prepare(path)
                tree=ET.parse(path)
                self.assertIsNone(tree.find('.//license'))
                self.assertEqual(tree.find('.//file').get('source'),'iso/menu/story.fbk')
