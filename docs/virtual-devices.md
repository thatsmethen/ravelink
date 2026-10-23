# Virtual audio devices

RaveLink builds its own named macOS Core Audio HAL plug-ins from the GPL-3.0 BlackHole source. These are userspace audio server plug-ins; they are not kernel extensions. The app routes input devices into its buses, writes the stream mix to the **output** side of `RaveLink Stream Mix`, and a receiving application such as a recorder selects the **input** side of that device. The monitor bus should target the physical headphones or speakers.

For application channels, select `RaveLink Music`, `RaveLink Browser`, `RaveLink Game`, or a custom device as the sending application's output; add that device's input to RaveLink. Applications without their own output selector need an OS-supported application capture/routing mechanism or the system output set to the intended virtual input. Merely creating a virtual device does not redirect a process automatically.

Never route a bus back into a virtual device which feeds that same bus. RaveLink's stream output must not also be used as one of its source channels: that creates an acoustic feedback loop without a microphone.

## Source and licensing

- Source: [ExistentialAudio/BlackHole](https://github.com/ExistentialAudio/BlackHole/tree/561d934c77a1fa64987e01ccabe890fed30e181f), version 0.7.1, commit `561d934c77a1fa64987e01ccabe890fed30e181f`.
- The vendored `Drivers/BlackHole/BlackHole.c`, `LICENSE`, and `VERSION` are unmodified and checked against `upstream.json` before every build.
- `scripts/virtual-devices.py` supplies independent RaveLink bundle identifiers, names, persistent UIDs, factory UUIDs, and an original icon. It replaces the upstream fallback box name in the compiled copy. It disables the hidden mirror streams, device gain, and system-alert default eligibility. No proprietary Elgato driver, upstream binary, or upstream artwork is redistributed.
- Every generated bundle contains the license, complete compiled C source, original upstream C source, configuration header, provenance manifest, and reproduction instructions under `Contents/Resources`. Preserve those when distributing a bundle or installer. RaveLink and the derived driver are GPL-3.0-only. Upstream's trademarks and official binary branding are separate from its source license.

## Build

Requires macOS, Python 3, and Apple's Command Line Tools (`xcode-select --install`). Full Xcode is unnecessary. The default build produces universal **arm64 and x86_64** binaries with a **macOS 12.0** deployment target; this driver target is separate from the application's deployment target.

```sh
python3 scripts/virtual-devices.py build
```

Default devices: `stream`, `voice`, `music`, `browser`, and `game`, each with two input and two output channels. Bundles appear in `build/virtual-devices`. The output directory must not already contain a requested device. Use a fresh output directory for rebuilding:

```sh
python3 scripts/virtual-devices.py build \
  --device podcast:Podcast \
  --device console:Console \
  --output build/extra-devices
```

IDs are immutable routing identities; labels are human-readable. The persistent UID is `RaveLink.<id>_UID`. Changing a label does not change this UID. Bundle identifiers use `au.textual.ravelink.audio.<id>`. Device IDs must be unique across installed instances. Each bundle has its own deterministic CFPlugIn factory UUID and independent ring buffer; it coexists with the official BlackHole device.

Optional multichannel transport:

```sh
python3 scripts/virtual-devices.py build \
  --device matrix:Matrix --channels 16 --output build/matrix
```

The application model has no fixed channel-count ceiling. Virtual buses can be added as independently named devices without a fixed product limit on the number of instances. Provisioning another system device requires installation by an administrator and a subsequent audio service reload or macOS restart. The current packaging supports an even 2–256 channels per device; 256 is this build's supported validation envelope, not a claim about the maximum channel count supported by Core Audio. A new device is preferable to inventing an unsupported enormous channel count. The upstream ring buffer consumes `65536 × channels × 4` bytes per active device (512 KiB stereo; 64 MiB at 256 channels), in addition to audio server and app overhead. CPU, memory, device count, sample rate, output hardware, and scheduling impose real limits. Runtime testing must establish a supported operating envelope.

The default sample rate is 48 kHz. The upstream device advertises several other rates; real multi-device routing must adapt sample rates and clocks. Passing an in-process loopback test does not prove drift-free physical-device mixing.

## Validate and package

```sh
python3 -m unittest discover -s Drivers/tests -p 'test_*.py' -v
python3 scripts/virtual-devices.py validate build/virtual-devices/*.driver
python3 scripts/virtual-devices.py package build/virtual-devices/*.driver \
  --output build/RaveLink-Virtual-Devices-0.1.0.pkg
```

The bundle validator checks identity, factory, architecture, exported factory symbol, symlink exclusion, and the sealed code signature. Packaging expands its own output and validates every archived driver. Component packages install only under `/Library/Audio/Plug-Ins/HAL`; bundle relocation is disabled and existing bundle identifiers must match. A package can upgrade the same RaveLink device identifiers. The package contains no scripts that restart audio services.

Builds are **ad-hoc signed** by default. That proves local byte integrity, not publisher identity or notarization. A release requires the developer's signing assets and independent installation verification:

```sh
python3 scripts/virtual-devices.py build --output build/release-devices \
  --sign 'Developer ID Application: YOUR NAME (TEAMID)'
python3 scripts/virtual-devices.py package build/release-devices/*.driver \
  --output build/RaveLink-Virtual-Devices.pkg \
  --sign 'Developer ID Installer: YOUR NAME (TEAMID)'
```

Notarization and stapling are separate release steps. A Developer ID Application identity cannot sign an Installer package. `build-info.json` records the requested signing identity and reports `notarized: false` until release tooling separately establishes notarization; it must not be used as proof of notarization.

## Install and uninstall

Installation is an explicit administrator action. First close applications that use audio. Installing or removing a driver affects all users of the Mac. The scripts never restart `coreaudiod` and never modify a BlackHole or Wave Link bundle.

From the repository root:

```sh
sudo python3 scripts/virtual-devices.py install build/virtual-devices/*.driver
```

The direct installer refuses to replace existing destinations, verifies copied signatures, applies `root:wheel` ownership and normal file modes, then moves each bundle into HAL. Restart macOS to activate the devices. The generated `.pkg` is an alternative administrator installation path.

Remove only the selected RaveLink IDs:

```sh
sudo python3 scripts/virtual-devices.py uninstall stream voice music browser game
```

Restart macOS after removal. Direct uninstall deliberately checks RaveLink identity and signature before removing a bundle. If an installed bundle is damaged, inspect that exact RaveLink path and remove it manually as an administrator; the script does not guess which files are safe to delete.

## Evidence and release gates

Local verification on 23 October 2026 built five stereo devices and a 256-channel device as universal arm64/x86_64 bundles. Native arm64 execution loaded the actual built bundles in a private process and checked identity, two directions of stream format, hidden mirror exclusion, malformed property requests, 4,096 blocks of exact loopback including ring wrap, stale-read silence, clock values, simultaneous independent instance buffers, and multi-client start/stop. The Python suite also checks pinned source hashes, invalid identifiers, channel bounds, format-string rejection, duplicate IDs, non-admin install refusal, payload symlinks, and signature tampering. This does not load the bundles into `coreaudiod`.

Still required before calling the driver release production-ready:

1. Install the signed package on a clean Mac, restart, and verify device discovery/UID persistence and removal.
2. Route audio from external applications through each device, through RaveLink, into a receiving application. Measure signal level, cross-bus isolation, latency, underruns, and silence after source termination.
3. Exercise mismatched physical and virtual device clocks, 44.1/48 kHz transitions, input permission changes, sleep/wake, audio-device disconnect, and long-duration workloads at stated channel counts.
4. Run actual x86_64 host tests. A universal binary and native arm64 contract tests do not establish Intel runtime behavior.
5. Verify Developer ID signatures, notarization acceptance, and installation after browser download on a separate machine.

The installed host originally had an independent BlackHole2ch v0.5.0 and an Elgato Wave Link virtual driver. Their existence is not evidence that these new RaveLink bundles were installed or that end-to-end routing passed.
