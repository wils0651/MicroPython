"""
IoT e-paper dashboard for Waveshare 7.5" V2 + Raspberry Pi Pico 2W.

Layout (800x480):
  ┌──────────────────────────────────────────────────────────┐
  │  ☀ 72F  Clear                     12:34   Thu Jun 1      │  (header, black)
  ├───────────────────────────┬──────────────────────────────┤
  │  TEMPERATURE              │  GARAGE                      │
  │  Garage         87.8 F    │  Status:    CLOSED           │
  │  Basement Offic 69.8 F    │  Distance:  186 cm           │
  │  Old Desk       80.4 F    │  Last:      2:30 PM          │
  │  Cold Corner    79.7 F    │                              │
  │  Pico Garage    87.8 F    │                              │
  ├──────────────────────┬────┴──┬──────────┬──────────┬─────┤
  │  TODAY               │  Tue  │  Wed     │  Thu     │ Fri │  (weather, 240+140*4)
  │  ☀ icon              │  icon │  icon    │  icon    │icon │
  │  85/62F  30%         │ 79/58 │  72/51   │  68/49   │ ... │
  ├──────────────────────┴───────┴──────────┴──────────┴─────┤
  │  Updated 12:34  ONLINE                                   │  (footer)
  └──────────────────────────────────────────────────────────┘

Upload order: epaper75.py, config.py, main.py (main.py runs on boot).
"""

import gc
import time
import framebuf
import network
import ntptime
import urequests

import config
from epaper75 import EPaper75

# ── constants ────────────────────────────────────────────────────────────────

W, H = EPaper75.WIDTH, EPaper75.HEIGHT   # 800, 480

# framebuf.MONO_HLSB: bit=0 → white on e-paper, bit=1 → black on e-paper
WHITE = 0
BLACK = 1

HEADER_H  = 70
WEATHER_Y    = H - 170                       # 310 — top of 5-day forecast strip (120 px tall)
FOOTER_Y     = H - 50                        # 430 — footer divider
MID_X        = W // 2                        # 400 — vertical centre divider
PAD          = 14                            # inner padding
TODAY_COL_W  = 240                           # today's column is wider
DAY_COL_W    = (W - TODAY_COL_W) // 4       # remaining 4 columns = 140 px each

DAYS   = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# ── time helpers ─────────────────────────────────────────────────────────────

def local_time():
    """Return time.localtime() adjusted by TZ_OFFSET."""
    return time.localtime(time.time() + config.TZ_OFFSET * 3600)


def fmt_time(t):
    return "{:02d}:{:02d}".format(t[3], t[4])


def fmt_date(t):
    return "{} {} {}".format(DAYS[t[6]], MONTHS[t[1]], t[2])


# ── text rendering ───────────────────────────────────────────────────────────

def draw_text(fb, text, x, y, scale=2, color=BLACK):
    """
    Render text using the built-in 8x8 font, scaled up by an integer factor.
    scale=2 → 16 px tall characters,  scale=3 → 24 px,  scale=4 → 32 px.
    At 800x480 a scale of 2 is readable body text; use 3+ for titles.
    """
    if not text:
        return
    char_w = 8
    n = len(text)
    w = n * char_w
    row_bytes = (w + 7) // 8
    buf = bytearray(row_bytes * char_w)
    tmp = framebuf.FrameBuffer(buf, w, char_w, framebuf.MONO_HLSB)
    tmp.fill(0)
    tmp.text(text, 0, 0, 1)
    for ty in range(char_w):
        for tx in range(w):
            if tmp.pixel(tx, ty):
                fb.fill_rect(x + tx * scale, y + ty * scale, scale, scale, color)
    del tmp, buf


# ── WiFi / NTP ───────────────────────────────────────────────────────────────

def connect_wifi(timeout_s=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if wlan.isconnected():
            return True
        time.sleep(0.5)
    return False


def sync_ntp():
    try:
        ntptime.settime()
        return True
    except Exception:
        return False


# ── API helpers ───────────────────────────────────────────────────────────────

def fetch_json(endpoint):
    try:
        r = urequests.get(config.API_BASE_URL + endpoint, timeout=8)
        data = r.json()
        r.close()
        return data
    except Exception:
        return None


def parse_temps(raw):
    """
    Normalize the temperature API response into a list of dicts:
      [{"name": str, "value": float, "unit": str}, ...]

    Handles both a JSON array and a single object.
    Adjust the field names here to match your actual API response.
    """
    if raw is None:
        return None
    items = raw if isinstance(raw, list) else [raw]
    result = []
    for item in items:
        name  = item.get("probeDescription") or item.get("probeName") or item.get("location") or "Probe"
        value = item.get("value") or item.get("temperature") or item.get("tempF")
        unit  = item.get("unit") or "F"
        if value is not None:
            result.append({"name": str(name)[:16], "value": float(value), "unit": str(unit)})
    return result or None


def fetch_temps():
    """Fetch all configured probe IDs and return a combined list for parse_temps."""
    results = []
    for pid in config.PROBE_IDS:
        raw = fetch_json("/api/ProbeData/Latest/{}".format(pid))
        parsed = parse_temps(raw)
        if parsed:
            results.extend(parsed)
    return results or None


def parse_garage(raw):
    """
    Normalize the garage API response into a dict:
      {"status": str, "distance": float|None, "last_event": str|None}

    Adjust field names to match your actual API response.
    """
    if raw is None:
        return None
    item = raw[0] if isinstance(raw, list) and raw else raw
    return {
        "status":     str(item.get("garageStatusName") or item.get("state") or "Unknown").upper(),
        "distance":   item.get("distanceCm") or item.get("distance"),
        "last_event": str(item.get("lastEvent") or item.get("lastChange") or ""),
    }


# ── weather ───────────────────────────────────────────────────────────────────

_WMO = {
    0: "Clear",    1: "MClear",   2: "PCloudy",  3: "Overcast",
    45: "Fog",     48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    61: "Rain",    63: "Rain",    65: "HvyRain",
    71: "Snow",    73: "Snow",    75: "HvySnow",  77: "Snow",
    80: "Showers", 81: "Showers", 82: "Showers",
    95: "TStorm",  96: "TStorm",  99: "TStorm",
}


def wmo_desc(code):
    return _WMO.get(code, "Wx:{}".format(code))


def fetch_weather():
    url = (
        "http://api.open-meteo.com/v1/forecast"
        "?latitude={}&longitude={}"
        "&current=temperature_2m,weathercode"
        "&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max"
        "&temperature_unit=fahrenheit&timezone={}&forecast_days=5"
    ).format(
        config.WEATHER_LAT,
        config.WEATHER_LON,
        config.WEATHER_TIMEZONE.replace("/", "%2F"),
    )
    try:
        r = urequests.get(url, timeout=10)
        data = r.json()
        r.close()
        return data
    except Exception:
        return None


def parse_weather(raw):
    if raw is None:
        return None
    try:
        cur = raw.get("current", {})
        current = {
            "temp": int(round(cur.get("temperature_2m", 0))),
            "code": cur.get("weathercode", 0),
        }
        d = raw["daily"]
        today_wd = local_time()[6]
        pp = d.get("precipitation_probability_max", [])
        forecast = []
        for i in range(len(d["time"])):
            forecast.append({
                "day":    DAYS[(today_wd + i) % 7],
                "hi":     int(round(d["temperature_2m_max"][i])),
                "lo":     int(round(d["temperature_2m_min"][i])),
                "code":   d["weathercode"][i],
                "precip": int(pp[i]) if i < len(pp) and pp[i] is not None else None,
            })
        return {"current": current, "forecast": forecast}
    except Exception:
        return None


# ── weather icons (32×32, requires MicroPython ≥1.20 for fb.ellipse) ─────────

def _draw_cloud(fb, x, y, c):
    """24×14 cloud shape anchored at (x, y) top-left."""
    fb.ellipse(x + 5,  y + 9, 5, 4, c, True)
    fb.ellipse(x + 12, y + 5, 6, 6, c, True)
    fb.ellipse(x + 19, y + 9, 5, 4, c, True)
    fb.fill_rect(x + 1, y + 9, 22, 5, c)

def _icon_sun(fb, x, y, c):
    cx, cy = x + 16, y + 16
    fb.line(cx,      cy - 13, cx,      cy - 8,  c)
    fb.line(cx,      cy + 8,  cx,      cy + 13, c)
    fb.line(cx - 13, cy,      cx - 8,  cy,      c)
    fb.line(cx + 8,  cy,      cx + 13, cy,      c)
    fb.line(cx - 9,  cy - 9,  cx - 6,  cy - 6,  c)
    fb.line(cx + 6,  cy - 6,  cx + 9,  cy - 9,  c)
    fb.line(cx - 9,  cy + 9,  cx - 6,  cy + 6,  c)
    fb.line(cx + 6,  cy + 6,  cx + 9,  cy + 9,  c)
    fb.ellipse(cx, cy, 6, 6, c, True)

def _icon_pcloudy(fb, x, y, c):
    sx, sy = x + 9, y + 9
    for dx, dy in ((0, -1), (-1, 0), (-1, -1), (1, -1)):
        fb.line(sx + dx * 5, sy + dy * 5, sx + dx * 8, sy + dy * 8, c)
    fb.ellipse(sx, sy, 4, 4, c, True)
    _draw_cloud(fb, x + 4, y + 14, c)

def _icon_cloud(fb, x, y, c):
    _draw_cloud(fb, x + 4, y + 9, c)

def _icon_fog(fb, x, y, c):
    for fy in range(y + 5, y + 26, 5):
        fb.hline(x + 3, fy, 26, c)

def _icon_rain(fb, x, y, c):
    _draw_cloud(fb, x + 4, y + 4, c)
    for rx, ry in ((x+7, y+21), (x+11, y+24), (x+15, y+21), (x+19, y+24), (x+23, y+21)):
        fb.line(rx, ry, rx - 2, ry + 4, c)

def _icon_snow(fb, x, y, c):
    _draw_cloud(fb, x + 4, y + 4, c)
    for sx2 in (x + 7, x + 12, x + 17, x + 22):
        fb.fill_rect(sx2, y + 22, 2, 2, c)
        fb.fill_rect(sx2, y + 27, 2, 2, c)

def _icon_storm(fb, x, y, c):
    _draw_cloud(fb, x + 4, y + 4, c)
    lx, ly = x + 18, y + 20
    fb.line(lx,     ly,     lx - 4, ly + 6, c)
    fb.line(lx - 4, ly + 6, lx - 1, ly + 6, c)
    fb.line(lx - 1, ly + 6, lx - 5, ly + 12, c)

def _draw_smiley(fb, x, y, c):
    """32×32 smiley face. c is the face fill; features draw in the opposite color."""
    cx, cy = x + 16, y + 16
    d = 1 - c  # contrast color for features
    fb.ellipse(cx, cy, 14, 14, c, True)          # filled face
    fb.ellipse(cx - 5, cy - 4, 2, 2, d, True)   # left eye
    fb.ellipse(cx + 5, cy - 4, 2, 2, d, True)   # right eye
    fb.ellipse(cx, cy + 3, 7, 5, d, False, 12)  # smile (bottom arc only)


_ICON_FN = {
    "Clear":    _icon_sun,
    "MClear":   _icon_sun,
    "PCloudy":  _icon_pcloudy,
    "Overcast": _icon_cloud,
    "Fog":      _icon_fog,
    "Drizzle":  _icon_rain,
    "Rain":     _icon_rain,
    "HvyRain":  _icon_rain,
    "Snow":     _icon_snow,
    "HvySnow":  _icon_snow,
    "Showers":  _icon_rain,
    "TStorm":   _icon_storm,
}


def draw_weather_strip(fb, forecast):
    if not forecast:
        draw_text(fb, "Weather unavailable", PAD, WEATHER_Y + 52, scale=2)
        return
    for i, day in enumerate(forecast[:5]):
        cx  = 0 if i == 0 else TODAY_COL_W + (i - 1) * DAY_COL_W
        cw  = TODAY_COL_W if i == 0 else DAY_COL_W

        if i > 0:
            fb.vline(cx, WEATHER_Y, FOOTER_Y - WEATHER_Y, BLACK)

        icon_fn = _ICON_FN.get(wmo_desc(day["code"]), _icon_cloud)

        if i == 0:
            # filled "TODAY" bar across the top of the wide column
            fb.fill_rect(cx, WEATHER_Y, cw, 24, BLACK)
            draw_text(fb, "TODAY", cx + (cw - 5 * 16) // 2, WEATHER_Y + 4, scale=2, color=WHITE)
        else:
            day_str = day["day"]
            draw_text(fb, day_str, cx + (cw - len(day_str) * 16) // 2, WEATHER_Y + 4, scale=2)

        # icon aligned at the same vertical position in all columns
        icon_fn(fb, cx + (cw - 32) // 2, WEATHER_Y + 28, BLACK)

        temp_str = "{}/{}F".format(day["hi"], day["lo"])
        draw_text(fb, temp_str, cx + (cw - len(temp_str) * 16) // 2, WEATHER_Y + 64, scale=2)

        precip_str = "{}%".format(day["precip"]) if day["precip"] is not None else "-%"
        draw_text(fb, precip_str, cx + (cw - len(precip_str) * 16) // 2, WEATHER_Y + 84, scale=2)


# ── dashboard rendering ───────────────────────────────────────────────────────

def render(fb, temps, garage, weather, wifi_ok):
    fb.fill(WHITE)

    t        = local_time()
    current  = weather["current"]  if weather else None
    forecast = weather["forecast"] if weather else None

    # ── Header (filled black) ────────────────────────────────────────────
    fb.fill_rect(0, 0, W, HEADER_H, BLACK)

    if current:
        icon_fn = _ICON_FN.get(wmo_desc(current["code"]), _icon_cloud)
        icon_fn(fb, PAD, (HEADER_H - 32) // 2, WHITE)
        draw_text(fb, "{}F".format(current["temp"]),  PAD + 36, 10, scale=3, color=WHITE)
        draw_text(fb, wmo_desc(current["code"]),      PAD + 36, 38, scale=2, color=WHITE)
        _draw_smiley(fb, PAD + 36 + 9 * 16, (HEADER_H - 32) // 2, WHITE)

    time_str = fmt_time(t)
    date_str = fmt_date(t)
    tx = W - len(time_str) * 24 - PAD
    dx = W - len(date_str) * 16 - PAD
    draw_text(fb, time_str, tx, 12, scale=3, color=WHITE)
    draw_text(fb, date_str, dx, 44, scale=2, color=WHITE)

    # ── Section dividers ─────────────────────────────────────────────────
    fb.hline(0, HEADER_H, W, BLACK)
    fb.vline(MID_X, HEADER_H, WEATHER_Y - HEADER_H, BLACK)
    fb.hline(0, WEATHER_Y, W, BLACK)
    fb.hline(0, FOOTER_Y, W, BLACK)

    # ── Left panel: Temperature ──────────────────────────────────────────
    sec_y = HEADER_H + 10
    draw_text(fb, "TEMPERATURE", PAD, sec_y, scale=2, color=BLACK)
    fb.hline(PAD, sec_y + 18, MID_X - PAD * 2, BLACK)

    row_y = sec_y + 28
    if temps:
        for probe in temps[:5]:           # max 5 readings fit the shortened panel
            name    = probe["name"]
            reading = "{:.1f} {}".format(probe["value"], probe["unit"])
            draw_text(fb, name, PAD, row_y, scale=2)
            # Right-align the reading within the left panel
            rx = MID_X - len(reading) * 16 - PAD
            draw_text(fb, reading, rx, row_y, scale=2)
            row_y += 40
    else:
        draw_text(fb, "No data", PAD, row_y, scale=2)

    # ── Right panel: Garage ──────────────────────────────────────────────
    lx = MID_X + PAD
    draw_text(fb, "GARAGE", lx, sec_y, scale=2, color=BLACK)
    fb.hline(lx, sec_y + 18, MID_X - PAD * 2, BLACK)

    row_y = sec_y + 28
    val_x = lx + 10 * 16   # value column: label width (max 9 chars) + gap

    if garage:
        rows = [
            ("Status:", garage["status"]),
        ]
        if garage["distance"] is not None:
            rows.append(("Distance:", "{:.0f} cm".format(float(garage["distance"]))))
        if garage["last_event"]:
            rows.append(("Last:", garage["last_event"][:14]))

        for label, value in rows:
            draw_text(fb, label, lx, row_y, scale=2)
            draw_text(fb, value, val_x, row_y, scale=2)
            row_y += 40
    else:
        draw_text(fb, "No data", lx, row_y, scale=2)

    # ── Weather strip ────────────────────────────────────────────────────
    draw_weather_strip(fb, forecast)

    # ── Footer ───────────────────────────────────────────────────────────
    status = "ONLINE" if wifi_ok else "OFFLINE"
    footer = "Updated {}  {}".format(fmt_time(t), status)
    draw_text(fb, footer, PAD, FOOTER_Y + 14, scale=2)


# ── main loop ─────────────────────────────────────────────────────────────────

def main():
    epd = EPaper75(
        spi_id=config.SPI_ID,
        clk=config.SPI_CLK,
        mosi=config.SPI_MOSI,
        cs=config.PIN_CS,
        dc=config.PIN_DC,
        rst=config.PIN_RST,
        busy=config.PIN_BUSY,
        pwr=config.PIN_PWR,
    )

    # Allocate the image buffer once to avoid heap fragmentation
    img_buf = bytearray(W * H // 8)   # 48 000 bytes
    fb = framebuf.FrameBuffer(img_buf, W, H, framebuf.MONO_HLSB)

    # Initial clear: power on → init → clear → sleep → power off
    epd.power_on()
    epd.init()
    epd.clear()
    epd.sleep()
    epd.power_off()

    wifi_ok = connect_wifi()
    if wifi_ok:
        sync_ntp()

    while True:
        gc.collect()

        # Reconnect if WiFi dropped between updates
        if not network.WLAN(network.STA_IF).isconnected():
            wifi_ok = connect_wifi()

        temps   = fetch_temps()                                      if wifi_ok else None
        garage  = parse_garage(fetch_json(config.GARAGE_ENDPOINT)) if wifi_ok else None
        weather = parse_weather(fetch_weather())                    if wifi_ok else None

        render(fb, temps, garage, weather, wifi_ok)

        epd.power_on()
        epd.init()
        epd.display(img_buf)
        epd.sleep()
        epd.power_off()

        gc.collect()
        time.sleep(config.UPDATE_INTERVAL)


main()

