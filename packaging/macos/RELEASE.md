# WhisperKey macOS Release Packaging

This release path is for customer-distributable builds. It requires Apple's
official Developer ID and notarization services. No third-party paid service is
used.

## One-Time Apple Setup

1. Enroll the Apple Developer account used for distribution.
2. Install a `Developer ID Application` certificate in the macOS login Keychain.
3. Store notarization credentials in Keychain:

```bash
xcrun notarytool store-credentials whisperkey-notary
```

Use `WHISPERKEY_NOTARY_PROFILE=<profile>` if you choose a different profile name.

## Release Build

```bash
packaging/macos/package_release.sh
```

The release script:

1. builds `dist/WhisperKey.app` with PyInstaller
2. refuses non-`Developer ID Application` signing identities
3. signs with hardened runtime and a secure timestamp
4. submits the app to Apple notarization
5. staples the notarization ticket to the app
6. creates ZIP and DMG artifacts
7. submits and staples the DMG artifact
8. verifies Developer ID signing, Gatekeeper assessment, and app stapling

## Local Diagnostics Only

```bash
packaging/macos/package_release.sh --skip-notarization
```

Do not ship artifacts created with `--skip-notarization`.

## Hard Rules

- Do not ship Apple Development signed builds.
- Do not ship ad-hoc signed builds.
- Do not ship builds that fail `packaging/macos/verify_release.sh`.
- Do not commit Apple ID passwords, app-specific passwords, API keys, or
  notarization credentials.

## Free Unsigned Build

Use this path only when shipping without an Apple Developer ID certificate:

```bash
packaging/macos/package_free_release.sh
```

The free build is ad-hoc signed, not notarized, and labeled
`free-unsigned` in artifact filenames. Users must right-click Open or use
System Settings -> Privacy & Security -> Open Anyway after download.

This is the most transparent no-Apple-fee distribution path, but it cannot
provide the same Gatekeeper trust experience as Developer ID notarization.
