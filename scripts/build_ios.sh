#!/usr/bin/env bash
# 📱 World Intelligence — one-command iOS build & run (macOS only, needs Xcode).
#
#   ./scripts/build_ios.sh
#     - iPhone connected  → builds, installs & launches on your phone
#                           (auto-signing; first time only, run:
#                            TEAM_ID=YOURTEAMID ./scripts/build_ios.sh
#                            or pick your team once in Xcode)
#     - no iPhone         → boots a simulator and runs the app there
#                           (no Apple ID, no signing — zero setup)
#
#   SIM_NAME="iPhone 16 Pro" ./scripts/build_ios.sh   # pick a simulator model
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/ios"

TEAM_ID="${TEAM_ID:-}"
SIM_NAME="${SIM_NAME:-iPhone 16}"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "❌ Xcode not found. Run this on a Mac with Xcode installed (App Store)."
  exit 1
fi

SCHEME="WorldIntel"
PROJ="WorldIntel.xcodeproj"
BUNDLE_ID="com.worldintel.app"

app_path() {
  local cfg="${1:-Debug}"
  local dest="${2:-}"
  local args=(-project "$PROJ" -scheme "$SCHEME" -configuration "$cfg")
  [ -n "$dest" ] && args+=(-destination "$dest")
  xcodebuild "${args[@]}" -showBuildSettings 2>/dev/null \
    | awk -F' = ' '/^[[:space:]]*TARGET_BUILD_DIR/ {print $2}' | tail -1
}

# --- Does an iPhone show up as connected? -----------------------------------
DEVICES="$(xcrun xctrace list devices 2>/dev/null || true)"
DEVICE_UDID="$(echo "$DEVICES" | grep -E '\([0-9A-Fa-f-]{36}\) \(device\)' | head -1 | grep -oE '[0-9A-Fa-f-]{36}' || true)"

if [ -n "$DEVICE_UDID" ]; then
  echo "📱 iPhone connected — building, installing and launching…"
  EXTRA=()
  [ -n "$TEAM_ID" ] && EXTRA=("DEVELOPMENT_TEAM=$TEAM_ID")
  xcodebuild -project "$PROJ" -scheme "$SCHEME" -configuration Debug \
    -destination "id=$DEVICE_UDID" -allowProvisioningUpdates \
    CODE_SIGN_STYLE=Automatic "${EXTRA[@]}" build
  APP="$(app_path Debug "id=$DEVICE_UDID")/WorldIntel.app"
  echo "🚀 Installing on device…"
  xcrun devicectl device install app --device "$DEVICE_UDID" "$APP"
  xcrun devicectl device process launch --device "$DEVICE_UDID" "$BUNDLE_ID"
  echo "✅ World Intelligence is now running on your iPhone."
  echo "   (If signing failed, set your Team ID once: TEAM_ID=XXXXXXXXXX ./scripts/build_ios.sh)"
else
  echo "📱 No iPhone connected — using a simulator (no Apple ID needed)."
  SIM_UDID="$(xcrun simctl list devices available 2>/dev/null | grep "$SIM_NAME" | head -1 | grep -oE '[0-9A-Fa-f-]{36}' || true)"
  if [ -z "$SIM_UDID" ]; then
    echo "🔧 Creating a $SIM_NAME simulator (one time)…"
    DEVICE_TYPE="$(xcrun simctl list devicetypes 2>/dev/null | grep -i "$SIM_NAME" | head -1 | grep -oE 'com\.apple\.[^)]+' | head -1)"
    [ -z "$DEVICE_TYPE" ] && DEVICE_TYPE="com.apple.CoreSimulator.SimDeviceType.iPhone-16"
    SIM_UDID="$(xcrun simctl create "$SIM_NAME" "$DEVICE_TYPE")"
  fi
  xcrun simctl boot "$SIM_UDID" 2>/dev/null || true
  open -a Simulator
  echo "🛠  Building…"
  xcodebuild -project "$PROJ" -scheme "$SCHEME" -configuration Debug \
    -destination "id=$SIM_UDID" CODE_SIGNING_ALLOWED=NO build
  APP="$(app_path Debug "id=$SIM_UDID")/WorldIntel.app"
  xcrun simctl install "$SIM_UDID" "$APP"
  xcrun simctl launch "$SIM_UDID" "$BUNDLE_ID"
  echo "✅ World Intelligence is running in the simulator."
fi
