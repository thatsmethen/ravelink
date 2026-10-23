/* Independently authored Core Audio system observer/player, 2026-10-24.
 * Uses Apple's public AudioHardware/AudioStream APIs; does not load driver
 * internals. This test instrument is not part of the shipping Rust product.
 * All allocation and file I/O occur outside the real-time IOProc. */
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach_time.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>

#define EXPECTED_RATE 48000.0
#define MAX_CALLBACK_FRAMES 8192u
#define MAX_EVENTS 262144u
#define PI 3.14159265358979323846

typedef struct {
    double sample_time;
    uint64_t host_time;
    uint64_t observed_host_time;
    uint32_t flags, frames, stored_frames;
} Event;
typedef struct {
    bool recording;
    double amplitude, left_hz, right_hz;
    uint64_t target_frames;
    float *pcm;
    Event *events;
    atomic_bool accepting;
    atomic_uint in_flight, fault;
    atomic_uint_fast64_t frames, event_count;
} Context;
typedef struct {
    const char *mode, *uid, *report, *wav, *events, *ready;
    double seconds, amplitude, left_hz, right_hz;
} Options;

static uint64_t monotonic_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 0;
    return (uint64_t)now.tv_sec * 1000000000ULL + (uint64_t)now.tv_nsec;
}
static void sleep_ms(unsigned milliseconds) {
    struct timespec duration = {milliseconds / 1000u, (long)(milliseconds % 1000u) * 1000000L};
    while (nanosleep(&duration, &duration) != 0 && errno == EINTR) {}
}
static AudioObjectPropertyAddress address(AudioObjectPropertySelector selector, AudioObjectPropertyScope scope) {
    return (AudioObjectPropertyAddress){selector, scope, kAudioObjectPropertyElementMain};
}
static OSStatus read_exact(AudioObjectID object, AudioObjectPropertyAddress property, void *destination, UInt32 expected) {
    UInt32 bytes = expected;
    OSStatus status = AudioObjectGetPropertyData(object, &property, 0, NULL, &bytes, destination);
    if (status == noErr && bytes != expected) return kAudioHardwareBadPropertySizeError;
    return status;
}
static OSStatus find_device(const char *uid, AudioObjectID *found, unsigned *matches) {
    AudioObjectPropertyAddress property = address(kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal);
    UInt32 bytes = 0;
    OSStatus status = AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &property, 0, NULL, &bytes);
    if (status != noErr) return status;
    if (bytes > 1024u * 1024u || bytes % sizeof(AudioObjectID)) return kAudioHardwareBadPropertySizeError;
    AudioObjectID *devices = malloc(bytes ? bytes : 1);
    if (!devices) return kAudioHardwareUnspecifiedError;
    status = AudioObjectGetPropertyData(kAudioObjectSystemObject, &property, 0, NULL, &bytes, devices);
    *found = kAudioObjectUnknown; *matches = 0;
    if (status == noErr) {
        CFStringRef requested = CFStringCreateWithCString(NULL, uid, kCFStringEncodingUTF8);
        if (!requested) status = kAudioHardwareIllegalOperationError;
        for (UInt32 index = 0; requested && status == noErr && index < bytes / sizeof(AudioObjectID); index++) {
            CFStringRef candidate = NULL;
            status = read_exact(devices[index], address(kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal), &candidate, sizeof candidate);
            if (status == noErr && candidate) {
                if (CFEqual(candidate, requested)) { *found = devices[index]; (*matches)++; }
                CFRelease(candidate);
            }
        }
        if (requested) CFRelease(requested);
    }
    free(devices);
    return status;
}
static OSStatus stream_format(AudioObjectID device, AudioObjectPropertyScope scope, AudioStreamBasicDescription *format) {
    AudioObjectPropertyAddress property = address(kAudioDevicePropertyStreams, scope);
    UInt32 bytes = 0;
    OSStatus status = AudioObjectGetPropertyDataSize(device, &property, 0, NULL, &bytes);
    if (status != noErr) return status;
    if (bytes != sizeof(AudioObjectID)) return kAudioHardwareBadPropertySizeError;
    AudioObjectID stream = kAudioObjectUnknown;
    status = read_exact(device, property, &stream, sizeof stream);
    if (status != noErr) return status;
    return read_exact(stream, address(kAudioStreamPropertyVirtualFormat, kAudioObjectPropertyScopeGlobal), format, sizeof *format);
}
static bool supported_format(const AudioStreamBasicDescription *f) {
    return isfinite(f->mSampleRate) && f->mSampleRate == EXPECTED_RATE && f->mFormatID == kAudioFormatLinearPCM
        && f->mFormatFlags == kAudioFormatFlagsNativeFloatPacked && f->mChannelsPerFrame == 2
        && f->mBitsPerChannel == 32 && f->mBytesPerFrame == 8 && f->mBytesPerPacket == 8 && f->mFramesPerPacket == 1;
}
static OSStatus set_direction(AudioObjectID device, AudioDeviceIOProcID proc, AudioObjectPropertyScope scope, bool enabled) {
    // This fixture requires exactly one stream in each direction. The HAL owns
    // IOProc usage, so the plug-in need not implement this client-side property.
    AudioHardwareIOProcStreamUsage usage = { .mIOProc = (void *)proc, .mNumberStreams = 1, .mStreamIsOn = {enabled ? 1u : 0u} };
    AudioObjectPropertyAddress property = address(kAudioDevicePropertyIOProcStreamUsage, scope);
    return AudioObjectSetPropertyData(device, &property, 0, NULL, sizeof usage, &usage);
}
static void latch_fault(Context *context, unsigned value) {
    unsigned expected = 0;
    atomic_compare_exchange_strong_explicit(&context->fault, &expected, value, memory_order_release, memory_order_relaxed);
}
static void silence(AudioBufferList *buffers) {
    if (!buffers) return;
    for (UInt32 index = 0; index < buffers->mNumberBuffers; index++) {
        AudioBuffer *buffer = &buffers->mBuffers[index];
        if (buffer->mData) memset(buffer->mData, 0, buffer->mDataByteSize);
    }
}
static OSStatus io_proc(AudioObjectID device, const AudioTimeStamp *now, const AudioBufferList *input,
                        const AudioTimeStamp *input_time, AudioBufferList *output,
                        const AudioTimeStamp *output_time, void *data) {
    (void)device; (void)now;
    Context *context = data;
    atomic_fetch_add_explicit(&context->in_flight, 1, memory_order_acq_rel);
    silence(output);
    if (!atomic_load_explicit(&context->accepting, memory_order_acquire)) goto done;
    const AudioBufferList *buffers = context->recording ? input : output;
    const AudioTimeStamp *timestamp = context->recording ? input_time : output_time;
    uint64_t position = atomic_load_explicit(&context->frames, memory_order_relaxed);
    if (position >= context->target_frames) goto done;
    if (!buffers || buffers->mNumberBuffers != 1 || !buffers->mBuffers[0].mData
        || buffers->mBuffers[0].mNumberChannels != 2 || buffers->mBuffers[0].mDataByteSize % 8u) { latch_fault(context, 1); goto done; }
    const UInt32 frames = buffers->mBuffers[0].mDataByteSize / 8u;
    if (!frames || frames > MAX_CALLBACK_FRAMES) { latch_fault(context, 2); goto done; }
    if (!timestamp || !(timestamp->mFlags & kAudioTimeStampSampleTimeValid) || !(timestamp->mFlags & kAudioTimeStampHostTimeValid)
        || !isfinite(timestamp->mSampleTime) || timestamp->mSampleTime < 0.0 || timestamp->mHostTime == 0) { latch_fault(context, 3); goto done; }
    uint64_t event_index = atomic_load_explicit(&context->event_count, memory_order_relaxed);
    if (event_index >= MAX_EVENTS) { latch_fault(context, 4); goto done; }
    UInt32 count = frames;
    if ((uint64_t)count > context->target_frames - position) count = (UInt32)(context->target_frames - position);
    if (context->recording) {
        memcpy(context->pcm + position * 2, buffers->mBuffers[0].mData, (size_t)count * 8u);
    } else {
        float *samples = output->mBuffers[0].mData;
        for (UInt32 frame = 0; frame < count; frame++) {
            double time = (timestamp->mSampleTime + frame) / EXPECTED_RATE;
            samples[frame * 2] = (float)(context->amplitude * sin(2.0 * PI * context->left_hz * time));
            samples[frame * 2 + 1] = (float)(context->amplitude * sin(2.0 * PI * context->right_hz * time));
        }
    }
    context->events[event_index] = (Event){ timestamp->mSampleTime, timestamp->mHostTime, mach_absolute_time(), timestamp->mFlags, frames, count };
    atomic_store_explicit(&context->event_count, event_index + 1, memory_order_release);
    atomic_store_explicit(&context->frames, position + count, memory_order_release);
done:
    atomic_fetch_sub_explicit(&context->in_flight, 1, memory_order_release);
    return noErr;
}
static void json_string(FILE *file, const char *value) {
    fputc('"', file);
    for (const unsigned char *p = (const unsigned char *)value; *p; p++) {
        if (*p == '"' || *p == '\\') { fputc('\\', file); fputc(*p, file); }
        else if (*p < 32) fprintf(file, "\\u%04x", *p);
        else fputc(*p, file);
    }
    fputc('"', file);
}
static bool u16(FILE *file, uint16_t value) {
    unsigned char bytes[2] = {(unsigned char)value, (unsigned char)(value >> 8)};
    return fwrite(bytes, 1, 2, file) == 2;
}
static bool u32(FILE *file, uint32_t value) {
    unsigned char bytes[4] = {(unsigned char)value, (unsigned char)(value >> 8), (unsigned char)(value >> 16), (unsigned char)(value >> 24)};
    return fwrite(bytes, 1, 4, file) == 4;
}
static bool write_wav(const char *path, const float *pcm, uint64_t frames) {
    if (frames > (UINT32_MAX - 36u) / 8u) return false;
    FILE *file = fopen(path, "wb"); if (!file) return false;
    uint32_t bytes = (uint32_t)frames * 8u;
    bool ok = fwrite("RIFF", 1, 4, file) == 4 && u32(file, 36u + bytes) && fwrite("WAVEfmt ", 1, 8, file) == 8
        && u32(file, 16) && u16(file, 3) && u16(file, 2) && u32(file, 48000) && u32(file, 48000 * 8)
        && u16(file, 8) && u16(file, 32) && fwrite("data", 1, 4, file) == 4 && u32(file, bytes)
        && fwrite(pcm, 1, bytes, file) == bytes;
    return fclose(file) == 0 && ok;
}
static bool write_events(const char *path, const Event *events, uint64_t count) {
    FILE *file = fopen(path, "w"); if (!file) return false;
    fputs("sample_time,host_time,observed_host_time,flags,frames,stored_frames\n", file);
    for (uint64_t index = 0; index < count; index++) {
        const Event *e = &events[index];
        fprintf(file, "%.17g,%llu,%llu,%u,%u,%u\n", e->sample_time, (unsigned long long)e->host_time,
                (unsigned long long)e->observed_host_time, e->flags, e->frames, e->stored_frames);
    }
    return fclose(file) == 0;
}
static bool ready_file(const char *path, uint64_t frames, uint64_t now) {
    if (!path) return true;
    // Publish a complete document atomically. The controller must never see a
    // newly created, empty file while the readiness JSON is still being written.
    size_t length = strlen(path);
    if (length > 4096) return false;
    char *pending = malloc(length + 9);
    if (!pending) return false;
    snprintf(pending, length + 9, "%s.pending", path);
    FILE *file = fopen(pending, "wx");
    if (!file) { free(pending); return false; }
    fprintf(file, "{\"ready\":true,\"frames\":%llu,\"monotonic_ns\":%llu}\n", (unsigned long long)frames, (unsigned long long)now);
    bool saved = fclose(file) == 0;
    // link is atomic and refuses an existing readiness name. Both paths live
    // in the same evidence directory on the same filesystem.
    bool published = saved && link(pending, path) == 0;
    unlink(pending);
    free(pending);
    return published;
}
static bool write_report(const Options *o, AudioObjectID device, unsigned matches, OSStatus status, OSStatus stop_status,
                         OSStatus destroy_status, Context *context, bool complete, bool ready, uint64_t started_ns, uint64_t ended_ns) {
    FILE *file = fopen(o->report, "w"); if (!file) return false;
    mach_timebase_info_data_t timebase; mach_timebase_info(&timebase);
    uint64_t frames = context ? atomic_load(&context->frames) : 0;
    uint64_t count = context ? atomic_load(&context->event_count) : 0;
    fprintf(file, "{\"schema\":1,\"mode\":"); json_string(file, o->mode); fputs(",\"uid\":", file); json_string(file, o->uid);
    fprintf(file, ",\"device_id\":%u,\"matches\":%u,\"status\":%d,\"stop_status\":%d,\"destroy_status\":%d,\"fault\":%u,\"complete\":%s,\"ready\":%s,\"frames\":%llu,\"events\":%llu,\"target_frames\":%llu,\"sample_rate\":48000,\"channels\":2,\"amplitude\":%.17g,\"left_hz\":%.17g,\"right_hz\":%.17g,\"started_monotonic_ns\":%llu,\"ended_monotonic_ns\":%llu,\"host_time_numer\":%u,\"host_time_denom\":%u}\n",
            device, matches, status, stop_status, destroy_status, context ? atomic_load(&context->fault) : 0, complete ? "true" : "false", ready ? "true" : "false",
            (unsigned long long)frames, (unsigned long long)count, (unsigned long long)(context ? context->target_frames : 0), o->amplitude, o->left_hz, o->right_hz,
            (unsigned long long)started_ns, (unsigned long long)ended_ns, timebase.numer, timebase.denom);
    return fclose(file) == 0;
}
static bool numeric(const char *value, double *output) {
    char *end = NULL; errno = 0; double result = strtod(value, &end);
    if (errno || !end || *end || !isfinite(result)) return false;
    *output = result; return true;
}
static bool options(int argc, char **argv, Options *o) {
    *o = (Options){.seconds = 20.0, .amplitude = 0.125, .left_hz = 440.0, .right_hz = 997.0};
    if (argc < 2) return false;
    o->mode = argv[1];
    if (strcmp(o->mode, "discover") && strcmp(o->mode, "record") && strcmp(o->mode, "play")) return false;
    for (int index = 2; index < argc; index += 2) {
        if (index + 1 >= argc) return false;
        const char *key = argv[index], *value = argv[index + 1];
        if (!strcmp(key, "--uid")) o->uid = value;
        else if (!strcmp(key, "--report")) o->report = value;
        else if (!strcmp(key, "--wav")) o->wav = value;
        else if (!strcmp(key, "--events")) o->events = value;
        else if (!strcmp(key, "--ready")) o->ready = value;
        else if (!strcmp(key, "--seconds")) { if (!numeric(value, &o->seconds)) return false; }
        else if (!strcmp(key, "--amplitude")) { if (!numeric(value, &o->amplitude)) return false; }
        else if (!strcmp(key, "--left-hz")) { if (!numeric(value, &o->left_hz)) return false; }
        else if (!strcmp(key, "--right-hz")) { if (!numeric(value, &o->right_hz)) return false; }
        else return false;
    }
    bool io = strcmp(o->mode, "discover") != 0;
    return o->uid && *o->uid && o->report && (!io || (o->events && o->ready))
        && (strcmp(o->mode, "record") || o->wav) && o->seconds >= 0.25 && o->seconds <= 60.0
        && o->amplitude >= 0.0 && o->amplitude <= 0.5 && o->left_hz >= 20.0 && o->left_hz < 20000.0
        && o->right_hz >= 20.0 && o->right_hz < 20000.0;
}
int main(int argc, char **argv) {
    Options o;
    if (!options(argc, argv, &o)) {
        fprintf(stderr, "usage: system-probe discover|play|record --uid UID --report JSON [--seconds 20 --events CSV --ready FILE --wav WAV --amplitude .125 --left-hz 440 --right-hz 997]\n");
        return 2;
    }
    AudioObjectID device = kAudioObjectUnknown; unsigned matches = 0;
    OSStatus status = find_device(o.uid, &device, &matches), stop_status = 0, destroy_status = 0;
    Context *context = NULL; AudioDeviceIOProcID proc = NULL;
    bool started = false, complete = false, ready = false, quiescent = true;
    uint64_t started_ns = 0, ended_ns = 0;
    if (status == noErr && matches > 1) status = kAudioHardwareIllegalOperationError;
    if (!strcmp(o.mode, "discover")) {
        complete = status == noErr;
        if (!write_report(&o, device, matches, status, 0, 0, NULL, complete, false, 0, 0)) return 4;
        return status == noErr ? 0 : 1;
    }
    if (status == noErr && device == kAudioObjectUnknown) status = kAudioHardwareBadDeviceError;
    AudioStreamBasicDescription in_format = {0}, out_format = {0};
    if (status == noErr) status = stream_format(device, kAudioObjectPropertyScopeInput, &in_format);
    if (status == noErr) status = stream_format(device, kAudioObjectPropertyScopeOutput, &out_format);
    if (status == noErr && (!supported_format(&in_format) || !supported_format(&out_format))) status = kAudioDeviceUnsupportedFormatError;
    if (status == noErr) {
        context = calloc(1, sizeof *context);
        if (!context) status = kAudioHardwareUnspecifiedError;
        else {
            atomic_init(&context->accepting, false);
            atomic_init(&context->in_flight, 0);
            atomic_init(&context->fault, 0);
            atomic_init(&context->frames, 0);
            atomic_init(&context->event_count, 0);
        }
    }
    if (status == noErr) {
        context->recording = !strcmp(o.mode, "record"); context->amplitude = o.amplitude;
        context->left_hz = o.left_hz; context->right_hz = o.right_hz;
        context->target_frames = (uint64_t)llround(o.seconds * EXPECTED_RATE);
        context->events = calloc(MAX_EVENTS, sizeof(Event));
        if (context->recording) context->pcm = calloc((size_t)context->target_frames * 2u, sizeof(float));
        if (!context->events || (context->recording && !context->pcm)) status = kAudioHardwareUnspecifiedError;
        // Touch every owned page before real-time execution, including samples
        // that will eventually be overwritten; volatile stores cannot disappear.
        if (status == noErr) {
            volatile unsigned char *bytes = (volatile unsigned char *)context->events;
            for (size_t p = 0; p < MAX_EVENTS * sizeof(Event); p += 4096) bytes[p] = 0;
            bytes = (volatile unsigned char *)context->pcm;
            for (size_t p = 0; bytes && p < context->target_frames * 8u; p += 4096) bytes[p] = 0;
        }
    }
    if (status == noErr) status = AudioDeviceCreateIOProcID(device, io_proc, context, &proc);
    if (status == noErr) status = set_direction(device, proc, kAudioObjectPropertyScopeInput, context->recording);
    if (status == noErr) status = set_direction(device, proc, kAudioObjectPropertyScopeOutput, !context->recording);
    if (status == noErr) {
        atomic_store_explicit(&context->accepting, true, memory_order_release);
        started_ns = monotonic_ns(); status = AudioDeviceStart(device, proc); started = status == noErr;
    }
    if (started) {
        uint64_t deadline = started_ns + (uint64_t)((o.seconds + 8.0) * 1e9), last_progress_ns = started_ns, previous_frames = 0;
        while (!atomic_load_explicit(&context->fault, memory_order_acquire)) {
            uint64_t frames = atomic_load_explicit(&context->frames, memory_order_acquire), now = monotonic_ns();
            if (frames != previous_frames) { last_progress_ns = now; previous_frames = frames; }
            if (!ready && frames) {
                ready = ready_file(o.ready, frames, now);
                if (!ready) { latch_fault(context, 5); break; }
            }
            if (frames >= context->target_frames) { complete = true; break; }
            if (now > deadline || now - last_progress_ns > 4000000000ULL) { latch_fault(context, 6); break; }
            sleep_ms(5);
        }
    }
    if (context) atomic_store_explicit(&context->accepting, false, memory_order_release);
    if (started) stop_status = AudioDeviceStop(device, proc);
    if (proc) destroy_status = AudioDeviceDestroyIOProcID(device, proc);
    if (context) {
        uint64_t deadline = monotonic_ns() + 2000000000ULL;
        while (atomic_load_explicit(&context->in_flight, memory_order_acquire) && monotonic_ns() < deadline) sleep_ms(1);
        quiescent = atomic_load_explicit(&context->in_flight, memory_order_acquire) == 0;
        if (!quiescent) latch_fault(context, 7);
    }
    ended_ns = monotonic_ns();
    bool saved = true;
    if (context && quiescent) {
        uint64_t frames = atomic_load(&context->frames), count = atomic_load(&context->event_count);
        if (context->recording && context->pcm) saved = write_wav(o.wav, context->pcm, frames) && saved;
        if (context->events) saved = write_events(o.events, context->events, count) && saved;
    }
    saved = write_report(&o, device, matches, status, stop_status, destroy_status, context, complete, ready, started_ns, ended_ns) && saved;
    bool success = saved && status == noErr && stop_status == noErr && destroy_status == noErr && complete && ready
        && context && atomic_load(&context->fault) == 0;
    // Keep context alive until process exit if unregistering failed. No unsafe
    // freeing of storage still reachable from an OS callback.
    if (context && quiescent && destroy_status == noErr) { free(context->pcm); free(context->events); free(context); }
    return success ? 0 : 1;
}
