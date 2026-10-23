#include "RaveLinkRealtime.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>

_Static_assert(ATOMIC_INT_LOCK_FREE == 2, "Realtime controls require lock-free atomics");
_Static_assert(ATOMIC_LLONG_LOCK_FREE == 2, "Realtime counters require lock-free atomics");
// Atomic float lock freedom is checked when the first graph object is allocated.
static bool atomics_supported(void) { _Atomic float f = 0; return atomic_is_lock_free(&f); }
static float db_gain(float db) { return powf(10.f, fmaxf(-120.f, fminf(db, 36.f)) / 20.f); }
static float finite_sample(float x) { return isfinite(x) ? x : 0.f; }
static void peak_store(_Atomic float *meter, float value) {
    float old = atomic_load_explicit(meter, memory_order_relaxed);
    while (value > old && !atomic_compare_exchange_weak_explicit(meter, &old, value,
            memory_order_relaxed, memory_order_relaxed)) {}
}
struct RLRing {
    float *data;
    float *kernel;
    uint32_t capacity, mask;
    _Atomic uint64_t write, read, dropped, underruns;
    double fraction;
    bool primed;
    double correction;
    double configuredRatio;
    uint32_t taps;
};
#define RL_PHASES 512
bool rl_ring_prepare_ratio(RLRing *r, double ratio) {
    if (!r || !isfinite(ratio) || ratio < 1.0 / 24 || ratio > 24) return false;
    uint32_t taps = 64 * (uint32_t)ceil(fmax(1, ratio));
    float *kernel = calloc((size_t)taps * RL_PHASES, sizeof(float));
    if (!kernel) return false;
    free(r->kernel); r->kernel = kernel; r->taps = taps;
    double cutoff = fmin(1, 1 / ratio) * .90;
    for (uint32_t phase = 0; phase < RL_PHASES; phase++) {
        double fraction = (double)phase / RL_PHASES, sum = 0;
        for (uint32_t t = 0; t < taps; t++) {
            double x = (double)t - (taps / 2 - 1) - fraction;
            double sinc = fabs(x) < 1e-9 ? cutoff : sin(M_PI * cutoff * x) / (M_PI * x);
            double window = .42 - .5 * cos(2 * M_PI * t / (taps - 1)) + .08 * cos(4 * M_PI * t / (taps - 1));
            r->kernel[phase * taps + t] = (float)(sinc * window); sum += sinc * window;
        }
        for (uint32_t t = 0; t < taps; t++) r->kernel[phase * taps + t] /= (float)sum;
    }
    r->configuredRatio = ratio; return true;
}
RLRing *rl_ring_create(uint32_t capacity) {
    if (!atomics_supported() || capacity < 4 || capacity > (1u << 25)) return NULL;
    uint32_t size = 4; while (size < capacity) size <<= 1;
    RLRing *r = calloc(1, sizeof(*r)); if (!r) return NULL;
    r->data = calloc((size_t)size * 2, sizeof(float));
    if (!r->data) { free(r); return NULL; }
    r->capacity = size; r->mask = size - 1;
    if (!rl_ring_prepare_ratio(r, 1)) { rl_ring_destroy(r); return NULL; }
    return r;
}
void rl_ring_destroy(RLRing *r) { if (r) { free(r->data); free(r->kernel); free(r); } }
uint32_t rl_ring_write(RLRing *r, const float *stereo, uint32_t frames) {
    if (!r || !stereo) return 0;
    uint64_t w = atomic_load_explicit(&r->write, memory_order_relaxed);
    uint64_t read = atomic_load_explicit(&r->read, memory_order_acquire);
    uint32_t count = (uint32_t)fmin((double)frames, (double)(r->capacity - (w - read)));
    for (uint32_t i = 0; i < count; i++) {
        uint32_t at = (uint32_t)(w + i) & r->mask;
        r->data[at * 2] = finite_sample(stereo[i * 2]);
        r->data[at * 2 + 1] = finite_sample(stereo[i * 2 + 1]);
    }
    atomic_store_explicit(&r->write, w + count, memory_order_release);
    atomic_fetch_add_explicit(&r->dropped, frames - count, memory_order_relaxed);
    return count;
}
uint32_t rl_ring_read(RLRing *r, float *stereo, uint32_t frames, double ratio) {
    if (!r || !stereo) return 0;
    if (!isfinite(ratio) || ratio < 1.0 / 24 || ratio > 24 || fabs(ratio - r->configuredRatio) > .000001) {
        memset(stereo, 0, (size_t)frames * 2 * sizeof(float)); return 0;
    }
    uint64_t rd = atomic_load_explicit(&r->read, memory_order_relaxed);
    uint64_t w = atomic_load_explicit(&r->write, memory_order_acquire);
    // A small elastic buffer absorbs independent device clocks. A bounded slowly
    // varying correction avoids periodic sample deletion and unbounded latency.
    double target = fmin(r->capacity - 1, fmax(r->taps + 16.0, frames * ratio * 2.0 + r->taps));
    if (!r->primed) {
        if ((double)(w - rd) < target) { memset(stereo, 0, frames * 2 * sizeof(float)); return 0; }
        r->primed = true;
    }
    double error = ((double)(w - rd) - target) / fmax(target, 1.0);
    r->correction = r->correction * .995 + fmax(-.003, fmin(.003, error * .0002)) * .005;
    double step = ratio * (1.0 + r->correction);
    uint32_t produced = 0;
    for (; produced < frames; produced++) {
        uint64_t whole = (uint64_t)r->fraction;
        if (rd + whole + r->taps >= w) break;
        float fraction = (float)(r->fraction - whole);
        uint32_t phase = (uint32_t)(fraction * RL_PHASES); if (phase >= RL_PHASES) phase = RL_PHASES - 1;
        float *kernel = r->kernel + phase * r->taps;
        for (uint32_t c = 0; c < 2; c++) {
            double value = 0;
            for (uint32_t tap = 0; tap < r->taps; tap++) value += r->data[(((uint32_t)(rd + whole) + tap) & r->mask) * 2 + c] * kernel[tap];
            stereo[produced * 2 + c] = (float)value;
        }
        r->fraction += step;
        uint64_t advance = (uint64_t)r->fraction;
        // Never publish a read cursor beyond the write cursor.
        if (advance > w - rd) advance = w - rd;
        rd += advance; r->fraction -= advance;
    }
    atomic_store_explicit(&r->read, rd, memory_order_release);
    if (produced < frames) {
        memset(stereo + produced * 2, 0, (frames - produced) * 2 * sizeof(float));
        atomic_fetch_add_explicit(&r->underruns, frames - produced, memory_order_relaxed);
        r->primed = false; r->fraction = 0;
    }
    return produced;
}
uint64_t rl_ring_dropped(RLRing *r) { return r ? atomic_load(&r->dropped) : 0; }
uint64_t rl_ring_underruns(RLRing *r) { return r ? atomic_load(&r->underruns) : 0; }

struct RLDSP {
    double sampleRate;
    _Atomic float gain, highpass, gate, threshold, ratio;
    float previousInput[2], previousOutput[2], envelope, smoothedGain, inputGain;
};
RLDSP *rl_dsp_create(double sampleRate) {
    if (!atomics_supported() || sampleRate < 8000 || !isfinite(sampleRate)) return NULL;
    RLDSP *d = calloc(1, sizeof(*d)); if (!d) return NULL;
    d->sampleRate = sampleRate; atomic_store(&d->gain, 1); atomic_store(&d->ratio, 1);
    atomic_store(&d->threshold, 1); atomic_store(&d->gate, 0); d->smoothedGain = 1; d->inputGain = 1;
    return d;
}
void rl_dsp_destroy(RLDSP *d) { free(d); }
void rl_dsp_controls(RLDSP *d, float gainDB, float highPassHz, float gateDB, float compressorDB, float ratio) {
    if (!d) return;
    atomic_store(&d->gain, db_gain(gainDB)); atomic_store(&d->highpass, fmaxf(0, fminf(highPassHz, 20000)));
    atomic_store(&d->gate, gateDB <= -80 ? 0 : db_gain(gateDB));
    atomic_store(&d->threshold, db_gain(compressorDB)); atomic_store(&d->ratio, fmaxf(1, fminf(ratio, 20)));
}
void rl_dsp_process(RLDSP *d, float *stereo, uint32_t frames) {
    if (!d) return;
    float gain = atomic_load(&d->gain), hp = atomic_load(&d->highpass), gate = atomic_load(&d->gate);
    float threshold = atomic_load(&d->threshold), ratio = atomic_load(&d->ratio);
    float alpha = hp > 0 ? (float)(1 / (1 + 2 * M_PI * hp / d->sampleRate)) : 0;
    float attack = (float)exp(-1 / (.005 * d->sampleRate)), release = (float)exp(-1 / (.100 * d->sampleRate));
    float smooth = (float)exp(-1 / (.005 * d->sampleRate));
    for (uint32_t i = 0; i < frames; i++) {
        d->inputGain = smooth * d->inputGain + (1 - smooth) * gain;
        float pair[2];
        for (int c = 0; c < 2; c++) {
            float x = finite_sample(stereo[i * 2 + c]) * d->inputGain;
            float y = hp > 0 ? alpha * (d->previousOutput[c] + x - d->previousInput[c]) : x;
            d->previousInput[c] = x; d->previousOutput[c] = y; pair[c] = y;
        }
        float level = fmaxf(fabsf(pair[0]), fabsf(pair[1]));
        float coefficient = level > d->envelope ? attack : release;
        d->envelope = coefficient * d->envelope + (1 - coefficient) * level;
        float target = 1;
        if (gate > 0 && d->envelope < gate) target = 0;
        else if (d->envelope > threshold && ratio > 1)
            target = powf(d->envelope / threshold, 1 / ratio - 1);
        d->smoothedGain = smooth * d->smoothedGain + (1 - smooth) * target;
        stereo[i * 2] = pair[0] * d->smoothedGain;
        stereo[i * 2 + 1] = pair[1] * d->smoothedGain;
    }
}

// Buffers are Float32, validated against stream virtual formats before IO starts.
// A channel index spans AudioBufferList buffers, supporting planar and interleaved devices.
static float input_sample(const AudioBufferList *list, uint32_t channel, uint32_t frame) {
    if (!list) return 0;
    for (uint32_t b = 0; b < list->mNumberBuffers; b++) {
        const AudioBuffer *buf = &list->mBuffers[b];
        if (channel < buf->mNumberChannels) {
            size_t at = (size_t)frame * buf->mNumberChannels + channel;
            return buf->mData && (at + 1) * sizeof(float) <= buf->mDataByteSize ? ((float *)buf->mData)[at] : 0;
        }
        channel -= buf->mNumberChannels;
    }
    return 0;
}
static uint32_t list_channels(const AudioBufferList *list) {
    uint32_t n = 0; if (list) for (uint32_t b = 0; b < list->mNumberBuffers; b++) n += list->mBuffers[b].mNumberChannels; return n;
}
static uint32_t list_frames(const AudioBufferList *list) {
    uint32_t n = UINT_MAX;
    if (list) for (uint32_t b = 0; b < list->mNumberBuffers; b++) {
        const AudioBuffer *buf = &list->mBuffers[b];
        if (buf->mNumberChannels && buf->mData) {
            uint32_t count = buf->mDataByteSize / sizeof(float) / buf->mNumberChannels;
            if (count < n) n = count;
        }
    }
    return n == UINT_MAX ? 0 : n;
}
static void add_sample(AudioBufferList *list, uint32_t channel, uint32_t frame, float sample) {
    if (!list) return;
    for (uint32_t b = 0; b < list->mNumberBuffers; b++) {
        AudioBuffer *buf = &list->mBuffers[b];
        if (channel < buf->mNumberChannels) {
            size_t at = (size_t)frame * buf->mNumberChannels + channel;
            if (buf->mData && (at + 1) * sizeof(float) <= buf->mDataByteSize) ((float *)buf->mData)[at] += sample;
            return;
        }
        channel -= buf->mNumberChannels;
    }
}
struct RLCapture {
    RLDSP *dsp;
    uint32_t channelOffset, maxFrames, destinationCount;
    RLRing **destinations;
    float *scratch;
    _Atomic float peak;
    _Atomic uint64_t frames;
};
RLCapture *rl_capture_create(double rate, uint32_t offset, uint32_t maxFrames, uint32_t destinations) {
    if (!maxFrames || maxFrames > (1u << 20)) return NULL;
    RLCapture *c = calloc(1, sizeof(*c)); if (!c) return NULL;
    c->dsp = rl_dsp_create(rate); c->scratch = calloc((size_t)maxFrames * 2, sizeof(float));
    c->destinations = calloc(destinations ? destinations : 1, sizeof(RLRing *));
    if (!c->dsp || !c->scratch || !c->destinations) { rl_capture_destroy(c); return NULL; }
    c->channelOffset = offset; c->maxFrames = maxFrames; c->destinationCount = destinations; return c;
}
void rl_capture_destroy(RLCapture *c) { if (c) { rl_dsp_destroy(c->dsp); free(c->scratch); free(c->destinations); free(c); } }
void rl_capture_set_destination(RLCapture *c, uint32_t i, RLRing *ring) { if (c && i < c->destinationCount) c->destinations[i] = ring; }
void rl_capture_controls(RLCapture *c, float gain, float hp, float gate, float threshold, float ratio) { if (c) rl_dsp_controls(c->dsp, gain, hp, gate, threshold, ratio); }
float rl_capture_take_peak(RLCapture *c) { return c ? atomic_exchange(&c->peak, 0) : 0; }
uint64_t rl_capture_frames(RLCapture *c) { return c ? atomic_load(&c->frames) : 0; }
OSStatus rl_capture_callback(AudioObjectID device, const AudioTimeStamp *now, const AudioBufferList *input,
        const AudioTimeStamp *inputTime, AudioBufferList *output, const AudioTimeStamp *outputTime, void *context) {
    // A capture IOProc on a duplex device still owns an output contribution.
    // Silence it explicitly; CoreAudio may mix it with another render IOProc.
    if (output) for (uint32_t b = 0; b < output->mNumberBuffers; b++)
        if (output->mBuffers[b].mData) memset(output->mBuffers[b].mData, 0, output->mBuffers[b].mDataByteSize);
    RLCapture *c = context; if (!c) return noErr;
    uint32_t frames = list_frames(input), channels = list_channels(input);
    uint32_t right = c->channelOffset + 1 < channels ? c->channelOffset + 1 : c->channelOffset;
    for (uint32_t base = 0; base < frames; base += c->maxFrames) {
        uint32_t count = frames - base; if (count > c->maxFrames) count = c->maxFrames;
        for (uint32_t f = 0; f < count; f++) {
            c->scratch[f * 2] = input_sample(input, c->channelOffset, base + f);
            c->scratch[f * 2 + 1] = input_sample(input, right, base + f);
        }
        rl_dsp_process(c->dsp, c->scratch, count);
        float peak = 0; for (uint32_t f = 0; f < count * 2; f++) peak = fmaxf(peak, fabsf(c->scratch[f]));
        peak_store(&c->peak, peak);
        for (uint32_t d = 0; d < c->destinationCount; d++) rl_ring_write(c->destinations[d], c->scratch, count);
    }
    atomic_fetch_add(&c->frames, frames); return noErr;
}

typedef struct { RLRing *ring; double ratio, phase; uint32_t leader; bool tone; _Atomic bool audible; RLDSP *dsp; _Atomic float peak; } RLSource;
typedef struct { uint32_t offset; _Atomic float gain; _Atomic bool muted; _Atomic float peak; float smoothedGain; } RLBus;
typedef struct { _Atomic float left, right; _Atomic bool muted; float smoothLeft, smoothRight; } RLSend;
struct RLRender {
    double sampleRate;
    uint32_t maxFrames, sourceCount, busCount;
    RLSource *sources; RLBus *buses; RLSend *sends;
    float *sourceScratch, *groupScratch, *busScratch;
    _Atomic uint64_t frames, oversized;
};
RLRender *rl_render_create(double rate, uint32_t maxFrames, uint32_t sourceCount, uint32_t busCount) {
    if (!atomics_supported() || !maxFrames || !isfinite(rate) || rate < 8000) return NULL;
    // All size products are checked before allocation; public C inputs need not
    // have passed the Swift model's validation.
    size_t sources = sourceCount ? sourceCount : 1, buses = busCount ? busCount : 1;
    if (sources > SIZE_MAX / buses / sizeof(RLSend) ||
        (size_t)maxFrames > SIZE_MAX / 2 / sizeof(float) / sources ||
        (size_t)maxFrames > SIZE_MAX / 2 / sizeof(float) / buses) return NULL;
    RLRender *r = calloc(1, sizeof(*r)); if (!r) return NULL;
    r->sampleRate = rate; r->maxFrames = maxFrames; r->sourceCount = sourceCount; r->busCount = busCount;
    r->sources = calloc(sourceCount ? sourceCount : 1, sizeof(RLSource));
    r->buses = calloc(busCount ? busCount : 1, sizeof(RLBus));
    r->sends = calloc((size_t)(sourceCount ? sourceCount : 1) * (busCount ? busCount : 1), sizeof(RLSend));
    r->sourceScratch = calloc((size_t)maxFrames * 2, sizeof(float));
    r->groupScratch = calloc((size_t)maxFrames * 2 * sources, sizeof(float));
    r->busScratch = calloc((size_t)maxFrames * 2 * buses, sizeof(float));
    if (!r->sources || !r->buses || !r->sends || !r->sourceScratch || !r->groupScratch || !r->busScratch) { rl_render_destroy(r); return NULL; }
    for (uint32_t i = 0; i < sourceCount; i++) {
        r->sources[i].leader = i;
        r->sources[i].dsp = rl_dsp_create(rate); if (!r->sources[i].dsp) { rl_render_destroy(r); return NULL; }
    }
    for (size_t i = 0; i < (size_t)sourceCount * busCount; i++) atomic_store(&r->sends[i].muted, true);
    return r;
}
void rl_render_destroy(RLRender *r) {
    if (!r) return;
    if (r->sources) for (uint32_t i = 0; i < r->sourceCount; i++) rl_dsp_destroy(r->sources[i].dsp);
    free(r->sources); free(r->buses); free(r->sends); free(r->sourceScratch); free(r->groupScratch); free(r->busScratch); free(r);
}
void rl_render_set_source(RLRender *r, uint32_t i, RLRing *ring, double inputRate, bool tone) {
    if (!r || i >= r->sourceCount) return;
    r->sources[i].ring = ring; r->sources[i].ratio = inputRate / r->sampleRate; r->sources[i].tone = tone;
}
bool rl_render_set_source_group(RLRender *r, uint32_t source, uint32_t leader) {
    if (!r || source >= r->sourceCount || leader >= r->sourceCount) return false;
    if (source == leader) { r->sources[source].leader = source; return true; }
    if (r->sources[leader].leader != leader) return false;
    if (source != leader) {
        // Only direct parent links are allowed, so render never traverses a tree
        // (or encounters a cycle) on the real-time thread.
        for (uint32_t i = 0; i < r->sourceCount; i++)
            if (i != source && r->sources[i].leader == source) return false;
    }
    r->sources[source].leader = leader;
    return true;
}
void rl_render_source_controls(RLRender *r, uint32_t i, bool audible, float gain, float hp, float gate, float threshold, float ratio) {
    if (!r || i >= r->sourceCount) return;
    atomic_store(&r->sources[i].audible, audible); rl_dsp_controls(r->sources[i].dsp, gain, hp, gate, threshold, ratio);
}
void rl_render_set_bus(RLRender *r, uint32_t i, uint32_t offset) { if (r && i < r->busCount) r->buses[i].offset = offset; }
void rl_render_bus_controls(RLRender *r, uint32_t i, float gain, bool muted) {
    if (!r || i >= r->busCount) return; atomic_store(&r->buses[i].gain, db_gain(gain)); atomic_store(&r->buses[i].muted, muted);
}
void rl_render_send_controls(RLRender *r, uint32_t source, uint32_t bus, float gain, float pan, bool muted) {
    if (!r || source >= r->sourceCount || bus >= r->busCount) return;
    RLSend *s = &r->sends[(size_t)source * r->busCount + bus]; float g = db_gain(gain); pan = fmaxf(-1, fminf(pan, 1));
    // Stereo balance: unity at centre; attenuate opposite side toward the edges.
    atomic_store(&s->left, g * (pan > 0 ? 1 - pan : 1)); atomic_store(&s->right, g * (pan < 0 ? 1 + pan : 1));
    atomic_store(&s->muted, muted);
}
float rl_render_take_bus_peak(RLRender *r, uint32_t b) { return r && b < r->busCount ? atomic_exchange(&r->buses[b].peak, 0) : 0; }
float rl_render_take_source_peak(RLRender *r, uint32_t s) { return r && s < r->sourceCount ? atomic_exchange(&r->sources[s].peak, 0) : 0; }
uint64_t rl_render_frames(RLRender *r) { return r ? atomic_load(&r->frames) : 0; }
uint64_t rl_render_oversized_blocks(RLRender *r) { return r ? atomic_load(&r->oversized) : 0; }
OSStatus rl_render_callback(AudioObjectID device, const AudioTimeStamp *now, const AudioBufferList *input,
        const AudioTimeStamp *inputTime, AudioBufferList *output, const AudioTimeStamp *outputTime, void *context) {
    RLRender *r = context; if (!r || !output) return noErr;
    uint32_t frames = list_frames(output);
    for (uint32_t b = 0; b < output->mNumberBuffers; b++) if (output->mBuffers[b].mData) memset(output->mBuffers[b].mData, 0, output->mBuffers[b].mDataByteSize);
    if (frames > r->maxFrames) { atomic_fetch_add(&r->oversized, 1); return noErr; }
    memset(r->busScratch, 0, (size_t)frames * 2 * r->busCount * sizeof(float));
    memset(r->groupScratch, 0, (size_t)frames * 2 * r->sourceCount * sizeof(float));
    // Resample each member onto this output clock before summing its group.
    for (uint32_t s = 0; s < r->sourceCount; s++) {
        RLSource *src = &r->sources[s];
        if (src->tone) {
            for (uint32_t f = 0; f < frames; f++) {
                float value = (float)sin(src->phase) * .12589254f; // 440 Hz, -18 dBFS peak.
                src->phase += 2 * M_PI * 440 / r->sampleRate; if (src->phase >= 2 * M_PI) src->phase -= 2 * M_PI;
                r->sourceScratch[f * 2] = value; r->sourceScratch[f * 2 + 1] = value;
            }
        } else {
            memset(r->sourceScratch, 0, (size_t)frames * 2 * sizeof(float));
            if (src->ring) rl_ring_read(src->ring, r->sourceScratch, frames, src->ratio);
        }
        float *group = r->groupScratch + (size_t)src->leader * frames * 2;
        for (size_t sample = 0; sample < (size_t)frames * 2; sample++) group[sample] += r->sourceScratch[sample];
    }
    // The parent owns one effect chain and one set of sends. Child sends are
    // lowering metadata only: routing them again would duplicate the whole mix.
    for (uint32_t s = 0; s < r->sourceCount; s++) {
        RLSource *src = &r->sources[s];
        if (src->leader != s) continue;
        float *group = r->groupScratch + (size_t)s * frames * 2;
        rl_dsp_process(src->dsp, group, frames);
        float peak = 0;
        for (size_t sample = 0; sample < (size_t)frames * 2; sample++) peak = fmaxf(peak, fabsf(group[sample]));
        peak_store(&src->peak, peak);
        bool audible = atomic_load(&src->audible);
        float smoothing = (float)exp(-1 / (.005 * r->sampleRate));
        for (uint32_t b = 0; b < r->busCount; b++) {
            RLSend *send = &r->sends[(size_t)s * r->busCount + b]; bool muted = atomic_load(&send->muted) || !audible;
            float left = muted ? 0 : atomic_load(&send->left), right = muted ? 0 : atomic_load(&send->right);
            float *dst = r->busScratch + (size_t)b * frames * 2;
            for (uint32_t f = 0; f < frames; f++) {
                send->smoothLeft = smoothing * send->smoothLeft + (1 - smoothing) * left;
                send->smoothRight = smoothing * send->smoothRight + (1 - smoothing) * right;
                dst[f * 2] += group[f * 2] * send->smoothLeft; dst[f * 2 + 1] += group[f * 2 + 1] * send->smoothRight;
            }
        }
    }
    for (uint32_t b = 0; b < r->busCount; b++) {
        RLBus *bus = &r->buses[b]; float gain = atomic_load(&bus->muted) ? 0 : atomic_load(&bus->gain), peak = 0;
        float *src = r->busScratch + (size_t)b * frames * 2;
        float smoothing = (float)exp(-1 / (.005 * r->sampleRate));
        for (uint32_t f = 0; f < frames; f++) {
            bus->smoothedGain = smoothing * bus->smoothedGain + (1 - smoothing) * gain;
            for (uint32_t c = 0; c < 2; c++) {
                float sample = finite_sample(src[f * 2 + c] * bus->smoothedGain); peak = fmaxf(peak, fabsf(sample)); add_sample(output, bus->offset + c, f, sample);
            }
        }
        peak_store(&bus->peak, peak);
    }
    // Finite hard ceiling on physical device output; meters remain pre-ceiling so
    // overload remains visible. This is protection, not a mastering limiter.
    for (uint32_t b = 0; b < output->mNumberBuffers; b++) {
        AudioBuffer *buf = &output->mBuffers[b]; if (!buf->mData) continue;
        float *p = buf->mData; for (uint32_t i = 0; i < buf->mDataByteSize / sizeof(float); i++) p[i] = fmaxf(-1, fminf(1, finite_sample(p[i])));
    }
    atomic_fetch_add(&r->frames, frames); return noErr;
}
AudioDeviceIOProc rl_capture_io_proc(void) { return rl_capture_callback; }
AudioDeviceIOProc rl_render_io_proc(void) { return rl_render_callback; }
