"""Exercise the native uploader's VRAM coordinates, not a replacement renderer."""
import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/ps1asset'))
from framebank import pack_indices

class BankUpload(unittest.TestCase):
 def test_subpage_upload_and_draw_address_the_same_pixels(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)
   for name in ('framebank.c','framebank.h','framecodec.c','framecodec.h'):shutil.copy2(ROOT/'overlay/src'/name,p/name)
   (p/'test.fbk').write_bytes(pack_indices(28,28,[0]*256,[bytes([9])*784,bytes([17])*784]))
   stub=r'''
#ifndef STUB_H
#define STUB_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned int u32;typedef short s16;
typedef void *IO_Data;typedef struct {unsigned int size;} CdlFILE;
typedef struct {int x,y,w,h;} RECT;typedef struct {int x,y;} Gfx_Tex;
static unsigned char vram[512][2048];static char error_msg[256];static int expected;
static unsigned int U16(const unsigned char *p) {return p[0]|p[1]<<8;}
static void ErrorLock(void) {exit(3);}
static void IO_FindFile(CdlFILE *f,const char *path) {FILE *p=fopen(path,"rb");assert(p);fseek(p,0,SEEK_END);f->size=ftell(p);fclose(p);}
static void *IO_ReadFile(CdlFILE *f) {void *data=malloc(f->size);FILE *p=fopen("test.fbk","rb");assert(fread(data,1,f->size,p)==f->size);fclose(p);return data;}
static void Mem_Free(void *p) {free(p);}
static void Gfx_LoadTex(Gfx_Tex *tex,void *data,int flags) {
 unsigned char *b=data;int x=U16(b+536),y=U16(b+538),w=U16(b+540)*2,h=U16(b+542);
 tex->x=x&~63;tex->y=y&~255;
 for(int row=0;row<h;row++)memcpy(&vram[y+row][x*2],b+544+row*w,w);
}
static void Gfx_BlitTex(Gfx_Tex *tex,RECT *r,int x,int y) {
 assert(x==163 && y==29 && r->w==28 && r->h==28);
 for(int row=0;row<r->h;row++)for(int col=0;col<r->w;col++)
  assert(vram[tex->y+r->y+row][tex->x*2+r->x+col]==expected);
 assert(vram[111][1664]==0 && vram[140][1664]==0);
}
#endif
'''
   (p/'gfx.h').write_text(stub)
   for name in ('mem.h','main.h'):(p/name).write_text('#include "gfx.h"\n')
   (p/'test.c').write_text('#include "framebank.c"\nint main(int argc,char **argv) {FrameBank b;FrameBank_Load(&b,"test.fbk",832,argc>1?240:112,0,491);expected=9;FrameBank_Draw(&b,0,163,29);expected=17;FrameBank_Draw(&b,1,163,29);FrameBank_Free(&b);return 0;}')
   subprocess.run(['cc','-std=c99',str(p/'test.c'),str(p/'framecodec.c'),'-o',str(p/'test')],check=True)
   run=subprocess.run([str(p/'test')],cwd=p,capture_output=True,text=True)
   self.assertEqual(run.returncode,0,run.stderr)
   run=subprocess.run([str(p/'test'),'cross-page'],cwd=p)
   self.assertEqual(run.returncode,3,'a bank must not wrap UV coordinates across a texture page')
