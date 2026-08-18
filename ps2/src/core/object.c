#include "object.h"
#include "mem.h"

void ObjectList_Add(ObjectList *list, Object *obj)
{
    obj->prev = NULL;
    if ((obj->next = *list) != NULL)
        (*list)->prev = obj;
    *list = obj;
}

void ObjectList_Remove(ObjectList *list, Object *obj)
{
    if (obj->prev != NULL)
        obj->prev->next = obj->next;
    else
        *list = obj->next;

    if (obj->next != NULL)
        obj->next->prev = obj->prev;

    if (obj->free != NULL)
        obj->free(obj);
    Mem_Free(obj);
}

void ObjectList_Tick(ObjectList *list)
{
    Object *obj = *list;
    while (obj != NULL) {
        Object *next = obj->next;
        if (obj->tick != NULL && obj->tick(obj))
            ObjectList_Remove(list, obj);
        obj = next;
    }
}

void ObjectList_Free(ObjectList *list)
{
    Object *obj = *list;
    while (obj != NULL) {
        Object *next = obj->next;
        if (obj->free != NULL)
            obj->free(obj);
        Mem_Free(obj);
        obj = next;
    }
    *list = NULL;
}
