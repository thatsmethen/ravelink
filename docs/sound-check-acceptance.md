# Installed Sound Check acceptance

`RAVELINK_TEST_SOUND_CHECK=1 scripts/run-sound-check.sh` is an explicit test for a
disposable host with the named RaveLink CI virtual devices already installed.
It never installs a driver or selects a physical output. Ordinary test runs skip
the Swift hardware case.

The app's `EngineClient` starts one Sound Check channel and one explicit output,
`RaveLink.ci-mix-a_UID`. Its source is the fixed 440 Hz calibration tone. The
channel's effect gain starts at −12 dB while the clip is recorded; recording and
the ready state must produce silence. The test restores unity gain and loops the
clip, then adjusts gain to −12 dB during playback. Unity playback demonstrates
that the buffer contains dry audio. Stop and clear must silence playback, erase
the clip and leave no helper process after shutdown.

Two independent recorder processes capture the audition's first stereo pair
and `RaveLink.ci-mix-b_UID` as a separate guard output for 24 seconds. The verifier
requires ordered unity and −12 dB phases longer than two clip durations, expected
absolute levels, 440 Hz, equal stereo channels, bounded adjacent sample changes
through the loop seam, and final silence including partial tail samples. Its
fixed RMS envelope accommodates the documented five millisecond loop edge fades.
The guard pair must remain silent throughout. There is no gain fitting,
resampling or waveform alignment.

Raw captures, engine state events, recorder logs, per-component exit codes and
analysis are written as `build/sound-check-*`. Engine failure does not interrupt
the bounded recorders; all component failures preserve an overall failed result.
The 12 synthetic controls in `Drivers/tests/test_sound_check_verifier.py` validate
the instrument, including dry/wet confusion, wrong gain/frequency, hard seams,
dropouts, early recording leakage, guard leakage, stereo errors and partial tails.
They do not establish actual installed-device behavior.

The test observes one audition pair and one guard pair, not every possible system
endpoint. A generated input does not establish microphone permissions, physical
hardware capture compatibility, third-party effects behavior or long-session
stability. Installed-HAL acceptance requires matching raw captures and provenance
from a successful CI run.
