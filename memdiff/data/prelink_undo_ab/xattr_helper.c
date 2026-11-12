#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/xattr.h>

static void hex(const unsigned char *p, size_t n) {
  for (size_t i = 0; i < n; i++) printf("%02x", p[i]);
}

static int dump(const char *path) {
  ssize_t len = llistxattr(path, NULL, 0);
  if (len < 0) { perror("llistxattr"); return 1; }
  char *names = calloc((size_t)len + 1, 1);
  if (!names) return 2;
  if (llistxattr(path, names, (size_t)len) != len) { perror("llistxattr"); free(names); return 1; }
  for (char *name = names; name < names + len; name += strlen(name) + 1) {
    ssize_t n = lgetxattr(path, name, NULL, 0);
    if (n < 0) { perror("lgetxattr"); free(names); return 1; }
    unsigned char *value = malloc((size_t)n + 1);
    if (!value) { free(names); return 2; }
    if (lgetxattr(path, name, value, (size_t)n) != n) { perror("lgetxattr"); free(value); free(names); return 1; }
    printf("%s\t", name); hex(value, (size_t)n); putchar('\n');
    free(value);
  }
  free(names);
  return 0;
}

static int restore(const char *path, const char *manifest) {
  FILE *f = fopen(manifest, "r");
  if (!f) { perror("fopen"); return 1; }
  char *line = NULL; size_t cap = 0; ssize_t n;
  while ((n = getline(&line, &cap, f)) != -1) {
    char *tab = strchr(line, '\t');
    if (!tab) { fprintf(stderr, "bad manifest line\n"); free(line); fclose(f); return 1; }
    *tab++ = 0;
    char *end = strchr(tab, '\n'); if (end) *end = 0;
    size_t hlen = strlen(tab);
    if (hlen % 2) { fprintf(stderr, "odd hex length\n"); free(line); fclose(f); return 1; }
    unsigned char *value = malloc(hlen / 2 + 1);
    if (!value) { free(line); fclose(f); return 2; }
    for (size_t i = 0; i < hlen / 2; i++) {
      unsigned int byte;
      if (sscanf(tab + i * 2, "%2x", &byte) != 1) { fprintf(stderr, "bad hex\n"); free(value); free(line); fclose(f); return 1; }
      value[i] = (unsigned char)byte;
    }
    if (lsetxattr(path, line, value, hlen / 2, 0)) { perror("lsetxattr"); free(value); free(line); fclose(f); return 1; }
    free(value);
  }
  free(line);
  if (ferror(f)) { perror("getline"); fclose(f); return 1; }
  fclose(f);
  return 0;
}

int main(int argc, char **argv) {
  if (argc == 3 && !strcmp(argv[1], "dump")) return dump(argv[2]);
  if (argc == 4 && !strcmp(argv[1], "restore")) return restore(argv[2], argv[3]);
  fprintf(stderr, "usage: xattr_helper dump PATH | restore PATH MANIFEST\n");
  return 2;
}
