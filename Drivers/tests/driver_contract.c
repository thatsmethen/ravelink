// SPDX-License-Identifier: GPL-3.0-only
// Calls the actual built bundle interface in a private process. This is not a HAL install test.
#include <CoreAudio/AudioServerPlugIn.h>
#include <CoreFoundation/CoreFoundation.h>
#include <assert.h>
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static OSStatus copy_storage(AudioServerPlugInHostRef host, CFStringRef key, CFPropertyListRef *result) {
    (void)host; (void)key; *result = NULL; return noErr;
}
static OSStatus changed(AudioServerPlugInHostRef host, AudioObjectID object, UInt32 count, const AudioObjectPropertyAddress *addresses) {
    (void)host; (void)object; (void)count; (void)addresses; return noErr;
}
static AudioServerPlugInHostInterface host = {.PropertiesChanged = changed, .CopyFromStorage = copy_storage};

typedef struct {
    void *handle;
    AudioServerPlugInDriverRef driver;
    unsigned channels;
} Instance;

static void get_property(Instance instance, AudioObjectID object, AudioObjectPropertySelector selector, AudioObjectPropertyScope scope, UInt32 size, void *output) {
    AudioObjectPropertyAddress address = {selector, scope, kAudioObjectPropertyElementMain};
    UInt32 actual = 0;
    assert((*instance.driver)->GetPropertyData(instance.driver, object, 0, &address, 0, NULL, size, &actual, output) == noErr);
    assert(actual == size);
}

static Instance open_instance(const char *binary, const char *uid, const char *channels) {
    Instance instance = {0};
    instance.channels = (unsigned)strtoul(channels, NULL, 10);
    assert(instance.channels > 0 && instance.channels <= 256);
    instance.handle = dlopen(binary, RTLD_NOW | RTLD_LOCAL);
    if (!instance.handle) { fprintf(stderr, "dlopen: %s\n", dlerror()); exit(1); }
    void *(*factory)(CFAllocatorRef, CFUUIDRef) = dlsym(instance.handle, "RaveLink_Create");
    assert(factory);
    assert(factory(NULL, kAudioServerPlugInDriverInterfaceUUID) == NULL);
    instance.driver = factory(NULL, kAudioServerPlugInTypeUUID);
    assert(instance.driver);
    assert((*instance.driver)->Initialize(instance.driver, &host) == noErr);
    CFStringRef actual_uid = NULL;
    get_property(instance, 3, kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal, sizeof(actual_uid), &actual_uid);
    char buffer[256];
    assert(CFStringGetCString(actual_uid, buffer, sizeof(buffer), kCFStringEncodingUTF8));
    assert(strcmp(buffer, uid) == 0);
    CFRelease(actual_uid);
    UInt32 transport;
    get_property(instance, 3, kAudioDevicePropertyTransportType, kAudioObjectPropertyScopeGlobal, sizeof(transport), &transport);
    assert(transport == kAudioDeviceTransportTypeVirtual);
    Float64 rate;
    get_property(instance, 3, kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, sizeof(rate), &rate);
    assert(rate == 48000.0);
    for (int direction = 0; direction < 2; ++direction) {
        AudioStreamBasicDescription format;
        get_property(instance, direction == 0 ? 4 : 7, kAudioStreamPropertyVirtualFormat, kAudioObjectPropertyScopeGlobal, sizeof(format), &format);
        assert(format.mFormatID == kAudioFormatLinearPCM);
        assert(format.mChannelsPerFrame == instance.channels);
        assert(format.mBitsPerChannel == 32);
        assert(format.mSampleRate == 48000.0);
    }
    UInt32 hidden;
    get_property(instance, 12, kAudioDevicePropertyIsHidden, kAudioObjectPropertyScopeGlobal, sizeof(hidden), &hidden);
    assert(hidden == 1);
    AudioObjectPropertyAddress streams = {kAudioDevicePropertyStreams, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 mirror_size = 123;
    assert((*instance.driver)->GetPropertyDataSize(instance.driver, 12, 0, &streams, 0, NULL, &mirror_size) == noErr);
    assert(mirror_size == 0);
    UInt32 sentinel = 0x12345678;
    UInt32 returned_size = 0;
    AudioObjectPropertyAddress bad = {kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    assert((*instance.driver)->GetPropertyData(instance.driver, 3, 0, &bad, 0, NULL, sizeof(sentinel), &returned_size, &sentinel) == kAudioHardwareBadPropertySizeError);
    assert(sentinel == 0x12345678);
    assert((*instance.driver)->StartIO(instance.driver, 9999, 1) == kAudioHardwareBadObjectError);
    assert((*instance.driver)->StartIO(instance.driver, 3, 1) == noErr);
    assert((*instance.driver)->StartIO(instance.driver, 3, 2) == noErr);
    return instance;
}

static void loopback(Instance instance, unsigned salt) {
    const unsigned frames = 256;
    const size_t count = frames * instance.channels;
    float *written = calloc(count, sizeof(float));
    float *read = calloc(count, sizeof(float));
    assert(written && read);
    AudioServerPlugInIOCycleInfo cycle = {0};
    for (unsigned block = 0; block < 4096; ++block) {
        // Start near the ring end, so the first operation splits over its boundary.
        double sample = 65536.0 - 73.0 + block * frames;
        cycle.mOutputTime.mSampleTime = sample;
        cycle.mInputTime.mSampleTime = sample;
        cycle.mCurrentTime.mSampleTime = sample;
        for (size_t i = 0; i < count; ++i) written[i] = (float)((i + block + salt) % 257) / 1024.0f;
        assert((*instance.driver)->DoIOOperation(instance.driver, 3, 7, 1, kAudioServerPlugInIOOperationWriteMix, frames, &cycle, written, NULL) == noErr);
        memset(read, 0xff, count * sizeof(float));
        assert((*instance.driver)->DoIOOperation(instance.driver, 3, 4, 2, kAudioServerPlugInIOOperationReadInput, frames, &cycle, read, NULL) == noErr);
        assert(memcmp(written, read, count * sizeof(float)) == 0);
    }
    // A reader beyond the last complete write receives silence, never stale ring contents.
    cycle.mInputTime.mSampleTime += frames * 2;
    assert((*instance.driver)->DoIOOperation(instance.driver, 3, 4, 2, kAudioServerPlugInIOOperationReadInput, frames, &cycle, read, NULL) == noErr);
    for (size_t i = 0; i < count; ++i) assert(read[i] == 0);
    Float64 sample_time;
    UInt64 host_time, seed;
    assert((*instance.driver)->GetZeroTimeStamp(instance.driver, 3, 1, &sample_time, &host_time, &seed) == noErr);
    assert(isfinite(sample_time) && host_time > 0 && seed == 1);
    free(written); free(read);
}

static void isolation(Instance a, Instance b) {
    assert(a.driver != b.driver);
    float *one = calloc(a.channels, sizeof(float));
    float *two = calloc(b.channels, sizeof(float));
    float *read_a = calloc(a.channels, sizeof(float));
    float *read_b = calloc(b.channels, sizeof(float));
    assert(one && two && read_a && read_b);
    for (unsigned i = 0; i < a.channels; ++i) one[i] = 0.125f;
    for (unsigned i = 0; i < b.channels; ++i) two[i] = -0.25f;
    AudioServerPlugInIOCycleInfo cycle = {0};
    cycle.mOutputTime.mSampleTime = cycle.mInputTime.mSampleTime = 1024;
    assert((*a.driver)->DoIOOperation(a.driver, 3, 7, 1, kAudioServerPlugInIOOperationWriteMix, 1, &cycle, one, NULL) == noErr);
    assert((*b.driver)->DoIOOperation(b.driver, 3, 7, 1, kAudioServerPlugInIOOperationWriteMix, 1, &cycle, two, NULL) == noErr);
    assert((*a.driver)->DoIOOperation(a.driver, 3, 4, 2, kAudioServerPlugInIOOperationReadInput, 1, &cycle, read_a, NULL) == noErr);
    assert((*b.driver)->DoIOOperation(b.driver, 3, 4, 2, kAudioServerPlugInIOOperationReadInput, 1, &cycle, read_b, NULL) == noErr);
    assert(memcmp(one, read_a, a.channels * sizeof(float)) == 0);
    assert(memcmp(two, read_b, b.channels * sizeof(float)) == 0);
    free(one); free(two); free(read_a); free(read_b);
}

int main(int argc, const char **argv) {
    if (argc < 4 || (argc - 1) % 3) {
        fprintf(stderr, "usage: driver-contract BINARY UID CHANNELS [BINARY UID CHANNELS ...]\n"); return 2;
    }
    const int count = (argc - 1) / 3;
    Instance *instances = calloc((size_t)count, sizeof(Instance));
    assert(instances);
    for (int i = 0; i < count; ++i) {
        instances[i] = open_instance(argv[1 + i * 3], argv[2 + i * 3], argv[3 + i * 3]);
        loopback(instances[i], (unsigned)i);
    }
    for (int i = 1; i < count; ++i) isolation(instances[0], instances[i]);
    for (int i = 0; i < count; ++i) {
        Instance v = instances[i];
        assert((*v.driver)->StopIO(v.driver, 3, 1) == noErr);
        assert((*v.driver)->StopIO(v.driver, 3, 2) == noErr);
        assert((*v.driver)->StopIO(v.driver, 3, 2) == kAudioHardwareIllegalOperationError);
        dlclose(v.handle);
    }
    printf("PASS: %d bundles; identity, virtual transport, formats, hidden mirror, malformed request, 4096-block loopback per bundle, ring wrap, silence, clock, instance isolation, client lifecycle.\n", count);
    free(instances);
    return 0;
}
