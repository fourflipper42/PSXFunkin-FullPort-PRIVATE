import subprocess, tempfile, unittest, sys, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

class PreviewAudio(unittest.TestCase):
 def test_preview_bounds_are_fractions_of_instrumental_duration(self):
  path=ROOT/'scripts/build_freeplay_music.py'
  self.assertTrue(path.exists())
  from build_freeplay_music import preview_bounds
  self.assertEqual(preview_bounds({},150),(0,30))
  self.assertEqual(preview_bounds({'previewStart':.25,'previewEnd':.5},120),(30,60))
  self.assertEqual(preview_bounds({'previewStart':.7,'previewEnd':.2},120),(0,24))

 def test_preview_debounces_routes_and_stops_for_confirmation(self):
  source=ROOT/'overlay/src/freeplay_music.c'
  self.assertTrue(source.exists())
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)
   stub=r'''
#ifndef STUB_H
#define STUB_H
#include <assert.h>
#include <string.h>
typedef unsigned char u8;typedef unsigned int u32;typedef int fixed_t;
typedef struct {int pos,size;} CdlFILE;
#define COUNT_OF(a) (sizeof(a)/sizeof((a)[0]))
#define IO_SECT_SIZE 2048
static int playing,reads,starts,stops,channel,size;
static void Audio_StopXA(void) {playing=0;stops++;}
static int Audio_PlayingXA(void) {return playing;}
static void IO_FindFile(CdlFILE *f,const char *s) {assert(!playing);reads++;f->pos=reads;f->size=99999;}
static void Audio_PlayXA_File(CdlFILE *f,int volume,int ch,int loop) {assert(volume==89 && !loop);playing=1;starts++;channel=ch;size=f->size;}
#endif
'''
   (p/'stubs.h').write_text(stub)
   for name in ('audio.h','io.h','fixed.h'):(p/name).write_text('#include "stubs.h"\n')
   (p/'freeplay_music.h').write_text((ROOT/'overlay/src/freeplay_music.h').read_text())
   (p/'freeplay_music.c').write_text(source.read_text())
   (p/'freeplay_music_generated.h').write_text('static const char *const fp_music_files[]={"A","B"};\nstatic const struct {unsigned int file,channel,sectors;} fp_music_routes[]={{0,0,100},{0,1,120},{1,2,140}};\nstatic const unsigned char fp_music_map[26][2]={{0,1}};\n#define FP_MUSIC_RANDOM 2\n')
   (p/'test.c').write_text(r'''
#include "freeplay_music.c"
int main(void) {
 FreeplayMusic_Load();assert(reads==2);
 FreeplayMusic_Tick(0,1,100,1);assert(starts==0);
 FreeplayMusic_Tick(0,1,100,1);assert(starts==0);
 FreeplayMusic_Tick(0,1,100,1);assert(starts==1 && channel==0 && size==100*2048);
 FreeplayMusic_Tick(0,2,300,1);assert(starts==1);
 FreeplayMusic_Tick(0,3,100,1);assert(starts==1);
 FreeplayMusic_Tick(-1,1,100,1);assert(starts==1);
 FreeplayMusic_Tick(0,4,100,1);assert(starts==1);
 FreeplayMusic_Tick(0,4,300,1);assert(starts==2 && channel==1);
 playing=0;FreeplayMusic_Tick(0,4,17,1);assert(starts==3);
 int n=stops;FreeplayMusic_Tick(0,4,17,0);assert(!playing && stops==n+1);
 FreeplayMusic_Tick(0,4,17,0);assert(stops==n+1);
 assert(reads==2);return 0;
}
''')
   subprocess.run(['cc','-std=c99','-Wall','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
   run=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(run.returncode,0,run.stderr)
