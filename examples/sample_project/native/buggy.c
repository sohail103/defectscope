#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Deliberately defective code used to demonstrate static-analysis findings. */

int deref_null(int *p) {
    if (p == NULL) {
        return *p;
    }
    return *p + 1;
}

void leak_memory(int n) {
    char *buf = malloc(n);
    if (n > 10) {
        return;
    }
    free(buf);
}

int out_of_bounds(void) {
    int table[4];
    int i;
    for (i = 0; i <= 4; i++) {
        table[i] = i;
    }
    return table[4];
}

int uninitialised(int flag) {
    int value;
    if (flag) {
        value = 1;
    }
    return value;
}
