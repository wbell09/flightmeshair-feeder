#!/usr/bin/env python3
"""Forward dump1090/readsb aircraft.json observations to FlightMesh."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


FEET_TO_METERS = 0.3048
KNOTS_TO_METERS_PER_SECOND = 0.514444
FEET_PER_MINUTE_TO_METERS_PER_SECOND = 0.00508
CLIENT_VERSION = "flightmesh-dump1090/0.2.3"
MAX_BATCH_SIZE = 100
MAX_POSITION_AGE_SECONDS = 45


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def convert_aircraft(document: dict[str, Any], received_at: int | None = None) -> list[dict[str, Any]]:
    """Convert a dump1090/readsb document to FlightMesh observations."""
    now = received_at if received_at is not None else int(time.time())
    source_now = int(_number(document.get("now")) or now)
    observations: list[dict[str, Any]] = []
    for aircraft in document.get("aircraft", []):
        if not isinstance(aircraft, dict):
            continue
        icao24 = str(aircraft.get("hex", "")).strip().lower().lstrip("~")
        latitude = _number(aircraft.get("lat"))
        longitude = _number(aircraft.get("lon"))
        if len(icao24) != 6 or any(char not in "0123456789abcdef" for char in icao24):
            continue
        if latitude is None or longitude is None:
            continue

        age = _number(aircraft.get("seen_pos"))
        if age is None:
            age = _number(aircraft.get("seen")) or 0.0
        if age > MAX_POSITION_AGE_SECONDS or aircraft.get("alt_baro") == "ground":
            continue
        observation: dict[str, Any] = {
            "icao24": icao24,
            "observed_at": max(1, source_now - max(0, round(age))),
            "latitude": latitude,
            "longitude": longitude,
        }
        callsign = str(aircraft.get("flight", "")).strip()
        if callsign:
            observation["callsign"] = callsign[:16]

        altitude = aircraft.get("alt_baro")
        observation["on_ground"] = False
        if (altitude_number := _number(altitude)) is not None:
            observation["baro_altitude"] = altitude_number * FEET_TO_METERS
        if (geometric := _number(aircraft.get("alt_geom"))) is not None:
            observation["geo_altitude"] = geometric * FEET_TO_METERS
        if (speed := _number(aircraft.get("gs"))) is not None and speed >= 0:
            observation["velocity"] = speed * KNOTS_TO_METERS_PER_SECOND
        if (track := _number(aircraft.get("track"))) is not None:
            observation["true_track"] = track % 360
        if (vertical_rate := _number(aircraft.get("baro_rate"))) is not None:
            observation["vertical_rate"] = vertical_rate * FEET_PER_MINUTE_TO_METERS_PER_SECOND
        squawk = str(aircraft.get("squawk", "")).strip()
        if len(squawk) == 4:
            observation["squawk"] = squawk
        observations.append(observation)
    return observations


def load_document(source: str, timeout: float) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        with urllib.request.urlopen(source, timeout=timeout) as response:
            return json.load(response)
    path = Path(parsed.path if parsed.scheme == "file" else source)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def submit(api_url: str, station_id: str, token: str, observations: list[dict[str, Any]], timeout: float, insecure: bool) -> int:
    accepted = 0
    context = ssl._create_unverified_context() if insecure else None
    endpoint = f"{api_url.rstrip('/')}/feeders/{station_id}/observations"
    for start in range(0, len(observations), MAX_BATCH_SIZE):
        batch = observations[start:start + MAX_BATCH_SIZE]
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"observations": batch}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            result = json.load(response)
        accepted += int(result.get("accepted", len(batch)))
    return accepted


def send_heartbeat(api_url: str, station_id: str, token: str, aircraft_count: int, timeout: float, insecure: bool) -> None:
    context = ssl._create_unverified_context() if insecure else None
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/feeders/{station_id}/heartbeat",
        data=json.dumps({"aircraft_count": aircraft_count, "client_version": CLIENT_VERSION}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="http://127.0.0.1/dump1090-fa/data/aircraft.json")
    parser.add_argument("--api-url", default="https://127.0.0.1:8000")
    parser.add_argument("--station", required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--heartbeat-interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Allow a local self-signed API certificate")
    args = parser.parse_args()
    token = os.getenv("FLIGHTMESH_FEEDER_TOKEN")
    if not token:
        parser.error("set FLIGHTMESH_FEEDER_TOKEN to this station's upload token")
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")

    print(f"{CLIENT_VERSION} forwarding {args.source} as {args.station}; press Ctrl+C to stop.")
    last_heartbeat = 0.0
    try:
        while True:
            started = time.monotonic()
            try:
                observations = convert_aircraft(load_document(args.source, args.timeout))
                if args.once or time.monotonic() - last_heartbeat >= max(1.0, args.heartbeat_interval):
                    send_heartbeat(args.api_url, args.station, token, len(observations), args.timeout, args.insecure)
                    last_heartbeat = time.monotonic()
                accepted = submit(args.api_url, args.station, token, observations, args.timeout, args.insecure) if observations else 0
                print(f"read={len(observations)} accepted={accepted} at={int(time.time())}")
            except Exception as exc:
                print(f"forwarding error: {exc}", flush=True)
                if args.once:
                    raise
            if args.once:
                break
            time.sleep(max(0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("Feeder forwarding stopped.")


if __name__ == "__main__":
    main()
