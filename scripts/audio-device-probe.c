// Independent CoreAudio/HAL probe. No RaveLink engine code is linked.
// It never changes default devices, sample rates, or device volume.
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>

typedef struct {
    _Atomic uint64_t callbacks, outputFrames, capturedFrames;
    float *samples;
    uint64_t capacity;
} Probe;
static uint32_t frames(const AudioBufferList *list) {
    if (!list) return 0;
    for (UInt32 b=0;b<list->mNumberBuffers;b++) {
        const AudioBuffer *p=&list->mBuffers[b];
        if(p->mData && p->mNumberChannels) return p->mDataByteSize/(4*p->mNumberChannels);
    }
    return 0;
}
static float sample(const AudioBufferList *list, UInt32 channel, UInt32 frame) {
    for (UInt32 b=0;b<list->mNumberBuffers;b++) {
        const AudioBuffer *p=&list->mBuffers[b];
        if(channel<p->mNumberChannels) {
            uint64_t i=(uint64_t)frame*p->mNumberChannels+channel;
            return p->mData && (i+1)*4<=p->mDataByteSize ? ((float*)p->mData)[i] : 0;
        }
        channel-=p->mNumberChannels;
    }
    return 0;
}
static OSStatus callback(AudioObjectID d,const AudioTimeStamp*n,const AudioBufferList*i,const AudioTimeStamp*t,AudioBufferList*o,const AudioTimeStamp*u,void*ctx) {
    Probe *p=ctx;
    atomic_fetch_add_explicit(&p->callbacks,1,memory_order_relaxed);
    atomic_fetch_add_explicit(&p->outputFrames,frames(o),memory_order_relaxed);
    // Duplex registration contributes silence only; no signal is generated here.
    if(o) for(UInt32 b=0;b<o->mNumberBuffers;b++) if(o->mBuffers[b].mData) memset(o->mBuffers[b].mData,0,o->mBuffers[b].mDataByteSize);
    if(p->samples && i) {
        uint64_t offset=atomic_load_explicit(&p->capturedFrames,memory_order_relaxed);
        uint32_t count=frames(i); if(count>p->capacity-offset) count=(uint32_t)(p->capacity-offset);
        for(uint32_t f=0;f<count;f++) { p->samples[(offset+f)*2]=sample(i,0,f); p->samples[(offset+f)*2+1]=sample(i,1,f); }
        atomic_store_explicit(&p->capturedFrames,offset+count,memory_order_release);
    }
    return noErr;
}
static void stringProperty(AudioObjectID object, AudioObjectPropertySelector selector, char*text, size_t count) {
    AudioObjectPropertyAddress a={selector,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    CFStringRef value=NULL; UInt32 size=sizeof(value); text[0]=0;
    if(!AudioObjectGetPropertyData(object,&a,0,NULL,&size,&value) && value) { CFStringGetCString(value,text,count,kCFStringEncodingUTF8); CFRelease(value); }
}
static int writeWave(const char *path, Probe *probe, double rate) {
    uint64_t count=atomic_load(&probe->capturedFrames), length=count*8;
    if(length>UINT32_MAX-36) return 1;
    FILE *f=fopen(path,"wb"); if(!f) return 1;
    uint32_t chunk=(uint32_t)length+36, fmt=16, sr=(uint32_t)rate, byteRate=sr*8, data=(uint32_t)length;
    uint16_t format=3, channels=2, block=8, bits=32;
    fwrite("RIFF",1,4,f); fwrite(&chunk,4,1,f); fwrite("WAVEfmt ",1,8,f); fwrite(&fmt,4,1,f);
    fwrite(&format,2,1,f); fwrite(&channels,2,1,f); fwrite(&sr,4,1,f); fwrite(&byteRate,4,1,f); fwrite(&block,2,1,f); fwrite(&bits,2,1,f);
    fwrite("data",1,4,f); fwrite(&data,4,1,f); fwrite(probe->samples,1,(size_t)length,f);
    return fclose(f);
}
int main(int argc,char**argv) {
    setbuf(stdout,NULL);
    const char *uid=NULL,*name=NULL,*wav=NULL,*ready=NULL; double seconds=0; int list=0,capture=0;
    for(int a=1;a<argc;a++) {
        if(!strcmp(argv[a],"--list")) list=1;
        else if(a+1<argc && !strcmp(argv[a],"--uid")) uid=argv[++a];
        else if(a+1<argc && !strcmp(argv[a],"--name")) name=argv[++a];
        else if(a+1<argc && !strcmp(argv[a],"--silent-seconds")) seconds=atof(argv[++a]);
        else if(a+1<argc && !strcmp(argv[a],"--capture-seconds")) { seconds=atof(argv[++a]); capture=1; }
        else if(a+1<argc && !strcmp(argv[a],"--wav")) wav=argv[++a];
        else if(a+1<argc && !strcmp(argv[a],"--ready-file")) ready=argv[++a];
        else { fprintf(stderr,"Unknown or incomplete argument: %s\n",argv[a]); return 2; }
    }
    if((!list && !uid && !name) || seconds<0 || seconds>60 || !isfinite(seconds) || (capture && (!wav || seconds<=0))) {
        fprintf(stderr,"Use --list, --uid UID, or --name NAME; optionally --silent-seconds 1 or --capture-seconds 10 --wav capture.wav [--ready-file ready].\n"); return 2;
    }
    AudioObjectPropertyAddress a={kAudioHardwarePropertyDevices,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain}; UInt32 size=0;
    OSStatus status=AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,&a,0,NULL,&size); printf("enumerate-size status=%d\n",status); if(status) return 3;
    AudioObjectID *ids=malloc(size); if(!ids) return 3;
    status=AudioObjectGetPropertyData(kAudioObjectSystemObject,&a,0,NULL,&size,ids); if(status) { free(ids); return 3; }
    AudioObjectID device=0;
    for(unsigned j=0;j<size/sizeof(AudioObjectID);j++) {
        char n[1024],u[1024]; stringProperty(ids[j],kAudioObjectPropertyName,n,sizeof(n)); stringProperty(ids[j],kAudioDevicePropertyDeviceUID,u,sizeof(u));
        if(list || (uid && !strcmp(uid,u)) || (name && !strcmp(name,n))) printf("device id=%u uid=%s name=%s\n",ids[j],u,n);
        if((uid && !strcmp(uid,u)) || (name && !strcmp(name,n))) device=ids[j];
    }
    free(ids); if(list && !uid && !name) return 0; if(!device) { fprintf(stderr,"No matching device\n"); return 4; }
    double rate=0; size=sizeof(rate); a.mSelector=kAudioDevicePropertyNominalSampleRate;
    status=AudioObjectGetPropertyData(device,&a,0,NULL,&size,&rate); if(status || rate<8000 || rate>384000) return 5;
    Probe probe={0};
    if(capture) { probe.capacity=(uint64_t)ceil(rate*seconds); probe.samples=calloc(probe.capacity*2,sizeof(float)); if(!probe.samples)return 5; }
    printf("register-start rate=%.0f\n",rate); AudioDeviceIOProcID proc=NULL;
    status=AudioDeviceCreateIOProcID(device,callback,&probe,&proc); printf("register-return status=%d\n",status); if(status) {free(probe.samples); return 6;}
    if(seconds>0) {
        printf("start-begin\n"); status=AudioDeviceStart(device,proc); printf("start-return status=%d\n",status);
        if(status) {AudioDeviceDestroyIOProcID(device,proc);free(probe.samples);return 7;}
        if(ready) {FILE*f=fopen(ready,"w");if(f){fprintf(f,"ready\n");fclose(f);}}
        usleep((useconds_t)(seconds*1000000));
        printf("stop-begin\n"); status=AudioDeviceStop(device,proc); printf("stop-return status=%d\n",status);
    }
    OSStatus destroyed=AudioDeviceDestroyIOProcID(device,proc); printf("unregister-return status=%d\n",destroyed);
    printf("telemetry callbacks=%llu outputFrames=%llu capturedFrames=%llu\n",(unsigned long long)atomic_load(&probe.callbacks),(unsigned long long)atomic_load(&probe.outputFrames),(unsigned long long)atomic_load(&probe.capturedFrames));
    if(!destroyed && capture) { if(writeWave(wav,&probe,rate)) {free(probe.samples);return 8;} printf("capture-wav %s\n",wav); }
    if(!destroyed) free(probe.samples); // Never free a context still owned by HAL.
    return status || destroyed ? 9 : 0;
}
