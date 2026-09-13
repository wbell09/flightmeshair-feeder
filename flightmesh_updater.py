#!/usr/bin/env python3
"""Pull an owner-approved, checksum-pinned FlightMeshAir feeder update."""

import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

INSTALL_PATH = Path("/opt/flightmesh/forward_dump1090.py")
BACKUP_PATH = Path("/opt/flightmesh/forward_dump1090.py.previous")


def api_request(url, token, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "flightmesh-updater/1.0",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def report(api_url, station, token, request_id, status, message=None):
    return api_request(
        f"{api_url}/feeders/{station}/update/{request_id}", token, "POST",
        {"status": status, "message": message},
    )


def update_error_message(exc):
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return (
                "FlightMesh updater authentication failed: the station upload "
                "token in /etc/flightmesh/feeder.env was rejected. Rotate or "
                "reinstall the station upload token, then retry the updater."
            )
        return f"FlightMesh updater request failed with HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"FlightMesh updater could not reach the API: {exc.reason}"
    return f"FlightMesh updater failed: {exc}"


def run():
    api_url = os.environ["FLIGHTMESH_API_URL"].rstrip("/")
    station = os.environ["FLIGHTMESH_STATION_ID"]
    token = os.environ["FLIGHTMESH_FEEDER_TOKEN"]
    response = api_request(f"{api_url}/feeders/{station}/update", token)
    update = response.get("update")
    if not update:
        return
    request_id = int(update["id"])
    artifact_url = str(update["artifact_url"])
    expected_hash = str(update["artifact_sha256"]).lower()
    try:
        if not artifact_url.startswith("https://") or len(expected_hash) != 64:
            raise ValueError("release metadata failed validation")
        report(api_url, station, token, request_id, "downloading")
        with urllib.request.urlopen(artifact_url, timeout=60) as response:
            artifact = response.read(2_000_001)
        if len(artifact) > 2_000_000:
            raise ValueError("release artifact is unexpectedly large")
        if hashlib.sha256(artifact).hexdigest() != expected_hash:
            raise ValueError("release checksum verification failed")
        with tempfile.NamedTemporaryFile(
            prefix="flightmesh-update-", suffix=".py", delete=False,
            dir=INSTALL_PATH.parent,
        ) as handle:
            handle.write(artifact)
            candidate = Path(handle.name)
        py_compile.compile(str(candidate), doraise=True)
        report(api_url, station, token, request_id, "installing")
        if INSTALL_PATH.exists():
            BACKUP_PATH.write_bytes(INSTALL_PATH.read_bytes())
            BACKUP_PATH.chmod(0o755)
        candidate.replace(INSTALL_PATH)
        INSTALL_PATH.chmod(0o755)
        subprocess.run(["systemctl", "restart", "flightmesh-feeder.service"], check=True)
        subprocess.run(["systemctl", "is-active", "--quiet", "flightmesh-feeder.service"], check=True)
        report(api_url, station, token, request_id, "succeeded", "Feeder restarted successfully")
    except Exception as exc:
        if BACKUP_PATH.exists():
            BACKUP_PATH.replace(INSTALL_PATH)
            subprocess.run(["systemctl", "restart", "flightmesh-feeder.service"], check=False)
        message = update_error_message(exc)
        try:
            report(api_url, station, token, request_id, "failed", message[:500])
        except Exception as report_exc:
            print(update_error_message(report_exc), file=sys.stderr)
            print(message, file=sys.stderr)
            raise SystemExit(1) from None
        print(message, file=sys.stderr)
        raise SystemExit(1) from None


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as exc:
        print(update_error_message(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
