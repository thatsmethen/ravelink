// Generated PCM only. No HAL device registration or hardware IO.
#include "RaveLinkRealtime.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>

static long faults(void) {
    struct rusage value = {0};
    if (getrusage(RUSAGE_SELF, &value)) exit(2);
    return value.ru_minflt;
}
int main(void) {
    enum { frames = 16384, sources = 64, buses = 4 };
    float *output = malloc(frames * 2 * sizeof(float));
    float *input = malloc(frames * 2 * sizeof(float));
    if (!output || !input) return 3;
    for (unsigned i = 0; i < frames * 2; i++) { output[i] = 0.75f; input[i] = 0.125f; }
    // Resolve arithmetic routines before measuring buffer first-use faults.
    RLDSP *warm = rl_dsp_create(48000);
    if (!warm) return 4;
    rl_dsp_process(warm, input, frames); rl_dsp_destroy(warm);
    AudioBufferList out = {1, {2, frames * 2 * sizeof(float), output}};
    AudioBufferList in = {1, {2, frames * 2 * sizeof(float), input}};
    long before = faults();
    RLRender *render = rl_render_create(48000, frames, sources, buses);
    RLRing *ring = rl_ring_create(65536);
    RLCapture *capture = rl_capture_create(48000, 0, frames, 1);
    if (!render || !ring || !capture) return 5;
    rl_capture_set_destination(capture, 0, ring);
    long prepared = faults();
    rl_capture_callback(0, NULL, &in, NULL, NULL, NULL, capture);
    rl_render_callback(0, NULL, NULL, NULL, &out, NULL, render);
    long first = faults();
    rl_capture_callback(0, NULL, &in, NULL, NULL, NULL, capture);
    rl_render_callback(0, NULL, NULL, NULL, &out, NULL, render);
    long second = faults();
    unsigned invalid = 0;
    for (unsigned i = 0; i < frames * 2; i++) if (!isfinite(output[i]) || output[i] != 0) invalid++;
    printf("{\"preparationMinorFaults\":%ld,\"firstCallbackMinorFaults\":%ld,\"secondCallbackMinorFaults\":%ld,\"nonzeroOrNonfiniteSilentOutputSamples\":%u}\n",
           prepared-before, first-prepared, second-first, invalid);
    rl_capture_destroy(capture); rl_ring_destroy(ring); rl_render_destroy(render);
    free(output); free(input); return invalid ? 6 : 0;
}
