// SPDX-License-Identifier: GPL-3.0-only
// Actual built-bundle interface tests; private process, no host HAL installation.
#define main original_driver_contract_main
#include "driver_contract.c"
#undef main
#include <pthread.h>
#include <stdatomic.h>

static OSStatus transfer(Instance v, bool writing, double sample, UInt32 frames, UInt64 cycleOrdinal, float *data) {
    AudioServerPlugInIOCycleInfo cycle = {0};
    cycle.mOutputTime.mSampleTime = cycle.mInputTime.mSampleTime = cycle.mCurrentTime.mSampleTime = sample;
    cycle.mIOCycleCounter = cycleOrdinal;
    return (*v.driver)->DoIOOperation(v.driver, 3, writing ? 7 : 4, writing ? 1 : 2,
        writing ? kAudioServerPlugInIOOperationWriteMix : kAudioServerPlugInIOOperationReadInput,
        frames, &cycle, data, NULL);
}
static void write_value(Instance v, UInt64 sample, UInt32 frames, UInt64 cycle, float value) {
    float *buffer = calloc((size_t)frames * v.channels, sizeof(float)); assert(buffer);
    for (size_t i = 0; i < (size_t)frames * v.channels; ++i) buffer[i] = value;
    assert(transfer(v, true, sample, frames, cycle, buffer) == noErr); free(buffer);
}
static void expect_value(Instance v, UInt64 sample, UInt32 frames, UInt64 cycle, float value) {
    float *buffer = malloc((size_t)frames * v.channels * sizeof(float)); assert(buffer);
    memset(buffer, 0xff, (size_t)frames * v.channels * sizeof(float));
    assert(transfer(v, false, sample, frames, cycle, buffer) == noErr);
    for (size_t i = 0; i < (size_t)frames * v.channels; ++i) {
        if (buffer[i] != value) { fprintf(stderr, "at sample %llu + %zu got %.9g expected %.9g\n", sample, i / v.channels, buffer[i], value); abort(); }
    }
    free(buffer);
}
static void restart(Instance v) {
    assert((*v.driver)->StopIO(v.driver,3,1)==noErr);
    // The second reader keeps the same device timeline alive.
    assert((*v.driver)->StopIO(v.driver,3,2)==noErr);
    assert((*v.driver)->StartIO(v.driver,3,1)==noErr);
    assert((*v.driver)->StartIO(v.driver,3,2)==noErr);
}
typedef struct { Instance v; atomic_bool done; atomic_uint checks; } ConcurrentProbe;
static void *read_concurrently(void *context) {
    ConcurrentProbe *probe = context;
    float data[256];
    do {
        assert(transfer(probe->v,false,100,1,0,data)==noErr);
        assert(data[0]==0 || data[0]==0.25f || data[0]==-0.5f);
        for(unsigned channel=1;channel<probe->v.channels;channel++) assert(data[channel]==data[0]);
        atomic_fetch_add_explicit(&probe->checks,1,memory_order_relaxed);
    } while(!atomic_load_explicit(&probe->done,memory_order_acquire));
    return NULL;
}
static void concurrent_readers(Instance v) {
    restart(v);
    ConcurrentProbe probe = {.v=v}; atomic_init(&probe.done,false); atomic_init(&probe.checks,0);
    pthread_t readers[2];
    for(unsigned i=0;i<2;i++)assert(pthread_create(&readers[i],NULL,read_concurrently,&probe)==0);
    float data[256];
    for(unsigned iteration=0;iteration<100000;iteration++) {
        for(unsigned channel=0;channel<v.channels;channel++)data[channel]=iteration%2?0.25f:-0.5f;
        assert(transfer(v,true,100,1,0,data)==noErr);
    }
    atomic_store_explicit(&probe.done,true,memory_order_release);
    for(unsigned i=0;i<2;i++)assert(pthread_join(readers[i],NULL)==0);
    assert(atomic_load(&probe.checks)>0);
}
int main(int argc, const char **argv) {
    assert(argc == 4); Instance v = open_instance(argv[1],argv[2],argv[3]);
    // Frozen failure: hole inside last-output boundary reused the prior ring epoch.
    write_value(v,512,512,0,0.125f);
    write_value(v,65536,512,0,0.25f);
    write_value(v,66560,512,0,0.5f);
    expect_value(v,66048,512,0,0);
    expect_value(v,65536,512,0,0.25f);
    expect_value(v,66560,512,0,0.5f);
    // Future and expired readers must not erase another client's valid frames.
    expect_value(v,70000,512,0,0);
    expect_value(v,512,512,0,0); // Expired, even if the slot has not been overwritten.
    expect_value(v,66560,512,0,0.5f);
    write_value(v,66048,512,0,0.75f); // Backwards write starts a fresh timeline.
    expect_value(v,66560,512,0,0);
    expect_value(v,66048,512,0,0.75f);
    restart(v);
    expect_value(v,66048,512,0,0);
    // Variable block crossing the ring edge; read spans several independently written ranges.
    write_value(v,65500,100,0,0.2f);
    write_value(v,65620,53,0,0.4f);
    expect_value(v,65500,100,0,0.2f);
    expect_value(v,65600,20,0,0);
    expect_value(v,65620,53,0,0.4f);
    float partial[200 * 256] = {0};
    assert(transfer(v,false,65490,200,0,partial)==noErr);
    for (unsigned f=0;f<200;f++) for(unsigned c=0;c<v.channels;c++) {
        float expected=f>=10&&f<110?0.2f:f>=130&&f<183?0.4f:0;
        assert(partial[(size_t)f*v.channels+c]==expected);
    }
    // A newer epoch overwrites the same modulo slots; old reads cannot expose it.
    write_value(v,65500+65536,100,0,0.8f);
    expect_value(v,65500,100,0,0);
    expect_value(v,65500+65536,100,0,0.8f);
    // Reader counters can lag or lead independently without invalidating other clients.
    restart(v); write_value(v,100,16,10,0.6f);
    expect_value(v,100,16,10,0.6f);
    write_value(v,116,16,11,0.8f);
    expect_value(v,100,16,10,0.6f);
    expect_value(v,116,16,1,0.8f);
    expect_value(v,100,16,900,0.6f);
    // Only the mixed writer's counter reset is authoritative; its sample time
    // advances here so the test does not depend on backwards-timestamp detection.
    write_value(v,132,16,1,0.7f);
    expect_value(v,100,16,1,0);
    expect_value(v,116,16,1,0);
    expect_value(v,132,16,1,0.7f);
    // Stopping one of several clients preserves the remaining client's ring.
    assert((*v.driver)->StopIO(v.driver,3,1)==noErr);
    expect_value(v,132,16,1,0.7f);
    assert((*v.driver)->StartIO(v.driver,3,1)==noErr);
    expect_value(v,132,16,1,0.7f);
    float sentinel[256]; for(unsigned i=0;i<v.channels;i++)sentinel[i]=0.123f;
    assert(transfer(v,true,NAN,1,0,sentinel)!=noErr);
    assert(transfer(v,true,-1,1,0,sentinel)!=noErr);
    assert(transfer(v,true,INFINITY,1,0,sentinel)!=noErr);
    assert(transfer(v,true,9007199254740992.0,1,0,sentinel)!=noErr);
    assert(transfer(v,true,0,65537,0,sentinel)!=noErr);
    assert(transfer(v,true,0,1,0,NULL)!=noErr);
    expect_value(v,132,16,1,0.7f);
    // Preserve the pinned source's finite nonnegative truncation on both paths.
    for(unsigned i=0;i<v.channels;i++)sentinel[i]=0.375f;
    assert(transfer(v,true,200.75,1,0,sentinel)==noErr);
    memset(sentinel,0,sizeof(sentinel));
    assert(transfer(v,false,200.125,1,0,sentinel)==noErr);
    for(unsigned i=0;i<v.channels;i++)assert(sentinel[i]==0.375f);
    assert(transfer(v,false,199.999,1,0,sentinel)==noErr);
    for(unsigned i=0;i<v.channels;i++)assert(sentinel[i]==0);
    assert(transfer(v,false,201.001,1,0,sentinel)==noErr);
    for(unsigned i=0;i<v.channels;i++)assert(sentinel[i]==0);
    concurrent_readers(v);
    assert((*v.driver)->StopIO(v.driver,3,1)==noErr);
    assert((*v.driver)->StopIO(v.driver,3,2)==noErr);
    dlclose(v.handle);
    puts("PASS: actual bundle stale-hole silence, intact adjacent frames, future-reader isolation, variable blocks, partial holes, wrap, overwritten old reads, timestamp/cycle reset, multiple-client lifecycle, malformed bounds, concurrent readers with 100000 writes.");
}
