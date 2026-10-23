#ifndef RAVELINK_REALTIME_H
#define RAVELINK_REALTIME_H
#include <CoreAudio/CoreAudio.h>
#include <stdint.h>
#include <stdbool.h>
#include "SoundCheck.h"

// All allocation occurs while the graph is stopped. Controls and telemetry use
// lock-free C11 atomics; each FIFO has exactly one capture writer and render reader.
typedef struct RLRing RLRing;
typedef struct RLCapture RLCapture;
typedef struct RLRender RLRender;
typedef struct RLDSP RLDSP;

RLRing *rl_ring_create(uint32_t capacity);
void rl_ring_destroy(RLRing *ring);
uint32_t rl_ring_write(RLRing *ring, const float *stereo, uint32_t frames);
uint32_t rl_ring_read(RLRing *ring, float *stereo, uint32_t frames, double ratio);
// Configure the band-limited resampling kernel before starting either callback.
bool rl_ring_prepare_ratio(RLRing *ring, double ratio);
uint64_t rl_ring_dropped(RLRing *ring);
uint64_t rl_ring_underruns(RLRing *ring);

RLDSP *rl_dsp_create(double sampleRate);
void rl_dsp_destroy(RLDSP *dsp);
void rl_dsp_controls(RLDSP *dsp, float gainDB, float highPassHz, float gateDB,
                     float compressorDB, float compressorRatio);
void rl_dsp_process(RLDSP *dsp, float *stereo, uint32_t frames);

RLCapture *rl_capture_create(double sampleRate, uint32_t channelOffset,
                             uint32_t maxFrames, uint32_t destinationCount);
void rl_capture_destroy(RLCapture *capture);
void rl_capture_set_destination(RLCapture *capture, uint32_t index, RLRing *ring);
void rl_capture_controls(RLCapture *capture, float gainDB, float highPassHz,
                          float gateDB, float compressorDB, float compressorRatio);
float rl_capture_take_peak(RLCapture *capture);
uint64_t rl_capture_frames(RLCapture *capture);
OSStatus rl_capture_callback(AudioObjectID device, const AudioTimeStamp *now,
                             const AudioBufferList *input, const AudioTimeStamp *inputTime,
                             AudioBufferList *output, const AudioTimeStamp *outputTime, void *context);
AudioDeviceIOProc rl_capture_io_proc(void);

RLRender *rl_render_create(double sampleRate, uint32_t maxFrames,
                           uint32_t sourceCount, uint32_t busCount);
void rl_render_destroy(RLRender *render);
// Install only while stopped. Context must outlive every callback. A nonzero
// return permanently latches silence for this graph until explicit rebuild.
typedef int32_t (*RLGroupProcessor)(void *context, uint32_t sourceIndex, float *stereo, uint32_t frames);
void rl_render_set_group_processor(RLRender *render, RLGroupProcessor processor, void *context);
int32_t rl_render_processor_error(RLRender *render);
// Configure only while stopped. Sound Check storage must outlive callbacks.
bool rl_render_set_sound_check(RLRender *render, uint32_t leader, RLSoundCheck *check);
void rl_render_set_source(RLRender *render, uint32_t index, RLRing *ring,
                          double inputSampleRate, bool tone);
// Configure while callbacks are stopped. Leaders must be direct roots; invalid
// indices, chains, and reparenting a leader with children are rejected.
// The leader's controls and sends apply once to the sum of all group members.
bool rl_render_set_source_group(RLRender *render, uint32_t source, uint32_t leader);
void rl_render_source_controls(RLRender *render, uint32_t index, bool audible,
                               float gainDB, float highPassHz, float gateDB,
                               float compressorDB, float compressorRatio);
void rl_render_set_bus(RLRender *render, uint32_t index, uint32_t channelOffset);
void rl_render_bus_controls(RLRender *render, uint32_t index, float gainDB, bool muted);
void rl_render_send_controls(RLRender *render, uint32_t source, uint32_t bus,
                             float gainDB, float pan, bool muted);
float rl_render_take_bus_peak(RLRender *render, uint32_t bus);
float rl_render_take_source_peak(RLRender *render, uint32_t source);
uint64_t rl_render_frames(RLRender *render);
uint64_t rl_render_oversized_blocks(RLRender *render);
OSStatus rl_render_callback(AudioObjectID device, const AudioTimeStamp *now,
                            const AudioBufferList *input, const AudioTimeStamp *inputTime,
                            AudioBufferList *output, const AudioTimeStamp *outputTime, void *context);
AudioDeviceIOProc rl_render_io_proc(void);
#endif
