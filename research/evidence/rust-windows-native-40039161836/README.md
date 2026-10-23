# Windows native build evidence — run 40039161836

[GitHub run](https://github.com/thatsmethen/ravelink/actions/runs/40039161836)
completed successfully at commit `6484db8f80d3ad6d7233b5c927b11b6889c82b75`.
Its `unsigned-package` job ran on Windows Server 2022, version 10.0.20348,
runner image `windows-2022` / `20261012.333.1`.

The retained evidence establishes a native Windows build of the original Rust
AMD64 driver, nine passing Windows user-mode host tests, compile-only SDK ABI
assertions, PE structure/import validation, INF verification, and unsigned catalog
generation. The host tests include mocked PortCls interfaces and transport
checks; they do not execute the installed driver in the Windows kernel.

`build-at-6484.ps1` is the exact build script from that commit. Its checked commands
run `infverif /w` and `Inf2Cat /os:10_VB_X64 /uselocaltime`; nonzero exits fail the
job. The log records no catalog signability errors or warnings and reports
catalog generation complete. `build-evidence.json` and `pe-evidence.json` inside
the artifact explicitly record `signed: false` and no kernel load. Catalog
creation does not establish a signed/trusted package, successful installation,
endpoint discovery, driver runtime safety, audio continuity, HLK qualification,
or production readiness. None of those outcomes is evidenced by this run.

## Preserved bytes

`artifact-original.zip` is the original GitHub artifact ZIP, downloaded by artifact
ID `12538083934`. Its SHA-256 matches both GitHub's artifact API metadata and the
upload digest in `ci.log`:

`72dccbdb999223e44f9ca9ac37f2b69062c1720ad6a049d6228bc3cbbf623dd9`

It is 72,773 bytes and contains all 16 uploaded files, including the `.sys`, `.inf`,
`.cat`, PDB, build/PE records, proprietary licence and Rust runtime notices.
Every member was checked byte-for-byte against the parent-provided extraction
at `/tmp/ravelink-native-40039161836/RaveLink-Windows-driver-unsigned`.
The driver is 20,480 bytes, SHA-256:

`15cb6ad85aa3541b3c62f281121eea9a31152e6d899d7d134db25c237a94e314`

The provided `run.json` and `ci.log` were copied without newline or encoding
conversion. `artifact-api.json` records the separately fetched GitHub artifact
metadata. `toolchain-at-6484.json` and `build-at-6484.ps1` were read directly from
the source commit. The directory's `.gitattributes` prevents Git from normalizing
these original bytes. The temporary source files were left untouched.

`custody.json` records every preserved file and archive member's size/SHA-256,
acquisition details and the evidence boundary. Run `python3 verify.py` from this
directory to verify the retained originals without extracting or executing them.
