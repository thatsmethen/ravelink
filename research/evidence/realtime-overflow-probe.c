#include "RaveLinkRealtime.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
int main(void) {
    RLDSP *d = rl_dsp_create(48000);
    rl_dsp_controls(d, 24, 100, -80, -20, 4);
    float warmup[1024]; for (int i=0;i<1024;i++) warmup[i]=0.1f;
    rl_dsp_process(d,warmup,512);
    float spike[2]={FLT_MAX,FLT_MAX}; rl_dsp_process(d,spike,1);
    float recovery[1024]; for (int i=0;i<1024;i++) recovery[i]=0.1f;
    rl_dsp_process(d,recovery,512);
    int invalid=0; for(int i=0;i<1024;i++) if(!isfinite(recovery[i])) invalid++;
    printf("spike_finite=%d recovery_nonfinite_samples=%d last=%g\n",isfinite(spike[0]),invalid,recovery[1023]);
    rl_dsp_destroy(d); return 0;
}
