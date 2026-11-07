"""BK-Light LED panels (Action ACT1026 32x32, ACT1025 / ACT1033 64x16) for Home Assistant.

Actions: bk_light_panel.show_clock, .show_text, .show_icon,
.show_nearest_aircraft, .fill, .show_image, .clear
Protocol based on Bk-Light-AppBypass by Puparia (MIT License).
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import partial

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_BACKGROUND,
    ATTR_BRIGHTNESS,
    ATTR_CAPTION,
    ATTR_CAPTION_COLOR,
    ATTR_DURATION,
    ATTR_ICON,
    ATTR_COLOR,
    ATTR_FIT,
    ATTR_LINE_COLORS,
    ATTR_PANEL,
    ATTR_PATH,
    ATTR_SCALE,
    ATTR_TEXT,
    CONF_ADDRESS,
    DOMAIN,
    SERVICE_CLEAR,
    SERVICE_FILL,
    SERVICE_SHOW_AIRCRAFT,
    SERVICE_SHOW_CLOCK,
    SERVICE_SHOW_ICON,
    SERVICE_SHOW_IMAGE,
    SERVICE_SHOW_TEXT,
)
from .aircraft import pick_nearest, render_aircraft
from .aurora import DEFAULT_URL as AURORA_URL, OVATION_URL, next_hours, ovation_at, render_aurora, summary
from .icons import ANIMATED, LANGUAGES, language_for, render_icon, season_for
from .panel import BkLightPanel
from .readings import ORDER as READING_KINDS, render_readings
from .wide import (
    is_wide,
    render_aircraft_wide,
    render_aurora_wide,
    render_clock_wide,
    render_icon_wide,
)
from .render import (
    apply_tint,
    render_clock,
    render_file,
    render_fill,
    render_flip_clock,
    render_text,
    to_png,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type BkLightConfigEntry = ConfigEntry[BkLightPanel]

COLOR = vol.All(
    vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(list)
)

BASE = {
    vol.Optional(ATTR_PANEL): cv.string,
    vol.Optional(ATTR_BRIGHTNESS, default=100): vol.All(vol.Coerce(int), vol.Range(0, 100)),
}

SHOW_TEXT_SCHEMA = vol.Schema(
    {
        **BASE,
        vol.Required(ATTR_TEXT): cv.string,
        vol.Optional(ATTR_COLOR): COLOR,
        vol.Optional(ATTR_BACKGROUND): COLOR,
        vol.Optional(ATTR_LINE_COLORS): vol.All(cv.ensure_list, [COLOR]),
        vol.Optional(ATTR_SCALE, default=1): vol.All(vol.Coerce(int), vol.Range(1, 4)),
    }
)
FILL_SCHEMA = vol.Schema({**BASE, vol.Required(ATTR_COLOR): COLOR})
SHOW_IMAGE_SCHEMA = vol.Schema(
    {
        **BASE,
        vol.Required(ATTR_PATH): cv.string,
        vol.Optional(ATTR_FIT, default="contain"): vol.In(["contain", "cover", "stretch"]),
        vol.Optional(ATTR_BACKGROUND): COLOR,
    }
)
CLEAR_SCHEMA = vol.Schema({vol.Optional(ATTR_PANEL): cv.string})
SHOW_ICON_SCHEMA = vol.Schema(
    {
        **BASE,
        # unknown names (e.g. a new weather state) show a warning sign
        vol.Required(ATTR_ICON): cv.string,
        vol.Optional(ATTR_CAPTION): vol.Any(None, cv.string),
        vol.Optional(ATTR_CAPTION_COLOR): COLOR,
        vol.Optional(ATTR_DURATION, default=0): vol.All(vol.Coerce(float), vol.Range(0, 60)),
        vol.Optional("frame_interval", default=1.5): vol.All(vol.Coerce(float), vol.Range(0, 10)),
        vol.Optional("language"): vol.In(LANGUAGES),
        vol.Optional("night"): cv.boolean,
    }
)
SHOW_CLOCK_SCHEMA = vol.Schema(
    {
        **BASE,
        vol.Optional("time"): cv.string,
        vol.Optional("time_color"): COLOR,
        vol.Optional("line1", default=""): cv.string,
        vol.Optional("line1_color"): COLOR,
        vol.Optional("line2", default=""): cv.string,
        vol.Optional("line2_color"): COLOR,
        vol.Optional("bar_value"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("bar_max", default=75): vol.Coerce(float),
        vol.Optional("style", default="classic"): vol.In(["classic", "flip"]),
        vol.Optional("animate", default=True): cv.boolean,
        vol.Optional("tint"): vol.Any(None, COLOR),
    }
)
SHOW_AIRCRAFT_SCHEMA = vol.Schema(
    {
        **BASE,
        vol.Required("url"): cv.string,
        vol.Optional("max_distance", default=100): vol.All(vol.Coerce(float), vol.Range(1, 500)),
        vol.Optional("latitude"): cv.latitude,
        vol.Optional("longitude"): cv.longitude,
        vol.Optional(ATTR_DURATION, default=8): vol.All(vol.Coerce(float), vol.Range(0, 60)),
        vol.Optional("frame_interval", default=1.5): vol.All(vol.Coerce(float), vol.Range(0, 10)),
    }
)
SHOW_AURORA_SCHEMA = vol.Schema(
    {
        **BASE,
        vol.Optional("url", default=AURORA_URL): cv.string,
        vol.Optional("nowcast_url", default=OVATION_URL): cv.string,
        vol.Optional("latitude"): cv.latitude,
        vol.Optional("longitude"): cv.longitude,
        vol.Optional("min_kp", default=0): vol.All(vol.Coerce(float), vol.Range(0, 9)),
        vol.Optional("show", default=True): cv.boolean,
        vol.Optional(ATTR_DURATION, default=8): vol.All(vol.Coerce(float), vol.Range(0, 60)),
        vol.Optional("frame_interval", default=1.5): vol.All(vol.Coerce(float), vol.Range(0, 10)),
        vol.Optional("tint"): vol.Any(None, COLOR),
    }
)
SHOW_READINGS_SCHEMA = vol.Schema(
    {
        **BASE,
        # numbers (or unavailable / unknown, shown as --)
        **{vol.Optional(kind): vol.Any(None, cv.string, vol.Coerce(float)) for kind in READING_KINDS},
        vol.Optional("tint"): vol.Any(None, COLOR),
    }
)
AURORA_CACHE_SECONDS = 15 * 60
NOWCAST_CACHE_SECONDS = 10 * 60

# animations are drawn for this pace; with a slower frame_interval the
# frames skip ahead so the motion keeps its speed (just fewer steps)
ANIMATION_STEP_SECONDS = 0.6


async def _animate(hass, panel, render_frame, duration: float, interval: float) -> None:
    """Send frames every 'interval' seconds for 'duration' seconds.

    The panel confirms a frame when it arrives, not when it is shown; sending
    faster than it can display makes it fall behind, so keep the pace calm.
    interval 0 = one still frame held for the duration.
    """
    started = time.monotonic()
    end = started + duration
    while True:
        sent_at = time.monotonic()
        step = int((sent_at - started) / ANIMATION_STEP_SECONDS)
        png = await hass.async_add_executor_job(render_frame, step)
        await panel.async_send_png(png)
        now = time.monotonic()
        wait = max(0.0, interval - (now - sent_at)) if interval > 0 else end - now
        if now + wait >= end:
            await asyncio.sleep(max(0.0, end - now))
            return
        await asyncio.sleep(wait)
_LOGGER = logging.getLogger(__name__)


def _panel_for(hass: HomeAssistant, call: ServiceCall) -> BkLightPanel:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get(ATTR_PANEL)
    if wanted:
        for entry in entries:
            if wanted.upper() == entry.data[CONF_ADDRESS] or wanted == entry.title:
                return entry.runtime_data
        raise ServiceValidationError(f"No BK-Light panel called {wanted}")
    if len(entries) == 1:
        return entries[0].runtime_data
    if not entries:
        raise ServiceValidationError("No BK-Light panel is set up")
    raise ServiceValidationError("Several panels are set up: choose one with 'panel'")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once for all panels."""

    async def show_text(call: ServiceCall) -> None:
        panel = _panel_for(hass, call)
        size = await panel.async_get_size()
        png = await hass.async_add_executor_job(
            lambda: to_png(
                render_text(
                    call.data[ATTR_TEXT],
                    call.data.get(ATTR_COLOR),
                    call.data.get(ATTR_BACKGROUND),
                    call.data.get(ATTR_LINE_COLORS),
                    call.data[ATTR_SCALE],
                    size,
                ),
                call.data[ATTR_BRIGHTNESS],
            )
        )
        await panel.async_send_png(png)

    async def fill(call: ServiceCall) -> None:
        panel = _panel_for(hass, call)
        size = await panel.async_get_size()
        png = await hass.async_add_executor_job(
            lambda: to_png(render_fill(call.data[ATTR_COLOR], size), call.data[ATTR_BRIGHTNESS])
        )
        await panel.async_send_png(png)

    async def show_image(call: ServiceCall) -> None:
        panel = _panel_for(hass, call)
        path = call.data[ATTR_PATH]
        if not hass.config.is_allowed_path(path):
            raise ServiceValidationError(
                f"{path} is not in an allowed folder - put pictures in /config/www "
                "or add the folder to allowlist_external_dirs"
            )
        size = await panel.async_get_size()
        try:
            png = await hass.async_add_executor_job(
                lambda: to_png(
                    render_file(path, call.data[ATTR_FIT], call.data.get(ATTR_BACKGROUND), size),
                    call.data[ATTR_BRIGHTNESS],
                )
            )
        except OSError as err:
            raise ServiceValidationError(f"Cannot read picture {path}: {err}") from err
        await panel.async_send_png(png)

    async def clear(call: ServiceCall) -> None:
        panel = _panel_for(hass, call)
        size = await panel.async_get_size()
        png = await hass.async_add_executor_job(partial(to_png, render_fill([0, 0, 0], size)))
        await panel.async_send_png(png)

    async def show_icon(call: ServiceCall) -> None:
        """Show a built-in picture for 'duration' seconds (rain, snow, leaves move)."""
        panel = _panel_for(hass, call)
        name = call.data[ATTR_ICON].lower().strip()
        if name == "season":
            name = season_for()
        caption = call.data.get(ATTR_CAPTION)
        brightness = call.data[ATTR_BRIGHTNESS]

        # captions follow Home Assistant's language unless one is given
        lang = call.data.get("language") or language_for(hass.config.language)
        # night versions (moon instead of sun) after sunset, unless told otherwise
        night = call.data.get("night")
        if night is None:
            sun = hass.states.get("sun.sun")
            night = sun is not None and sun.state == "below_horizon"

        draw = render_icon_wide if is_wide(await panel.async_get_size()) else render_icon

        def frame_png(frame: int) -> bytes:
            return to_png(
                draw(name, caption, call.data.get(ATTR_CAPTION_COLOR), frame, lang=lang, night=night),
                brightness,
            )

        interval = call.data["frame_interval"] if name in ANIMATED else 0
        await _animate(hass, panel, frame_png, call.data[ATTR_DURATION], interval)

    async def show_clock(call: ServiceCall) -> None:
        """Clock face (classic or flip) with two small lines and a level bar."""
        panel = _panel_for(hass, call)
        data = call.data
        time_text = data.get("time") or dt_util.now().strftime("%H:%M")
        extras = (data["line1"], data.get("line1_color"), data["line2"],
                  data.get("line2_color"), data.get("bar_value"), data["bar_max"])
        if is_wide(await panel.async_get_size()):
            previous = getattr(panel, "last_clock_time", None)
            flip = data["style"] == "flip"
            steps = (0, 1, 2) if flip and data["animate"] and previous and previous != time_text else (2,)
            for step in steps:
                png = await hass.async_add_executor_job(
                    lambda st=step: to_png(
                        apply_tint(
                            render_clock_wide(time_text, previous, st, data["style"],
                                              data.get("time_color"), *extras),
                            data.get("tint"),
                        ),
                        data[ATTR_BRIGHTNESS],
                    )
                )
                await panel.async_send_png(png)
            panel.last_clock_time = time_text
            return
        if data["style"] == "classic":
            png = await hass.async_add_executor_job(
                lambda: to_png(
                    apply_tint(render_clock(time_text, data.get("time_color"), *extras),
                               data.get("tint")),
                    data[ATTR_BRIGHTNESS],
                )
            )
            await panel.async_send_png(png)
            return
        previous = getattr(panel, "last_clock_time", None)
        steps = (0, 1, 2) if data["animate"] and previous and previous != time_text else (2,)
        for step in steps:
            png = await hass.async_add_executor_job(
                lambda st=step: to_png(
                    apply_tint(
                        render_flip_clock(time_text, previous, st, data.get("time_color"), *extras),
                        data.get("tint"),
                    ),
                    data[ATTR_BRIGHTNESS],
                )
            )
            await panel.async_send_png(png)
        panel.last_clock_time = time_text

    async def show_nearest_aircraft(call: ServiceCall) -> ServiceResponse:
        """Fetch ADS-B data, show the closest plane; nothing is drawn if none."""
        url = call.data["url"]
        lat = call.data.get("latitude", hass.config.latitude)
        lon = call.data.get("longitude", hass.config.longitude)
        try:
            async with asyncio.timeout(6):
                response = await async_get_clientsession(hass).get(url)
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.debug("ADS-B data from %s not available: %s", url, err)
            return {"found": False, "error": str(err) or type(err).__name__}
        nearest = pick_nearest(data, lat, lon, call.data["max_distance"])
        if nearest is None:
            return {"found": False}
        panel = _panel_for(hass, call)
        brightness = call.data[ATTR_BRIGHTNESS]
        draw = render_aircraft_wide if is_wide(await panel.async_get_size()) else render_aircraft
        await _animate(
            hass, panel, lambda f: to_png(draw(nearest, f), brightness),
            call.data[ATTR_DURATION], call.data["frame_interval"],
        )
        return {"found": True, **nearest}

    aurora_cache: dict[str, tuple[float, object]] = {}

    async def fetch_json(url: str, max_age: float) -> tuple[object | None, str | None]:
        """JSON from url, cached for max_age s; the last good copy on errors."""
        cached = aurora_cache.get(url)
        if cached and time.monotonic() - cached[0] < max_age:
            return cached[1], None
        try:
            async with asyncio.timeout(15):
                response = await async_get_clientsession(hass).get(url)
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.debug("Aurora data from %s not available: %s", url, err)
            return (cached[1] if cached else None), str(err) or type(err).__name__
        aurora_cache[url] = (time.monotonic(), data)
        return data, None

    async def show_aurora(call: ServiceCall) -> ServiceResponse:
        """Kp forecast for 24 h plus the local nowcast; drawn only from min_kp."""
        data, error = await fetch_json(call.data["url"], AURORA_CACHE_SECONDS)
        if data is None:
            return {"shown": False, "error": error}
        slots = next_hours(data)
        info = summary(slots)
        # chance of aurora at / north of home right now (NOAA OVATION)
        nowcast, _ = await fetch_json(call.data["nowcast_url"], NOWCAST_CACHE_SECONDS)
        info.update(ovation_at(
            nowcast,
            call.data.get("latitude", hass.config.latitude),
            call.data.get("longitude", hass.config.longitude),
        ))
        if not call.data["show"] or not slots or info["max_kp"] < call.data["min_kp"]:
            return {"shown": False, **info}
        panel = _panel_for(hass, call)
        brightness, tint = call.data[ATTR_BRIGHTNESS], call.data.get("tint")
        tz = dt_util.get_default_time_zone()
        draw = render_aurora_wide if is_wide(await panel.async_get_size()) else render_aurora
        await _animate(
            hass, panel,
            lambda f: to_png(apply_tint(draw(slots, f, tz), tint), brightness),
            call.data[ATTR_DURATION], call.data["frame_interval"],
        )
        return {"shown": True, **info}

    async def show_readings(call: ServiceCall) -> None:
        """Temperature, humidity, PM2.5, PM10, pressure with icons (max four)."""
        panel = _panel_for(hass, call)
        size = await panel.async_get_size()
        values: dict[str, float | None] = {}
        for kind in READING_KINDS:
            if kind not in call.data:
                continue
            try:
                values[kind] = float(call.data[kind])
            except (TypeError, ValueError):
                values[kind] = None
        if not values:
            raise ServiceValidationError("Give at least one reading, e.g. temperature: 9.6")
        png = await hass.async_add_executor_job(
            lambda: to_png(apply_tint(render_readings(values, size), call.data.get("tint")),
                           call.data[ATTR_BRIGHTNESS])
        )
        await panel.async_send_png(png)

    hass.services.async_register(DOMAIN, "show_readings", show_readings, SHOW_READINGS_SCHEMA)
    hass.services.async_register(
        DOMAIN, "show_aurora", show_aurora, SHOW_AURORA_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_SHOW_CLOCK, show_clock, SHOW_CLOCK_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SHOW_AIRCRAFT, show_nearest_aircraft, SHOW_AIRCRAFT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_SHOW_ICON, show_icon, SHOW_ICON_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SHOW_TEXT, show_text, SHOW_TEXT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FILL, fill, FILL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SHOW_IMAGE, show_image, SHOW_IMAGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, clear, CLEAR_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BkLightConfigEntry) -> bool:
    entry.runtime_data = BkLightPanel(hass, entry.data[CONF_ADDRESS], entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BkLightConfigEntry) -> bool:
    await entry.runtime_data.async_shutdown()
    return True
