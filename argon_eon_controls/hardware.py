"""HA OS adapter for the Argon EON hardware layer.

Protocol addresses, fan spin-up sequence, OLED block transfer and PCF8563 RTC
layout are adapted from JeffCurless/argoneon commit da5756a. The upstream
snapshot is shipped in /app/upstream_argoneon for auditability.
"""
import glob, json, os, re, subprocess, threading, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import textwrap
from entities import monitored

try:
    from smbus2 import SMBus
except Exception:
    SMBus = None

FAN_ADDR = 0x1A
OLED_ADDR = 0x3C
OLED_DATA = 0x6A
RTC_ADDR = 0x51


class EonHardware:
    def __init__(self):
        self.lock = threading.RLock()
        self.bus = None
        self.error = None
        self.fan = 0
        self._open()

    def _open(self):
        try:
            if SMBus is None:
                raise RuntimeError("smbus2 is unavailable")
            self.bus = SMBus(1)
            self.error = None
        except FileNotFoundError:
            self.error = "I2C device /dev/i2c-1 not found: enable I2C on the Pi host and reboot (see DOCS.md)"
        except PermissionError as exc:
            self.error = f"I2C device /dev/i2c-1 not accessible ({exc}): disable Protection mode for this app"
        except Exception as exc:
            self.error = str(exc)

    def scan(self):
        found = []
        if not self.bus:
            return found
        with self.lock:
            for addr in (FAN_ADDR, OLED_ADDR, 0x51, 0x68):
                try:
                    self.bus.read_byte(addr)
                    found.append(f"0x{addr:02x}")
                except Exception:
                    pass
        return found

    def set_fan(self, percent):
        percent = max(0, min(100, int(percent)))
        if not self.bus:
            self._open()
        if not self.bus:
            raise RuntimeError(self.error or "I2C bus unavailable")
        with self.lock:
            if percent and self.fan == 0:
                self.bus.write_byte(FAN_ADDR, 100)
                time.sleep(.7)
            self.bus.write_byte(FAN_ADDR, percent)
            self.fan = percent
        return percent

    @staticmethod
    def _bcd(value):
        return (value & 0x0F) + (((value >> 4) & 0x0F) * 10)

    def rtc_status(self):
        """Read the EON PCF8563-compatible RTC without changing host time."""
        result = {"detected": False, "time": None, "clock_valid": None}
        if not self.bus:
            return result
        try:
            with self.lock:
                # Match the upstream EON routine: set register pointer then read sequentially.
                self.bus.write_byte(RTC_ADDR, 2)
                raw = [self.bus.read_byte(RTC_ADDR) for _ in range(7)]
            sec = self._bcd(raw[0] & 0x7F)
            minute = self._bcd(raw[1] & 0x7F)
            hour = self._bcd(raw[2] & 0x3F)
            day = self._bcd(raw[3] & 0x3F)
            month = self._bcd(raw[5] & 0x1F)
            year = 2000 + self._bcd(raw[6])
            result.update(detected=True, clock_valid=not bool(raw[0] & 0x80),
                          time=f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}")
        except Exception as exc:
            result["error"] = str(exc)
        return result

    def oled_power(self, enabled):
        if not self.bus:
            raise RuntimeError("I2C unavailable")
        with self.lock:
            self.bus.write_byte_data(OLED_ADDR, 0, 0xAF if enabled else 0xAE)

    def oled_brightness(self, percent):
        if not self.bus:
            raise RuntimeError("I2C unavailable")
        value = max(1, min(255, round(int(percent) * 255 / 100)))
        with self.lock:
            self.bus.write_byte_data(OLED_ADDR, 0, 0x81)
            self.bus.write_byte_data(OLED_ADDR, 0, value)

    def oled_image(self, image):
        if not self.bus:
            raise RuntimeError("I2C unavailable")
        image = image.convert("1").resize((128, 64))
        pixels = image.load()
        buf = []
        for page in range(8):
            for x in range(128):
                value = 0
                for bit in range(8):
                    if pixels[x, page * 8 + bit]:
                        value |= 1 << bit
                buf.append(value)
        with self.lock:
            from upstream_adapter import oled
            driver=oled(self.bus)
            driver['oled_imagebuffer'][:]=buf
            for page in range(8):
                for x in range(0,128,32):
                    driver['oled_flushblock'](x,page*8)
            driver['oled_reset']()
            driver['oled_power'](True)



def cpu_temp():
    paths = glob.glob("/sys/class/thermal/thermal_zone*/temp")
    for path in paths:
        try:
            value = float(Path(path).read_text().strip())
            return round(value / 1000 if value > 200 else value, 1)
        except Exception:
            pass
    return None


def test_pattern(name):
    """A pattern drawn with nothing from the app's own state, for telling a panel fault from a software one."""
    image = Image.new("1", (128, 64), 0); d = ImageDraw.Draw(image)
    if name == 'white': d.rectangle((0, 0, 127, 63), fill=1)
    elif name == 'checker':
        for y in range(0, 64, 8):
            for x in range(0, 128, 8):
                if (x // 8 + y // 8) % 2 == 0: d.rectangle((x, y, x + 7, y + 7), fill=1)
    elif name == 'rings':
        for r in range(4, 40, 4): d.ellipse((64 - r, 32 - r, 64 + r, 32 + r), outline=1)
    # 'black': leave blank
    return image

HEALTH_SHORT = {'Passed': 'OK', 'Warning': 'WARN', 'Failed': 'FAIL'}

def duration(seconds):
    if seconds is None: return '--'
    s = int(seconds); d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m" if h else f"{m}m {s}s"

def drive_row(disk):
    """'sdc 33C WARN', with 'zz' when the temperature is the last reading from before the drive went to sleep."""
    t = disk.get('temperature'); asleep = t is None and disk.get('last_temperature') is not None
    if asleep: t = disk['last_temperature']
    return f"{disk.get('name', '?')}  {t if t is not None else '--'}C  {HEALTH_SHORT.get(disk.get('health'), '?')}" + (' zz' if asleep else '')

def drive_detail(disk):
    for key, word in (('pending', 'pending sectors'), ('uncorrectable', 'bad sectors')):
        if isinstance(disk.get(key), int) and disk[key] > 0: return f"{disk[key]} {word}"
    return str(disk.get('message') or 'See app for details')[:21].rstrip()

def render_page(page, state, cfg, shift=(0, 0)):
    image = Image.new("1", (128, 64), 0)
    d = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    bold = font
    def line(y, text, fill=1): d.text((3, y), str(text)[:21], font=font, fill=fill)
    if page == "clock":
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(cfg.get("timezone","Europe/London"))).timetuple(); line(5, time.strftime("%a %d %b", now));
        try: big = ImageFont.load_default(size=30)
        except TypeError: big = bold
        t = time.strftime("%H:%M", now); d.text(((128 - d.textlength(t, font=big)) / 2, 22), t, font=big, fill=1)
    elif page == "temperature":
        line(2, "TEMPERATURES"); line(20, f"CPU   {state.get('cpu_temp','--')} C")
        line(34, f"Drive {state.get('max_disk_temp','--')} C"); line(49, f"Fan   {state.get('fan',0)} %")
    elif page == "storage":
        rows = [x for x in state.get("disks", []) if monitored(x)]   # not ignored drives, empty bays or drives with no SMART type
        if not rows: line(2, "STORAGE"); line(22, "No drives monitored")
        elif len(rows) <= 3:
            line(2, "STORAGE")
            for i, disk in enumerate(rows): line(17+i*14, drive_row(disk))
        else:
            for i, disk in enumerate(rows[:4]): line(2+i*16, drive_row(disk))
    elif page == "alerts":
        mon = [x for x in state.get("disks", []) if monitored(x)]; bad = [x for x in mon if x.get("health") in ("Failed", "Warning")]
        if not bad:
            line(2, "DRIVE ALERTS"); line(20, "No drive problems"); line(36, f"{len(mon)} drive{'s' if len(mon) != 1 else ''} monitored")
        elif len(bad) <= 2:
            for i, disk in enumerate(bad): line(2+i*32, f"{disk.get('name','?')} {disk['health'].upper()}"); line(16+i*32, drive_detail(disk))
        else:
            for i, disk in enumerate(bad[:4]): line(2+i*16, f"{disk.get('name','?')} {disk['health'].upper()}")
    elif page == "cooling":
        fan = state.get("fan"); line(2, f"COOLING  Fan {fan if fan is not None else '--'} %")
        for i, text in enumerate(textwrap.wrap(str(state.get("reason") or "Starting").replace("\u00b0", ""), 21)[:3]): line(17+i*14, text)
    elif page == "uptime":
        m = state.get("metrics", {}); line(2, "UPTIME")
        try: big = ImageFont.load_default(size=22)
        except TypeError: big = bold
        t = duration(m.get("uptime_seconds")); d.text(((128 - d.textlength(t, font=big)) / 2, 20), t, font=big, fill=1)
        line(49, f"CPU {m.get('cpu_percent','--')}%  RAM {m.get('memory_percent','--')}%")
    elif page == "network":
        line(2, "HOME ASSISTANT"); line(20, state.get("hostname", "homeassistant")); line(36, state.get("ip", "Network active")); line(51, "Argon EON Controls")
    elif page in ('cpu','ram','bandwidth','raid'):
        m=state.get('metrics',{})
        line(2,page.upper())
        if page=='cpu': line(24,str(m.get('cpu_percent','--'))+' %')
        if page=='ram':
            line(22,str(m.get('memory_percent','--'))+' % used')
            line(40,'Swap '+str(m.get('swap_used',0)//1048576)+' MB')
        if page=='bandwidth':
            line(22,'Read '+str(m.get('disk_bytes',{}).get('read',0)//1048576)+' MB')
            line(40,'Write '+str(m.get('disk_bytes',{}).get('write',0)//1048576)+' MB')
        if page=='raid':
            for i,l in enumerate(m.get('raid','Unavailable').splitlines()[:3]): line(18+i*14,l)
    else:
        line(2, "ARGON EON"); line(22, cfg.get("custom_line_1", "Home Assistant")); line(39, cfg.get("custom_line_2", "Storage online"))
    if shift != (0, 0):
        shifted = Image.new("1", (128, 64), 0)
        shifted.paste(image, shift)
        return shifted
    return image
