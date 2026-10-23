# RaveLink virtual audio driver source

`BlackHole/` contains the checksum-pinned upstream GPL-3.0 source. The upstream source, license, and version files are unmodified. See `BlackHole/upstream.json` for custody details.

Build, package, install, and remove RaveLink-named devices with `scripts/virtual-devices.py`. Full instructions, licensing, identity rules, and evidence boundaries are in [docs/virtual-devices.md](../docs/virtual-devices.md).

`tests/driver_contract.c` loads built bundles into a private process and exercises the real exported driver interface without installing into the audio server. `tests/test_virtual_devices.py` builds two universal devices and tests their independence plus installer input validation.
