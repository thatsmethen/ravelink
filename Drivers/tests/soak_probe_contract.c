// Exercise the independent probe callback with synthetic buffers only.
#define main soak_probe_unused_main
#include "../../scripts/audio-soak-probe.c"
#undef main
#include <assert.h>

int main(void) {
    float input[7*8],output[7*8];
    for(unsigned i=0;i<7*8;i++){input[i]=(float)i;output[i]=99;}
    AudioBufferList in={.mNumberBuffers=1,.mBuffers={{.mNumberChannels=8,.mDataByteSize=sizeof(input),.mData=input}}};
    AudioBufferList out={.mNumberBuffers=1,.mBuffers={{.mNumberChannels=8,.mDataByteSize=sizeof(output),.mData=output}}};
    AudioTimeStamp stamp={.mSampleTime=0,.mHostTime=1000,.mFlags=kAudioTimeStampSampleTimeValid|kAudioTimeStampHostTimeValid};
    Probe feeder={.feed=true,.rate=8000,.channels=8,.capacity=4};
    atomic_store(&feeder.enabled,true);
    callback(0,NULL,&in,&stamp,&out,&stamp,&feeder);
    assert(atomic_load(&feeder.signalFrames)==4 && atomic_load(&feeder.firstSignalHost)==1000);
    for(unsigned f=0;f<7;f++)for(unsigned c=0;c<8;c++){
        float expected=(f<4&&c<4)? .01f*cos(2*M_PI*(c<2?400:1000)*f/8000):0;
        assert(fabs(output[f*8+c]-expected)<1e-8);
    }
    stamp.mSampleTime=7;stamp.mHostTime=2000;
    callback(0,NULL,&in,&stamp,&out,&stamp,&feeder);
    for(unsigned i=0;i<7*8;i++)assert(output[i]==0);
    assert(atomic_load(&feeder.signalFrames)==4 && atomic_load(&feeder.discontinuities)==0);
    Probe recorder={.rate=8000,.hostScale=1e-9,.channels=8,.capacity=3};
    recorder.samples=calloc(3*8,sizeof(float));assert(recorder.samples);
    callback(0,NULL,&in,&stamp,&out,&stamp,&recorder);
    assert(atomic_load(&recorder.count)==3);
    assert(atomic_load(&recorder.firstSignalHost)==2000);
    for(unsigned i=0;i<3*8;i++)assert(recorder.samples[i]==input[i]);
    for(unsigned i=0;i<7*8;i++)assert(output[i]==0);
    stamp.mSampleTime=99;stamp.mHostTime=3000;
    callback(0,NULL,&in,&stamp,&out,&stamp,&recorder);
    assert(atomic_load(&recorder.discontinuities)==1);
    assert(recorder.firstDiscontinuityCallback==1 && recorder.discontinuityPriorSample==7
           && recorder.discontinuityNextSample==99 && recorder.discontinuityPriorFrames==7);
    callback(0,NULL,&in,NULL,&out,NULL,&recorder);
    assert(atomic_load(&recorder.invalidTimestamps)==1);
    free(recorder.samples);
    puts("soak probe synthetic callback contract passed; no HAL I/O performed");
    return 0;
}
