# FlightMeshAir Linux ADS-B feeder

This installer connects an approved ADS-B receiver to FlightMeshAir. You must receive a unique station ID and private upload token from FlightMeshAir before installation.

> **Recommended, not required:** A Raspberry Pi running PiAware/dump1090-fa is the tested and recommended setup. Other Debian-based Linux computers and compatible decoders can be used when they run `systemd`, have Python 3, and expose an accessible `aircraft.json` file.

Never post your upload token in GitHub, email screenshots, terminal screenshots, or support messages. The installer prompts for it privately and stores it in `/etc/flightmesh/feeder.env`, readable only by root.

## Before you begin

You need:

- A Raspberry Pi running 64-bit Raspberry Pi OS, or another Debian-based Linux computer using `systemd`
- Ethernet or Wi-Fi internet access
- A compatible ADS-B USB receiver and 1090 MHz antenna
- PiAware, dump1090-fa, readsb or another compatible decoder receiving aircraft and producing `aircraft.json`; the installer will detect common local URLs automatically, or can try a guarded package-managed receiver install on Raspberry Pi OS/Debian
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

The installer checks common local PiAware/dump1090-fa/readsb/tar1090 sources and prints a receiver summary before it configures FlightMeshAir. It validates that the URL returns dump1090/readsb-style `aircraft.json`, not just that a web port is open.

For the recommended PiAware setup, you can also confirm dump1090-fa manually:

```bash
sudo systemctl status dump1090-fa --no-pager
curl -fsS http://127.0.0.1:8080/data/aircraft.json | python3 -m json.tool | head -60
```

If no valid local receiver source is found, the installer stops with next steps instead of installing a feeder service pointed at a dead URL. On Raspberry Pi OS or Debian, you can opt in to a conservative package-managed receiver install:

```bash
sudo ./install.sh --station YOUR-STATION-ID --install-receiver
```

This path only installs `dump1090-mutability` when it is already available from the computer's configured apt repositories. It does not add FlightAware or other third-party repositories, and it will not overwrite an existing PiAware, dump1090-fa, dump1090-mutability, readsb or tar1090 installation. After the install attempt, FlightMeshAir checks again for a valid `aircraft.json` URL and still stops if one is not available.

## 3. Install the FlightMeshAir feeder

```bash
curl -fsSLo flightmeshair-install.sh https://raw.githubusercontent.com/wbell09/flightmeshair-feeder/main/bootstrap.sh
chmod +x flightmeshair-install.sh
./flightmeshair-install.sh --station YOUR-STATION-ID
```

Replace `YOUR-STATION-ID` with the ID provided by FlightMeshAir. When prompted, paste the private upload token and press Enter. The token will not appear while you type or paste it.

The bootstrap downloads the public installer files into `~/flightmeshair-feeder`, then runs the normal installer with `sudo`. During installation you will see the receiver services checked and the `aircraft.json` URL selected. The chosen URL is stored as `FLIGHTMESH_AIRCRAFT_SOURCE` in `/etc/flightmesh/feeder.env`.

If you prefer to review the installer before running it, open `flightmeshair-install.sh` after the download, or review the same source in this repository. The bootstrap avoids putting your upload token in the command line or shell history; the normal installer still prompts for it privately.

If you do not want the installer to prompt about receiver software when no source is found, use:

```bash
sudo ./install.sh --station YOUR-STATION-ID --no-install-receiver
```

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
sudo systemctl status dump1090-fa dump1090-mutability readsb tar1090 flightmesh-feeder --no-pager
```

See which aircraft source FlightMeshAir is using:

```bash
sudo grep '^FLIGHTMESH_AIRCRAFT_SOURCE=' /etc/flightmesh/feeder.env
```

## Updating an existing feeder

The private feeder portal compares the version reported by this service with the current release. Version 0.2.7 includes guarded receiver detection, optional aircraft category/type forwarding, the one-step bootstrap installer and the updater that checks every five minutes for an update explicitly approved by the feeder owner in the portal. The backend cannot connect inbound to the Pi; the Pi securely pulls only a checksum-pinned HTTPS artifact, validates its Python syntax, keeps a rollback copy and reports success or failure.

Existing installations need this one-time bootstrap before the portal button can work:

```bash
curl -fsSLo flightmeshair-install.sh https://raw.githubusercontent.com/wbell09/flightmeshair-feeder/main/bootstrap.sh
chmod +x flightmeshair-install.sh
./flightmeshair-install.sh --station YOUR-STATION-ID
```

After that, future feeder-script updates can be approved from the portal. Manual update steps remain available as a recovery path.

The portal update button updates the feeder forwarding script. To refresh the updater service itself, including clearer token-authentication diagnostics, rerun the one-time bootstrap command above.

### Updating manually

These recovery steps update only the forwarding script. Use the bootstrap command above to refresh the updater or service definitions; it overwrites matching downloaded files and reruns the installer, including its configuration prompts.

Run the block in Bash as your **normal feeder user**, not from a root shell or with `sudo bash`. The block uses that user's home directory and calls `sudo` only for the installed files and service. Git and sudo must already be installed; on Debian-based systems, Git can be installed separately with `sudo apt-get update` followed by `sudo apt-get install git`.

The block preserves bootstrap-downloaded files and uses a separate Git checkout when needed. It requires a clean `main` branch tracking `origin/main`. After fetching, it stops for any local commits ahead of or diverged from the published branch, as well as local edits and untracked files. Review and preserve your work before retrying; do not discard it just to complete an update.

Before replacing the installed script, the block makes a uniquely named backup beside it. Keep the printed backup path for recovery. This updates an existing feeder; if the installed script is absent, use the bootstrap installation first.

```bash
(
  set -euo pipefail

  if [ "$(id -u)" -eq 0 ]; then
    echo "Run this block as the normal feeder user, not with sudo or as root." >&2
    exit 1
  fi
  command -v git >/dev/null || {
    echo "Git is required. Install it before running these update steps." >&2
    exit 1
  }

  original_dir="$HOME/flightmeshair-feeder"
  alternate_dir="$HOME/flightmeshair-feeder-git"

  is_checkout_root() {
    [ -d "$1" ] || return 1
    [ "$(git -C "$1" rev-parse --is-inside-work-tree 2>/dev/null)" = true ] || return 1
    [ "$(git -C "$1" rev-parse --show-prefix 2>/dev/null)" = "" ]
  }

  if is_checkout_root "$original_dir"; then
    source_dir="$original_dir"
  else
    if [ -d "$original_dir" ]; then
      echo "Original directory is not an accessible checkout root; leaving it unchanged."
    elif [ -e "$original_dir" ] || [ -L "$original_dir" ]; then
      echo "Original source path is not a usable directory; leaving it unchanged."
    else
      echo "Original source directory is missing."
    fi

    source_dir="$alternate_dir"
    if [ -e "$source_dir" ] || [ -L "$source_dir" ]; then
      if ! is_checkout_root "$source_dir"; then
        echo "Alternate destination exists but is not an accessible checkout root. Review it before continuing." >&2
        exit 1
      fi
    else
      git clone https://github.com/wbell09/flightmeshair-feeder.git "$source_dir"
    fi
  fi

  origin_url="$(git -C "$source_dir" remote get-url origin)"
  case "$origin_url" in
    https://github.com/wbell09/flightmeshair-feeder.git|https://github.com/wbell09/flightmeshair-feeder|git@github.com:wbell09/flightmeshair-feeder.git)
      ;;
    *)
      echo "Unexpected origin: $origin_url. Review the repository before continuing." >&2
      exit 1
      ;;
  esac

  branch="$(git -C "$source_dir" symbolic-ref --quiet --short HEAD)" || {
    echo "Detached HEAD: select the intended main checkout before updating." >&2
    exit 1
  }
  upstream="$(git -C "$source_dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}')" || {
    echo "No upstream branch is configured. Review the checkout before updating." >&2
    exit 1
  }
  if [ "$branch" != main ] || [ "$upstream" != origin/main ]; then
    echo "These update steps require main tracking origin/main. Review the checkout before continuing." >&2
    exit 1
  fi

  if [ -n "$(git -C "$source_dir" status --porcelain)" ]; then
    git -C "$source_dir" status --short
    echo "Review and preserve local edits and untracked files before updating." >&2
    exit 1
  fi

  git -C "$source_dir" fetch origin
  if [ "$(git -C "$source_dir" rev-list --count origin/main..HEAD)" -ne 0 ]; then
    echo "Local commits are ahead of or diverged from origin/main. Review them before updating." >&2
    exit 1
  fi
  git -C "$source_dir" merge --ff-only origin/main

  if [ ! -f "$source_dir/forward_dump1090.py" ]; then
    echo "The updated forwarding script is missing. No installed files were replaced." >&2
    exit 1
  fi
  installed_script=/opt/flightmesh/forward_dump1090.py
  if ! sudo test -f "$installed_script"; then
    echo "Existing feeder script not found. Use the bootstrap installation first." >&2
    exit 1
  fi
  backup="$(sudo mktemp "${installed_script}.backup.XXXXXXXX")"
  sudo cp -p "$installed_script" "$backup"
  printf 'Saved previous forwarding script to %s\n' "$backup"
  sudo install -m 0755 "$source_dir/forward_dump1090.py" "$installed_script"
  sudo systemctl restart flightmesh-feeder
  sudo systemctl status flightmesh-feeder --no-pager
)
```

A detached HEAD, missing or unexpected upstream, failed fetch, or unsuccessful fast-forward also stops before installation. If the service fails after installation, the backup remains available; these steps do not automatically restore it.

Verify uploads:

```bash
sudo journalctl -u flightmesh-feeder -n 30 --no-pager
```

Look for successful uploads, for example `read=21 accepted=21`. The counts vary; 21 is not a required value. Check the surrounding logs for errors. Live receiver reception and accepted uploads must be verified on the feeder computer.

## View your private portal

Sign in at [feed.flightmeshair.com](https://feed.flightmeshair.com/) using the customer account provided by FlightMeshAir. The upload token used by the Pi is separate from your website password.

## Support

Email [feeders@flightmeshair.com](mailto:feeders@flightmeshair.com) with your station ID and a description of the problem. Do not send your upload token.

## Development checks

From the repository root, run:

```bash
python3 tests/check_manual_update.py
```

The checker requires Python 3, Bash, and a recent Git. It extracts the documented update block and exercises 28 isolated scenarios with local Git remotes, simulated source directories, and stubbed privileged commands. It does not install software, contact GitHub, or control real services. It verifies the update flow, not live receiver reception or uploads.
