// Independent installed-HAL acceptance instrument: no RaveLink code is linked.
// Only explicitly named virtual devices are accepted. No default/rate changes.
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach_time.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef struct {
    bool feed;
    double rate, hostScale;
    uint32_t channels;
    uint64_t capacity;
    float *samples;
    _Atomic bool enabled;
    _Atomic uint64_t callbacks, count, signalFrames, firstHost, firstSignalHost, discontinuities, invalidTimestamps;
    uint64_t priorHost;
    double priorSample;
    uint32_t priorFrames;
    bool havePrior;
    uint32_t minBlock, maxBlock;
} Probe;
static uint32_t blockFrames(const AudioBufferList *list) {
    uint32_t frames=UINT32_MAX;
    if(list) for(UInt32 b=0;b<list->mNumberBuffers;b++) {
        const AudioBuffer *p=&list->mBuffers[b];
        if(p->mData && p->mNumberChannels) {
            uint32_t n=p->mDataByteSize/(4*p->mNumberChannels); if(n<frames)frames=n;
        }
    }
    return frames==UINT32_MAX?0:frames;
}
static float readSample(const AudioBufferList *list,uint32_t channel,uint32_t frame) {
    if(list)for(UInt32 b=0;b<list->mNumberBuffers;b++) {
        const AudioBuffer *p=&list->mBuffers[b];
        if(channel<p->mNumberChannels) {
            uint64_t i=(uint64_t)frame*p->mNumberChannels+channel;
            return p->mData && (i+1)*4<=p->mDataByteSize?((float*)p->mData)[i]:0;
        }
        channel-=p->mNumberChannels;
    }
    return 0;
}
static void writeSample(AudioBufferList *list,uint32_t channel,uint32_t frame,float sample) {
    if(list)for(UInt32 b=0;b<list->mNumberBuffers;b++) {
        AudioBuffer *p=&list->mBuffers[b];
        if(channel<p->mNumberChannels) {
            uint64_t i=(uint64_t)frame*p->mNumberChannels+channel;
            if(p->mData && (i+1)*4<=p->mDataByteSize)((float*)p->mData)[i]=sample;
            return;
        }
        channel-=p->mNumberChannels;
    }
}
static OSStatus callback(AudioObjectID device,const AudioTimeStamp *now,const AudioBufferList *input,const AudioTimeStamp *inputTime,AudioBufferList *output,const AudioTimeStamp *outputTime,void *context) {
    (void)device;(void)now;
    Probe *p=context;
    if(output)for(UInt32 b=0;b<output->mNumberBuffers;b++)if(output->mBuffers[b].mData)memset(output->mBuffers[b].mData,0,output->mBuffers[b].mDataByteSize);
    uint32_t frames=blockFrames(p->feed?output:input); if(!frames)return noErr;
    const AudioTimeStamp *stamp=p->feed?outputTime:inputTime;
    uint64_t sequence=atomic_fetch_add(&p->callbacks,1);
    if(!sequence || frames<p->minBlock)p->minBlock=frames;
    if(frames>p->maxBlock)p->maxBlock=frames;
    bool timestamp=stamp && (stamp->mFlags&kAudioTimeStampHostTimeValid) && (stamp->mFlags&kAudioTimeStampSampleTimeValid);
    if(!timestamp)atomic_fetch_add(&p->invalidTimestamps,1);
    else {
        if(!sequence)atomic_store(&p->firstHost,stamp->mHostTime);
        if(p->havePrior && (stamp->mHostTime<=p->priorHost || fabs(stamp->mSampleTime-p->priorSample-p->priorFrames)>.5))atomic_fetch_add(&p->discontinuities,1);
        p->priorHost=stamp->mHostTime;p->priorSample=stamp->mSampleTime;p->priorFrames=frames;p->havePrior=true;
    }
    if(p->feed) {
        if(!atomic_load_explicit(&p->enabled,memory_order_acquire))return noErr;
        uint64_t at=atomic_load(&p->signalFrames);
        uint32_t count=frames; if(count>p->capacity-at)count=(uint32_t)(p->capacity-at);
        if(!at && timestamp)atomic_store(&p->firstSignalHost,stamp->mHostTime);
        for(uint32_t f=0;f<count;f++) {
            // Two source pairs with distinct frequencies; identical stereo polarity.
            float a=.01f*cos(2*M_PI*400*(at+f)/p->rate);
            float b=.01f*cos(2*M_PI*1000*(at+f)/p->rate);
            writeSample(output,0,f,a);writeSample(output,1,f,a);
            writeSample(output,2,f,b);writeSample(output,3,f,b);
        }
        atomic_store_explicit(&p->signalFrames,at+count,memory_order_release);
    } else {
        uint64_t at=atomic_load(&p->count);
        uint32_t count=frames; if(count>p->capacity-at)count=(uint32_t)(p->capacity-at);
        for(uint32_t f=0;f<count;f++)for(uint32_t c=0;c<p->channels;c++)p->samples[(at+f)*p->channels+c]=readSample(input,c,f);
        atomic_store_explicit(&p->count,at+count,memory_order_release);
    }
    return noErr;
}
static OSStatus property(AudioObjectID object,AudioObjectPropertySelector selector,AudioObjectPropertyScope scope,void *value,UInt32 *size) {
    AudioObjectPropertyAddress address={selector,scope,kAudioObjectPropertyElementMain};
    return AudioObjectGetPropertyData(object,&address,0,NULL,size,value);
}
static AudioObjectID findDevice(const char *uid) {
    AudioObjectPropertyAddress address={kAudioHardwarePropertyDevices,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};UInt32 size=0;
    if(AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,&address,0,NULL,&size))return 0;
    AudioObjectID *devices=malloc(size);if(!devices)return 0;
    if(AudioObjectGetPropertyData(kAudioObjectSystemObject,&address,0,NULL,&size,devices)){free(devices);return 0;}
    AudioObjectID result=0;
    for(UInt32 i=0;i<size/sizeof(*devices);i++) {
        CFStringRef value=NULL;UInt32 n=sizeof(value);char text[2048]={0};
        if(!property(devices[i],kAudioDevicePropertyDeviceUID,kAudioObjectPropertyScopeGlobal,&value,&n)&&value) {
            CFStringGetCString(value,text,sizeof(text),kCFStringEncodingUTF8);CFRelease(value);
            if(!strcmp(uid,text)){result=devices[i];break;}
        }
    }
    free(devices);return result;
}
static bool validFormat(AudioObjectID device,AudioObjectPropertyScope scope,uint32_t minimum,double rate) {
    AudioObjectPropertyAddress address={kAudioDevicePropertyStreams,scope,kAudioObjectPropertyElementMain};UInt32 size=0;
    if(AudioObjectGetPropertyDataSize(device,&address,0,NULL,&size)||!size)return false;
    AudioStreamID *streams=malloc(size);if(!streams)return false;
    if(AudioObjectGetPropertyData(device,&address,0,NULL,&size,streams)){free(streams);return false;}
    uint32_t channels=0;bool valid=true;
    for(UInt32 i=0;i<size/sizeof(*streams);i++) {
        AudioStreamBasicDescription f={0};UInt32 n=sizeof(f);
        if(property(streams[i],kAudioStreamPropertyVirtualFormat,kAudioObjectPropertyScopeGlobal,&f,&n)
           ||f.mFormatID!=kAudioFormatLinearPCM||!(f.mFormatFlags&kAudioFormatFlagIsFloat)
           ||!(f.mFormatFlags&kAudioFormatFlagIsPacked)||(f.mFormatFlags&kAudioFormatFlagIsBigEndian)
           ||f.mBitsPerChannel!=32||f.mFramesPerPacket!=1||fabs(f.mSampleRate-rate)>.01
           ||f.mBytesPerFrame!=4*((f.mFormatFlags&kAudioFormatFlagIsNonInterleaved)?1:f.mChannelsPerFrame))valid=false;
        channels+=f.mChannelsPerFrame;
    }
    free(streams);return valid&&channels>=minimum;
}
static int wave(const char *path,Probe *p) {
    uint64_t bytes=atomic_load(&p->count)*p->channels*4;if(bytes>UINT32_MAX-36)return 1;
    FILE*f=fopen(path,"wb");if(!f)return 1;
    uint32_t length=(uint32_t)bytes+36,fmt=16,rate=(uint32_t)p->rate,byteRate=rate*p->channels*4,data=(uint32_t)bytes;
    uint16_t code=3,channels=(uint16_t)p->channels,align=channels*4,bits=32;
    fwrite("RIFF",1,4,f);fwrite(&length,4,1,f);fwrite("WAVEfmt ",1,8,f);fwrite(&fmt,4,1,f);
    fwrite(&code,2,1,f);fwrite(&channels,2,1,f);fwrite(&rate,4,1,f);fwrite(&byteRate,4,1,f);fwrite(&align,2,1,f);fwrite(&bits,2,1,f);
    fwrite("data",1,4,f);fwrite(&data,4,1,f);fwrite(p->samples,1,(size_t)bytes,f);
    int bad=ferror(f);return fclose(f)||bad;
}
static bool touch(const char *path) {FILE*f=fopen(path,"w");if(!f)return false;fputs("ready\n",f);return fclose(f)==0;}
static double monotonicSeconds(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
int main(int argc,char **argv) {
    setbuf(stdout,NULL);
    const char *mode=NULL,*uid=NULL,*wav=NULL,*report=NULL,*ready=NULL,*go=NULL;double seconds=0;
    for(int i=1;i<argc;i++) {
        if(i+1<argc&&!strcmp(argv[i],"--mode"))mode=argv[++i];
        else if(i+1<argc&&!strcmp(argv[i],"--uid"))uid=argv[++i];
        else if(i+1<argc&&!strcmp(argv[i],"--seconds"))seconds=atof(argv[++i]);
        else if(i+1<argc&&!strcmp(argv[i],"--wav"))wav=argv[++i];
        else if(i+1<argc&&!strcmp(argv[i],"--report"))report=argv[++i];
        else if(i+1<argc&&!strcmp(argv[i],"--ready-file"))ready=argv[++i];
        else if(i+1<argc&&!strcmp(argv[i],"--go-file"))go=argv[++i];
        else {fprintf(stderr,"Unknown/incomplete argument %s\n",argv[i]);return 2;}
    }
    bool feed=mode&&!strcmp(mode,"feed");
    if(!uid||!report||!ready||!isfinite(seconds)||seconds<1||seconds>60||(!feed&&(!mode||strcmp(mode,"record")||!wav))||(feed&&!go))return 2;
    AudioObjectID device=findDevice(uid);if(!device){fprintf(stderr,"Missing named device\n");return 3;}
    UInt32 transport=0,n=sizeof(transport);
    if(property(device,kAudioDevicePropertyTransportType,kAudioObjectPropertyScopeGlobal,&transport,&n)||transport!=kAudioDeviceTransportTypeVirtual){fprintf(stderr,"Refusing non-virtual device\n");return 4;}
    Probe p={0};p.feed=feed;p.channels=8;n=sizeof(p.rate);
    if(property(device,kAudioDevicePropertyNominalSampleRate,kAudioObjectPropertyScopeGlobal,&p.rate,&n)||!isfinite(p.rate)||p.rate<8000||p.rate>96000||floor(p.rate)!=p.rate)return 5;
    if(!validFormat(device,feed?kAudioObjectPropertyScopeOutput:kAudioObjectPropertyScopeInput,8,p.rate)){fprintf(stderr,"Expected at least eight packed Float32 channels\n");return 5;}
    mach_timebase_info_data_t timebase;mach_timebase_info(&timebase);p.hostScale=(double)timebase.numer/timebase.denom*1e-9;
    p.capacity=(uint64_t)ceil(seconds*p.rate);
    if(!feed){p.samples=calloc(p.capacity*p.channels,sizeof(float));if(!p.samples)return 6;}
    UInt32 bufferFrames=0;n=sizeof(bufferFrames);property(device,kAudioDevicePropertyBufferFrameSize,kAudioObjectPropertyScopeGlobal,&bufferFrames,&n);
    AudioDeviceIOProcID proc=NULL;OSStatus status=AudioDeviceCreateIOProcID(device,callback,&p,&proc);if(status){fprintf(stderr,"Register %d\n",status);return 7;}
    status=AudioDeviceStart(device,proc);if(status){AudioDeviceDestroyIOProcID(device,proc);return 8;}
    bool okay=touch(ready);double deadline=monotonicSeconds()+60;
    if(feed) {
        while(okay&&access(go,F_OK)&&monotonicSeconds()<deadline)usleep(10000);
        if(access(go,F_OK))okay=false;
        if(okay){atomic_store_explicit(&p.enabled,true,memory_order_release);deadline=monotonicSeconds()+seconds+5;}
    } else deadline=monotonicSeconds()+seconds+5;
    while(okay&&atomic_load(feed?&p.signalFrames:&p.count)<p.capacity&&monotonicSeconds()<deadline)usleep(10000);
    if(atomic_load(feed?&p.signalFrames:&p.count)!=p.capacity)okay=false;
    OSStatus stopped=AudioDeviceStop(device,proc),destroyed=AudioDeviceDestroyIOProcID(device,proc);
    if(stopped||destroyed){fprintf(stderr,"Stop %d destroy %d\n",stopped,destroyed);return 9;}
    if(!feed&&wave(wav,&p))okay=false;
    FILE*f=fopen(report,"w");if(!f)return 10;
    fprintf(f,"{\"mode\":\"%s\",\"sampleRate\":%.0f,\"channels\":%u,\"configuredBufferFrames\":%u,\"minBlockFrames\":%u,\"maxBlockFrames\":%u,\"frames\":%llu,\"callbacks\":%llu,\"firstFrameHostSeconds\":%.9f,\"firstSignalHostSeconds\":%.9f,\"timestampDiscontinuities\":%llu,\"invalidTimestamps\":%llu,\"complete\":%s}\n",mode,p.rate,p.channels,bufferFrames,p.minBlock,p.maxBlock,(unsigned long long)atomic_load(feed?&p.signalFrames:&p.count),(unsigned long long)atomic_load(&p.callbacks),atomic_load(&p.firstHost)*p.hostScale,atomic_load(&p.firstSignalHost)*p.hostScale,(unsigned long long)atomic_load(&p.discontinuities),(unsigned long long)atomic_load(&p.invalidTimestamps),okay?"true":"false");
    if(fclose(f))okay=false;free(p.samples);return okay?0:11;
}
