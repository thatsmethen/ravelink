# Product decisions and acceptance

## Reference and independent implementation

RaveLink targets Wave Link 3's input-by-mix routing workflow on macOS. The research ledger in `research/` separates documented claims, static observations, runtime observations and independent candidate checks. Elgato binaries and assets stay outside source control. Names and visual assets are independent.

## Initial design decisions

The matrix keeps every input's destination visible. Inputs are rows; personal, stream and voice-chat mixes are columns. New routes start off to avoid accidental microphone broadcast or feedback. Every destination is explicitly selected; the app does not change system default audio devices. An unconfigured destination is shown as such, never as an active output.

No input or mix count is imposed by the UI or session model. Horizontal and vertical scrolling keep the layout usable as sessions grow. Hardware channel counts and CPU limits remain real limits; a large session model test is not a sustained audio capacity claim.

Effects belong to the input and therefore affect every mix; mix sends retain independent gain and pan. The initial chain is input gain, high-pass, gate and compression. Third-party Audio Units and richer EQ are acceptance items, not implied by the existence of built-in controls.

Session saves are atomic and versioned; invalid imports leave the running session unchanged. Audio starts explicitly rather than broadcasting automatically at login. The stop control is always visible.

## Journeys to inspect in the actual app

1. Empty studio → add a hardware/application input → choose destination → enable route → start → observe real meter → stop.
2. Independent levels across two mixes; mute/solo; effects; return to matrix.
3. Add and remove more than eight inputs and five mixes; keyboard navigation and scrolling.
4. Save/relaunch/export/import, corrupt file rejection and visible recovery.
5. Missing device and denied capture permission; no false running or false silent success.
6. Virtual stream device visible to an independent receiver and captured samples match expected route.
7. Device loss/reconnect, sleep/wake, long run, overload and plugin failure.

Each journey needs a recorded outcome. Compiling and deterministic tests alone do not close runtime journeys.
