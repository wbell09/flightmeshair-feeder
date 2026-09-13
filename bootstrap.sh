#!/usr/bin/env bash
set -euo pipefail

readonly REPO_RAW_BASE="${FLIGHTMESH_FEEDER_RAW_BASE:-https://raw.githubusercontent.com/wbell09/flightmeshair-feeder/main}"
readonly TARGET_DIR="${FLIGHTMESH_FEEDER_DIR:-${HOME}/flightmeshair-feeder}"
readonly REQUIRED_FILES=(
  "install.sh"
  "forward_dump1090.py"
  "flightmesh-feeder.service"
  "flightmesh_updater.py"
  "flightmesh-updater.service"
  "flightmesh-updater.timer"
)

usage() {
  cat <<'EOF'
Download and run the FlightMeshAir feeder installer.

Usage:
  ./flightmeshair-install.sh --station STATION_ID [installer options]

This bootstrap downloads the public installer files into ~/flightmeshair-feeder,
then runs the normal installer with sudo. The installer prompts privately for
the station upload token.
EOF
}

fail() {
  printf 'FlightMesh bootstrap: %s\n' "$1" >&2
  exit 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

[[ $# -gt 0 ]] || {
  usage >&2
  exit 1
}

command -v curl >/dev/null || fail "curl is required to download the installer"
command -v sudo >/dev/null || fail "sudo is required to install the system service"

if command -v apt-get >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y python3 curl
fi

mkdir -p "${TARGET_DIR}"
for file in "${REQUIRED_FILES[@]}"; do
  curl -fsSLo "${TARGET_DIR}/${file}" "${REPO_RAW_BASE}/${file}"
done

chmod 0755 "${TARGET_DIR}/install.sh" "${TARGET_DIR}/forward_dump1090.py" "${TARGET_DIR}/flightmesh_updater.py"

printf 'Downloaded FlightMeshAir installer to %s\n' "${TARGET_DIR}"
exec sudo "${TARGET_DIR}/install.sh" "$@"
