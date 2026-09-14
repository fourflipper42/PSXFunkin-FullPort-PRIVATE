#ifndef FREEPLAY_RESULTS_H
#define FREEPLAY_RESULTS_H
/* Session records. They survive gameplay/menu changes, not a power cycle. */
void FreeplayResults_Begin(unsigned int notes);
void FreeplayResults_Hit(unsigned int grade);
void FreeplayResults_GhostMiss(void);
void FreeplayResults_Finish(int stage, int difficulty, int score);
unsigned int FreeplayResults_Score(int stage, int difficulty);
unsigned int FreeplayResults_Completion(int stage, int difficulty);
#endif
