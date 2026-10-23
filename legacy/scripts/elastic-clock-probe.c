// Generated schedules only: no HAL device or wall-clock waiting. Compile with
// -DRL_LEGACY_CLOCK against the frozen implementation to retain its comparison.
#include "RaveLinkRealtime.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct {
    const char *name;
    double inputRate, outputRate, ppm, seconds, jitter;
    unsigned inputFrames, outputFrames, varyingBlocks, varyingDrift;
    double outputPPM, missingUntil;
} Case;
static const Case cases[] = {
    {"minus1000",48000,48000,-1000,180,0,256,256,0,0},
    {"minus500",48000,48000,-500,180,0,256,256,0,0},
    {"minus250",48000,48000,-250,180,0,256,256,0,0},
    {"minus100",48000,48000,-100,180,0,256,256,0,0},
    {"minus50",48000,48000,-50,180,0,256,256,0,0},
    {"nominal",48000,48000,0,180,0,256,256,0,0},
    {"plus50",48000,48000,50,180,0,256,256,0,0},
    {"plus100",48000,48000,100,180,0,256,256,0,0},
    {"plus250",48000,48000,250,180,0,256,256,0,0},
    {"plus500",48000,48000,500,180,0,256,256,0,0},
    {"plus1000",48000,48000,1000,180,0,256,256,0,0},
    {"large-input-slow",48000,48000,-500,90,0,1024,64,0,0},
    {"large-input-fast",48000,48000,500,90,0,1024,64,0,0},
    {"large-output-slow",48000,48000,-500,90,0,64,1024,0,0},
    {"large-output-fast",48000,48000,500,90,0,64,1024,0,0},
    {"jitter-slow",48000,48000,-1000,90,.35,256,256,0,0},
    {"jitter-fast",48000,48000,1000,90,.35,256,256,0,0},
    {"unequal-jitter-slow",48000,48000,-1000,90,.35,1024,64,0,0},
    {"unequal-jitter-fast",48000,48000,1000,90,.35,64,1024,0,0},
    {"varying-blocks-slow",48000,48000,-1000,90,.15,512,512,1,0},
    {"varying-blocks-fast",48000,48000,1000,90,.15,512,512,1,0},
    {"drift-step",48000,48000,1000,180,.15,256,512,0,1},
    {"drift-sine",48000,48000,1000,180,.15,512,256,0,2},
    {"44100-to-48000-slow",44100,48000,-1000,90,.15,256,512,0,0},
    {"44100-to-48000-fast",44100,48000,1000,90,.15,256,512,0,0},
    {"96000-to-44100-slow",96000,44100,-1000,90,.15,512,256,0,0},
    {"96000-to-44100-fast",96000,44100,1000,90,.15,512,256,0,0},
    {"8000-largest-block",8000,8000,-1000,120,0,16384,16384,0,0},
    {"192000-small-block",192000,192000,1000,30,.15,64,128,0,0},
    {"ratio24-slow",192000,8000,-1000,90,.15,1024,256,0,0},
    {"ratio24-fast",192000,8000,1000,90,.15,1024,256,0,0},
    {"ratio-one24-slow",8000,192000,-1000,30,.15,64,512,0,0},
    {"ratio-one24-fast",8000,192000,1000,30,.15,64,512,0,0},
    {"boundary100ms-8000-slow",8000,8000,-1000,180,0,800,800,0,0},
    {"boundary100ms-8000-fast",8000,8000,1000,180,0,800,800,0,0},
    {"boundary100ms-44100-slow",44100,44100,-1000,180,0,4410,4410,0,0},
    {"boundary100ms-44100-fast",44100,44100,1000,180,0,4410,4410,0,0},
    {"boundary100ms-48000-slow",48000,48000,-1000,180,0,4800,4800,0,0},
    {"boundary100ms-48000-fast",48000,48000,1000,180,0,4800,4800,0,0},
    {"boundary100ms-96000-slow",96000,96000,-1000,180,0,9600,9600,0,0},
    {"boundary100ms-96000-fast",96000,96000,1000,180,0,9600,9600,0,0},
    {"boundary100ms-192000-slow",192000,192000,-1000,180,0,16384,16384,0,0},
    {"boundary100ms-192000-fast",192000,192000,1000,180,0,16384,16384,0,0},
    {"boundary100ms-384000-slow",384000,384000,-1000,180,0,16384,16384,0,0},
    {"boundary100ms-384000-fast",384000,384000,1000,180,0,16384,16384,0,0},
    {"opposing-clocks-slow-input",48000,48000,-1000,180,.35,256,256,0,0,1000,0},
    {"opposing-clocks-fast-input",48000,48000,1000,180,.35,256,256,0,0,-1000,0},
    {"matching-fast-clocks",48000,48000,1000,90,.35,256,256,0,0,1000,0},
    {"output-clock-fast",8000,96000,0,90,.15,64,1024,0,0,1000,0},
    {"output-clock-slow",8000,96000,0,90,.15,64,1024,0,0,-1000,0},
    {"opposing100ms-slow-input",44100,48000,-1000,180,.15,4410,4800,0,0,1000,0},
    {"opposing100ms-fast-input",44100,48000,1000,180,.15,4410,4800,0,0,-1000,0},
    {"input-step-output-fast",48000,48000,1000,180,.15,256,512,0,1,1000,0},
    {"late-metadata",48000,48000,-1000,90,.15,256,256,0,0,0,20},
    {"temporary-missing-metadata",48000,48000,-1000,90,.15,256,256,0,0,0,-1}
};
static double offset(const Case *c, double time) {
    if (c->varyingDrift == 1) return time < c->seconds/2 ? -c->ppm : c->ppm;
    if (c->varyingDrift == 2) return c->ppm * sin(2*M_PI*time/60);
    return c->ppm;
}
static double randomSigned(unsigned *state) {
    *state = *state * 1664525u + 1013904223u;
    return (double)*state / 4294967295.0 * 2 - 1;
}
static unsigned block(unsigned maximum, unsigned varying, unsigned index) {
    static const unsigned divisors[] = {1,4,2,8,2,1,4};
    return varying ? maximum/divisors[index%7] : maximum;
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    puts("case,inputRate,outputRate,ppm,outputPPM,missingUntil,seconds,inputBlock,outputBlock,jitter,varyingBlocks,varyingDrift,initialZeroBlocks,lateZeroBlocks,partialBlocks,dropped,underrun,nonfinite,maxAmplitudeError,maxPhaseStepError,phaseStepLimit,meanFrequency,frequencyLimit,timedReads,timestampFaults,pass");
    int failures = 0, matched = 0;
    for (unsigned index=0;index<sizeof(cases)/sizeof(cases[0]);index++) {
        const Case *c = &cases[index];
        if (argc > 1 && strcmp(c->name,argv[1])) continue;
        matched++;
        double ratio=c->inputRate/c->outputRate;
        unsigned capacity=65536;
        while (capacity < 4*fmax(c->inputFrames,c->outputFrames*ratio)+2048) capacity*=2;
        RLRing *ring=rl_ring_create(capacity);
        if (!ring) return 2;
#ifdef RL_LEGACY_CLOCK
        if (!rl_ring_prepare_ratio(ring,ratio)) return 3;
#else
        if (!rl_ring_prepare_clock(ring,c->inputRate,c->outputRate) ||
            !rl_ring_prepare_buffers(ring,c->inputFrames,c->outputFrames)) return 3;
        RLClock *inputClock=rl_clock_create(c->inputRate,1e9), *outputClock=rl_clock_create(c->outputRate,1e9);
        if(!inputClock || !outputClock) return 6;
#endif
        float *input=calloc(c->inputFrames*2,sizeof(float)),*output=calloc(c->outputFrames*2,sizeof(float));
        if (!input || !output) return 4;
        double inputIdeal=0,inputTime=0,outputIdeal=0,outputTime=0,phase=0,previousPhase=0;
        double phaseSum=0,maxPhaseError=0,maxAmplitudeError=0;
        unsigned initialZero=0,lateZero=0,partial=0,inputIndex=0,outputIndex=0,seed=0x47625319u;
        unsigned long long nonfinite=0,phaseCount=0,inputSample=0,outputSample=0,timedReads=0,timestampFaults=0;
        float inputFactor=0;
        int primed=0,havePrevious=0;
        const double actualOutputRate=c->outputRate*(1+c->outputPPM/1e6);
        const double expectedStep=2*M_PI*440/actualOutputRate;
        while(outputIdeal<c->seconds) {
            if(inputTime<=outputTime) {
                unsigned frames=block(c->inputFrames,c->varyingBlocks,inputIndex++);
                double actualRate=c->inputRate*(1+offset(c,inputIdeal)/1e6);
                for(unsigned f=0;f<frames;f++) {
                    input[f*2]=(float)(.125*sin(phase)); input[f*2+1]=(float)(.125*cos(phase));
                    phase += 2*M_PI*440/actualRate;
                    if (phase>2*M_PI) phase-=2*M_PI;
                }
#ifndef RL_LEGACY_CLOCK
                AudioTimeStamp stamp={.mSampleTime=(double)inputSample,.mHostTime=(uint64_t)llround(inputIdeal*1e9),
                    .mFlags=kAudioTimeStampSampleTimeValid|kAudioTimeStampHostTimeValid};
                if ((c->missingUntil>0 && inputIdeal<c->missingUntil) || (c->missingUntil<0 && inputIdeal>=60 && inputIdeal<70)) stamp.mFlags=0;
                inputFactor=rl_clock_observe(inputClock,&stamp,frames,false);
                rl_ring_set_source_clock(ring,inputFactor);
#endif
                inputSample+=frames;
                rl_ring_write(ring,input,frames);
                inputIdeal += frames/actualRate;
                double next=inputIdeal+c->jitter*frames/actualRate*randomSigned(&seed);
                inputTime=fmax(inputTime+.000000001,next);
            } else {
                unsigned frames=block(c->outputFrames,c->varyingBlocks,outputIndex++);
#ifdef RL_LEGACY_CLOCK
                unsigned n=rl_ring_read(ring,output,frames,ratio);
#else
                AudioTimeStamp stamp={.mSampleTime=(double)outputSample,.mHostTime=(uint64_t)llround(outputIdeal*1e9),
                    .mFlags=kAudioTimeStampSampleTimeValid|kAudioTimeStampHostTimeValid};
                if ((c->missingUntil>0 && outputIdeal<c->missingUntil) || (c->missingUntil<0 && outputIdeal>=60 && outputIdeal<70)) stamp.mFlags=0;
                float outputFactor=rl_clock_observe(outputClock,&stamp,frames,false);
                unsigned n=rl_ring_read_clocked(ring,output,frames,ratio,outputFactor);
                if(inputFactor>0 && outputFactor>0) timedReads++;
#endif
                outputSample+=frames;
                if(n) { if(n<frames) partial++; primed=1; }
                else if(primed) lateZero++; else initialZero++;
                for(unsigned f=0;f<n;f++) {
                    double left=output[f*2],right=output[f*2+1];
                    if(!isfinite(left)||!isfinite(right)) {nonfinite++;continue;}
                    maxAmplitudeError=fmax(maxAmplitudeError,fabs(hypot(left,right)-.125));
                    double current=atan2(left,right),delta=current-previousPhase;
                    if(delta>M_PI) delta-=2*M_PI; if(delta<-M_PI) delta+=2*M_PI;
                    if(havePrevious && outputIdeal>10) {
                        phaseSum+=delta; phaseCount++;
                        maxPhaseError=fmax(maxPhaseError,fabs(delta-expectedStep));
                    }
                    previousPhase=current;havePrevious=1;
                }
                outputIdeal += frames/actualOutputRate;
                double next=outputIdeal+c->jitter*frames/actualOutputRate*randomSigned(&seed);
                outputTime=fmax(outputTime+.000000001,next);
            }
        }
        double phaseLimit=expectedStep*.01+2*(2*M_PI*440/c->inputRate)/512;
        double frequency=phaseCount?phaseSum/phaseCount*actualOutputRate/(2*M_PI):0;
#ifndef RL_LEGACY_CLOCK
        timestampFaults=rl_clock_discontinuities(inputClock)+rl_clock_discontinuities(outputClock);
        rl_clock_destroy(inputClock);rl_clock_destroy(outputClock);
#endif
        int pass=!timestampFaults&&!lateZero&&!partial&&!rl_ring_dropped(ring)&&!rl_ring_underruns(ring)&&!nonfinite&&
            maxAmplitudeError<.0001&&maxPhaseError<phaseLimit&&fabs(frequency-440)<.15;
        printf("%s,%.0f,%.0f,%.0f,%.0f,%.0f,%.0f,%u,%u,%.2f,%u,%u,%u,%u,%u,%llu,%llu,%llu,%.9g,%.9g,%.9g,%.9f,.15,%llu,%llu,%s\n",
            c->name,c->inputRate,c->outputRate,c->ppm,c->outputPPM,c->missingUntil,c->seconds,c->inputFrames,c->outputFrames,c->jitter,c->varyingBlocks,c->varyingDrift,
            initialZero,lateZero,partial,(unsigned long long)rl_ring_dropped(ring),(unsigned long long)rl_ring_underruns(ring),nonfinite,
            maxAmplitudeError,maxPhaseError,phaseLimit,frequency,timedReads,timestampFaults,pass?"true":"false");
        if(!pass)failures++;
        free(input);free(output);rl_ring_destroy(ring);
    }
    return !matched ? 5 : failures ? 1 : 0;
}
