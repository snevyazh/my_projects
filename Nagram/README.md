# Clean Nagram

Clean Nagram is a personal Android Telegram client built from Nagram. This
repository contains the application code, local customizations, and build
configuration used for the `xyz.nextalone.nagram.clean` Android package.

## Current build

- App name: Clean Nagram
- Package: `xyz.nextalone.nagram.clean`
- Version: `12.9.2`
- App version code: `1243`
- Compile and target SDK: Android 35
- Minimum SDK: Android 21
- NDK: `27.2.12479018`
- Main Android module: `TMessagesProj`

## Project-specific changes

The codebase includes Nagram and NekoX functionality together with local
changes, including:

- inline-bot rule settings, editing, storage, and dual-track rule handling;
- custom message markdown parsing;
- compact chat action icons and hidden-option filtering;
- chat copy and message-menu customizations;
- cache-control hooks;
- custom Nagram settings and debug-menu integration;
- Nagram-branded storage, update, and notification behavior.

The app also retains the broader Telegram/Nagram feature set, including
multiple accounts, proxy support, translation tools, custom themes, enhanced
message actions, UnifiedPush support, and Firebase Cloud Messaging.

## Private credentials

The canonical Firebase configuration is stored at:

```text
./GOOGLE_VERY_SECRET_PASSWORD/google-services.json
```

The Android build plugin expects the file at:

```text
./TMessagesProj/google-services.json
```

That path is an ignored symbolic link to the canonical file. Keep the real
credential file in `GOOGLE_VERY_SECRET_PASSWORD`; do not commit it, paste its
contents into documentation, or replace it with placeholder credentials.

The permanent personal Android signing identity is stored at:

```text
./GOOGLE_VERY_SECRET_PASSWORD/clean-nagram.keystore
./GOOGLE_VERY_SECRET_PASSWORD/clean-nagram.password
```

The key alias is `clean-nagram`. Its certificate SHA-1 fingerprint is:

```text
47:98:1C:D2:43:15:BD:9E:20:61:FD:D9:F4:98:4F:56:64:3E:1F:CC
```

Gradle automatically uses these ignored local files for both debug and release
builds. Back up the keystore and password together in a secure location. If the
keystore is lost, future APKs cannot upgrade installations signed with this
identity.

Telegram credentials and optional signing overrides belong in the ignored
`local.properties` file:

```properties
TELEGRAM_APP_ID=<your app id>
TELEGRAM_APP_HASH=<your app hash>
KEYSTORE_FILE=<keystore path>
KEYSTORE_PASS=<keystore password>
ALIAS_NAME=<key alias>
ALIAS_PASS=<key password>
```

## Build

Install JDK 17, Android SDK 35, Build Tools 35.0.0, CMake, and Android NDK
27.2.12479018. Initialize the repository dependencies when needed:

```shell
git submodule update --init --recursive
./run init libs
./run libs native
```

Build an ARM64 debug APK:

```shell
NATIVE_TARGET=arm64-v8a ./gradlew :TMessagesProj:assembleDebug
```

Gradle writes the generated APK under:

```text
./TMessagesProj/build/outputs/apk/debug/
```

Verified APKs intended for installation are also kept in the simple top-level
folder:

```text
./APKs/
```

Before distributing an APK, verify its package ID and install and launch it on
a connected device. A successful Gradle build alone does not prove that
runtime services such as Firebase are correctly configured.

## Install and verify

```shell
adb install -r ./APKs/Nagram-arm64-debug.apk
adb shell monkey -p xyz.nextalone.nagram.clean 1
```

Use `adb logcat` to investigate any startup failure before treating an APK as
ready for installation.

## Security

Private Firebase files, local properties, signing keys, APKs, and app bundles
are excluded from Git. Check `git status` before every commit to ensure that no
credential or generated binary is staged.

## Upstream

This project is derived from Nagram, NekoX, Nekogram, and Telegram for Android.
Their original licensing and attribution files remain in the repository.
