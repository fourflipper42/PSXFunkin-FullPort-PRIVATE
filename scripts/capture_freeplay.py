"""Record the real C Freeplay renderer's graphics calls; not GPU emulation."""
import json,re,shutil,subprocess,tempfile
from pathlib import Path
STUB=r'''
#ifndef STUB_H
#define STUB_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <assert.h>
typedef unsigned char u8; typedef signed char s8; typedef unsigned short u16; typedef int fixed_t;
#define FIXED_SHIFT 10
#define COUNT_OF(a) (sizeof(a)/sizeof((a)[0]))
#define GFX_LOADTEX_FREE 1
typedef struct {int x,y,w,h;} RECT;
typedef struct {char name[64];} Gfx_Tex;
typedef struct {struct {unsigned int width,height,frames;} info;char name[64];} FrameBank;
static int recording;
static const char *Name(const char *path) {
 static char name[64];int i=0;const char *p=strrchr(path,'\\');p=p?p+1:path;
 while(*p && *p!=';' && i<63)name[i++]=tolower((unsigned char)*p++);
 name[i]=0;return name;
}
static void *IO_Read(const char *path) {return (void*)Name(path);}
static void Gfx_LoadTex(Gfx_Tex *t,void *data,int flags) {snprintf(t->name,64,"%s",(char*)data);}
static void FrameBank_Load(FrameBank *b,const char *path,int x,int y,int cx,int cy) {
 unsigned char h[16];char file[1024];snprintf(b->name,64,"%s",Name(path));
 snprintf(file,sizeof(file),"%s/%s",ASSET_ROOT,b->name);FILE *f=fopen(file,"rb");assert(f);
 assert(fread(h,1,16,f)==16);fclose(f);
 b->info.width=h[8]|(h[9]<<8);b->info.height=h[10]|(h[11]<<8);b->info.frames=h[12]|(h[13]<<8);
 assert(!(x&63) && (y&255)+b->info.height<=256 && x+b->info.width/2<=1024 && y+b->info.height<=512);
}
static void FrameBank_Free(FrameBank *b) {}
static void FrameBank_Draw(FrameBank *b,unsigned int frame,int x,int y) {
 assert(frame<b->info.frames);if(recording)printf("B %s %u %d %d\n",b->name,frame,x,y);
}
static void Gfx_BlitTexCol(Gfx_Tex *t,RECT *s,int x,int y,int r,int g,int b) {
 if(recording)printf("T %s %d %d %d %d %d %d %d %d %d\n",t->name,x,y,s->x,s->y,s->w,s->h,r,g,b);
}
static void Gfx_BlitTex(Gfx_Tex *t,RECT *s,int x,int y) {Gfx_BlitTexCol(t,s,x,y,128,128,128);}
#endif
'''

class Capture:
    def __init__(self,upstream):
        self.temp=tempfile.TemporaryDirectory();p=Path(self.temp.name)
        repo=Path(__file__).resolve().parents[1]
        for name in ('freeplay_art.c','freeplay_art.h'):shutil.copy2(repo/'overlay/src'/name,p/name)
        shutil.copy2(upstream/'src/freeplay_art_generated.h',p/'freeplay_art_generated.h')
        (p/'stubs.h').write_text('#define ASSET_ROOT '+json.dumps(str((upstream/'iso/freeplay').resolve()))+'\n'+STUB)
        for name in ('fixed.h','framebank.h'):(p/name).write_text('#include "stubs.h"\n')
        source=re.sub(r'//[^\n]*','',(repo/'overlay/src/menu.c').read_text())
        names=['Random']+re.findall(r'\{StageId_\d_\d,\s*"([^"]+)"\}',source)
        (p/'capture.c').write_text('#include "freeplay_art.c"\nstatic const char *names[]={'+','.join(json.dumps(s) for s in names)+r'''};
int main(int argc,char **argv) {
 assert(argc>=4);int selection=atoi(argv[1]);fixed_t time=atoi(argv[2]);fixed_t confirm=atoi(argv[3]);
 int diff=argc>4?atoi(argv[4]):1, direction=argc>5?atoi(argv[5]):0;
 int score=argc>6?atoi(argv[6]):0,completion=argc>7?atoi(argv[7]):0;
 int filter=argc>8?atoi(argv[8]):2,favorites=argc>9?atoi(argv[9]):0;
 FreeplayArt_Load();
 FreeplayArt_State(selection-1,filter,favorites,0,0);FreeplayArt_UI(diff,0);
 recording=1;
 FreeplayArt_State(selection-1,filter,favorites,direction,time);
 FreeplayArt_Results(score,completion);
 FreeplayArt_UI(diff,time);
 for(int i=0;i<COUNT_OF(names);i++)FreeplayArt_Song(names[i],i-1,i==selection,(i-selection)*1024,time,confirm);
 FreeplayArt_Back(diff,time,confirm>=0,confirm);FreeplayArt_Free();return 0;
}
''')
        self.exe=p/'capture'
        subprocess.run(['cc','-std=c99','-Wall','-Werror',str(p/'capture.c'),'-o',str(self.exe)],check=True)
    def commands(self,selection,time,confirm=-1,diff=1,direction=0,score=0,completion=0,filter=2,favorites=0):
        result=subprocess.run([str(self.exe),*map(str,(selection,time,confirm,diff,direction,score,completion,filter,favorites))],check=True,capture_output=True,text=True)
        return [line.split() for line in result.stdout.splitlines()]
    def close(self):self.temp.cleanup()
