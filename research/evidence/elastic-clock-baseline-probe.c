#include "RaveLinkRealtime.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
int main(void) {
  const double offsets[]={-500,-250,-100,-50,0,50,100,250,500};
  const unsigned frames=256;
  float input[512],output[512];for(unsigned i=0;i<512;i++) input[i]=.125f;
  puts("ppm,seconds,produced,initialPrimingBlocks,lateZeroBlocks,dropped,underrun,firstLateZeroSeconds");
  for(unsigned c=0;c<sizeof(offsets)/sizeof(offsets[0]);c++){
    RLRing *r=rl_ring_create(65536);if(!r)return 1;
    double inputTime=0,outputTime=0,firstLate=-1;
    unsigned initial=0,late=0;unsigned long long produced=0;int primed=0;
    while(outputTime<180){
      if(inputTime<=outputTime){rl_ring_write(r,input,frames);inputTime+=frames/(48000*(1+offsets[c]/1e6));}
      else {
        unsigned n=rl_ring_read(r,output,frames,1);produced+=n;
        if(n)primed=1;
        else if(primed){late++;if(firstLate<0)firstLate=outputTime;}
        else initial++;
        outputTime+=frames/48000.;
      }
    }
    printf("%.0f,180,%llu,%u,%u,%llu,%llu,%.6f\n",offsets[c],produced,initial,late,(unsigned long long)rl_ring_dropped(r),(unsigned long long)rl_ring_underruns(r),firstLate);
    rl_ring_destroy(r);
  }
}
