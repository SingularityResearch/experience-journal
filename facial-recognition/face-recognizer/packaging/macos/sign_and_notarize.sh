#!/bin/sh
# Signs FaceRecognizer.app with a Developer ID certificate and has Apple notarize it, so macOS opens it without
# warnings. Run by CI's macOS build job, only when the repository's signing secrets are set:
#   MACOS_CERT_P12_BASE64   the "Developer ID Application" certificate with its key, exported as .p12, base64
#   MACOS_CERT_PASSWORD     that .p12's password
#   APPLE_API_KEY_ID, APPLE_API_ISSUER_ID, APPLE_API_KEY_P8_BASE64   an App Store Connect API key (notarytool)
# Usage: sign_and_notarize.sh <path to FaceRecognizer.app>
set -eu
APP="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
KEYCHAIN="$WORK/signing.keychain-db"
KC_PASS="$(uuidgen)"
trap 'security delete-keychain "$KEYCHAIN" >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT

echo "$MACOS_CERT_P12_BASE64" | base64 --decode > "$WORK/cert.p12"
security create-keychain -p "$KC_PASS" "$KEYCHAIN"
security set-keychain-settings -lut 3600 "$KEYCHAIN"
security unlock-keychain -p "$KC_PASS" "$KEYCHAIN"
security import "$WORK/cert.p12" -k "$KEYCHAIN" -P "$MACOS_CERT_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple: -s -k "$KC_PASS" "$KEYCHAIN" >/dev/null
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
IDENTITY="$(security find-identity -v -p codesigning "$KEYCHAIN" | sed -n 's/.*"\(Developer ID Application:.*\)"/\1/p' | head -1)"
[ -n "$IDENTITY" ] || { echo "No Developer ID Application certificate in MACOS_CERT_P12_BASE64"; exit 1; }

codesign --force --deep --timestamp --options runtime --entitlements "$HERE/entitlements.plist" \
  --sign "$IDENTITY" --keychain "$KEYCHAIN" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "$APPLE_API_KEY_P8_BASE64" | base64 --decode > "$WORK/key.p8"
ditto -c -k --keepParent "$APP" "$WORK/notarize.zip"
xcrun notarytool submit "$WORK/notarize.zip" --key "$WORK/key.p8" --key-id "$APPLE_API_KEY_ID" \
  --issuer "$APPLE_API_ISSUER_ID" --wait
xcrun stapler staple "$APP"
spctl --assess --type execute --verbose "$APP"
echo "Signed and notarized: $APP"
