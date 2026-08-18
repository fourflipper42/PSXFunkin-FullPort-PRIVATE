#ifndef FNF_PS2_OBJECT_H
#define FNF_PS2_OBJECT_H

#include "psx.h"

typedef struct Object {
    struct Object *prev;
    struct Object *next;
    boolean (*tick)(struct Object *);
    void (*free)(struct Object *);
} Object;

typedef Object *ObjectList;

void ObjectList_Add(ObjectList *list, Object *obj);
void ObjectList_Remove(ObjectList *list, Object *obj);
void ObjectList_Tick(ObjectList *list);
void ObjectList_Free(ObjectList *list);

#endif
