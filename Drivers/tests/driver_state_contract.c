// Instrument controls only: mock every device-property access; never query HAL.
#include <CoreAudio/CoreAudio.h>
#include <assert.h>
#include <math.h>
#include <string.h>
static int mode;
static OSStatus fakeSize(AudioObjectID id,const AudioObjectPropertyAddress *a,UInt32 q,const void *qd,UInt32 *size) {
    (void)id;(void)a;(void)q;(void)qd;
    if(mode==0)return 7331;
    *size=mode==1?0:sizeof(AudioStreamID);return noErr;
}
static OSStatus fakeGet(AudioObjectID id,const AudioObjectPropertyAddress *a,UInt32 q,const void *qd,UInt32 *size,void *data) {
    (void)id;(void)q;(void)qd;(void)size;
    if(a->mSelector==kAudioDevicePropertyStreams){*(AudioStreamID*)data=17;return noErr;}
    if(a->mSelector==kAudioStreamPropertyVirtualFormat) {
        AudioStreamBasicDescription f={0};f.mSampleRate=mode==2?NAN:48000;f.mFormatID=kAudioFormatLinearPCM;
        f.mFormatFlags=kAudioFormatFlagIsFloat|kAudioFormatFlagIsPacked;f.mBitsPerChannel=32;f.mChannelsPerFrame=2;f.mBytesPerFrame=8;f.mFramesPerPacket=1;
        memcpy(data,&f,sizeof(f));return noErr;
    }
    return 7332;
}
static OSStatus fakeSet(AudioObjectID id,const AudioObjectPropertyAddress *a,UInt32 q,const void *qd,UInt32 size,const void *data) {
    (void)id;(void)a;(void)q;(void)qd;(void)size;(void)data;assert(!"No device mutations allowed in contract test");return 7333;
}
#define AudioObjectGetPropertyDataSize fakeSize
#define AudioObjectGetPropertyData fakeGet
#define AudioObjectSetPropertyData fakeSet
#define main observer_main
#include "../../scripts/driver-state-probe.c"
#undef main
int main(void) {
    AudioObjectID id=0;mode=0;assert(find("missing",&id)==7331&&id==0);
    char *arguments[]={"observer","missing"};assert(observer_main(2,arguments)==10);
    mode=1;assert(find("missing",&id)==noErr&&id==0);
    mode=2;assert(streams(17,kAudioObjectPropertyScopeInput,48000)==-1);
    mode=3;assert(streams(17,kAudioObjectPropertyScopeInput,48000)==2);
    puts("Driver lifecycle observer error, absence and NaN controls passed (mocked property API).");return 0;
}
