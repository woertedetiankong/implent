/* bearings_run.h: record one real run of a route from a C program, for the bearings map.
 *
 * A route on the parts list says in words how one thing travels through the project. This header measures
 * that journey once: which of the functions you name were called, in what order and how deep, where each is
 * defined, and the values you read out as each one starts and ends. It writes the same file as
 * bearings_run.py does for Python (docs/runs/<name>.json; `bearings.py --help` gives its shape), which
 * `bearings.py web` shows under the route and `bearings.py doctor` compares with it.
 *
 * The project's own source is not changed. Compile it with -finstrument-functions -g, which makes the
 * compiler call a hook as every function starts and ends, and link a small harness of your own:
 *
 *     #define BEARINGS_RUN_IMPLEMENTATION      // in exactly one file, compiled WITHOUT -finstrument-functions
 *     #include "bearings_run.h"
 *
 *     static void at_current_loop(int leaving) {          // runs as the function starts (0) and ends (1)
 *         if (!leaving) br_floats("iabc_now_A", axis.iabc_now_A, 3);     // what went in
 *         else          br_floats("uabc_tar_V", axis.uabc_tar_V, 3);     // what came out
 *     }
 *
 *     br_open("One control period", "simulator, mid-move", "/path/to/repo");
 *     BR_WATCH(CurrentLoopCtrl, "Motor control loop", at_current_loop);  // function, box of the route, probe
 *     BR_WATCH(bsp_set_phase_voltage, "Simulated driver", NULL);         // no probe: the call alone is noted
 *     ...run the program up to the moment worth recording...
 *     br_arm();   tick();   br_disarm();                                 // only this stretch is recorded
 *     br_save("/path/to/repo/docs/runs/one-control-period.json");
 *
 * Only functions the harness can name can be watched, so not `static` ones. A watched function called in
 * a loop makes a step each time: arm for one pass, not for a thousand. At most 200 steps are kept.
 *
 * Where each function is defined is looked up from the debug information when the run is saved. That is
 * done with `atos` and works on macOS only; elsewhere the steps are written without a place. On macOS the
 * debug information stays in the object files until `dsymutil` gathers it, so compile to .o files, link,
 * then run `dsymutil <program>`; compiling and linking in one command throws the objects away and leaves
 * no places. The line noted is where the function's body opens, which is the line after its signature when
 * the brace stands on a line of its own.
 * Times are the host's clock. For firmware run on a desktop they say nothing about the target, so they
 * are left out unless br_host_time(1) asks for them.
 *
 * The file holds real values from a real run: read it before committing it or sharing the map.
 * C99, no dependencies beyond the C library.
 */
#ifndef BEARINGS_RUN_H
#define BEARINGS_RUN_H

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*br_probe)(int leaving);

void br_open(const char *route, const char *name, const char *root); /* root: the repository; places are written relative to it */
void br_watch(void *fn, const char *fn_name, const char *box, br_probe probe);
#define BR_WATCH(fn, box, probe) br_watch((void *)(fn), #fn, (box), (probe))
void br_arm(void);                 /* start recording calls of the watched functions */
void br_disarm(void);              /* stop; steps still open are closed as their functions return */
void br_host_time(int on);         /* note how long each step took on this machine (off by default) */
void br_command(const char *text); /* how the run was started, for the record */
/* Inside a probe: note a value of the step that is starting (what went in) or ending (what came out). */
void br_num(const char *name, double value);
void br_int(const char *name, long long value);
void br_text(const char *name, const char *value);
void br_floats(const char *name, const float *values, int n);
void br_note(const char *text);
int br_save(const char *path);     /* write the run; 0 on success */

#ifdef __cplusplus
}
#endif

#ifdef BEARINGS_RUN_IMPLEMENTATION

#include <limits.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define BR_NOI __attribute__((no_instrument_function))
#define BR_MAX_STEPS 200
#define BR_MAX_WATCH 128
#define BR_MAX_DEPTH 64
#define BR_HEAD 6 /* numbers kept from the start of a long array */
#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

typedef struct { char *s; size_t n, cap; } br_buf;
typedef struct { void *fn; const char *name, *box; br_probe probe; char file[PATH_MAX]; int line; } br_watched;
typedef struct { int watch, depth; double t0, ms; br_buf in, out, note; } br_step;

static struct {
    char route[256], name[256], command[512], root[PATH_MAX];
    br_watched watch[BR_MAX_WATCH];
    int n_watch;
    br_step steps[BR_MAX_STEPS];
    int n_steps, dropped;
    int stack[BR_MAX_DEPTH];      /* the open steps, innermost last; -1 for one that was not kept */
    void *stack_fn[BR_MAX_DEPTH];
    int depth, armed, busy, leaving, timed;
} br;

BR_NOI static void br_put(br_buf *b, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int need = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);
    if (need < 0) return;
    if (b->n + (size_t)need + 1 > b->cap) {
        size_t cap = (b->cap ? b->cap * 2 : 128) + (size_t)need;
        char *s = (char *)realloc(b->s, cap);
        if (!s) return;
        b->s = s;
        b->cap = cap;
    }
    va_start(ap, fmt);
    vsnprintf(b->s + b->n, b->cap - b->n, fmt, ap);
    va_end(ap);
    b->n += (size_t)need;
}

BR_NOI static void br_quote(br_buf *b, const char *text)
{
    br_put(b, "\"");
    for (const unsigned char *p = (const unsigned char *)(text ? text : ""); *p; p++) {
        if (*p == '"' || *p == '\\') br_put(b, "\\%c", *p);
        else if (*p < 0x20) br_put(b, "\\u%04x", *p);
        else br_put(b, "%c", *p);
    }
    br_put(b, "\"");
}

BR_NOI static void br_number(br_buf *b, double v)
{
    if (isfinite(v)) br_put(b, "%.6g", v);
    else br_put(b, isnan(v) ? "\"nan\"" : v > 0 ? "\"inf\"" : "\"-inf\"");
}

BR_NOI static double br_now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

/* The values of the step that is starting or ending: its "in" as it starts, its "out" as it ends. */
BR_NOI static br_buf *br_values(const char *name)
{
    if (!br.depth || br.stack[br.depth - 1] < 0) return NULL;
    br_step *s = &br.steps[br.stack[br.depth - 1]];
    br_buf *b = br.leaving ? &s->out : &s->in;
    if (b->n) br_put(b, ", ");
    br_quote(b, name);
    br_put(b, ": ");
    return b;
}

BR_NOI void br_num(const char *name, double value)
{
    br_buf *b = br_values(name);
    if (b) br_number(b, value);
}

BR_NOI void br_int(const char *name, long long value)
{
    br_buf *b = br_values(name);
    if (b) br_put(b, "%lld", value);
}

BR_NOI void br_text(const char *name, const char *value)
{
    br_buf *b = br_values(name);
    if (b) br_quote(b, value);
}

BR_NOI void br_floats(const char *name, const float *values, int n)
{
    br_buf *b = br_values(name);
    if (!b) return;
    int shown = n > BR_HEAD ? BR_HEAD : n;
    if (n > BR_HEAD) br_put(b, "\"%d \xC3\x97 ", n); /* "61 × [a, b, …]": a long array as its length and its start */
    br_put(b, "[");
    for (int i = 0; i < shown; i++) {
        if (i) br_put(b, ", ");
        if (n > BR_HEAD && !isfinite(values[i])) br_put(b, isnan(values[i]) ? "nan" : "inf");
        else br_number(b, values[i]);
    }
    br_put(b, n > BR_HEAD ? ", \xE2\x80\xA6]\"" : "]");
}

BR_NOI void br_note(const char *text)
{
    if (!br.depth || br.stack[br.depth - 1] < 0) return;
    br_buf *b = &br.steps[br.stack[br.depth - 1]].note;
    b->n = 0;
    br_quote(b, text);
}

BR_NOI void br_open(const char *route, const char *name, const char *root)
{
    memset(&br, 0, sizeof br);
    snprintf(br.route, sizeof br.route, "%s", route ? route : "");
    snprintf(br.name, sizeof br.name, "%s", name ? name : "");
    if (!root || !realpath(root, br.root)) br.root[0] = 0;
}

BR_NOI void br_watch(void *fn, const char *fn_name, const char *box, br_probe probe)
{
    if (br.n_watch == BR_MAX_WATCH) return;
    br_watched *w = &br.watch[br.n_watch++];
    w->fn = fn;
    w->name = fn_name;
    w->box = box;
    w->probe = probe;
}

BR_NOI void br_arm(void) { br.armed = 1; }
BR_NOI void br_disarm(void) { br.armed = 0; }
BR_NOI void br_host_time(int on) { br.timed = on; }
BR_NOI void br_command(const char *text) { snprintf(br.command, sizeof br.command, "%s", text ? text : ""); }

BR_NOI void __cyg_profile_func_enter(void *fn, void *site)
{
    (void)site;
    if (!br.armed || br.busy || br.depth == BR_MAX_DEPTH) return;
    int k = 0;
    while (k < br.n_watch && br.watch[k].fn != fn) k++;
    if (k == br.n_watch) return;
    int at = -1;
    if (br.n_steps < BR_MAX_STEPS) {
        at = br.n_steps++;
        br.steps[at].watch = k;
        br.steps[at].depth = br.depth;
        br.steps[at].ms = -1;
    } else {
        br.dropped++;
    }
    br.stack[br.depth] = at;
    br.stack_fn[br.depth++] = fn;
    if (at >= 0 && br.watch[k].probe) {
        br.busy = 1;
        br.leaving = 0;
        br.watch[k].probe(0);
        br.busy = 0;
    }
    if (at >= 0) br.steps[at].t0 = br_now();
}

BR_NOI void __cyg_profile_func_exit(void *fn, void *site)
{
    (void)site;
    if (br.busy || !br.depth || br.stack_fn[br.depth - 1] != fn) return;
    int at = br.stack[br.depth - 1];
    if (at >= 0) {
        br_step *s = &br.steps[at];
        if (br.timed) s->ms = br_now() - s->t0;
        if (br.watch[s->watch].probe) {
            br.busy = 1;
            br.leaving = 1;
            br.watch[s->watch].probe(1);
            br.busy = 0;
        }
    }
    br.depth--;
}

/* Where each watched function is defined, from the debug information. */
BR_NOI static void br_places(void)
{
#ifdef __APPLE__
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t size = sizeof exe;
    if (!br.n_watch || _NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real) || strchr(real, '\'')) return;
    br_buf cmd = {0};
    br_put(&cmd, "atos -o '%s' -l %p -fullPath", real, (void *)_dyld_get_image_header(0));
    for (int k = 0; k < br.n_watch; k++) br_put(&cmd, " %p", br.watch[k].fn);
    br_put(&cmd, " 2>/dev/null");
    FILE *p = popen(cmd.s, "r");
    free(cmd.s);
    if (!p) return;
    char line[PATH_MAX + 512];
    for (int k = 0; k < br.n_watch && fgets(line, sizeof line, p); k++) {
        /* "CurrentLoopCtrl (in sil) (/abs/path/motor_ctl_loop.c:179)" */
        char *open = strrchr(line, '('), *close = strrchr(line, ')'), *colon = strrchr(line, ':'), full[PATH_MAX];
        if (!open || !close || !colon || colon < open || colon > close || atoi(colon + 1) <= 0) continue;
        *colon = 0;
        size_t root = strlen(br.root);
        if (!root || !realpath(open + 1, full) || strncmp(full, br.root, root) != 0 || full[root] != '/') continue;
        snprintf(br.watch[k].file, sizeof br.watch[k].file, "%s", full + root + 1);
        br.watch[k].line = atoi(colon + 1);
    }
    pclose(p);
#endif
}

BR_NOI static void br_git(char *out, size_t size, const char *args)
{
    out[0] = 0;
    if (!br.root[0] || strchr(br.root, '\'')) return;
    br_buf cmd = {0};
    br_put(&cmd, "git -C '%s' %s 2>/dev/null", br.root, args);
    FILE *p = popen(cmd.s, "r");
    free(cmd.s);
    if (!p) return;
    if (fgets(out, (int)size, p)) out[strcspn(out, "\r\n")] = 0;
    pclose(p);
}

BR_NOI int br_save(const char *path)
{
    br.armed = 0;
    br_places();
    char commit[64], dirty[256], when[32];
    br_git(commit, sizeof commit, "rev-parse --short HEAD");
    br_git(dirty, sizeof dirty, "status --porcelain --untracked-files=no -- . ':(exclude)docs/runs'");
    time_t now = time(NULL);
    strftime(when, sizeof when, "%Y-%m-%dT%H:%M:%S", localtime(&now));
    br_buf b = {0};
    br_put(&b, "{\n \"route\": ");
    br_quote(&b, br.route);
    br_put(&b, ",\n \"name\": ");
    br_quote(&b, br.name);
    br_put(&b, ",\n \"recorded\": \"%s\",\n \"commit\": ", when);
    br_quote(&b, commit);
    br_put(&b, ",\n \"dirty\": %s,\n \"command\": ", dirty[0] ? "true" : "false");
    br_quote(&b, br.command);
    br_put(&b, ",\n \"dropped\": %d,\n \"steps\": [", br.dropped);
    for (int i = 0; i < br.n_steps; i++) {
        br_step *s = &br.steps[i];
        br_watched *w = &br.watch[s->watch];
        br_put(&b, "%s\n  {\"box\": ", i ? "," : "");
        br_quote(&b, w->box);
        br_put(&b, ", \"fn\": ");
        br_quote(&b, w->name);
        br_put(&b, ", \"file\": ");
        br_quote(&b, w->file);
        br_put(&b, ", \"line\": %d, \"depth\": %d, \"ms\": ", w->line, s->depth);
        if (s->ms >= 0) br_put(&b, "%.4f", s->ms);
        else br_put(&b, "null");
        br_put(&b, ",\n   \"in\": {%s},\n   \"out\": {%s}", s->in.s ? s->in.s : "", s->out.s ? s->out.s : "");
        if (s->note.n) br_put(&b, ",\n   \"note\": %s", s->note.s);
        br_put(&b, "}");
    }
    br_put(&b, "\n ]\n}\n");
    FILE *f = b.s ? fopen(path, "w") : NULL;
    if (!f) {
        free(b.s);
        return 1;
    }
    fwrite(b.s, 1, b.n, f);
    free(b.s);
    return fclose(f) ? 1 : 0;
}

#endif /* BEARINGS_RUN_IMPLEMENTATION */
#endif /* BEARINGS_RUN_H */
