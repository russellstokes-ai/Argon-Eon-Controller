"""Enable I2C on Home Assistant OS from inside the app.

The EON fan controller, OLED and RTC sit on I2C bus 1, which HAOS ships disabled. If /dev/i2c-1 is
missing this edits config.txt and the module list on the hassos-boot partition once, then the caller
asks for ONE host reboot. A marker file guarantees it can never reboot-loop.
"""
import os, re, subprocess, time
from pathlib import Path

OPTION_SETS = ["rw", "rw,iocharset=ascii", "rw,iocharset=utf8", "rw,iocharset=iso8859-1",
               "rw,codepage=437,iocharset=ascii", "rw,fmask=0022,dmask=0022,codepage=437,iocharset=ascii,shortname=mixed"]
HOST_BOOT = "/proc/1/root/mnt/boot"  # the host's own mount of hassos-boot, visible when the app shares the host PID namespace
BOOT_CANDIDATES = ("/boot/firmware", "/boot")  # standalone: Raspberry Pi OS bookworm+ vs. older layouts

def apply_boot_config(boot):
    """Idempotent. Returns True if anything was changed."""
    boot = Path(boot); changed = False
    cfg = boot / "config.txt"; text = cfg.read_text() if cfg.exists() else ""
    if not re.search(r"(?m)^\s*dtparam=i2c_arm=on\s*$", text):
        backup = boot / "config.txt.eon-backup"
        if cfg.exists() and not backup.exists(): backup.write_text(text)
        text = re.sub(r"(?m)^\s*dtparam=i2c_arm=(off|0)\s*\n?", "", text)
        # [all] resets any [pi4]/[cm4] filter the file may end inside, so the setting always applies
        cfg.write_text(text.rstrip("\n") + ("\n" if text.strip() else "") +
                        "\n# Added by Argon EON Controls: EON fan/OLED/RTC use I2C bus 1\n[all]\ndtparam=i2c_arm=on\n")
        changed = True
    mod = boot / "CONFIG" / "modules" / "rpi-i2c.conf"
    if not mod.exists() or "i2c-dev" not in mod.read_text():
        mod.parent.mkdir(parents=True, exist_ok=True); mod.write_text("i2c-dev\n"); changed = True
    return changed

def _kernel_reason():
    try:
        out = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10).stdout.splitlines()
        return " | ".join([l for l in out if "FAT-fs" in l or "mmcblk0p1" in l][-4:])
    except Exception:
        return ""

def ensure(marker, device="/dev/i2c-1", mountpoint="/mnt/hassos-boot", report=None, host_boot=HOST_BOOT, standalone=False):
    """'present' | 'attempted' | 'configured' (edited, nothing to reboot for) | 'reboot' (edited: reboot once).
    Every step is appended to `report` so a failure explains itself.
    standalone=True: running directly on the host (no container boundary), so /boot is just a normal
    directory — no mount is needed or attempted."""
    log = report if report is not None else []
    try:
        if Path(device).exists(): return "present"
    except OSError: pass
    if Path(marker).exists(): return "attempted"
    def done(changed):
        Path(marker).write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
        return "reboot" if changed else "configured"
    if standalone:
        for boot in BOOT_CANDIDATES:  # Raspberry Pi OS bookworm+ vs. older layouts
            if (Path(boot) / "config.txt").exists():
                changed = apply_boot_config(boot); os.sync(); log.append("edited "+boot); return done(changed)
        raise RuntimeError("no config.txt found under /boot/firmware or /boot; enable I2C manually (e.g. raspi-config)")
    try: host_has_boot = (Path(host_boot) / "config.txt").exists()
    except OSError: host_has_boot = False  # not privileged / no shared PID namespace: fall through
    if host_has_boot:  # 1. host already has it mounted
        try:
            changed = apply_boot_config(host_boot); os.sync(); log.append("edited the host's /mnt/boot"); return done(changed)
        except OSError as e:
            log.append("host /mnt/boot not writable: %s" % e)
    dev = subprocess.run(["blkid", "-L", "hassos-boot"], capture_output=True, text=True, timeout=10).stdout.strip()
    if not dev: raise RuntimeError("hassos-boot partition not found; enable I2C manually")
    Path(mountpoint).mkdir(parents=True, exist_ok=True)
    for opts in OPTION_SETS:  # 2. mount it ourselves, trying option sets
        r = subprocess.run(["mount", "-t", "vfat", "-o", opts, dev, mountpoint], capture_output=True, text=True, timeout=20)
        log.append("mount -o %s: exit %d %s" % (opts, r.returncode, (r.stderr or r.stdout).strip()))
        if r.returncode == 0: break
    else:
        raise RuntimeError("could not mount %s. %s Kernel: %s" % (dev, " ; ".join(log), _kernel_reason() or "n/a"))
    try:
        changed = apply_boot_config(mountpoint); os.sync()
    finally:
        subprocess.run(["umount", mountpoint], timeout=20)
    log.append("edited hassos-boot via own mount")
    return done(changed)
