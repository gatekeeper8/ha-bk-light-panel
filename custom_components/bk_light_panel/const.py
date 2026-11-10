"""Constants for the BK-Light LED panel integration."""

DOMAIN = "bk_light_panel"

# Panel size (ACT1026 = 32 x 32)
PANEL_WIDTH = 32
PANEL_HEIGHT = 32

# Stay connected all the time (None). When nothing is connected, the panel
# falls back to the animations stored in it by its phone app, so a
# disconnect would bring those back. A number = disconnect after that many
# idle seconds (frees the proxy's connection slot, but the animations return).
IDLE_DISCONNECT_SECONDS: int | None = None

# After an unexpected disconnect, reconnect and put the last picture back
# after these delays (seconds), so the stored animations show only briefly.
RECOVER_DELAYS = (2, 10, 30, 60, 120)

CONF_ADDRESS = "address"

SERVICE_SHOW_TEXT = "show_text"
SERVICE_FILL = "fill"
SERVICE_SHOW_IMAGE = "show_image"
SERVICE_CLEAR = "clear"
SERVICE_SHOW_ICON = "show_icon"
SERVICE_SHOW_CLOCK = "show_clock"
SERVICE_SHOW_AIRCRAFT = "show_nearest_aircraft"

ATTR_PANEL = "panel"
ATTR_TEXT = "text"
ATTR_COLOR = "color"
ATTR_BACKGROUND = "background"
ATTR_LINE_COLORS = "line_colors"
ATTR_SCALE = "scale"
ATTR_BRIGHTNESS = "brightness"
ATTR_PATH = "path"
ATTR_FIT = "fit"
ATTR_ICON = "icon"
ATTR_CAPTION = "caption"
ATTR_CAPTION_COLOR = "caption_color"
ATTR_DURATION = "duration"

# Largest piece of a picture per Bluetooth write. 244 bytes fit in one
# radio packet (data length extension): short writes get through an ESP32
# proxy that shares its radio with Wi-Fi and other connections far more
# reliably than full 514-byte (MTU 517) writes, which kept breaking links.
MAX_PIECE_BYTES = 244

# Picture pieces go out as acknowledged writes (each piece confirmed). The
# faster mode without receipts (FAST_WRITES = True) made the panels miss
# pictures through an ESPHome proxy - every miss costs a reconnect, and a day
# of it meant ~2000 drops instead of a few dozen - so it is off.
FAST_WRITES = False
# fast mode only: misses in a row before falling back, and for how long
UNCONFIRMED_LIMIT = 3
ACKNOWLEDGED_MINUTES = 30
