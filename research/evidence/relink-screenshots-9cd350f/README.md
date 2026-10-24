# ReLink native screenshots — 24 October 2026

The public [mixer screenshot](../../../docs/screenshots/mixer-macos.png) and
[mix-effects screenshot](../../../docs/screenshots/mix-effects-macos.png) are
unedited native macOS captures of ReLink source commit
`9cd350fcae96c5043da877b718aac60f2e4366be`. The window title reads **ReLink** and
the in-app header reads **RE / LINK**.

The application was built locally in debug mode from an isolated extraction of
that commit. All 79 build-input files matched the Git tree before compilation
and their recorded SHA-256 values afterward. The unrelated native audio-owner
work in the main workspace was excluded. `source-files.json`, `local-build.txt`
and `observation.json` preserve the source, build, executable and image identity.
The published build log replaces the local checkout path with `<workspace>`.
The bundle passed strict ad-hoc signature verification; this is not notarization.

Both screenshots use the existing explicit four-test-tone, three-mix fixture
recorded in `observation.json`. Audio remained stopped, no listening output was
selected and the meters remained silent. The effects view was opened through
the actual native interface. Its pointer rests in an empty margin; the native
macOS screen-capture badge remains visible. The capture tool returned JPEG bytes;
the original JPEGs are retained here. Their decoded RGB pixels were losslessly
encoded as PNG for the existing documentation paths and verified pixel-identical.
No visual content was removed or altered. The accompanying accessibility records
confirm the visible state.

The original studio was backed up and restored byte for byte after the app
exited. Its before/after SHA-256 is
`94efd0f900d0d205944bbd291fa87a078ea469d7a3c1b462fedc5b123f3a6615`.
No audio stream was started, driver installed, system default changed or privacy
permission granted. These screenshots qualify stopped macOS presentation only.

The desktop CI run for `9cd350f` failed its Rust formatting gate. These are
**local source-build screenshots**, not CI artifacts, and do not turn that CI
result into a pass. Earlier preview downloads and screenshot evidence remain
unchanged; the README identifies the older preview release separately.
