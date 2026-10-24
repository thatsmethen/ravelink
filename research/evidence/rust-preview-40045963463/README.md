# Public development preview custody

[Desktop CI 40045963463](https://github.com/thatsmethen/ravelink/actions/runs/40045963463) passed on macOS and Windows at source `03ff13a4f3b38fd4568ffdf96d893f7c05564f17`. Its unchanged application ZIPs are published on the [development preview release](https://github.com/thatsmethen/ravelink/releases/tag/v0.1.0-preview.20261024). Each release asset was downloaded again and matched the original archive bytes; the public screenshot URLs also matched the committed PNGs exactly.

`preview-verification.json` retains the macOS package, Mach-O architecture, executable mode, icon, licence and Windows embedded-resource checks. Native Windows CI verified seven RT_ICON entries and one RT_GROUP_ICON against the original artwork, and its report matches the packaged executable. This does not establish Windows shell appearance or runtime interaction.

The new icon was separately inspected in macOS Finder’s small icon and large Preview for the local debug UI candidate. That screenshot stays local because it includes unrelated filesystem/account details; its hash and observation scope are recorded. The actual application UI screenshots are public. Original studio data was restored byte-for-byte after stopped UI testing.

The packages are macOS Apple silicon (ad-hoc signed, not notarized) and Windows x64 (unsigned). They do not contain virtual-driver installers. This preview precedes the native macOS capture checkpoint. Desktop CI success does not supersede the separately failed installed-audio observations or establish production readiness.

Original outer GitHub artifact archives remain locally retained; their digests and exact nested release ZIP hashes are recorded in the published metadata. The release contains the original nested application ZIP bytes, not a rebuilt package. `publication.json` identifies asset URLs, sizes and GitHub digests; `SHA256SUMS.txt` permits independent download verification.
