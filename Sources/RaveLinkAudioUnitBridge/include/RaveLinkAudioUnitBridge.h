#ifndef RAVELINK_AUDIO_UNIT_BRIDGE_H
#define RAVELINK_AUDIO_UNIT_BRIDGE_H
#import <AudioToolbox/AUAudioUnit.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct RLAUGraph RLAUGraph;
RLAUGraph * _Nullable rl_au_graph_create(uint32_t sourceCount, uint32_t maxFrames, double sampleRate);
void rl_au_graph_destroy(RLAUGraph * _Nullable graph);
// Configuration is allowed only before the render callback begins.
bool rl_au_graph_append(RLAUGraph * _Nonnull graph, uint32_t sourceIndex, uint32_t slotIndex, AURenderBlock _Nonnull block, AUScheduleParameterBlock _Nullable schedule, bool bypassed);
bool rl_au_graph_set_bypass(RLAUGraph * _Nonnull graph, uint32_t sourceIndex, uint32_t slotIndex, bool bypassed);
bool rl_au_graph_set_parameter(RLAUGraph * _Nonnull graph, uint32_t sourceIndex, uint32_t slotIndex, uint64_t address, float value, uint32_t rampFrames);
int32_t rl_au_graph_process(void * _Nullable context, uint32_t sourceIndex, float * _Nullable stereo, uint32_t frames);
int32_t rl_au_graph_error(RLAUGraph * _Nonnull graph, uint32_t * _Nullable sourceIndex, uint32_t * _Nullable slotIndex);
#endif
