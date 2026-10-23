// Read-only observer for an explicitly diagnostic RaveLink HAL build.
// This process never creates an IOProc, starts audio, or changes a property.
#include <CoreAudio/CoreAudio.h>
#include <CoreAudio/HostTime.h>
#include <CoreFoundation/CoreFoundation.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../Drivers/patches/RaveLinkDiagnostics.h"

static void quote(const char *s) {
    putchar('"');
    for (; *s; ++s) { unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') putchar('\\');
        if (c < 32) printf("\\u%04x", c); else putchar(c);
    }
    putchar('"');
}
static int lookup(const char *uid, AudioObjectID *device) {
    CFStringRef key = CFStringCreateWithCString(NULL, uid, kCFStringEncodingUTF8);
    if (!key) { fprintf(stderr, "UID is not valid UTF-8\n"); return 3; }
    AudioValueTranslation translation = { &key, sizeof(key), device, sizeof(*device) };
    AudioObjectPropertyAddress address = {kAudioHardwarePropertyTranslateUIDToDevice,
        kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 size = sizeof(translation);
    OSStatus status = AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, &size, &translation);
    CFRelease(key);
    if (status || size != sizeof(translation) || *device == kAudioObjectUnknown) {
        fprintf(stderr, "Could not resolve device UID %s (OSStatus=%d)\n", uid, (int)status); return 3;
    }
    return 0;
}
static int read_diagnostics(AudioObjectID device, RLDriverDiagnostics *snapshot) {
    AudioObjectPropertyAddress address = {RL_DRIVER_DIAGNOSTIC_SELECTOR,
        kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    if (!AudioObjectHasProperty(device, &address)) {
        fprintf(stderr, "Device %u has no rldg diagnostic property; use the explicit diagnostic driver build\n", device); return 4;
    }
    UInt32 size = 0;
    OSStatus status = AudioObjectGetPropertyDataSize(device, &address, 0, NULL, &size);
    if (status || size != sizeof(CFPropertyListRef)) {
        fprintf(stderr, "Diagnostic property has invalid pointer size %u (OSStatus=%d)\n", size, (int)status); return 5;
    }
    CFPropertyListRef value = NULL;
    status = AudioObjectGetPropertyData(device, &address, 0, NULL, &size, &value);
    if (status || size != sizeof(value) || !value) {
        if (value) CFRelease(value);
        fprintf(stderr, "Diagnostic property read failed (OSStatus=%d)\n", (int)status); return 6;
    }
    if (CFGetTypeID(value) != CFDataGetTypeID() || CFDataGetLength((CFDataRef)value) != sizeof(*snapshot)) {
        CFRelease(value); fprintf(stderr, "Diagnostic property is not the expected fixed-size CFData payload\n"); return 7;
    }
    memcpy(snapshot, CFDataGetBytePtr((CFDataRef)value), sizeof(*snapshot)); CFRelease(value);
    if (snapshot->version != RL_DRIVER_DIAGNOSTIC_VERSION || snapshot->bytes != sizeof(*snapshot) ||
        snapshot->snapshotsPerReason != RL_DRIVER_DIAGNOSTIC_SNAPSHOTS || snapshot->channels == 0) {
        fprintf(stderr, "Diagnostic ABI mismatch: version=%u bytes=%u channels=%u snapshots=%u\n",
            snapshot->version, snapshot->bytes, snapshot->channels, snapshot->snapshotsPerReason); return 8;
    }
    for (unsigned reason = 0; reason < RLDiagReasonCount; ++reason)
        for (unsigned i = 0; i < RL_DRIVER_DIAGNOSTIC_SNAPSHOTS; ++i) {
            const RLDriverDiagnosticEvent *e = &snapshot->events[reason][i];
            if (e->present > 1 || (e->present && e->reason != reason)) {
                fprintf(stderr, "Diagnostic event has invalid publication or reason tag\n"); return 8;
            }
        }
    return 0;
}
static void print_event(const RLDriverDiagnosticEvent *e) {
    printf("{\"present\":%u,\"reason\":%u,\"operation\":%" PRIu64 ",\"clientID\":%" PRIu64
        ",\"cycle\":%" PRIu64 ",\"hostTime\":%" PRIu64 ",\"requestedSampleTime\":",
        e->present, e->reason, e->operation, e->clientID, e->cycle, e->hostTime);
    if (isfinite(e->requestedSampleTime)) printf("%.17g", e->requestedSampleTime); else fputs("null", stdout);
    printf(",\"requestedSampleTimeFinite\":%s,\"requestedFrame\":%" PRIu64 ",\"blockFrames\":%" PRIu64
        ",\"writeEnd\":%" PRIu64 ",\"slotSample\":%" PRIu64 ",\"slotGeneration\":%" PRIu64
        ",\"beforeSequence\":%" PRIu64 ",\"afterSequence\":%" PRIu64 ",\"driverGeneration\":%" PRIu64
        ",\"priorWriteStart\":%" PRIu64 ",\"priorCycle\":%" PRIu64 "}",
        isfinite(e->requestedSampleTime) ? "true" : "false", e->requestedFrame, e->blockFrames,
        e->writeEnd, e->slotSample, e->slotGeneration, e->beforeSequence, e->afterSequence,
        e->driverGeneration, e->priorWriteStart, e->priorCycle);
}
static void print_snapshot(const char *uid, AudioObjectID device, const RLDriverDiagnostics *s) {
    static const char *names[] = RL_DRIVER_DIAGNOSTIC_REASON_NAMES;
    _Static_assert(sizeof(names) / sizeof(names[0]) == RLDiagReasonCount, "Diagnostic reason names must cover the ABI");
    printf("{\"uid\":"); quote(uid);
    printf(",\"deviceID\":%u,\"version\":%u,\"bytes\":%u,\"channels\":%u,\"snapshotsPerReason\":%u,\"reasonCount\":%u,"
        "\"readCalls\":%" PRIu64 ",\"writeCalls\":%" PRIu64 ",\"readFrames\":%" PRIu64
        ",\"writeFrames\":%" PRIu64 ",\"startAllocations\":%" PRIu64 ",\"reasons\":{",
        device, s->version, s->bytes, s->channels, s->snapshotsPerReason, RLDiagReasonCount,
        s->readCalls, s->writeCalls, s->readFrames, s->writeFrames, s->startAllocations);
    for (unsigned reason = 0; reason < RLDiagReasonCount; ++reason) {
        if (reason) putchar(','); quote(names[reason]);
        printf(":{\"frameCount\":%" PRIu64 ",\"blockCount\":%" PRIu64 ",\"events\":[",
            s->frameCounts[reason], s->blockCounts[reason]);
        for (unsigned i = 0; i < RL_DRIVER_DIAGNOSTIC_SNAPSHOTS; ++i) {
            if (i) putchar(',');
            if (s->events[reason][i].present) print_event(&s->events[reason][i]); else fputs("null", stdout);
        }
        fputs("]}", stdout);
    }
    fputs("}}", stdout);
}
int main(int argc, char **argv) {
    if (argc < 3 || argc > 129 || argc % 2 == 0) {
        fprintf(stderr, "Usage: driver-diagnostics-probe --uid UID [--uid UID ...] (up to 64 devices)\n"); return 2;
    }
    unsigned count = (unsigned)(argc - 1) / 2;
    for (unsigned i = 0; i < count; ++i)
        if (strcmp(argv[1 + 2*i], "--uid") || !argv[2 + 2*i][0] || strlen(argv[2 + 2*i]) > 4096) {
            fprintf(stderr, "Each device requires --uid and a nonempty UTF-8 UID of at most 4096 bytes\n"); return 2;
        }
    RLDriverDiagnostics *snapshots = calloc(count, sizeof(*snapshots));
    AudioObjectID *devices = calloc(count, sizeof(*devices));
    if (!snapshots || !devices) { free(snapshots); free(devices); return 9; }
    int result = 0;
    for (unsigned i = 0; i < count; ++i) {
        result = lookup(argv[2 + 2*i], &devices[i]);
        if (!result) result = read_diagnostics(devices[i], &snapshots[i]);
        if (result) break;
    }
    if (!result) {
        printf("{\"diagnosticProtocol\":1,\"hostTicksPerSecond\":%.17g,"
            "\"scope\":\"Read-only driver property; no audio IO started. Lifetime counters may overlap and are not a simultaneous snapshot. Published events are immutable.\",\"devices\":[", AudioGetHostClockFrequency());
        for (unsigned i = 0; i < count; ++i) {
            if (i) putchar(','); print_snapshot(argv[2 + 2*i], devices[i], &snapshots[i]);
        }
        fputs("]}\n", stdout);
    }
    free(snapshots); free(devices); return result;
}
