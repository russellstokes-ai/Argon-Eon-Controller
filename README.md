# Argon EON Controller

A Home Assistant add-on that runs the Argon EON case on Home Assistant OS: fan control, the OLED display, drive
temperature and SMART health monitoring, and Home Assistant sensors for every monitored drive.

> Unofficial community add-on. It is not affiliated with or endorsed by Argon40.

## Install

1. In Home Assistant open **Settings → Add-ons → Add-on Store**, choose the **⋮** menu, then **Repositories**, and add:

   `https://github.com/russellstokes-ai/Argon-Eon-Controller`

   Or use this button:
   [![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frussellstokes-ai%2FArgon-Eon-Controller)
2. Install **Argon EON Controls**, start it, and open its page from the sidebar or **Open web UI**.
3. I2C must be enabled on the Pi host for the fan, OLED and RTC to work. The add-on can enable it for you (it asks to
   reboot the host once).

Only one program may own the EON fan and OLED. Stop and remove any other Argon controller add-on first.

Updates appear as an **Update** button on the add-on page when a new version is published here. The first install and
each update build the image on your Home Assistant device, which takes a few minutes. The build runs the project's
test suite and stops if anything fails, so a bad build never replaces the running version.

## Requirements

- Argon EON case with a Raspberry Pi 4 family board (the add-on is built for `aarch64` and `raspberrypi4-64`)
- Home Assistant OS, 64-bit

## What it does

- **Cooling:** fan curves from CPU and drive temperature, an emergency threshold, a failsafe speed, and a minimum
  fan speed while a drive's temperature cannot be read.
- **Drive monitoring:** SMART health and temperature. Argon EON bays are detected automatically; other USB drives can be
  given a SMART bridge type. Drives that are asleep are never woken to be read.
- **OLED display:** configurable pages (clock, temperature, storage, network, CPU, memory, disk activity, drive alerts,
  cooling, uptime, custom text) with page cycling, pixel shifting, periodic rests and an overnight schedule.
- **Home Assistant sensors:** CPU temperature, fan, and for each monitored drive a temperature sensor and a health
  sensor, plus a hottest-drive sensor and a "drive problem" sensor for automations.
- **Notifications** for drive problems and hardware errors, a **physical button** (observe-only until you enable
  actions), **RTC** status and sync, and **diagnostics** with settings export and import.

See the add-on's **Documentation** tab (`argon_eon_controls/DOCS.md`) for details and the **Changelog** tab for the
version history.

## Moving from a locally installed copy

Settings are stored per add-on, so a copy installed from this repository starts with default settings.

1. In the old add-on, open **System & diagnostics → Export settings**.
2. Stop and uninstall the old add-on.
3. Install and start the new one, then use **Import settings**.

## Third-party code

`argon_eon_controls/upstream_argoneon/` contains an unmodified-except-where-noted snapshot of
[JeffCurless/argoneon](https://github.com/JeffCurless/argoneon) (commit `da5756a`), itself derived from Argon40's
scripts; the OLED and RTC routines are used from it. That snapshot has no declared licence, and its authors keep their
rights; see `argon_eon_controls/upstream_argoneon/UPSTREAM.md`. No licence has been chosen yet for the rest of this
repository.

## Development

The test suite runs inside the Docker build. To run it locally:

```
cd argon_eon_controls
python3 -m unittest discover -s tests
```

To publish a release, change the files, raise `version` in `argon_eon_controls/config.yaml` (and `VERSION` in `app.py`,
`BUILD_VERSION` in the `Dockerfile`, and the top of `CHANGELOG.md`; a test checks they agree), and commit.
