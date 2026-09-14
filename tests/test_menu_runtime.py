"""Actual menu state machine with controller/CD stubs; not hardware emulation."""
from pathlib import Path
import os, re, shutil, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class MenuNavigation(unittest.TestCase):
 def test_navigation_difficulty_and_asset_lifetime(self):
  cc=shutil.which('cc')
  if not cc:self.skipTest('host C compiler unavailable')
  source=(ROOT/'overlay/src/menu.c').read_text()
  stages=sorted(set(re.findall(r'StageId_[0-9]+_[0-9]+',source)))
  stub=r'''
#ifndef STUB_H
#define STUB_H
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef int boolean; typedef int fixed_t;
#define true 1
#define false 0
#define FIXED_SHIFT 10
#define FIXED_UNIT 1024
#define FIXED_DEC(n,d) (((n)*1024)/(d))
#define COUNT_OF(a) (sizeof(a)/sizeof((a)[0]))
#define SCREEN_WIDTH 320
#define SCREEN_HEIGHT 240
#define SCREEN_WIDTH2 160
#define SCREEN_HEIGHT2 120
typedef struct {int x,y,w,h;} RECT;
typedef struct {int unused;} Gfx_Tex; typedef void *IO_Data;
typedef enum { STAGES } StageId;
typedef enum {StageDiff_Easy,StageDiff_Normal,StageDiff_Hard,StageDiff_Erect,StageDiff_Nightmare,StageDiff_Max} StageDiff;
struct {int song_step; boolean expsync,kade,ghost,downscroll;} stage;
struct {unsigned int press,held;} pad_state;
enum {PAD_UP=1,PAD_DOWN=2,PAD_LEFT=4,PAD_RIGHT=8,PAD_CROSS=16,PAD_START=32,PAD_CIRCLE=64,PAD_L1=128,PAD_R1=256,PAD_SQUARE=512};
enum {GameLoop_Stage=1,XA_GettinFreaky=1};
int gameloop,pending,reads,freed,played,timer_dt=17;
enum {MenuSound_Scroll,MenuSound_Confirm,MenuSound_Cancel};
int sound_counts[3];
void MenuSound_Load(void) {} void MenuSound_Free(void) {}
void MenuSound_Play(int sound) {assert(sound>=0 && sound<3);sound_counts[sound]++;}
StageId played_id; StageDiff played_diff; boolean played_story;
int art_owner,xa_active,freeplay_loads;
void MenuArt_Load(void) {assert(art_owner==0 && !xa_active);art_owner=1;}
void MenuArt_Free(void) {assert(art_owner==1);art_owner=0;freed++;}
void MenuArt_Enter(void) {assert(art_owner==1);} void MenuArt_Tick(int s) {}
void MenuArt_Label(int i,int s,int x,int y) {assert(i>=0 && i<5);}
void MenuArt_Title(unsigned int t) {} void MenuArt_Back(void) {}
void MenuArt_Prompt(int c,fixed_t t) {} void MenuArt_MainBack(int y,int m) {}
void FreeplayArt_Load(void) {assert(!xa_active && art_owner==0);art_owner=2;freeplay_loads++;}
void FreeplayArt_Free(void) {assert(art_owner==2);art_owner=0;}
void FreeplayArt_Song(const char*n,int i,int s,fixed_t o,fixed_t t,fixed_t c) {assert(art_owner==2);}
void FreeplayArt_Back(int d,fixed_t t,int c,fixed_t e) {assert(art_owner==2 && d>=0 && d<5);}
void FreeplayArt_UI(int d,fixed_t t) {assert(art_owner==2 && d>=0 && d<5);}
void FreeplayArt_State(int s,int f,unsigned int v,int d,fixed_t t) {}
void FreeplayArt_Results(unsigned int s,unsigned int c) {}
unsigned int FreeplayResults_Score(int s,int d) {return 0;}
unsigned int FreeplayResults_Completion(int s,int d) {return 0;}
void MenuArt_Text(const char *s,int x,int y,int c,int b) {
 if (!s) return;
 int left=c ? x-(int)strlen(s)*4:x;
 assert(left>=12 && left+(int)strlen(s)*8<=308);
 assert(y>=12 && y+12<=228);
}
unsigned int MenuArt_CreditCount(void) {return 262;}
const char *MenuArt_Credit(unsigned int i) {return "CREDIT";}
IO_Data IO_Read(const char *p) {reads++;return NULL;}
IO_Data Archive_Find(IO_Data a,const char *n) {return NULL;}
void Mem_Free(IO_Data a) {} void Gfx_LoadTex(Gfx_Tex*t,IO_Data a,int f) {}
void Gfx_SetClear(int r,int g,int b) {} void Gfx_BlitTex(Gfx_Tex*t,RECT*r,int x,int y) {}
void Gfx_DrawRect(RECT*r,int x,int y,int z) {}
void Audio_PlayXA_Track(int a,int b,int c,int d) {xa_active=1;} void Audio_WaitPlayXA(void) {}
void Audio_StopXA(void) {xa_active=0;}
unsigned int Audio_TellXA_Milli(void) {return 10000;}
void Trans_Start(void) {pending=1;} void Trans_Clear(void) {pending=0;}
boolean Trans_Idle(void) {return !pending;}
boolean Trans_Tick(void) {int p=pending;pending=0;return p;}
boolean Stage_SupportsDifficulty(StageId id,StageDiff d) {return d<=StageDiff_Hard || id==StageId_1_1;}
void Stage_Load(StageId id,StageDiff d,boolean story) {played++;played_id=id;played_diff=d;played_story=story;}
void LoadScr_Start(void) {} void LoadScr_End(void) {}
#endif
'''.replace('STAGES',','.join(stages))
  harness=r'''
#include "menu.c"
static void tick(unsigned int press,unsigned int held) {pad_state.press=press;pad_state.held=held;if(gameloop!=GameLoop_Stage)Menu_Tick();}
static void reset(MenuPage p) {memset(&menu,0,sizeof(menu));menu.page=menu.next_page=p;menu.page_swap=true;pending=0;gameloop=0;art_owner=1;xa_active=1;tick(0,0);}
int main(void) {
 reset(MenuPage_Title);tick(PAD_START,0);
 assert(sound_counts[MenuSound_Confirm]==1);
 for(int i=0;i<90;i++)tick(0,0);
 assert(menu.page==MenuPage_Title && menu.next_page==MenuPage_Title);
 for(int i=0;i<40;i++)tick(0,0);
 assert(menu.page==MenuPage_Main);
 reset(MenuPage_Title);tick(PAD_CROSS,0);tick(PAD_START,0);tick(0,0);
 assert(menu.page==MenuPage_Main);
 reset(MenuPage_Main);int scrolls=sound_counts[MenuSound_Scroll];tick(PAD_UP,0);assert(menu.select==4);tick(PAD_DOWN,0);assert(menu.select==0);
 assert(sound_counts[MenuSound_Scroll]==scrolls+2);
 MenuPage pages[]={MenuPage_Story,MenuPage_Freeplay,MenuPage_Merch,MenuPage_Options,MenuPage_Credits};
 for (int i=0;i<5;i++) {
  reset(MenuPage_Main);menu.select=i;tick(PAD_CROSS,0);
  for(int j=0;j<50;j++)tick(PAD_DOWN|PAD_CROSS,0);
  assert(menu.page==MenuPage_Main && menu.select==i);
  for(int j=0;j<40;j++)tick(0,0);
  assert(menu.page==pages[i]);
  if(menu.page==MenuPage_Freeplay)for(int j=0;j<60;j++)tick(0,0);
  tick(PAD_CIRCLE,0);tick(0,0);assert(menu.page==MenuPage_Main && menu.select==i);
 }
 reset(MenuPage_Story);tick(PAD_UP,0);assert(menu.select==8);tick(PAD_START,0);tick(0,0);
 assert(played==1 && freed>=1 && played_id==StageId_8_1 && played_story);
 reset(MenuPage_Freeplay);menu.select=2;menu.difficulty=StageDiff_Nightmare;
 for(int j=0;j<60;j++)tick(0,0);
 tick(PAD_UP|PAD_START,0);
 for(int j=0;j<45;j++)tick(PAD_DOWN|PAD_START,0);
 assert(played==1 && menu.select==1);
 for(int j=0;j<40;j++)tick(0,0);
 assert(played==2 && played_id==StageId_1_4 && played_diff==StageDiff_Normal && !played_story);
 reset(MenuPage_Freeplay);int loaded=freeplay_loads;
 for(int j=0;j<60;j++)tick(0,0);
 for(int j=0;j<100;j++)tick(PAD_DOWN|PAD_RIGHT,0);
 assert(freeplay_loads==loaded && art_owner==2);
 reset(MenuPage_Freeplay);
 for(int j=0;j<60;j++)tick(0,0);
 tick(PAD_DOWN,PAD_DOWN);assert(menu.select==1);
 for(int j=0;j<15;j++)tick(0,PAD_DOWN);
 assert(menu.select==1);
 for(int j=0;j<45;j++)tick(0,PAD_DOWN);
 assert(menu.select>1);
 int stopped=menu.select;
 for(int j=0;j<60;j++)tick(0,0);
 assert(menu.select==stopped);
 reset(MenuPage_Freeplay);
 for(int j=0;j<60;j++)tick(0,0);
 tick(PAD_L1,0); // Empty favourites: Random must not launch another song.
 int before_empty=played;
 tick(PAD_START,0);for(int j=0;j<85;j++)tick(0,0);
 assert(played==before_empty && menu.page==MenuPage_Freeplay);
 tick(PAD_R1,0);tick(PAD_DOWN,0);tick(PAD_SQUARE,0);
 tick(PAD_L1,0);assert(menu.select==1);
 tick(PAD_START,0);for(int j=0;j<85;j++)tick(0,0);
 assert(played==before_empty+1 && played_id==StageId_1_4);
 reset(MenuPage_Freeplay);
 for(int j=0;j<60;j++)tick(0,0);
 tick(PAD_L1,0);tick(PAD_L1,0);tick(PAD_DOWN,0);tick(PAD_START,0);
 for(int j=0;j<85;j++)tick(0,0);
 assert(played_id==StageId_8_3); // Official name "2hot" belongs in #.
 reset(MenuPage_Freeplay);menu.difficulty=StageDiff_Nightmare;
 for(int j=0;j<60;j++)tick(0,0);
 tick(PAD_START,0);for(int j=0;j<85;j++)tick(0,0);
 assert(played==5 && played_id==StageId_1_1 && played_diff==StageDiff_Nightmare);
 reset(MenuPage_Options);boolean before=stage.expsync;tick(PAD_RIGHT,0);assert(stage.expsync!=before);
 reset(MenuPage_Credits);for(int i=0;i<400;i++)tick(PAD_RIGHT,0);
 assert(menu.credits_scroll==FIXED_DEC((262-13)*12,1));
 for(int i=0;i<400;i++)tick(PAD_LEFT,0);assert(menu.credits_scroll==0);
 for(int page=MenuPage_Title;page<=MenuPage_Credits;page++) {reset(page);for(int i=0;i<35;i++)tick(PAD_DOWN,0);}
 assert(reads==0);return 0;
}
'''
  with tempfile.TemporaryDirectory() as td:
   path=Path(td);(path/'stubs.h').write_text(stub)
   for name in re.findall(r'#include "([^"]+)"',source):
    if name=='menu.h':shutil.copy2(ROOT/'overlay/src/menu.h',path/name)
    elif name=='menu_intro_generated.h':(path/name).write_text('static const char *const funny_messages[][2]={{"FUNKIN","FOREVER"}};')
    else:(path/name).write_text('#include "stubs.h"\n')
   (path/'menu.c').write_text(source);(path/'test.c').write_text(harness)
   compile=subprocess.run([cc,'-std=c99','-Wall','-Werror','-Wno-misleading-indentation','-fsanitize=undefined,address','-fno-omit-frame-pointer',str(path/'test.c'),'-o',str(path/'test')],capture_output=True,text=True)
   self.assertEqual(compile.returncode,0,compile.stderr)
   # This harness performs no heap allocation; leak scanning needs /proc
   # permissions that are not available in some managed build environments.
   run=subprocess.run([str(path/'test')],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
   self.assertEqual(run.returncode,0,run.stderr)
if __name__=='__main__':unittest.main()
