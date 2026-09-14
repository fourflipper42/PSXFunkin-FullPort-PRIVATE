#include "freeplay_results.h"
static struct {unsigned int score; unsigned char completion, played;} records[32][5];
static unsigned int total, hits, good, ghost_misses;
static int Valid(int stage,int difficulty) {return stage>=0 && stage<32 && difficulty>=0 && difficulty<5;}
void FreeplayResults_Begin(unsigned int notes) {total=notes;hits=good=ghost_misses=0;}
void FreeplayResults_Hit(unsigned int grade) {if(hits<total) {hits++;if(grade<2)good++;}}
void FreeplayResults_GhostMiss(void) {if(ghost_misses<65535)ghost_misses++;}
void FreeplayResults_Finish(int stage,int difficulty,int score)
{
    unsigned int missed=total-hits+ghost_misses;
    unsigned int completion=total && good>missed ? (good-missed)*100/total : 0;
    if(!Valid(stage,difficulty) || !total)return;
    if(score<0)score=0;
    if(score>9999999)score=9999999;
    if(!records[stage][difficulty].played || (unsigned int)score>records[stage][difficulty].score) {
        records[stage][difficulty].score=score;
        records[stage][difficulty].completion=completion;
        records[stage][difficulty].played=1;
    }
    total=hits=good=ghost_misses=0;
}
unsigned int FreeplayResults_Score(int stage,int difficulty) {return Valid(stage,difficulty) ? records[stage][difficulty].score : 0;}
unsigned int FreeplayResults_Completion(int stage,int difficulty) {return Valid(stage,difficulty) ? records[stage][difficulty].completion : 0;}
