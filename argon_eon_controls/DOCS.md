# Argon EON Controls 1.0.2

Version 1.0.0 is the first stable release. It supersedes every earlier build, including the 1.0 and 1.1 prototypes and the 1.2.0 release candidates, which should not be kept as fallbacks. Hardware features that Home Assistant OS does not support on this case (RTC alarms and automatic power-cut scheduling) remain unavailable and are marked as such in the app.

## Install or update

**From GitHub (recommended).** In Home Assistant open Settings > Apps (formerly Add-ons) > Install app > the three-dot menu > Repositories, add `https://github.com/russellstokes-ai/Argon-Eon-Controller`, then install Argon EON Controls from the new list. Each later release then appears as an Update button. Stop any other Argon controller first, and if you are moving from a local install, use Export settings in the old app and Import settings in the new one.

**Local install (manual copy).** Steps:

1. Keep a current Home Assistant backup outside the EON.
2. Extract the ZIP; copy only `argon_eon_controls` into the Samba `addons` share. The resulting file must be `/addons/argon_eon_controls/config.yaml`.
3. Stop any existing Argon controller app. Only one program may own the EON fan/OLED.
4. In the Home Assistant Apps store (formerly Add-ons), check for updates/refresh so the Local apps entry appears, then install Argon EON Controls; if updating, replace the source folder, check for updates and use Update (or Rebuild where offered). 1.0.0 is numerically lower than the earlier 1.2.0 release candidates, so Home Assistant will not offer an Update to it from one of those builds: use Rebuild instead. The first install builds the image on the Pi (several minutes, needs internet for the Debian base and smartmontools). If it fails, open Logs, choose Supervisor, and read the Build output section: that shows exactly which Dockerfile step stopped.
5. This hardware app requests full device access. Turn off its Protection mode so HA OS can grant the declared access. Enable Start on boot and Watchdog.
6. Start and open its Web UI. The fan runs the configured curve immediately; there is no manual confirmation step.
7. Confirm CPU temperature is plausible. Choose automatic cooling and save settings.

I2C must be enabled on the Pi host (`/dev/i2c-1` must exist) for the fan, OLED and RTC to work. The app
tries to enable it itself on first run (edits the boot partition, then requests one host reboot). If the
Supervisor log shows repeated "I2C auto-enable skipped" lines with the mount failing "permission denied"
regardless of options tried, this app cannot mount the boot partition on your system from inside the
container - this has been observed and is not yet resolved. In that case use the community "HassOS I2C
Configurator" app (Settings > Apps > Store > add repository `github.com/adamoutler/HassOSConfigurator`),
or edit the SD card's `config.txt` directly on another computer. Do not run the Raspberry Pi OS Argon
installer on HA OS.

## Disk policy

CPU temperature: every 10 seconds, independent cooling worker. Dashboard reads cached data only. Drive inventory comes from `/sys/block`, with no disk reads. SMART refresh: every five minutes in a separate worker; each command has an eight-second timeout. A separate watcher reads only kernel I/O counters under `/sys/block` every 10 seconds (no command is sent to any disk). If the OS touches a drive last seen in Standby, one immediate SMART poll is requested (at most once per 30 seconds) so a naturally woken drive is measured and used for cooling within seconds. A drive that vanishes from `/sys/block` raises a Home Assistant warning naming its model, size and USB port.

To avoid device-type autodetection waking a drive, SMART is disabled until an explicit SATA passthrough type is selected for that disk. Argon EON bays (USB IDs 174e:1155 and 1741:1156) are recognised and use `sat` automatically; a type chosen in the Drives tab overrides that. Select `sat`, `sat,12` or `sat,16` only after verifying the bridge supports it. Unknown or unsupported power-state reporting stops further probing; there is no fallback command that bypasses the power check.

Commands use `-n standby,99,98`: 99 means standby, 98 means the power-state check is unsupported. Exit 99 is trusted as Standby only when smartctl says STANDBY; smartctl also exits 99 with SLEEP when the power-mode command itself failed, and that is shown as Unknown so the conservative minimum fan applies. Awake disks provide SMART and temperature; sleeping disks display Standby and retain the last temperature/timestamp. Cached standby values are not treated as current thermal readings. A missing CPU sensor always requests 100%; unmonitored active/unknown drives impose the configured conservative minimum.

Weekly/monthly short or long self-tests are optional and disabled by default. These are once per calendar period, deferred until naturally awake. Even manual tests use the no-wake guard. Unsupported bridges cannot support a guaranteed non-waking query, so monitoring remains unavailable on them. This cannot prevent other apps from waking disks.

Health is Warning when pending or uncorrectable sectors are reported, and Failed on overall SMART failure or a pre-failure attribute at its threshold. The dashboard card and one Home Assistant notification identify the drive by name, model, size, serial tail and USB port. Old error-log or self-test-log entries are shown as notes only, so an old cable glitch does not alert forever.

Disk settings use Linux device names in this candidate. Re-check mappings after changing drive connections. Cached measurements are process-local; restart begins with Unknown rather than a misleading old measurement.

## Physical button

The GPIO worker locates the Pi 4 `pinctrl-bcm2711` device and requests GPIO4 input only. Kernel edge timestamps classify the upstream short encoded pulses. Observe mode logs actions and supports page switching. Observe the expected actions in the log before enabling shutdown; double-press reboot is separately configurable.

Enabled shutdown/reboot uses Supervisor `/host/shutdown` or `/host/reboot`, with force=false. This safely requests an OS action. It does not issue a physical EON power cut. Do not hold the button into the case's forced-cut behaviour while testing.

## RTC

The RTC is read at address 0x51. Copy-current-time writes UTC to the RTC using the selected pinned upstream setter and verifies readback within three seconds. It never changes the host clock. Invalid RTC clock status is displayed; it is not a battery percentage gauge.

## Cooling and shutdown

The cooling loop owns all fan writes. Tests are queued to it and expire after ten seconds; the current policy applies within the next one-second loop cycle. Emergencies and missing CPU readings override tests/manual/off. A normal app stop requests 100% fan. Failed writes are reported as Unknown, not successful cooling.

The heartbeat health endpoint becomes unhealthy if cooling stops progressing for 25 seconds. Enable Supervisor Watchdog for recovery. No software can guarantee a new fan command after process SIGKILL, an OS hang, power loss, a failed MCU or a seized fan. Hardware may retain the last command; this needs physical verification. No RPM feedback is available.

## OLED

Brightness, ordered pages with up/down buttons, custom text, one-pixel shifts, periodic rests, overnight schedule and timezone are configurable. Stock information categories are provided with a different visual layout; disk activity is shown as cumulative byte totals, not an instantaneous throughput benchmark. Pixel shifts/rests reduce exposure but cannot guarantee no OLED ageing.

Pages: Clock, Temperature, Storage (monitored drives only, with a short health word; "zz" marks a last reading from before a drive went to sleep), Network, Custom, CPU load, Memory, Disk activity, RAID status, Drive alerts (names a drive that is Warning or Failed and why, otherwise says all is well), Cooling (fan speed and the reason for it) and Uptime. Tick the ones you want on the OLED panel tab.

## Home Assistant entities

With "Publish Home Assistant sensor states" on, the app publishes:

- `sensor.argon_eon_cpu_temperature` and `sensor.argon_eon_fan_command`.
- For each monitored drive: a temperature sensor and a SMART health sensor. Bad-sector counts, power-on hours and power state are attributes. A sleeping drive keeps its last temperature, flagged as a cached reading.
- `sensor.argon_eon_hottest_drive_temperature`.
- `binary_sensor.argon_eon_drive_problem`, on when any monitored drive is Warning or Failed. Its `drives` attribute lists them.

Drive sensors are named after the end of the drive's serial number, so a drive keeps its history if Linux renames sda/sdb/sdc; a replacement drive starts a new history. Drives that are ignored, unmonitored or in an empty bay are not published, and a drive that disappears is marked unavailable. These are state-only entities created through the Home Assistant API: they have no unique ID, so they cannot be renamed or assigned to an area in the UI, and they reappear within 30 seconds after Home Assistant restarts. Example automation: notify when `binary_sensor.argon_eon_drive_problem` turns on.

## Security and host isolation

Ingress-only web UI; no host port. Requests from outside the Supervisor ingress proxy are rejected. Mutations require a same-origin custom header. Configuration is validated and replaced atomically with fsync. No shell is invoked for user input. The app has no disk format/mount/erase, controller flash or host clock-setting command.

It requires broad hardware access for I2C, GPIO and SMART. Do not expose the container port externally. The local process lock stops duplicate copies sharing /data; it does not detect other Argon apps. Stop conflicting apps manually.

## Deliberately unfinished / unsupported

- Automatic EON power cut after host shutdown, RTC alarm wake/power schedules: require a verified late host-shutdown mechanism unavailable to an ordinary add-on. No delay-based power cut is supplied.
- IR receiver support: no verified EON hardware/configuration in this setup.
- Native registered HA device/integration and dashboard controls: this release publishes sensor states (see Home Assistant entities) and persistent notifications only.
- Per-drive custom cooling curves: hottest-current-drive curve is used.
- USB reset history, undervoltage/throttle history, live network throughput and verified end-to-end TRIM: not implemented. USB topology/reported revision/link speed/driver and kernel discard advertisement are diagnostics only.
- Container and real hardware acceptance are outstanding. Unit tests cannot prove a physical fan, bridge or power sequence.

## Source

Pinned JeffCurless/argoneon commit: da5756a02a6409ec98b3aa8e3ceb8b40609a572d.

Selected OLED transfer/reset functions and the RTC setter execute from the included, checksummed source through `upstream_adapter.py`. The installer, original service loop and stock shutdown hook are never executed. Fan writing and cooling policy remain a reviewed HA OS adapter; the full original daemon is not running. The upstream snapshot has no declared licence; its attribution/headers are retained and no public repository is published by this task.
