#!/bin/sh
# Fly.io entrypoint.
#
# The ADB wallet is never committed or baked into the image. On Fly the needed
# wallet files are provided as base64 **secrets**; decode them into WALLET_DIR at
# startup, then run the given process command. Locally / in docker-compose the
# wallet is bind-mounted and these vars are unset, so this step is skipped.
set -e

WALLET_DIR="${WALLET_DIR:-/app/wallet}"

if [ -n "$WALLET_EWALLET_PEM_B64" ]; then
  mkdir -p "$WALLET_DIR"
  printf '%s' "$WALLET_EWALLET_PEM_B64" | base64 -d > "$WALLET_DIR/ewallet.pem"
  printf '%s' "$WALLET_TNSNAMES_B64"    | base64 -d > "$WALLET_DIR/tnsnames.ora"
  printf '%s' "$WALLET_SQLNET_B64"      | base64 -d > "$WALLET_DIR/sqlnet.ora"
  chmod 600 "$WALLET_DIR/ewallet.pem"
fi

exec "$@"
