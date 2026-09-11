"""Run the real STR playback loop against deterministic CD/MDEC stubs."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class MoviePlayback(unittest.TestCase):
 def test_final_frame_short_stream_skip_and_resolution(self):
  cc=shutil.which('cc')
  if not cc:self.skipTest('host C compiler unavailable')
  stub=r'''
#ifndef PSX_STUB_H
#define PSX_STUB_H
#include <stdio.h>
#include <stdint.h>
#include <assert.h>
typedef unsigned long u_long; typedef unsigned short u_short; typedef unsigned char u_char;
typedef struct {short x,y,w,h;} RECT;
typedef struct {RECT disp;int isrgb24;} DISPENV;
typedef struct {int sector;} CdlLOC;
typedef struct {CdlLOC pos;} CdlFILE;
typedef struct {int width,height,frameCount;} StHEADER;
#define WAIT_TIME 16
#define SECTOR_SIZE 512
#define PADstart 8
#define CdlPause 1
#define CdlModeSpeed 2
#define CdlSetloc 3
#define CdlSetmode 4
#define CdlModeStream 8
#define CdlModeRT 16
#define setRECT(r,a,b,c,d) (*(r)=(RECT){a,b,c,d})
int available,read_count,get_calls,displayed,decoded,skip_after,frame_width=16,change_width,clears,shutdowns;
u_long current_frame;
StHEADER packet;
void (*callback)(void);
void SetDispMask(int x) {}
int CdSearchFile(CdlFILE *f,const char *p) {return 1;}
void DecDCTReset(int n) {}
void DecDCToutCallback(void (*fn)(void)) {callback=fn;}
void StSetRing(u_long*p,int n) {}
void StSetStream(int a,int b,unsigned int c,int d,int e) {}
void DecDCTin(u_long*p,int mode) {decoded++;assert(*p==(u_long)decoded);}
void DecDCTout(u_long*p,int size) {assert(size>0);if(callback)callback();}
void SetDefDispEnv(DISPENV*p,int x,int y,int w,int h) {p->disp=(RECT){x,y,w,h};}
void PutDispEnv(DISPENV*p) {displayed++;}
void VSync(int n) {}
int PadRead(int n) {return skip_after && displayed>=skip_after ? PADstart:0;}
void StUnSetRing(void) {shutdowns++;}
int CdControlB(int a,int b,int c) {return 1;}
void LoadImage(RECT*r,u_long*p) {}
void DecDCTvlc(u_long*src,u_long*dst) {*dst=*src;}
void StFreeRing(u_long*p) {}
int StGetNext(u_long **p,u_long **header) {
 get_calls++;if(read_count>=available)return 1;
 current_frame=++read_count;
 packet=(StHEADER){change_width && read_count>1 ? 32:frame_width,16,read_count};
 *p=&current_frame;*header=(u_long*)&packet;return 0;
}
void ClearImage(RECT*r,int a,int b,int c) {clears++;}
int CdControl(int a,u_char*p,int c) {return 1;}
int CdRead2(int a) {return 1;}
#endif
'''
  harness=r'''
#include "strplay.c"
static int play(int frames,int present,int skip) {
 available=present;read_count=get_calls=displayed=decoded=0;skip_after=skip;
 STRFILE file={"TEST.STR",320,240,frames};
 return PlayStr(320,240,0,0,&file);
}
int main(void) {
 for(int n=1;n<=7;n++) {
  assert(play(n,n,0)==1);assert(displayed==n && decoded==n && read_count==n && get_calls==n);
 }
 assert(clears==7 && shutdowns==7);
 assert(play(4,2,0)==0);assert(displayed==2 && decoded==2 && get_calls<=2+WAIT_TIME);
 assert(play(4,4,1)==0);assert(displayed==1 && shutdowns==9);
 frame_width=321;assert(play(2,2,0)==0);assert(!decoded && !displayed);
 frame_width=16;change_width=1;assert(play(2,2,0)==0);assert(decoded==1 && displayed==1);
 assert(shutdowns==11);return 0;
}
'''
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'psx.h').write_text(stub);(p/'libpress.h').write_text('');(p/'test.c').write_text(harness)
   shutil.copy2(ROOT/'overlay/src/strplay.c',p/'strplay.c')
   result=subprocess.run([cc,'-std=c99','-Wall','-Werror','-fsanitize=address,undefined','-I'+str(p),str(p/'test.c'),'-o',str(p/'test')],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr)
   result=subprocess.run([str(p/'test')],text=True,capture_output=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
   self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
