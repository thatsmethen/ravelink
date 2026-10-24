# Effects editor and native preview — 24 October 2026

The Rust interface now exposes high-pass cutoff, gate timing, compressor timing/makeup and sample-peak limiter controls for sources and mix buses. Edits use validated session history and are available while audio is stopped. Saved values were checked after application relaunch.

Native testing found that Command-Shift-Z incorrectly performed Undo. Specific Redo matching now runs first; text editors retain their own history, while keyboard-focused buttons continue to allow studio Undo/Redo. Focused controls, save/relaunch persistence and original studio restoration were observed in the actual macOS application. Six application tests pass. `observation.json` identifies the builds, source hashes and limits.

`before.png`, `master.png` and `source.png` retain the initial UI observations. `relaunch-*-ax.txt`, `redo-shortcut-ax.txt` and `focused-button-redo-ax.txt` preserve native accessibility observations. The public [mixer screenshot](../../../docs/screenshots/mixer-macos.png) and [effects screenshot](../../../docs/screenshots/mix-effects-macos.png) show the final UI and icon build with `preview-session.json`, an explicit four-test-tone fixture. These are unedited native screenshots, with audio stopped. They are not mockups or live audio qualification.

The original studio was backed up, restored byte-for-byte and inspected. Its SHA-256 is recorded; test settings were not left in the user’s session. No audio device was opened, driver installed, default route changed or microphone permission granted during this UI check. Windows interaction and shell icon appearance remain unverified.
