# Proprietary code and dependency custody

First-party Rust product code and original drivers use the root proprietary notice. Permissively licensed ecosystem code remains under its respective terms; it is not relabelled as first-party proprietary code. No Cargo target links or packages archived GPL code. ASIO features are disabled.

`Cargo.lock` fixes registry package versions and checksums. `docs/dependencies.json` records the resolved macOS arm64 and Windows x64 graph, exact features, declared authors/licenses, and notice hashes. `scripts/dependency-notices.py --check` verifies generated records against the locked graph. The graph includes build-time dependencies as well as runtime dependencies.

The generator includes crate-shipped license/notice files, plus font notices from epaint_default_fonts. Where a crate omits license text, `docs/third-party-licenses/` preserves notices fetched from the maintainer's exact published VCS commit, with URL and SHA-256. For old `block`, `malloc_buf`, `dispatch` and `hexf-parse` releases that declare MIT or CC0 but ship no notice text, the standard SPDX grant is included alongside the package's declared authors and license. Standard text is identified as such, not represented as an upstream copyright notice. Some Objective-C binding licenses link to MIT rather than reproducing it; the standard MIT grant is also included.

The macOS application bundle includes THIRD-PARTY-NOTICES.txt. Windows development distributions must include that file and the root LICENSE next to the executable. Font resources retain OFL/Ubuntu-font terms. Platform SDKs remain subject to their own terms. The first-party macOS driver has no third-party Rust runtime dependency.

Regenerate and review notices after dependency, target or feature changes; a new license expression or missing notice requires review before packaging. Do not enable copyleft or separately licensed audio SDK features as an incidental build fix.
