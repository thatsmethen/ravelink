// Instrument only: calls an actual built bundle in a private process, no HAL install.
#define main original_contract_main
#include "../../Drivers/tests/driver_contract.c"
#undef main

static void transfer(Instance instance, bool writing, uint64_t sample, unsigned frames, float *data) {
    AudioServerPlugInIOCycleInfo cycle={0};
    cycle.mOutputTime.mSampleTime=cycle.mInputTime.mSampleTime=cycle.mCurrentTime.mSampleTime=(double)sample;
    assert((*instance.driver)->DoIOOperation(instance.driver,3,writing?7:4,writing?1:2,
           writing?kAudioServerPlugInIOOperationWriteMix:kAudioServerPlugInIOOperationReadInput,
           frames,&cycle,data,NULL)==noErr);
}
int main(int argc,const char **argv) {
    assert(argc==4);Instance instance=open_instance(argv[1],argv[2],argv[3]);
    const unsigned frames=512;size_t count=frames*instance.channels;
    float *data=calloc(count,sizeof(float)),*read=calloc(count,sizeof(float));assert(data&&read);
    // Old generation at slot512 is a distinctive nonzero sentinel.
    for(size_t i=0;i<count;i++)data[i]=0.125f;
    transfer(instance,true,512,frames,data);
    // Next ring generation writes on either side, skipping slot512 entirely.
    for(size_t i=0;i<count;i++)data[i]=0.25f;
    transfer(instance,true,65536,frames,data);
    for(size_t i=0;i<count;i++)data[i]=0.5f;
    transfer(instance,true,65536+1024,frames,data);
    transfer(instance,false,65536+1024,frames,read);
    assert(memcmp(data,read,count*sizeof(float))==0); // Positive current-generation control.
    transfer(instance,false,65536+512,frames,read);
    size_t stale=0;float peak=0;
    for(size_t i=0;i<count;i++){if(read[i]==0.125f)stale++;peak=fmaxf(peak,fabsf(read[i]));}
    // The existing future-read guard still works; it does not validate the hole.
    transfer(instance,false,65536+2048,frames,read);
    for(size_t i=0;i<count;i++)assert(read[i]==0);
    printf("{\"evidence\":\"Actual bundle in-process simulated missed write; no HAL installation or real callback scheduling\",\"ringFrames\":65536,\"blockFrames\":512,\"channels\":%u,\"skippedReadSample\":66048,\"staleSentinelSamples\":%zu,\"totalSamples\":%zu,\"skippedIntervalPeak\":%.9g,\"expectedSilence\":%s,\"currentWriteControlPassed\":true,\"futureReadSilenceControlPassed\":true}\n",instance.channels,stale,count,peak,peak==0?"true":"false");
    assert((*instance.driver)->StopIO(instance.driver,3,1)==noErr);assert((*instance.driver)->StopIO(instance.driver,3,2)==noErr);
    free(data);free(read);dlclose(instance.handle);return 0;
}
