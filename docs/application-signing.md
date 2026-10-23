# Application signing boundary

`scripts/build-app.sh` signs each nested executable before the app and verifies the complete bundle. Development builds use an ad-hoc signature; `SIGNING_IDENTITY` selects an existing Developer ID Application identity. Both modes enable the hardened runtime so development does not silently skip those constraints. The script stages and verifies the new bundle before replacing the previous build by rename.

The GUI and audio engine declare the [audio-input entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.device.audio-input) needed for CoreAudio recording under the hardened runtime. The existing microphone and system-audio usage descriptions remain in the enclosing app's Info.plist. These code entitlements do not grant macOS privacy consent; the user still controls that permission.

Only the two executables that instantiate third-party Audio Units declare [disable-library-validation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation). Apple documents this entitlement for loading plugins signed by other developers. The GUI retains library validation. No JIT, unsigned executable memory, debugger, Apple Events, or sandbox exception entitlements are added.

Audio Unit failure containment is a process-lifecycle boundary, not a sandbox guarantee: installed plugins execute with the helper's user privileges. `RaveLinkPluginHost` has no recording entitlement; `RaveLinkEngine` requires recording access to implement user-selected routes. Helpers load component identities from the installed Audio Component registry, not arbitrary executable paths from a studio file.

Packaged apps resolve helpers only at their expected embedded paths. Missing, non-executable, non-file or symlink-substituted helpers fail closed rather than searching outside the app. SwiftPM/test discovery and explicit developer helper injection remain available outside that default packaged resolution. This path check does not independently authenticate a replacement executable's signature; intact signed bundle verification and Gatekeeper remain separate checks.

Distribution still requires Developer ID signing, notarization/stapling, a properly signed driver installer, and clean-machine privacy/install/upgrade/uninstall checks. Ad-hoc runtime and local signature verification establish none of those release gates. macOS 15/26 privacy attribution for the packaged helper must be exercised with user consent.

## Build identity and architectures

Every new bundle includes `Contents/Resources/BuildInfo.json` under its code signature. It records the source revision, whether relevant source inputs were modified, the hashes of those inputs, Swift version, configuration, app version/build number, and requested architectures. The packager compares source hashes before and after compilation; if those inputs differ, it refuses to publish the staged bundle and preserves the previous app. This comparison cannot detect a transient edit reverted during compilation, so release builds still require a stable checkout. A recorded revision with `sourceModified: true` is not a clean build of that revision.

The default is a native build. Explicit `APP_ARCHITECTURES=arm64`, `x86_64`, or `universal` uses separate Swift build caches and verifies every executable's requested slices before signing. Universal packaging contains both slices in the app, audio engine, and plugin host:

```sh
APP_ARCHITECTURES=universal APP_VERSION=0.1.0 APP_BUILD_NUMBER=2 \
  SIGNING_IDENTITY='Developer ID Application: YOUR NAME (TEAMID)' scripts/build-app.sh
```

The version defaults to the checked-in Info.plist. `APP_VERSION` must have three numeric components, each at most four digits; `APP_BUILD_NUMBER` uses a positive integer up to 2,147,483,647. This is the packager's narrower numeric convention within Apple's [bundle build version format](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleversion). These are build inputs, not proof that a release has passed acceptance. Cross-compilation and translated Rosetta tests remain distinct from native Intel hardware qualification. The metadata deliberately does not assert notarization.
