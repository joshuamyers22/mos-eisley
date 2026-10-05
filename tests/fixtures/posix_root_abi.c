/* Synthetic ABI oracle: inspect only the descriptor explicitly inherited by tests. */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef __APPLE__
#include <sys/mount.h>
#include <sys/attr.h>
#include <sys/unistd.h>
#else
#include <sys/vfs.h>
#endif
int main(int argc, char **argv) {
    struct statfs info;
    if (argc != 2 || fstatfs(atoi(argv[1]), &info)) return 1;
    printf("%zu %zu %zu %llu\n", sizeof(info),
           offsetof(struct statfs, f_fsid), offsetof(struct statfs, f_flags),
           (unsigned long long)info.f_flags);
#ifdef __APPLE__
    printf("%zu %zu %d\n", sizeof(struct attrlist), sizeof(attrreference_t),
           _PC_EXTENDED_SECURITY_NP);
#endif
    return 0;
}
