// SPDX-License-Identifier: GPL-3.0-only
#define main original_contract_main
#include "driver_contract.c"
#undef main
#include "../patches/RaveLinkDiagnostics.h"

static RLDriverDiagnostics diagnostics(Instance v) {
    AudioObjectPropertyAddress property={RL_DRIVER_DIAGNOSTIC_SELECTOR,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    UInt32 size=0;
    assert((*v.driver)->GetPropertyDataSize(v.driver,3,0,&property,0,NULL,&size)==noErr);
    assert(size==sizeof(CFPropertyListRef));
    CFPropertyListRef object=NULL;UInt32 actual=0;
    assert((*v.driver)->GetPropertyData(v.driver,3,0,&property,0,NULL,size,&actual,&object)==noErr);
    assert(actual==size&&object&&CFGetTypeID(object)==CFDataGetTypeID());
    assert(CFDataGetLength((CFDataRef)object)==sizeof(RLDriverDiagnostics));
    RLDriverDiagnostics result;memcpy(&result,CFDataGetBytePtr((CFDataRef)object),sizeof(result));CFRelease(object);
    assert(result.version==RL_DRIVER_DIAGNOSTIC_VERSION&&result.bytes==sizeof(result)&&result.channels==v.channels);
    return result;
}
static void operation(Instance v,bool write,UInt64 sample,UInt64 counter) {
    float data[512*256];for(unsigned i=0;i<512*v.channels;i++)data[i]=0.25f;
    AudioServerPlugInIOCycleInfo cycle={0};
    cycle.mInputTime.mSampleTime=cycle.mOutputTime.mSampleTime=cycle.mCurrentTime.mSampleTime=sample;
    cycle.mInputTime.mHostTime=cycle.mOutputTime.mHostTime=sample+1234;cycle.mIOCycleCounter=counter;
    assert((*v.driver)->DoIOOperation(v.driver,3,write?7:4,write?1:2,write?kAudioServerPlugInIOOperationWriteMix:kAudioServerPlugInIOOperationReadInput,512,&cycle,data,NULL)==noErr);
}
int main(int argc,const char **argv) {
    assert(argc==5);Instance v=open_instance(argv[1],argv[2],argv[3]);bool enabled=atoi(argv[4])!=0;
    AudioObjectPropertyAddress property={RL_DRIVER_DIAGNOSTIC_SELECTOR,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    assert((*v.driver)->HasProperty(v.driver,3,0,&property)==enabled);
    if(enabled) {
        Boolean settable=true;assert((*v.driver)->IsPropertySettable(v.driver,3,0,&property,&settable)==noErr&&!settable);
        AudioObjectPropertyAddress list={kAudioObjectPropertyCustomPropertyInfoList,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
        AudioServerPlugInCustomPropertyInfo info={0};UInt32 actual=0;
        assert((*v.driver)->GetPropertyData(v.driver,3,0,&list,0,NULL,sizeof(info),&actual,&info)==noErr);
        assert(actual==sizeof(info)&&info.mSelector==RL_DRIVER_DIAGNOSTIC_SELECTOR&&info.mPropertyDataType==kAudioServerPlugInCustomPropertyDataTypeCFPropertyList);
        RLDriverDiagnostics initial=diagnostics(v);assert(initial.startAllocations==1&&initial.readCalls==0&&initial.writeCalls==0);
        operation(v,true,512,1);operation(v,true,65536,2);operation(v,true,66560,3);operation(v,false,66048,2);
        RLDriverDiagnostics hole=diagnostics(v);
        assert(hole.writeCalls==3&&hole.writeFrames==1536&&hole.readCalls==1&&hole.readFrames==512);
        assert(hole.frameCounts[RLDiagSampleMismatch]==512&&hole.blockCounts[RLDiagSampleMismatch]==1);
        RLDriverDiagnosticEvent first=hole.events[RLDiagSampleMismatch][0];
        assert(first.present&&first.requestedFrame==66048&&first.slotSample==512&&first.writeEnd==67072&&first.clientID==2);
        for(unsigned i=0;i<8;i++)operation(v,false,70000+i*512,100-i);
        RLDriverDiagnostics future=diagnostics(v);
        assert(future.blockCounts[RLDiagFutureWindow]==8&&future.frameCounts[RLDiagFutureWindow]==4096);
        assert(future.blockCounts[RLDiagWriterCycleReset]==0);
        for(unsigned i=0;i<RL_DRIVER_DIAGNOSTIC_SNAPSHOTS;i++)assert(future.events[RLDiagFutureWindow][i].present);
        assert(memcmp(&first,&future.events[RLDiagSampleMismatch][0],sizeof(first))==0);
        operation(v,true,67072,10);operation(v,true,67584,1);operation(v,false,67072,1);
        RLDriverDiagnostics reset=diagnostics(v);
        assert(reset.blockCounts[RLDiagWriterCycleReset]==1&&reset.frameCounts[RLDiagGenerationMismatch]==512);
        assert(reset.events[RLDiagWriterCycleReset][0].priorCycle==10&&reset.events[RLDiagWriterCycleReset][0].cycle==1);
        operation(v,true,512,2);assert(diagnostics(v).blockCounts[RLDiagWriterTimeRewind]==1);
        assert((*v.driver)->StopIO(v.driver,3,1)==noErr);assert((*v.driver)->StopIO(v.driver,3,2)==noErr);
        assert(diagnostics(v).writeCalls==6); // Read-only query still works after IO stops.
        assert((*v.driver)->StartIO(v.driver,3,1)==noErr);assert((*v.driver)->StartIO(v.driver,3,2)==noErr);
        assert(diagnostics(v).startAllocations==2&&diagnostics(v).writeCalls==6); // Lifetime counts never silently reset.
    }
    assert((*v.driver)->StopIO(v.driver,3,1)==noErr);assert((*v.driver)->StopIO(v.driver,3,2)==noErr);dlclose(v.handle);
    puts(enabled?"PASS: diagnostic CFPropertyList/CFData ABI, read-only property, bounded immutable snapshots, reason counters, reader/writer cycle distinction, lifetime persistence.":"PASS: diagnostic property absent in normal build.");
}
