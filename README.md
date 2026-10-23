# RaveLink

A native macOS audio router and mixer, developed using Elgato's documentation and [morluto/rea](https://github.com/morluto/rea) inspection of pinned Wave Link artifacts. Independently implemented; no Elgato code or branding is distributed.

**Status: in development. Not yet a production release.**

Inputs and mix buses are user-created without a product-imposed channel count. Actual capacity depends on the audio hardware, driver, CPU and memory.

## Development

Requires macOS 15+ and Swift 6. `swift build` builds the application; `scripts/test.sh` runs the Swift Testing suites. The test wrapper supplies framework paths for standalone Command Line Tools and uses normal discovery with full Xcode. On CLT distributions missing the Foundation testing overlay module, it disables automatic cross-import overlays for the test build. Runtime and virtual-device acceptance are tracked separately in `docs/` and [research/ACCEPTANCE.md](research/ACCEPTANCE.md).
