# Frozen Rust dependency advisory audit — 24 October 2026

The audited root lockfile has **zero known vulnerability matches and five unmaintained-package warnings** in the pinned RustSec database. `cargo-audit --deny warnings` exits **1**. This is not a clean advisory result or a security certification. No advisories were suppressed and no production dependencies were changed.

## Exact findings and target membership

| Package | RustSec advisory | macOS app | Windows app | Dependency path / scope |
| --- | --- | --- | --- | --- |
| `ttf-parser 0.25.1` | [RUSTSEC-2026-0192](https://rustsec.org/advisories/RUSTSEC-2026-0192.html) | Normal dependency graph | Normal dependency graph | `eframe → egui/egui-wgpu → epaint → ab_glyph → owned_ttf_parser → ttf-parser` |
| `paste 1.0.15` | [RUSTSEC-2024-0436](https://rustsec.org/advisories/RUSTSEC-2024-0436.html) | Build-time procedural macro | Absent | `wgpu → wgpu-hal → metal → paste` |
| `zvariant 5.15.1` | [RUSTSEC-2026-0370](https://rustsec.org/advisories/RUSTSEC-2026-0370.html) | Absent | Absent | Linux AT-SPI accessibility branch through `accesskit_unix`, `atspi`, and `zbus` |
| `zbus_names 4.3.5` | [RUSTSEC-2026-0371](https://rustsec.org/advisories/RUSTSEC-2026-0371.html) | Absent | Absent | Same Linux accessibility branch |
| `zvariant_derive 5.15.1` | [RUSTSEC-2026-0372](https://rustsec.org/advisories/RUSTSEC-2026-0372.html) | Absent | Absent | Procedural macro in the same Linux accessibility branch |

All five advisories are informational **unmaintained** notices. None identifies a vulnerability or supplies a patched version. `paste` is archived; `ttf-parser` no longer receives fixes. The three standalone `z*` packages were incorporated into `zbus 6`, according to their advisories. The raw notices are retained in `advisories/`, with exact upstream paths and their CC0-1.0 license in `advisory-sources.json`.

Both `aarch64-apple-darwin` and `x86_64-apple-darwin` have the macOS classifications above. The Windows graph is `x86_64-pc-windows-msvc`. These are Cargo package-graph results, not a symbol-level reachability analysis or an inspection of linked release binaries. `normal,build` records compiled dependencies; `normal,no-proc-macro` excludes build dependencies and procedural macro branches. The latter is a runtime *candidate* graph. Procedural macros still execute in the build environment and remain relevant to supply-chain risk.

The application enables `eframe`'s `default_fonts`. A first-party source search found no custom font-file loading API, but this audit does not establish complete font-input reachability. The unmaintained runtime parser should be addressed through a reviewed upstream font-stack migration; its presence is not evidence of an exploitable font-parser bug. The three Linux-only notices remain visible in the full-lock report even though Linux is not a shipping target. Do not remove accessibility features merely to hide those warnings.

The original macOS HAL crate has no third-party Cargo dependencies. The original Windows kernel crate is excluded from the root workspace and also declares no third-party Cargo dependencies. Neither observation audits Rust `std`/`core`/`compiler_builtins`, the WDK/Apple SDK, system libraries, native operating-system behavior, or first-party unsafe code.

## Input and tool custody

- Root snapshot: `Cargo.lock.snapshot`, SHA-256 `547f5fce785f43efad75d697e8a68212fcd161215c2787b30d4823080588aa6b`; 394 lockfile packages.
- Initial working-tree snapshot: `2026-10-23T23:45:00.182364+00:00`, based on Git HEAD `f9b96e8dfb3cc3e0b0051ebd27bbab32b09d8452`. This includes the candidate working-tree manifest state; it is not a claim that HEAD alone reproduces every candidate file. Manifest hashes are in `input.json`.
- [Official cargo-audit 0.22.2 release](https://github.com/RustSec/rustsec/releases/tag/cargo-audit/v0.22.2), published 5 June 2026; source commit `281452c35cf0870969042374110f099a411bc185`.
- Executed prebuilt `cargo-audit-aarch64-apple-darwin-v0.22.2.tgz`; archive SHA-256 `ec7ca4263769593df4d909be85b94a6b79efa2897be5d2bb8ebd516e823175af`, verified against the official GitHub release asset digest **before execution**. The tool reports `cargo-audit 0.22.2`. Release and tag API responses are retained. GitHub reports the annotated release tag's signature valid; no separate local signature verification or reproducible binary rebuild was performed.
- [Official RustSec advisory database](https://github.com/RustSec/advisory-db/tree/84d943a6deeb8cc6c6f632531aaf4f1c62275239) commit `84d943a6deeb8cc6c6f632531aaf4f1c62275239`, tree `63bd52e556d7d1454f8dd9633bf5c89b68942d4f`, commit time `2026-10-23T14:42:16Z`; 1,351 advisories. This was the official repository's HEAD at acquisition. Its API metadata says the commit is unsigned; the source is pinned by Git identity, not claimed to be signed.
- `--no-fetch` prevents the auditor changing that database. This causes its JSON database commit/date fields to be null; independently checked Git commit/tree values are retained in the provenance instead.
- The audit runs in a temporary working directory with an explicit empty `.cargo/audit.toml`. In [cargo-audit's pinned configuration loader](https://github.com/RustSec/rustsec/blob/281452c35cf0870969042374110f099a411bc185/cargo-audit/src/commands.rs), this overrides any user-level audit configuration. JSON settings confirm no ignored advisory IDs, no severity threshold, and no target filters.

**Yanked-package limit:** cargo-audit 0.22.2 also skips refreshing the crates.io index when `--no-fetch` is set. Its [pinned auditor implementation](https://github.com/RustSec/rustsec/blob/281452c35cf0870969042374110f099a411bc185/cargo-audit/src/auditor.rs) then opens the host's cached index. This run reported no yank warnings, but the result is **not** evidence of fresh, complete registry yank coverage. The vulnerability and maintenance matches above use the explicitly pinned RustSec database.

## Reproduce and refresh deliberately

From the repository root, with Python 3.11+, Git, and the pinned repository Rust toolchain available:

```sh
python3 scripts/audit-dependencies.py --output /tmp/ravelink-dependency-audit-review
```

The output directory must not already exist. The script downloads a hash-pinned official executable into a temporary cache; it does not install anything globally or build cargo-audit. It fetches the exact reviewed RustSec Git commit, uses no suppressions, audits a lockfile snapshot, records all three target graphs, checks that manifests/lockfile did not change during the scan, and writes evidence hashes. Expected exit status for this snapshot is **1**, with zero vulnerabilities and five warnings. Exit **2** indicates execution or provenance failure. The script can run on pinned macOS ARM64/x64, Windows x64, and glibc Linux ARM64/x64 release binaries; only macOS ARM64 execution was exercised here.

To audit against a newer database, resolve and review the official repository's full commit SHA, then pass it explicitly:

```sh
python3 scripts/audit-dependencies.py --database-revision FULL_40_CHARACTER_COMMIT --output /tmp/ravelink-dependency-audit-new
```

The default pin intentionally reproduces this historical audit; it is **not an always-current vulnerability monitor**. A future CI job should resolve and record a current official database commit, retain the artifact even on failure, and preserve `--deny warnings`. Do not silently treat exit 1 as a pass. No workflow has been changed in this scoped audit.

`script-validation/` is the actual script replay: the same lockfile and advisory results, expected exit 1, verified tool/database hashes, target-membership matrix, and evidence checksum manifest. `script-checks.json` additionally records a tampered cached-archive check: the tool was rejected before archive parsing or execution. The initial inverse dependency trees provide human-readable paths. `SHA256SUMS.json` covers the retained review files excluding itself.

## Follow-up

Prioritize the maintained-font-stack migration because `ttf-parser` is present in both desktop normal-dependency graphs. Track replacement of the deprecated `metal`/`paste` build chain through an appropriate, tested graphics-stack update. Resolve the Linux accessibility dependency migration through compatible upstream releases if maintaining a fully clean cross-platform lockfile is required. Each is dependency implementation work; none was silently upgraded or ignored in this audit. Re-run against a freshly pinned database before a release, and review first-party code/runtime behavior separately.
