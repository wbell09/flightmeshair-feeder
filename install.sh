#!/usr/bin/env bash
set -euo pipefail

readonly SERVICE_NAME="flightmesh-feeder"
readonly INSTALL_DIR="/opt/flightmesh"
readonly CONFIG_DIR="/etc/flightmesh"
readonly CONFIG_FILE="${CONFIG_DIR}/feeder.env"
readonly UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly FORWARDER_SOURCE="${SCRIPT_DIR}/forward_dump1090.py"
readonly UNIT_SOURCE="${SCRIPT_DIR}/${SERVICE_NAME}.service"

station_id=""
api_url="https://api.wbell09.com"
aircraft_source="http://127.0.0.1:8080/data/aircraft.json"
allow_insecure="false"

usage() {
  cat <<'EOF'
Install the FlightMesh feeder as a Raspberry Pi system service.

Usage:
  sudo ./install.sh --station STATION_ID [options]

Options:
  --api-url URL      FlightMeshAir API (default: https://api.wbell09.com)
  --source URL       aircraft.json URL (default: PiAware on port 8080)
  --insecure         allow a self-signed API certificate (local testing only)
  --help             show this help

The installer prompts privately for the station upload token. It does not
accept a token argument, which keeps the secret out of shell history.
EOF
}

fail() {
  printf 'FlightMesh installer: %s\n' "$1" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --station) [[ $# -ge 2 ]] || fail "--station requires a value"; station_id="$2"; shift 2 ;;
    --api-url) [[ $# -ge 2 ]] || fail "--api-url requires a value"; api_url="$2"; shift 2 ;;
    --source) [[ $# -ge 2 ]] || fail "--source requires a value"; aircraft_source="$2"; shift 2 ;;
    --insecure) allow_insecure="true"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

[[ ${EUID} -eq 0 ]] || fail "run this installer with sudo"
[[ "${station_id}" =~ ^[a-z0-9][a-z0-9-]{2,63}$ ]] || fail "invalid station ID"
[[ "${api_url}" =~ ^https?://[^[:space:]]+$ ]] || fail "--api-url must be an HTTP(S) URL"
[[ "${aircraft_source}" =~ ^https?://[^[:space:]]+$ ]] || fail "--source must be an HTTP(S) URL"
[[ -f "${FORWARDER_SOURCE}" ]] || fail "forward_dump1090.py was not found beside the installer"
[[ -f "${UNIT_SOURCE}" ]] || fail "systemd unit template is missing"
command -v python3 >/dev/null || fail "python3 is required"
command -v systemctl >/dev/null || fail "systemd is required"

upload_token="${FLIGHTMESH_FEEDER_TOKEN:-}"
if [[ -z "${upload_token}" ]]; then
  read -r -s -p "Station upload token: " upload_token
  printf '\n'
fi
[[ "${upload_token}" =~ ^[A-Za-z0-9_-]{32,}$ ]] || fail "the upload token format is invalid"

install -d -m 0755 -o root -g root "${INSTALL_DIR}"
install -m 0755 -o root -g root "${FORWARDER_SOURCE}" "${INSTALL_DIR}/forward_dump1090.py"
install -d -m 0700 -o root -g root "${CONFIG_DIR}"

umask 077
{
  printf 'FLIGHTMESH_FEEDER_TOKEN=%s\n' "${upload_token}"
  printf 'FLIGHTMESH_STATION_ID=%s\n' "${station_id}"
  printf 'FLIGHTMESH_API_URL=%s\n' "${api_url%/}"
  printf 'FLIGHTMESH_AIRCRAFT_SOURCE=%s\n' "${aircraft_source}"
  if [[ "${allow_insecure}" == "true" ]]; then
    printf 'FLIGHTMESH_EXTRA_ARGS=--insecure\n'
  else
    printf 'FLIGHTMESH_EXTRA_ARGS=\n'
  fi
} > "${CONFIG_FILE}"
chmod 0600 "${CONFIG_FILE}"

install -m 0644 -o root -g root "${UNIT_SOURCE}" "${UNIT_FILE}"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

printf '\nFlightMesh feeder installed for %s.\n' "${station_id}"
printf 'Status: sudo systemctl status %s\n' "${SERVICE_NAME}"
printf 'Logs:   sudo journalctl -u %s -f\n' "${SERVICE_NAME}"
