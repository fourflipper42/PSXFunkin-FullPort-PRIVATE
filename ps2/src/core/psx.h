#ifndef FNF_PS2_COMPAT_PSX_H
#define FNF_PS2_COMPAT_PSX_H

/*
 * Compatibility surface for portable PSXFunkin gameplay code.
 * This intentionally keeps the old type/macro names so core files can move
 * over with tiny diffs while all PS1 hardware APIs stay out of the PS2 build.
 */
#include <tamtypes.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

typedef s8 boolean;

#ifndef true
#define true 1
#endif
#ifndef false
#define false 0
#endif

typedef struct POINT {
    s16 x;
    s16 y;
} POINT;

#define sizeof_member(type, member) sizeof(((type *)0)->member)
#define COUNT_OF(x) (sizeof(x) / sizeof(0[x]))
#define COUNT_OF_MEMBER(type, member) \
    (sizeof_member(type, member) / sizeof_member(type, member[0]))

#endif
