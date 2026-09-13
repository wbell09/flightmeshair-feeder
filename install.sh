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
readonly UPDATER_SOURCE="${SCRIPT_DIR}/flightmesh_updater.py"

station_id=""
api_url="https://api.wbell09.com"
aircraft_source=""
source_provided="false"
allow_insecure="false"
receiver_install_mode="prompt"

readonly RECEIVER_SOURCES=(
  "http://127.0.0.1:8080/data/aircraft.json"
  "http://127.0.0.1/dump1090/data/aircraft.json"
  "http://127.0.0.1/dump1090-fa/data/aircraft.json"
  "http://127.0.0.1/tar1090/data/aircraft.json"
  "http://127.0.0.1/readsb/data/aircraft.json"
)

readonly RECEIVER_SERVICES=(
  "dump1090-fa"
  "dump1090-mutability"
  "readsb"
  "tar1090"
  "piaware"
)

usage() {
  cat <<'EOF'
Install the FlightMesh feeder as a Debian-based Linux system service.

Usage:
  sudo ./install.sh --station STATION_ID [options]

Options:
  --api-url URL      FlightMeshAir API (default: https://api.wbell09.com)
  --source URL       aircraft.json URL (default: auto-detect local receiver)
  --install-receiver install a package-managed receiver if no source is found
  --no-install-receiver
                    do not prompt to install receiver software
  --insecure         allow a self-signed API certificate (local testing only)
  --help             show this help

The installer prompts privately for the station upload token. It does not
accept a token argument, which keeps the secret out of shell history.

Receiver installation is conservative: it only uses packages already available
from the configured apt repositories, and it never adds third-party repositories
or replaces an existing receiver service.
EOF
}

fail() {
  printf 'FlightMesh installer: %s\n' "$1" >&2
  exit 1
}

fetch_aircraft_json() {
  local url="$1"

  curl -fsS --max-time 3 "${url}" 2>/dev/null || return 1
}

is_aircraft_json() {
  python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)

aircraft = data.get("aircraft") if isinstance(data, dict) else None
if not isinstance(aircraft, list):
    sys.exit(1)

if "now" in data and not isinstance(data["now"], (int, float)):
    sys.exit(1)

sys.exit(0)
'
}

service_state() {
  local service="$1"

  if ! command -v systemctl >/dev/null; then
    printf 'unknown'
    return
  fi
  if systemctl is-active --quiet "${service}.service" 2>/dev/null; then
    printf 'active'
  elif systemctl list-unit-files "${service}.service" --no-legend 2>/dev/null | awk 'NF { found = 1 } END { exit !found }'; then
    printf 'installed'
  else
    printf 'not found'
  fi
}

has_existing_receiver_service() {
  local service state

  for service in "${RECEIVER_SERVICES[@]}"; do
    state="$(service_state "${service}")"
    if [[ "${state}" == "active" || "${state}" == "installed" ]]; then
      return 0
    fi
  done
  return 1
}

print_receiver_services() {
  local service

  printf 'Receiver services:\n'
  for service in "${RECEIVER_SERVICES[@]}"; do
    printf '  %-12s %s\n' "${service}" "$(service_state "${service}")"
  done
}

probe_receiver_source() {
  local url payload

  printf 'Checking local ADS-B receiver sources:\n' >&2
  for url in "${RECEIVER_SOURCES[@]}"; do
    if payload="$(fetch_aircraft_json "${url}")" && printf '%s' "${payload}" | is_aircraft_json; then
      printf '  found    %s\n' "${url}" >&2
      printf '%s\n' "${url}"
      return 0
    fi
    printf '  missing  %s\n' "${url}" >&2
  done
  return 1
}

wait_for_receiver_source() {
  local attempt

  for attempt in 1 2 3 4 5 6; do
    if aircraft_source="$(probe_receiver_source)"; then
      return 0
    fi
    sleep 5
  done
  return 1
}

apt_package_available() {
  local package="$1"

  command -v apt-cache >/dev/null || return 1
  apt-cache policy "${package}" 2>/dev/null | awk '$1 == "Candidate:" { found = 1; ok = ($2 != "(none)") } END { exit !(found && ok) }'
}

confirm_receiver_install() {
  if [[ "${receiver_install_mode}" == "yes" ]]; then
    return 0
  fi
  if [[ "${receiver_install_mode}" == "no" ]]; then
    return 1
  fi
  if [[ ! -t 0 ]]; then
    return 1
  fi

  cat >&2 <<'EOF'

No working local ADS-B aircraft.json source was found.

The installer can try a conservative Raspberry Pi OS/Debian receiver install
using packages already available from this system's apt repositories. It will
not add FlightAware or other third-party repositories, and it will not replace
an existing receiver service.
EOF
  read -r -p "Install package-managed dump1090-mutability now? [y/N] " reply
  [[ "${reply}" =~ ^[Yy]$ ]]
}

install_package_managed_receiver() {
  if has_existing_receiver_service; then
    cat >&2 <<'EOF'
FlightMesh installer: receiver software appears to be installed already.

No valid aircraft.json source was found, but the installer will not overwrite or
replace an existing receiver. Start or repair the existing receiver, then rerun
this installer. If your decoder uses a custom URL, rerun with --source.
EOF
    return 1
  fi

  command -v apt-get >/dev/null || fail "apt-get is required for --install-receiver"

  apt-get update
  if ! apt_package_available "dump1090-mutability"; then
    cat >&2 <<'EOF'
FlightMesh installer: dump1090-mutability is not available from the configured apt repositories.

Install PiAware/dump1090-fa/readsb using the receiver vendor's documented steps,
or enable a repository you trust, confirm aircraft.json works, then rerun this
installer. The FlightMesh installer does not add third-party receiver
repositories automatically.
EOF
    return 1
  fi

  printf 'Installing package-managed ADS-B receiver: dump1090-mutability\n' >&2
  DEBIAN_FRONTEND=noninteractive apt-get install -y dump1090-mutability
  if command -v systemctl >/dev/null; then
    systemctl enable --now dump1090-mutability.service 2>/dev/null || true
  fi

  printf 'Waiting for receiver aircraft.json to become available...\n' >&2
}

while (($#)); do
  case "$1" in
    --station) [[ $# -ge 2 ]] || fail "--station requires a value"; station_id="$2"; shift 2 ;;
    --api-url) [[ $# -ge 2 ]] || fail "--api-url requires a value"; api_url="$2"; shift 2 ;;
    --source) [[ $# -ge 2 ]] || fail "--source requires a value"; aircraft_source="$2"; source_provided="true"; shift 2 ;;
    --install-receiver) receiver_install_mode="yes"; shift ;;
    --no-install-receiver) receiver_install_mode="no"; shift ;;
    --insecure) allow_insecure="true"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

[[ ${EUID} -eq 0 ]] || fail "run this installer with sudo"
[[ "${station_id}" =~ ^[a-z0-9][a-z0-9-]{2,63}$ ]] || fail "invalid station ID"
[[ "${api_url}" =~ ^https?://[^[:space:]]+$ ]] || fail "--api-url must be an HTTP(S) URL"
[[ -f "${FORWARDER_SOURCE}" ]] || fail "forward_dump1090.py was not found beside the installer"
[[ -f "${UNIT_SOURCE}" ]] || fail "systemd unit template is missing"
[[ -f "${UPDATER_SOURCE}" ]] || fail "flightmesh_updater.py was not found beside the installer"
command -v python3 >/dev/null || fail "python3 is required"
command -v systemctl >/dev/null || fail "systemd is required"
command -v curl >/dev/null || fail "curl is required"

print_receiver_services
if [[ "${source_provided}" == "true" ]]; then
  [[ "${aircraft_source}" =~ ^https?://[^[:space:]]+$ ]] || fail "--source must be an HTTP(S) URL"
  if fetch_aircraft_json "${aircraft_source}" | is_aircraft_json; then
    printf 'Receiver source: %s (provided with --source)\n' "${aircraft_source}"
  else
    fail "--source did not return dump1090/readsb-style aircraft.json: ${aircraft_source}"
  fi
else
  if aircraft_source="$(probe_receiver_source)"; then
    printf 'Receiver source: %s (auto-detected)\n' "${aircraft_source}"
  elif confirm_receiver_install && install_package_managed_receiver && wait_for_receiver_source; then
    printf 'Receiver source: %s (installed receiver)\n' "${aircraft_source}"
  else
    cat >&2 <<'EOF'
FlightMesh installer: no local dump1090/readsb aircraft.json source was found.

FlightMesh will use an existing receiver when one is already running. It can
also try a conservative package-managed receiver install on Raspberry Pi OS or
Debian with:

  sudo ./install.sh --station YOUR-STATION-ID --install-receiver

If that package is unavailable, install or start PiAware/dump1090-fa/readsb,
confirm its aircraft.json URL works, then rerun this installer. If your decoder
uses a custom URL, rerun with:

  sudo ./install.sh --station YOUR-STATION-ID --source http://127.0.0.1/.../aircraft.json
EOF
    exit 1
  fi
fi

upload_token="${FLIGHTMESH_FEEDER_TOKEN:-}"
if [[ -z "${upload_token}" ]]; then
  read -r -s -p "Station upload token: " upload_token
  printf '\n'
fi
[[ "${upload_token}" =~ ^[A-Za-z0-9_-]{32,}$ ]] || fail "the upload token format is invalid"

install -d -m 0755 -o root -g root "${INSTALL_DIR}"
install -m 0755 -o root -g root "${FORWARDER_SOURCE}" "${INSTALL_DIR}/forward_dump1090.py"
install -m 0755 -o root -g root "${UPDATER_SOURCE}" "${INSTALL_DIR}/flightmesh_updater.py"
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
install -m 0644 -o root -g root "${SCRIPT_DIR}/flightmesh-updater.service" /etc/systemd/system/flightmesh-updater.service
install -m 0644 -o root -g root "${SCRIPT_DIR}/flightmesh-updater.timer" /etc/systemd/system/flightmesh-updater.timer
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"
systemctl enable --now flightmesh-updater.timer

printf '\nFlightMesh feeder installed for %s.\n' "${station_id}"
printf 'Status: sudo systemctl status %s\n' "${SERVICE_NAME}"
printf 'Logs:   sudo journalctl -u %s -f\n' "${SERVICE_NAME}"
