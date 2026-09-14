#include "freeplay_music.h"
#include "audio.h"
#include "io.h"
#include "freeplay_music_generated.h"
static CdlFILE files[COUNT_OF(fp_music_files)];
static int current,wanted;
static fixed_t settle;
void FreeplayMusic_Load(void)
{
    for(unsigned int i=0;i<COUNT_OF(files);i++)IO_FindFile(&files[i],fp_music_files[i]);
    current=wanted=-1;settle=0;
}
void FreeplayMusic_Tick(int song,int difficulty,fixed_t dt,int enabled)
{
    if(!enabled) {
        if(current>=0)Audio_StopXA();
        current=wanted=-1;settle=0;return;
    }
    int route=song<0 ? FP_MUSIC_RANDOM : fp_music_map[song][difficulty>=3];
    if(route!=wanted) {wanted=route;settle=0;}
    settle+=dt;if(settle>205)settle=205;
    if(settle<205)return;
    if(current!=wanted || !Audio_PlayingXA()) {
        CdlFILE file=files[fp_music_routes[wanted].file];
        file.size=fp_music_routes[wanted].sectors*IO_SECT_SIZE;
        Audio_StopXA();
        Audio_PlayXA_File(&file,89,fp_music_routes[wanted].channel,0);
        current=wanted;
    }
}
