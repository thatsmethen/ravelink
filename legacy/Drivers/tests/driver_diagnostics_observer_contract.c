// Observer controls only: all HAL property accesses are replaced with fixtures.
#include <CoreAudio/CoreAudio.h>
#include <CoreAudio/AudioServerPlugIn.h>
#include <CoreFoundation/CoreFoundation.h>
#include <assert.h>
#include <math.h>
#include <string.h>
#include "../patches/RaveLinkDiagnostics.h"
static int mode;
static Boolean fakeHas(AudioObjectID device, const AudioObjectPropertyAddress *address) {
    (void)device; assert(address->mSelector == RL_DRIVER_DIAGNOSTIC_SELECTOR); return mode != 1;
}
static OSStatus fakeSize(AudioObjectID device, const AudioObjectPropertyAddress *address,
    UInt32 qualifierSize, const void *qualifier, UInt32 *size) {
    (void)device; (void)address; (void)qualifierSize; (void)qualifier;
    *size = sizeof(CFPropertyListRef) + (mode == 2 ? 8 : 0); return mode == 3 ? 7331 : noErr;
}
static OSStatus fakeGet(AudioObjectID device, const AudioObjectPropertyAddress *address,
    UInt32 qualifierSize, const void *qualifier, UInt32 *size, void *data) {
    (void)device; (void)qualifierSize; (void)qualifier; (void)size;
    if (address->mSelector == kAudioHardwarePropertyTranslateUIDToDevice) {
        AudioValueTranslation *translation = data;
        CFStringRef key = *(CFStringRef *)translation->mInputData;
        *(AudioObjectID *)translation->mOutputData = CFStringCompare(key, CFSTR("missing"), 0) == kCFCompareEqualTo ? 0 : 42;
        return noErr;
    }
    assert(address->mSelector == RL_DRIVER_DIAGNOSTIC_SELECTOR);
    if (mode == 4) return 7332;
    if (mode == 5) { *(CFPropertyListRef *)data = CFStringCreateWithCString(NULL, "wrong type", kCFStringEncodingUTF8); return noErr; }
    RLDriverDiagnostics snapshot = {0};
    snapshot.version = mode == 7 ? 999 : RL_DRIVER_DIAGNOSTIC_VERSION;
    snapshot.bytes = mode == 8 ? 0 : sizeof(snapshot);
    snapshot.channels = 8; snapshot.snapshotsPerReason = mode == 9 ? 2 : RL_DRIVER_DIAGNOSTIC_SNAPSHOTS;
    snapshot.readCalls = UINT64_MAX; snapshot.writeCalls = 39; snapshot.readFrames = 2048;
    snapshot.writeFrames = 1536; snapshot.startAllocations = 2;
    snapshot.frameCounts[RLDiagFutureWindow] = 512; snapshot.blockCounts[RLDiagFutureWindow] = 1;
    RLDriverDiagnosticEvent *event = &snapshot.events[RLDiagFutureWindow][0];
    event->present = mode == 10 ? 2 : 1; event->reason = mode == 11 ? RLDiagExpiredWindow : RLDiagFutureWindow;
    event->operation = kAudioServerPlugInIOOperationReadInput; event->clientID = 17; event->cycle = 29;
    event->hostTime = 123456789; event->requestedSampleTime = NAN; event->requestedFrame = 2560;
    event->blockFrames = 512; event->writeEnd = 2560; event->slotSample = 9;
    event->slotGeneration = 1; event->beforeSequence = 4; event->afterSequence = 6;
    event->driverGeneration = 2; event->priorWriteStart = 2048; event->priorCycle = 28;
    *(CFPropertyListRef *)data = CFDataCreate(NULL, (const UInt8 *)&snapshot, sizeof(snapshot) - (mode == 6 ? 1 : 0));
    return noErr;
}
#define AudioObjectHasProperty fakeHas
#define AudioObjectGetPropertyDataSize fakeSize
#define AudioObjectGetPropertyData fakeGet
#define main diagnostic_main
#include "../../scripts/driver-diagnostics-probe.c"
#undef main
int main(void) {
    const int failures[] = {0,4,5,5,6,7,7,8,8,8,8,8}; RLDriverDiagnostics snapshot;
    for (mode = 1; mode <= 11; ++mode) assert(read_diagnostics(42, &snapshot) == failures[mode]);
    mode = 0;
    assert(read_diagnostics(42, &snapshot) == 0 && snapshot.readCalls == UINT64_MAX);
    char *missing[] = {"probe", "--uid", "fixture", "--uid", "missing"};
    assert(diagnostic_main(5, missing) == 3);
    char *invalid[] = {"probe", "--start", "fixture"}; assert(diagnostic_main(3, invalid) == 2);
    char *valid[] = {"probe", "--uid", "fixture\"line\n", "--uid", "second"};
    assert(diagnostic_main(5, valid) == 0);
    fprintf(stderr, "Diagnostic observer malformed-property and complete-JSON controls passed; HAL mocked.\n");
    return 0;
}
