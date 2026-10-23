# Build the application from its bundled source

Each app includes `Contents/Resources/CorrespondingSource.tar.gz`, containing its
complete application sources, resources, license, package definition and build
scripts. `SourceManifest.json` records the original build inputs and their
SHA-256 hashes. The archive is covered by the app's code signature; its hash is
also recorded in `Contents/Resources/BuildInfo.json`.

Extract the archive into a new directory, then build on macOS 15 or later with
Swift 6 and Apple's Command Line Tools (or Xcode):

```sh
tar -xzf /path/to/CorrespondingSource.tar.gz
cd RaveLink-source
scripts/build-app.sh
```

The resulting `build/RaveLink.app` is ad-hoc signed for development. No Git
checkout, private repository access, Apple account or third-party package
download is required to compile it. The source archive declares its origin;
modified inputs are marked in the new bundle's build metadata. An archive
manifest does not independently authenticate a claimed revision.

Set `APP_ARCHITECTURES=universal` to build Apple Silicon and Intel slices, or
choose `arm64` or `x86_64`. `APP_VERSION` and `APP_BUILD_NUMBER` override the
checked-in version. A Developer ID build additionally requires the builder's own
signing identity through `SIGNING_IDENTITY`. Private signing keys are not
included. Build timestamps, compiler versions and signatures can change the
resulting bytes; this is a source rebuild procedure, not a byte-identical build
claim.

The archive includes all application build inputs. Tests, research recordings,
CI reports and separately built virtual drivers remain separate from this app
archive. Installed RaveLink virtual-driver bundles carry their own corresponding
source, configuration, local patches and rebuild instructions.

Compilation and signature verification do not grant microphone or system-audio
permission, install virtual devices, establish notarization, or qualify runtime
audio behavior. Audio remains stopped when the application opens.
