import ctypes, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class FreeplayResults(unittest.TestCase):
    def test_best_completed_run_keeps_score_and_tallies_together(self):
        source=ROOT/'overlay/src/freeplay_results.c'
        self.assertTrue(source.exists(),'Freeplay results must come from completed runs')
        with tempfile.TemporaryDirectory() as td:
            library=Path(td)/'results.so'
            subprocess.run(['cc','-Wall','-Wextra','-Werror','-shared','-fPIC',str(source),'-o',str(library)],check=True)
            lib=ctypes.CDLL(str(library))
            lib.FreeplayResults_Begin(10)
            for _ in range(7):lib.FreeplayResults_Hit(0)
            lib.FreeplayResults_Hit(1)
            lib.FreeplayResults_Hit(2)
            # One missed tap: (7 sick + 1 good - 1 miss) / 10 = 70%.
            lib.FreeplayResults_Finish(2,1,2700)
            self.assertEqual(lib.FreeplayResults_Score(2,1),2700)
            self.assertEqual(lib.FreeplayResults_Completion(2,1),70)
            self.assertEqual(lib.FreeplayResults_Score(2,2),0)
            lib.FreeplayResults_Begin(10)
            for _ in range(10):lib.FreeplayResults_Hit(0)
            self.assertEqual(lib.FreeplayResults_Score(2,1),2700,'unfinished run must not replace the record')
            lib.FreeplayResults_Finish(2,1,2000)
            self.assertEqual(lib.FreeplayResults_Completion(2,1),70)
            lib.FreeplayResults_Begin(10)
            for _ in range(10):lib.FreeplayResults_Hit(0)
            lib.FreeplayResults_Finish(2,1,3500)
            self.assertEqual(lib.FreeplayResults_Score(2,1),3500)
            self.assertEqual(lib.FreeplayResults_Completion(2,1),100)
            lib.FreeplayResults_Begin(0);lib.FreeplayResults_Finish(2,1,99999)
            self.assertEqual(lib.FreeplayResults_Score(2,1),3500)
            self.assertEqual(lib.FreeplayResults_Score(-1,9),0)
