# Application signing boundary

`scripts/build-app.sh` signs each nested executable before the app and verifies the complete bundle. Development builds use an ad-hoc signature; `SIGNING_IDENTITY` selects an existing Developer ID Application identity. Both modes enable the hardened runtime so development does not silently skip those constraints. The script stages and verifies the new bundle before replacing the previous build by rename.

The GUI and audio engine declare the [audio-input entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.device.audio-input) needed for CoreAudio recording under the hardened runtime. The existing microphone and system-audio usage descriptions remain in the enclosing app's Info.plist. These code entitlements do not grant macOS privacy consent; the user still controls that permission.

Only the two executables that instantiate third-party Audio Units declare [disable-library-validation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation). Apple documents this entitlement for loading plugins signed by other developers. The GUI retains library validation. No JIT, unsigned executable memory, debugger, Apple Events, or sandbox exception entitlements are added.

Audio Unit failure containment is a process-lifecycle boundary, not a sandbox guarantee: installed plugins execute with the helper's user privileges. `RaveLinkPluginHost` has no recording entitlement; `RaveLinkEngine` requires recording access to implement user-selected routes. Helpers load component identities from the installed Audio Component registry, not arbitrary executable paths from a studio file.

Distribution still requires Developer ID signing, notarization/stapling, a properly signed driver installer, and clean-machine privacy/install/upgrade/uninstall checks. Ad-hoc runtime and local signature verification establish none of those release gates. macOS 15/26 privacy attribution for the packaged helper must be exercised with user consent.
