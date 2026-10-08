# 1.0.2

New: every monitored drive is now published to Home Assistant, so it gets history graphs, dashboard cards and automations.
For each drive: a temperature sensor and a SMART health sensor (with bad-sector counts, power-on hours and power state as
attributes). Also a "hottest drive" temperature sensor and a "drive problem" on/off sensor that turns on when any drive is
Warning or Failed, which makes "tell me if a drive goes bad" a one-step automation. Drive sensors are named after the
drive's serial number tail, so a drive keeps its history when Linux renames sda/sdb/sdc, and a replacement drive starts
a fresh history. A sleeping drive keeps its last temperature, marked as a cached reading. Turn them off with "Publish Home
Assistant sensor states". Entities are created through the Home Assistant states API, as the CPU and fan sensors are, so
they have no unique ID and cannot be renamed or edited in the UI; they reappear within 30 seconds after a Home Assistant
restart.

New OLED pages (tick them on the OLED panel tab): Drive alerts (names the drive and the problem, or says all is well),
Cooling (fan speed and why) and Uptime (with CPU and memory load).

Fixed: the Storage page listed the first three disks by name, so it showed ignored drives and empty bays as "Unknown --C"
and could leave out a monitored drive. It now shows only monitored drives (up to four), with a short health word and a
marker when the temperature is the last reading from before a drive went to sleep.

Fixed: while a drive sleeps, its serial, model and bad-sector counts are now kept from its last awake reading instead of
disappearing.

# 1.0.1

Fixed: saving a changed drive setting (for example setting a disk to Ignore) now rechecks the drives immediately. Before,
the change only took effect at the next five-minute check, so the page and the fan's "cannot read temperature" minimum
kept showing the old state in the meantime.

Fixed: a manual SMART test can no longer be requested for an empty bay.

# 1.0.0

First stable release. It carries every fix from the 1.2.0-rc13 build (listed below) and supersedes all earlier builds,
including the 1.0 and 1.1 prototypes and the 1.2.0 release candidates. The version number was reset to 1.0.0 for the stable
release, so Home Assistant will not offer an Update from a 1.2.0-rc install: use Rebuild.

New: the header status now has three clear states. Connected shows the cooling status, "Connection lost" appears when the
add-on does not answer (the last readings stay on screen), and "Display error" appears, with an explanation banner, when
this page itself fails to draw. Each section of the page now draws independently, so one failing section can no longer
blank the others. This is the failure that made the Drives tab empty in 1.2.0-rc12.

New: unsaved changes are marked in the footer, the Save button highlights while there is something to save, the page warns
before you leave with unsaved changes, and confirmations clear themselves after a few seconds (errors stay longer).

New: the diagnostics tab shows problems as a short list, recent events newest first with dates and times, the connected
USB devices as a collapsible table (port, device, ID, speed, driver), and the RTC state in plain words. An About card shows
the version.

Changed: the add-on stage is now stable.

# 1.2.0-rc13

Fixed: the dashboard stopped drawing the Drives tab ("Cannot set properties of null (setting 'hidden')"). rc10 removed
the first-start fan-check card but left a line in app.js that still hid it; that line threw on every refresh, which
stopped the rest of the refresh (the drive cards, events, USB list). The line is gone, and a new test fails the build
if app.js ever references an element id that index.html does not contain.

Fixed: two drives behind one USB bridge (the Argon EON bays: sdc and sdd share one bridge) had the same identity, so
the second overwrote the first in the presence watcher, the SMART cache and the SMART alert tracking (the first drive
was missing from `present`, and alerts for one drive could be cleared by its neighbour's healthy status). Identity now
includes the SCSI channel:target:lun for LUN > 0 (LUN 0 keeps its previous identity, so nothing already stored changes).

New: Argon EON bays are detected from their USB IDs (174e:1155 and 1741:1156) and monitored with the explicit `sat`
type automatically; no manual drive setting is needed. The same no-wake guard applies (`-n standby,99,98`, explicit
`-d`, no autodetection). A type chosen in the Drives tab still wins, and "Ignore" is still honoured. Drives on other
bridges (for example one plugged into the Pi's own USB port) stay unmonitored until a type is selected. Scheduled and
manual SMART tests use the same effective type.

Known limitation, unchanged: the drive-type setting is keyed by device name (sda, sdb...).

# 1.2.0-rc12

Fixed a real bug seen in a field log: a drive's identity was derived from a sysfs path that
includes its kernel-assigned letter (sda/sdb/...), so a device rename (which Linux can do at
any reconnect or reboot, independent of this app) reset that drive's cached health/temperature
and could make the same failing drive raise its SMART alert twice under two different names.
Identity is now based on the drive's USB port, which does not change when the kernel reassigns
a letter. This affects the disk-presence watcher (patch 04) and the SMART cache/alert dedup
(patch 05) alike; both are covered by new regression tests reproducing the exact rename.

Known limitation, not fixed here: the drive-type setting in the Drives tab is still keyed by
device name (sda, sdb...), so if the kernel renames a drive, you may need to reassign its
bridge type. A future release should key it by the same stable identity instead.

Known limitation, not fixed here: on at least one system, the built-in I2C auto-enable cannot
mount the boot partition under any option set tried (fails "permission denied" with no kernel
detail). If this happens to you, the community HassOS I2C Configurator app, or editing the SD
card directly, are the reliable alternatives - see DOCS.md.

# 1.2.0-rc11

Fixed: hostname/OS/kernel/IP were being refetched from the Supervisor API every 30 seconds forever, flooding the Supervisor log with /host/info and /network/info lines. They now refresh once at startup and at most every 15 minutes; everything else in the telemetry loop (USB, disk metrics, RTC, notifications) still runs every 30 seconds as before.

# 1.2.0-rc10

UI: removed the "First-start fan check" card (dead since rc3 made the fan live immediately) and its now-unused /api/commission endpoint; header version is now read from the running app instead of a hand-edited string; static assets are cache-busted so an update can't be masked by a stale browser cache; merged a duplicated "Recheck all drives now" button into one.

# 1.2.0-rc9

Fixed: the "ignore" drive type was accepted by the backend (rc4) but missing from the dropdown in the Drives tab, so it could never actually be selected. It now appears as "Ignore this disk (not monitored)".

# 1.2.0-rc8

OLED panel tester: White/Black/Checker/Rings test patterns, drawn without touching any app state, so a panel fault can be told apart from a software one. Shown live on the physical screen for 10s via the OLED tab. "Recheck all drives now" button forces an immediate SMART poll instead of waiting for the schedule. Bug fixes found while re-verifying: the drive "ignore" setting was rejected by config validation; a permission error while probing the host's own boot mount could crash i2c auto-enable instead of falling back to mounting it directly.

# 1.2.0-rc2

Behaviour fixes (each also available as a separate patch): a failed power-mode check is no longer mistaken for a sleeping drive; every fan reduction waits its own fall delay; notifications raise once per condition, dismiss when it clears and can raise again; a sysfs-only watcher measures a naturally woken drive within seconds and reports vanished drives, without sending any command to a sleeping disk; pending/uncorrectable sectors raise a Warning and notifications name the exact drive (model, size, serial tail, USB port); the SMART sample schedule is anchored to poll start so readings stay inside the freshness window; a stale disk error clears after a good poll.

Build and install: Dockerfile now declares `io.hass.type="app"` and the version/arch/name labels required by Supervisor 2026.04+, retries apt on flaky networks, and runs the self-tests before the image is finalised. The one timing-dependent test now waits for its outcome instead of sleeping, so a slow Pi cannot fail the build spuriously. `.dockerignore` keeps stray bytecode out of the image.

# 1.2.0-rc1

Reliability rewrite: independent cooling, storage, display, GPIO and HA workers; truthful fan command status; temperature safety overrides; heartbeat health checks; atomic validated settings; ingress-only mutations; protected test expiry; non-waking, explicit-type SMART polling; cached standby values; optional deferred health tests; button event decoding and Supervisor OS requests; verified RTC UTC write; selected executable upstream functions; OLED protection/scheduling/page ordering; hashed bundled ARM64 Python dependencies.

Still a commissioning candidate. See DOCS.md for outstanding host power-cut, RTC wake and hardware acceptance limits.
