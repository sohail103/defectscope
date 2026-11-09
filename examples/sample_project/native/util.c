#include <stdio.h>
#include <stdlib.h>
#include "util.h"

/* Clamp a value */
int clamp(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

char *copy_buf(const char *src, int n) {
    char *p = malloc(n + 1);
    int i = 0;
    while (i < n && src[i] != '\0') {
        p[i] = src[i];
        i++;
    }
    p[i] = '\0';
    switch (n) {
        case 1: break;
        case 2: break;
        default: break;
    }
    return p;
}
