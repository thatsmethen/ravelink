// SPDX-License-Identifier: GPL-3.0-only
// Versioned read-only diagnostic ABI. No audio data or application identity is exposed.
// HAL selector rldg returns a CFPropertyListRef of CFData type, containing exactly
// sizeof(RLDriverDiagnostics) bytes. The caller owns/releases that returned object.
#ifndef RAVELINK_DRIVER_DIAGNOSTICS_H
#define RAVELINK_DRIVER_DIAGNOSTICS_H
#include <stdint.h>
#define RL_DRIVER_DIAGNOSTIC_SELECTOR ((uint32_t)0x726c6467) /* rldg */
#define RL_DRIVER_DIAGNOSTIC_VERSION 1
#define RL_DRIVER_DIAGNOSTIC_SNAPSHOTS 4
#ifndef RAVELINK_FRAME_DIAGNOSTICS
#define RAVELINK_FRAME_DIAGNOSTICS 0
#endif

enum RLDriverDiagnosticReason {
    RLDiagNoPublishedWrite,
    RLDiagFutureWindow,
    RLDiagExpiredWindow,
    RLDiagUnpublishedFrame,
    RLDiagSampleMismatch,
    RLDiagGenerationMismatch,
    RLDiagFrameInFlight,
    RLDiagSequenceChanged,
    RLDiagTimelineChanged,
    RLDiagMuted,
    RLDiagWriterCycleReset,
    RLDiagWriterTimeRewind,
    RLDiagCommittedBeyondWindow,
    RLDiagReasonCount
};
#define RL_DRIVER_DIAGNOSTIC_REASON_NAMES {"noPublishedWrite", "futureWindow", "expiredWindow", "unpublishedFrame", "sampleMismatch", "generationMismatch", "frameInFlight", "sequenceChanged", "timelineChanged", "muted", "writerCycleReset", "writerTimeRewind", "committedBeyondWindow"}

typedef struct {
    uint32_t present;
    uint32_t reason;
    uint64_t operation;
    uint64_t clientID;
    uint64_t cycle;
    uint64_t hostTime;
    double requestedSampleTime;
    uint64_t requestedFrame;
    uint64_t blockFrames;
    uint64_t writeEnd;
    uint64_t slotSample;
    uint64_t slotGeneration;
    uint64_t beforeSequence;
    uint64_t afterSequence;
    uint64_t driverGeneration;
    uint64_t priorWriteStart;
    uint64_t priorCycle;
} RLDriverDiagnosticEvent;

typedef struct {
    uint32_t version;
    uint32_t bytes;
    uint32_t channels;
    uint32_t snapshotsPerReason;
    uint64_t readCalls;
    uint64_t writeCalls;
    uint64_t readFrames;
    uint64_t writeFrames;
    uint64_t startAllocations;
    // Reasons overlap; frame counts are not a disjoint total of silent frames.
    // Counters are lifetime cumulative until the bundle process unloads, not a
    // simultaneous snapshot while IO runs. Published events never change.
    uint64_t frameCounts[RLDiagReasonCount];
    uint64_t blockCounts[RLDiagReasonCount];
    RLDriverDiagnosticEvent events[RLDiagReasonCount][RL_DRIVER_DIAGNOSTIC_SNAPSHOTS];
} RLDriverDiagnostics;
#endif
