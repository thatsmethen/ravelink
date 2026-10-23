# RaveLink

A native macOS audio router and mixer, developed against documented and observed Elgato Wave Link behavior using [morluto/rea](https://github.com/morluto/rea). Independently implemented; no Elgato code or branding is distributed.

**Status: in development. Not yet a production release.**

Inputs and mix buses are user-created without a product-imposed channel count. Actual capacity depends on the audio hardware, driver, CPU and memory.

## Development

Requires macOS 15+ and Swift 6. `swift build` builds the application; `swift test` runs deterministic core checks. Runtime and virtual-device acceptance are tracked separately in `docs/`.
