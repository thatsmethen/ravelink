# Native capture candidate: offline dependency comparison

The frozen native-capture/probe candidate has **no new or removed locked package
identities, no changed registry checksums, and no changed package membership in
the nine compared target graphs**. All 394 root-lock packages remain present.
The union of the shipping app/HAL normal-plus-build graphs still contains the
same 216 crates.io package versions covered by the historical yank observations.

This is an offline graph comparison, **not a new vulnerability or yank audit**.
The historical advisory and yank records cover these package versions at their
original observation times. They do not establish current security or yank
status. No network audit was performed and no warning was suppressed.

## Exact candidate and historical inputs

The completed comparison began at `2026-10-24T00:30:38.264081Z` with Cargo/Rust
`1.91.1`. The worktree had HEAD
`eebc08b19ba04f6b7d22d8593211532957633d5a`; the candidate was uncommitted, so the
retained lock, manifests and native source hashes identify its contents.

- Historical audited lock SHA-256:
  `547f5fce785f43efad75d697e8a68212fcd161215c2787b30d4823080588aa6b`.
- Candidate lock SHA-256:
  `386333dada7c9b29dce3350e811bbdf0c5a63ddc0d56c836d5f1d003b8c697a5`.
- Historical audit manifest SHA-256:
  `367c89de7383ff8cd38d43b6cb4f6a01d40b3940d754ee326171cb9a72e2d476`.
- All 485 files named by that historical manifest were checked before and after
  the comparison. Original audit evidence was not modified.

`checkpoint-2026-10-24-final/input.json` records the precise tool versions and
every candidate input hash. Its `inputs/` directory retains the manifests,
toolchain pin and native adapter/test sources. `Cargo.lock.snapshot` retains the
candidate lock. `graph-commands.json` records all nine successful commands and
their stderr; each retained tree is the command's original output.

## Membership result

Counts include first-party workspace roots. `app-all` and `hal-all` select
`normal,build` edges. `app-runtime` selects `normal,no-proc-macro`, matching the
historical audit's runtime-membership convention. These graphs were reconstructed
on an aarch64 macOS host using each explicit target, matching the historical
method. They are not observations from native Windows builds; host-dependent
build/proc-macro configuration and compiled output remain separate checks.

| Target | Graph | Historical | Candidate | Added / removed |
| --- | --- | ---: | ---: | --- |
| aarch64-apple-darwin | app-all | 177 | 177 | 0 / 0 |
| aarch64-apple-darwin | app-runtime | 157 | 157 | 0 / 0 |
| aarch64-apple-darwin | hal-all | 1 | 1 | 0 / 0 |
| x86_64-apple-darwin | app-all | 177 | 177 | 0 / 0 |
| x86_64-apple-darwin | app-runtime | 157 | 157 | 0 / 0 |
| x86_64-apple-darwin | hal-all | 1 | 1 | 0 / 0 |
| x86_64-pc-windows-msvc | app-all | 176 | 176 | 0 / 0 |
| x86_64-pc-windows-msvc | app-runtime | 153 | 153 | 0 / 0 |
| x86_64-pc-windows-msvc | hal-all | 1 | 1 | 0 / 0 |

Lock dependency lists changed for `objc2-core-audio 0.3.2` and first-party
`ravelink-audio 0.1.0`: the native adapter uses existing pinned objc2/block2
packages directly and enables CoreAudio block support; the probe adds the
already-locked `serde_json` as a development dependency. Unchanged package
membership does not imply identical edges, features, compiled code or behavior.

The five historical maintenance-warning memberships are also unchanged, as
retained in `historical-advisory-membership.json`: `ttf-parser 0.25.1` remains in
both desktop runtime graphs; `paste 1.0.15` remains in the macOS build graph; the
three zvariant/zbus warnings remain absent from these shipping target graphs.
The original advisory audit's nonzero result remains unchanged. This comparison
does not upgrade the historical result to a clean gate.

## Preserved unavailable attempt

`checkpoint-2026-10-24/` is the earlier incomplete attempt. The capture probe's
`serde_json` development-dependency edit was present before its matching lockfile
edge, so `cargo tree --offline --locked` returned 101. The comparison returned 2
(unavailable). Its input snapshots, executed script and failure record remain
unchanged; it contains no completed membership result. After the implementer
froze a consistent manifest and lock, the successful run used the separate
`checkpoint-2026-10-24-final/` directory above.

## Reproduction and limits

From the repository root, run against a new output directory:

```sh
python3 research/evidence/rust-dependency-native-capture/compare.py \
  --output /absolute/path/to/new-comparison
```

The script uses only `cargo tree --offline --locked`, local file reads and local
Git/tool-version queries. Missing cached metadata, a changed baseline hash,
changed candidate inputs or a failed command makes the comparison unavailable.
It does not install tools, fetch an index, change dependencies or overwrite an
existing output directory. Existing Cargo cache is used only to reconstruct the
graph, never to claim fresh yank or advisory status.

Package membership is not function-level reachability or exploit analysis.
Rust std/core/compiler builtins, native SDKs/system libraries and the separately
locked dependency-free Windows kernel crate are outside this root-lock
comparison. Historical source identifiers are preserved as historical evidence,
including across the repository's author-identity rewrite.
