// Independent CoreAudio driver lifecycle observer. Does not start audio IO.
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static OSStatus get(AudioObjectID id, AudioObjectPropertySelector selector, AudioObjectPropertyScope scope, void *value, UInt32 *size) {
    AudioObjectPropertyAddress a={selector,scope,kAudioObjectPropertyElementMain};
    return AudioObjectGetPropertyData(id,&a,0,NULL,size,value);
}
static OSStatus find(const char *uid,AudioObjectID *found) {
    AudioObjectPropertyAddress a={kAudioHardwarePropertyDevices,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};UInt32 size=0;
    OSStatus status=AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,&a,0,NULL,&size);
    if(status)return status;if(size%sizeof(AudioObjectID))return kAudioHardwareUnspecifiedError;
    if(!size)return noErr;
    AudioObjectID *ids=malloc(size);if(!ids)return kAudioHardwareUnspecifiedError;
    status=AudioObjectGetPropertyData(kAudioObjectSystemObject,&a,0,NULL,&size,ids);if(status){free(ids);return status;}
    for(UInt32 i=0;i<size/sizeof(*ids);i++) {
        CFStringRef s=NULL;UInt32 n=sizeof(s);char text[2048]={0};
        status=get(ids[i],kAudioDevicePropertyDeviceUID,kAudioObjectPropertyScopeGlobal,&s,&n);
        if(status||!s){free(ids);return status?status:kAudioHardwareUnspecifiedError;}
        bool converted=CFStringGetCString(s,text,sizeof(text),kCFStringEncodingUTF8);CFRelease(s);
        if(!converted){free(ids);return kAudioHardwareUnspecifiedError;}
        if(!strcmp(text,uid)){*found=ids[i];break;}
    }
    free(ids);return noErr;
}
static void quoted(const char *s) {
    putchar('"');for(;*s;s++){unsigned char c=(unsigned char)*s;if(c=='"'||c=='\\')putchar('\\');if(c<32)printf("\\u%04x",c);else putchar(c);}putchar('"');
}
static int streams(AudioObjectID id,AudioObjectPropertyScope scope,double rate) {
    AudioObjectPropertyAddress a={kAudioDevicePropertyStreams,scope,kAudioObjectPropertyElementMain};UInt32 size=0;
    if(AudioObjectGetPropertyDataSize(id,&a,0,NULL,&size)||!size)return -1;
    AudioStreamID *ids=malloc(size);if(!ids)return -1;
    if(AudioObjectGetPropertyData(id,&a,0,NULL,&size,ids)){free(ids);return -1;}
    int channels=0;
    for(UInt32 i=0;i<size/sizeof(*ids);i++) {
        AudioStreamBasicDescription f={0};UInt32 n=sizeof(f);
        if(get(ids[i],kAudioStreamPropertyVirtualFormat,kAudioObjectPropertyScopeGlobal,&f,&n)||f.mFormatID!=kAudioFormatLinearPCM
           ||!(f.mFormatFlags&kAudioFormatFlagIsFloat)||!(f.mFormatFlags&kAudioFormatFlagIsPacked)||(f.mFormatFlags&kAudioFormatFlagIsBigEndian)
           ||f.mBitsPerChannel!=32||f.mFramesPerPacket!=1||!isfinite(f.mSampleRate)||fabs(f.mSampleRate-rate)>.01
           ||f.mBytesPerFrame!=4*((f.mFormatFlags&kAudioFormatFlagIsNonInterleaved)?1:f.mChannelsPerFrame)){free(ids);return -1;}
        channels+=(int)f.mChannelsPerFrame;
    }
    free(ids);return channels;
}
int main(int argc,char **argv) {
    // Rate mutation is confined to the two explicitly disposable lifecycle IDs.
    if(argc!=2&&argc!=3)return 2;
    const char *uid=argv[1];AudioObjectID id=0;OSStatus query=find(uid,&id);
    if(query){fprintf(stderr,"Device enumeration failed OSStatus=%d\n",(int)query);return 10;}
    if(!id){puts("{\"present\":false}");return 0;}
    UInt32 transport=0,n=sizeof(transport);
    if(get(id,kAudioDevicePropertyTransportType,kAudioObjectPropertyScopeGlobal,&transport,&n)||transport!=kAudioDeviceTransportTypeVirtual)return 3;
    if(argc==3) {
        if(strcmp(uid,"RaveLink.ci-lifecycle-a_UID")&&strcmp(uid,"RaveLink.ci-lifecycle-b_UID"))return 4;
        if(strcmp(argv[2],"44100")&&strcmp(argv[2],"48000"))return 4;
        double requested=atof(argv[2]);AudioObjectPropertyAddress a={kAudioDevicePropertyNominalSampleRate,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
        OSStatus error=AudioObjectSetPropertyData(id,&a,0,NULL,sizeof(requested),&requested);
        if(error){fprintf(stderr,"Set sample rate OSStatus=%d\n",(int)error);return 5;}
        for(int i=0;i<100;i++){double rate=0;n=sizeof(rate);if(!get(id,kAudioDevicePropertyNominalSampleRate,kAudioObjectPropertyScopeGlobal,&rate,&n)&&rate==requested&&streams(id,kAudioObjectPropertyScopeInput,rate)>=0&&streams(id,kAudioObjectPropertyScopeOutput,rate)>=0)break;usleep(50000);}
    }
    double rate=0;n=sizeof(rate);if(get(id,kAudioDevicePropertyNominalSampleRate,kAudioObjectPropertyScopeGlobal,&rate,&n)||!isfinite(rate))return 6;
    int input=streams(id,kAudioObjectPropertyScopeInput,rate),output=streams(id,kAudioObjectPropertyScopeOutput,rate);if(input<0||output<0)return 7;
    UInt32 frames=0;n=sizeof(frames);if(get(id,kAudioDevicePropertyBufferFrameSize,kAudioObjectPropertyScopeGlobal,&frames,&n))return 8;
    CFStringRef s=NULL;n=sizeof(s);char name[2048]={0};
    if(get(id,kAudioObjectPropertyName,kAudioObjectPropertyScopeGlobal,&s,&n)||!s)return 9;
    CFStringGetCString(s,name,sizeof(name),kCFStringEncodingUTF8);CFRelease(s);
    printf("{\"present\":true,\"uid\":");quoted(uid);printf(",\"name\":");quoted(name);
    printf(",\"sampleRate\":%.0f,\"inputChannels\":%d,\"outputChannels\":%d,\"bufferFrames\":%u,\"format\":\"packed native Float32 PCM\"}\n",rate,input,output,frames);
    return 0;
}
