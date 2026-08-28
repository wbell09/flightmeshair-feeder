# FlightMeshAir Linux ADS-B feeder

This installer connects an approved ADS-B receiver to FlightMeshAir. You must receive a unique station ID and private upload token from FlightMeshAir before installation.

> **Recommended, not required:** A Raspberry Pi running PiAware/dump1090-fa is the tested and recommended setup. Other Debian-based Linux computers and compatible decoders can be used when they run `systemd`, have Python 3, and expose an accessible `aircraft.json` file.

Never post your upload token in GitHub, email screenshots, terminal screenshots, or support messages. The installer prompts for it privately and stores it in `/etc/flightmesh/feeder.env`, readable only by root.

## Before you begin

You need:

- A Raspberry Pi running 64-bit Raspberry Pi OS, or another Debian-based Linux computer using `systemd`
- Ethernet or Wi-Fi internet access
- A compatible ADS-B USB receiver and 1090 MHz antenna
- PiAware, dump1090-fa, readsb or another compatible decoder already receiving aircraft and producing `aircraft.json`
- Your assigned FlightMeshAir station ID and upload token

## 1. Connect to the feeder computer

From Terminal on your computer:

```bash
ssh YOUR-USERNAME@YOUR-FEEDER-HOST.local
```

## 2. Verify the receiver

Confirm Linux sees the USB receiver:

```bash
lsusb
```

For the recommended PiAware setup, confirm dump1090-fa is running:

```bash
sudo systemctl status dump1090-fa --no-pager
```

Confirm aircraft data is available:

```bash
curl -fsS http://127.0.0.1:8080/data/aircraft.json | python3 -m json.tool | head -60
```

Other decoder installations may use a different service name or URL. Use the local `aircraft.json` URL provided by that decoder.

## 3. Install the FlightMeshAir feeder

```bash
sudo apt-get update
sudo apt-get install -y git python3
git clone https://github.com/wbell09/flightmeshair-feeder.git
cd flightmeshair-feeder
sudo ./install.sh --station YOUR-STATION-ID
```

Replace `YOUR-STATION-ID` with the ID provided by FlightMeshAir. When prompted, paste the private upload token and press Enter. The token will not appear while you type or paste it.

If your aircraft JSON is at a different local URL, pass it explicitly:

```bash
sudo ./install.sh \
  --station YOUR-STATION-ID \
  --source http://127.0.0.1/dump1090-fa/data/aircraft.json
```

## 4. Verify uploads

```bash
sudo systemctl status flightmesh-feeder --no-pager
sudo journalctl -u flightmesh-feeder -n 30 --no-pager
```

Successful logs contain entries similar to:

```text
read=21 accepted=21
```

Only airborne aircraft with positions seen within the last 45 seconds are forwarded. Aircraft that land or stop transmitting automatically disappear from live maps instead of remaining at their last known position.

The service starts automatically after reboot and restarts if it encounters an unexpected error.

## Useful commands

Follow live logs:

```bash
sudo journalctl -u flightmesh-feeder -f
```

Restart the feeder:

```bash
sudo systemctl restart flightmesh-feeder
```

Check both receiver services:

```bash
sudo systemctl status dump1090-fa flightmesh-feeder --no-pager
```

## Updating an existing feeder

The private feeder portal compares the version reported by this service with the current release. Version 0.2.2 adds an updater that checks every five minutes for an update explicitly approved by the feeder owner in the portal. The backend cannot connect inbound to the Pi; the Pi securely pulls only a checksum-pinned HTTPS artifact, validates its Python syntax, keeps a rollback copy and reports success or failure.

Existing installations need this one-time bootstrap before the portal button can work:

```bash
git -C ~/flightmeshair-feeder pull
cd ~/flightmeshair-feeder
sudo ./install.sh --station YOUR-STATION-ID
```

After that, future feeder-script updates can be approved from the portal. Manual update steps remain available as a recovery path.

```bash
git -C ~/flightmeshair-feeder pull
sudo install -m 0755 \
  ~/flightmeshair-feeder/forward_dump1090.py \
  /opt/flightmesh/forward_dump1090.py
sudo systemctl restart flightmesh-feeder
sudo systemctl status flightmesh-feeder --no-pager
```

If `~/flightmeshair-feeder` does not exist yet, clone it first:

```bash
git clone https://github.com/wbell09/flightmeshair-feeder.git ~/flightmeshair-feeder
```

## View your private portal

Sign in at [feed.flightmeshair.com](https://feed.flightmeshair.com/) using the customer account provided by FlightMeshAir. The upload token used by the Pi is separate from your website password.

## Support

Email [feeders@flightmeshair.com](mailto:feeders@flightmeshair.com) with your station ID and a description of the problem. Do not send your upload token.
