/* Offline storage/serialization contract. Never calls the renamed device main
 * or any audio-device API. IOProc is invoked directly with owned fake buffers. */
#define main unused_device_probe_main
#include "system-probe.c"
#undef main
#include <assert.h>
#include <pthread.h>

typedef struct { Diagnostics *diagnostics; unsigned object; } Writer;
static void *publish(void *raw) {
    Writer *writer = raw;
    AudioObjectPropertyAddress addresses[16];
    for (unsigned index = 0; index < 16; index++)
        addresses[index] = (AudioObjectPropertyAddress){ writer->object + index, 2, index };
    for (unsigned iteration = 0; iteration < 32; iteration++)
        diagnostic_notify(writer->diagnostics, writer->object, 16, addresses, writer->object * 1000u + iteration);
    return NULL;
}
int main(int argc, char **argv) {
    assert(argc == 4);
    Diagnostics *diagnostics = calloc(1, sizeof *diagnostics);
    assert(diagnostics);
    diagnostic_initialize(diagnostics);
    Writer a = { diagnostics, 100 }, b = { diagnostics, 200 };
    pthread_t first, second;
    assert(pthread_create(&first, NULL, publish, &a) == 0);
    assert(pthread_create(&second, NULL, publish, &b) == 0);
    assert(pthread_join(first, NULL) == 0 && pthread_join(second, NULL) == 0);
    assert(atomic_load(&diagnostics->notification_count) == 1024);
    assert(atomic_load(&diagnostics->dropped) == 0 && atomic_load(&diagnostics->in_flight) == 0);
    unsigned counts[2] = {0};
    for (unsigned index = 0; index < 1024; index++) {
        NotificationEvent *event = &diagnostics->notifications[index];
        assert(atomic_load_explicit(&event->committed, memory_order_acquire) == index + 1);
        assert(event->object == 100 || event->object == 200);
        counts[event->object == 200]++;
        assert(event->address.mElement < 16 && event->address.mScope == 2);
        assert(event->address.mSelector == event->object + event->address.mElement);
        assert(event->host_time >= event->object * 1000u && event->host_time < event->object * 1000u + 32);
    }
    assert(counts[0] == 512 && counts[1] == 512);
    uint64_t first_tick = diagnostics->notifications[0].host_time;
    AudioObjectPropertyAddress addresses[33] = {0};
    diagnostic_notify(diagnostics, 999, 33, addresses, 888);
    assert(atomic_load(&diagnostics->notification_count) == 1040);
    assert(atomic_load(&diagnostics->dropped) == 33);
    assert(diagnostics->notifications[0].host_time == first_tick);
    atomic_store_explicit(&diagnostics->accepting, false, memory_order_release);
    diagnostic_notify(diagnostics, 999, 33, addresses, 888);
    assert(atomic_load(&diagnostics->notification_count) == 1040);
    assert(atomic_load(&diagnostics->dropped) == 33 && atomic_load(&diagnostics->in_flight) == 0);
    free(diagnostics);

    Context context = {0};
    atomic_init(&context.accepting, true);
    atomic_init(&context.in_flight, 0);
    atomic_init(&context.fault, 0);
    atomic_init(&context.frames, 0);
    atomic_init(&context.event_count, 0);
    context.recording = true;
    context.target_frames = 1536;
    context.pcm = calloc(1536 * 2, sizeof(float));
    context.events = calloc(3, sizeof(Event));
    context.diagnostics = calloc(1, sizeof(Diagnostics));
    assert(context.pcm && context.events && context.diagnostics);
    diagnostic_initialize(context.diagnostics);
    context.diagnostics->timings = calloc(3, sizeof(TimingEvent));
    assert(context.diagnostics->timings);
    float samples[512 * 2] = {0};
    AudioBufferList input = {.mNumberBuffers = 1, .mBuffers = {{2, sizeof samples, samples}}};
    const double positions[] = {1000, 1512, 2600};
    for (unsigned index = 0; index < 3; index++) {
        AudioTimeStamp timestamp = {.mSampleTime = positions[index], .mHostTime = mach_absolute_time(),
            .mFlags = kAudioTimeStampSampleTimeValid | kAudioTimeStampHostTimeValid};
        AudioTimeStamp current = timestamp;
        if (index == 2) { current.mSampleTime = NAN; current.mHostTime = 0; current.mFlags = 0; }
        assert(io_proc(100, &current, &input, &timestamp, NULL, NULL, &context) == noErr);
    }
    assert(atomic_load(&context.frames) == 1536 && atomic_load(&context.event_count) == 3);
    assert(atomic_load(&context.in_flight) == 0 && atomic_load(&context.fault) == 0);
    AudioObjectPropertyAddress property = {123, 456, 0};
    diagnostic_notify(context.diagnostics, 100, 1, &property, mach_absolute_time());
    atomic_store(&context.diagnostics->accepting, false);
    context.diagnostics->listeners_stopped = context.diagnostics->quiescent = true;
    Options o = {.mode = "offline-synthetic", .uid = "no-device-opened", .report = argv[3]};
    assert(write_events(argv[2], context.events, 3));
    assert(write_report(&o, 100, 1, 0, 0, 0, &context, true, true, 0, 0));
    assert(write_diagnostics(argv[1], &context, true));
    assert(!write_diagnostics(argv[1], &context, true)); // Original output cannot be overwritten.
    atomic_store(&context.in_flight, 1);
    assert(io_proc(100, NULL, NULL, NULL, NULL, NULL, &context) == noErr);
    assert(atomic_load(&context.in_flight) == 1 && atomic_load(&context.fault) == 8);
    assert(atomic_load(&context.event_count) == 3); // Reentrancy cannot overwrite owned records.
    atomic_store(&context.in_flight, 0);
    free(context.diagnostics->timings);
    free(context.diagnostics);
    free(context.events);
    free(context.pcm);
    return 0;
}
