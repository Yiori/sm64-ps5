// A few libc functions the console's libc.prx does not export, each trivial to
// build on ones it does (vsnprintf, sinf, cosf).
// Compiled with -fno-builtin: otherwise the compiler turns sinf + cosf back
// into a call to sincosf, and sincosf calls itself forever.

#include <stdio.h>
#include <stdarg.h>
#include <math.h>
#include <stddef.h>
#include <stdlib.h>

int sprintf(char *str, const char *format, ...) {
    va_list args;
    va_start(args, format);
    int ret = vsnprintf(str, 0x7FFFFFFF, format, args);
    va_end(args);
    return ret;
}

void sincosf(float x, float *s, float *c) {
    *s = sinf(x);
    *c = cosf(x);
}

// The BSD libc's assert() expands to __assert(func, file, line, expr), not
// glibc's __assert_fail.
void __assert(const char *func, const char *file, int line, const char *expr) {
    (void)func; (void)file; (void)line; (void)expr;
    abort();
}

// Configure PlayStation 5 Libc Heap for dynamic allocation (512 MB initial heap, expandable)
size_t sceLibcHeapSize = 512 * 1024 * 1024;
unsigned int sceLibcHeapExtendedAlloc = 1;

extern int sceKernelMkdir(const char *path, unsigned int mode);
extern int sceKernelUnlink(const char *path);
extern int sceKernelMprotect(const void *addr, size_t len, int prot);
extern int sceKernelStat(const char *path, void *sb);
extern int sceKernelClockGettime(int clock_id, void *tp);

int mkdir(const char *path, unsigned int mode) {
    return sceKernelMkdir(path, mode);
}

int unlink(const char *path) {
    return sceKernelUnlink(path);
}

int mprotect(void *addr, size_t len, int prot) {
    // On PS5, memory accessible to GPU must retain GPU permissions.
    // SCE_KERNEL_PROT_CPU_READ  = 0x01
    // SCE_KERNEL_PROT_CPU_WRITE = 0x02
    // SCE_KERNEL_PROT_GPU_READ  = 0x10
    // SCE_KERNEL_PROT_GPU_WRITE = 0x20
    int ps5_prot = prot;
    if (prot & 0x01) ps5_prot |= 0x10; // Add PROT_GPU_READ
    if (prot & 0x02) ps5_prot |= 0x20; // Add PROT_GPU_WRITE
    return sceKernelMprotect(addr, len, ps5_prot);
}

int stat(const char *path, void *sb) {
    return sceKernelStat(path, sb);
}

int clock_gettime(int clock_id, void *tp) {
    return sceKernelClockGettime(clock_id, tp);
}
