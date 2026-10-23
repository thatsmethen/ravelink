# Windows driver source provenance

Implementation date: 2026-10-24. Authoring boundary: new `crates/ravelink-windows-driver/` and `drivers/windows/`, with original logic under the repository's proprietary license.

No SysVAD implementation, legacy RaveLink driver, BlackHole code, or GPL implementation was read, copied, translated, or linked for this work. The driver logic, transport, descriptors, rollback, tests, and packaging were independently authored from public contracts. Published ABI names, values, structure fields, GUIDs, and signatures were transcribed from the official Microsoft SDK/WDK. Microsoft and Rust toolchain material retain their own terms; the proprietary license does not claim ownership of those materials.

## Pinned authoritative inputs

The exact packages, versions, and SHA-512 digests are recorded in [`toolchain.json`](toolchain.json). They were obtained from Microsoft's published NuGet packages:

- [Microsoft.Windows.WDK.x64 10.0.26100.6584](https://www.nuget.org/packages/Microsoft.Windows.WDK.x64/10.0.26100.6584)
- [Microsoft.Windows.SDK.CPP 10.0.26100.6584](https://www.nuget.org/packages/Microsoft.Windows.SDK.CPP/10.0.26100.6584)

Only SDK/WDK declarations and kernel import libraries were used to author and link the production driver. No sample-driver source was used. The build scripts also use Microsoft's INF validation and catalog tools. Header paths below are relative to `c/Include/10.0.26100.0/`:

| Header | SHA-256 |
| --- | --- |
| `km/portcls.h` | `9901a545d6aaf21d228a5f2c28a35ff7512177d1209a7dcc8fce000ef23d239e` |
| `km/unknown.h` | `0127ee0dd4ef9229c2fe027b6aa8acf63bc6ab3d8ead21cf512a9e5cd797bd05` |
| `km/wdm.h` | `c6a2a650c9799791accc407800861f672aea75ff0f1f60e2d3bf62d836275732` |
| `shared/ks.h` | `54e758c21575e0997489b838ed2862f0c3f66a921522bfb3ae0385dcb18c9a85` |
| `shared/ksmedia.h` | `245507adfc22c1fdceb671db3000a394c8f374a10b4e7a10b51a5ec13bc1e5cf` |
| `shared/mmreg.h` | `f1bfa2fdb661f7b3188813f9b4a056d818d26a95941155f13d9b7aab15772631` |
| `shared/ntdef.h` | `4a107192df73e5efae5b0ab6ec9024b9c40c9ef63f539471f70cb47db21fb12c` |

Rust is pinned to `nightly-2025-11-10`, rustc `1.93.0-nightly (6647be936 2025-11-09)`, with its matching `rust-src` core/compiler-builtins and bundled LLVM linker. Rust is MIT/Apache-2.0; compiler-builtins and LLVM contain their own documented upstream licensing. There are no third-party Cargo dependencies in this driver crate. The Rust sysroot and Microsoft packages are development inputs and are not vendored into this repository.

## Contract references consulted

- [Microsoft Rust driver infrastructure README](https://github.com/microsoft/windows-drivers-rs) — toolchain capabilities and experimental status; no driver samples used.
- [WDK download/version guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk) and [WDK NuGet setup](https://learn.microsoft.com/en-us/windows-hardware/drivers/install-the-wdk-using-nuget).
- [Audio miniport interfaces](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/miniport-interfaces) and [wave filters](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/wave-filters).
- [IMiniportWaveRTStream](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nn-portcls-iminiportwavertstream) — stream states, positions, format and buffer responsibilities; linked individual DDI method contracts.
- [PcInitializeAdapterDriver](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-pcinitializeadapterdriver), [PcAddAdapterDevice](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-pcaddadapterdevice), and [PcDispatchIrp](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-pcdispatchirp) — dispatch and extension ownership.
- [PcRegisterPhysicalConnection](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-pcregisterphysicalconnection) and corresponding unregister interface contracts.
- [PortCls PnP rebalance](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/implement-pnp-rebalance-for-portcls-audio-drivers).
- [Adapter power registration](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-pcregisteradapterpowermanagement), [unregistration](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-pcunregisteradapterpowermanagement), and [QueryDeviceCapabilities](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/portcls/nf-portcls-iadapterpowermanagement-querydevicecapabilities).
- [Audio INF core components](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/installing-core-system-components-for-an-audio-adapter), INF DDInstall/AddService/AddInterface documentation, and SDK category GUID declarations.
- [Microsoft spin-lock guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/introduction-to-spin-locks).
- [Rust build-std documentation](https://doc.rust-lang.org/cargo/reference/unstable.html#build-std) and [Microsoft's runtime-symbol issue #294](https://github.com/microsoft/windows-drivers-rs/issues/294) — basis for rebuilding panic-abort core and using the inert `_fltused` metadata definition. No runtime implementation was copied.

`tests/abi-check.cpp` is an original independent set of assertions over the Microsoft headers, not production glue. `src/kernel_tests.rs` mocks the documented call boundaries and allocators solely for host validation; it does not emulate or claim to verify Windows kernel behavior.
