#!/usr/bin/env bash
# okto-pulse init in PULSE_HOME. The bootstrap key goes through a handoff file into a 0600 keys file
# under the given role name. The key is never printed.
# Usage: init_pulse.sh ROLE_NAME KEYS_FILE
set -euo pipefail
source "$(dirname "$0")/_env.sh"
role="${1:?role name}"; keys="${2:?keys file}"
umask 077
handoff="$ROOT/.work/handoff-$$"
"$PULSE" init --bootstrap-key-handoff "$handoff"
key="$("$PULSE" api-key --handoff-file "$handoff" | tr -d '\n')"
mkdir -p "$(dirname "$keys")"
printf '%s=%s\n' "$role" "$key" >> "$keys"
chmod 600 "$keys"
echo "key for $role stored in $(basename "$keys")"
