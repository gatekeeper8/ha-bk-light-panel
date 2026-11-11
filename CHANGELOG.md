# Changelog

## 0.10.0 (unreleased)
- Runner animation: the castle ledge is darker, warmer sandstone with mortar lines (it
  showed almost white-pink on the panel).

## 0.9.0
- **Stored animations** (protocol read from the phone app's traffic): `play_animation`
  stores a GIF in one of the panel's slots and the panel plays it by itself, smoothly
  (e.g. 10 frames a second) and also while disconnected, until the next picture. Use a
  built-in animation or your own GIF. `set_playlist` chooses the slots that play in
  turn, `set_brightness` sets the panel's own brightness (full colour when dim).
- Pictures are sent in pieces of at most 244 bytes (one radio packet) instead of
  514: far fewer dropped connections through ESPHome Bluetooth proxies, especially
  with two panels on one proxy.
- Picture pieces stay acknowledged writes. A faster mode without per-piece receipts
  exists (`FAST_WRITES` in `const.py`) but is off: through an ESPHome proxy the
  panels missed pictures and every miss cost a reconnect.
- Wide 64×16 panels (Action ACT1025 / ACT1033): the size is read from the panel's
  handshake and every action picks a matching layout: flip or classic clock with the
  text lines beside it, pictures with the caption beside them, a flight-board line for
  the nearest plane, Kp bars with the peak for the aurora. Text, fill and your own
  images use the full 64×16. Existing 32×32 setups are unchanged.
- New action `show_readings`: temperature, humidity, PM2.5, PM10 and pressure with small
  icons, each coloured by level (2×2 grid on 64×16, four rows on 32×32).
- 64×16 text uses a new rounded 7-pixel font (two lines on the panel); the small font
  only where a text does not fit.
- `transition: slide` for `show_clock` and `show_readings`: the new screen pushes a
  different one out to the left. 64×16 flip cards are smaller with rounder corners.
- New `show_forecast` for both sizes: the weather in a few hours and tomorrow, each
  with its picture, hour or weekday (en / pl) and temperature.
- `show_clock` `date_text`: on 64×16 the clock moves up into a shorter band with a
  date line under it; line 1 is drawn in the clock's own digits level with the time,
  line 2 in the date's font level with the date.
- New 64×16 screens: `show_sky_graph` (24 h temperature from history and the hourly
  forecast, day warm with a sun, night blue with stars), `show_room` (a room's
  temperature and humidity or set point, with a steaming pot), `show_traffic` (network download / upload of the last
  minutes from history, e.g. SNMP sensors of a router), `show_retro` (blue and purple
  8-bit start-up screens, marching aliens, and four game-style animations: a root
  prompt running `rm -rf /*`, a green chomper munching gems in a maze chased by a bat,
  an adventurer long-jumping a gap and an agent fighting a drone, drawn with
  jointed, shaded figures and copper-gradient skies; all original designs). On 64×16 the nearest plane becomes a
  flight board showing the nearest planes in turn (`count`). 64×16 flip cards are 15
  pixels wide, with the digits centred between the pins.
- Example package `examples/led_panel_wide.yaml`: a 64×16 panel as a second clock with
  the date, alternating with the outdoor readings, red at night.

## 0.8.1
- Fix: the panel's stored phone-app animations flashed up briefly every 30th frame
  (every 10 minutes with the night clock). The integration no longer sends the
  "frame validation" command that caused it.

## 0.8.0
- Location-aware aurora: `show_aurora` also returns NOAA's OVATION nowcast for your
  location: chance overhead (`nowcast_local`) and the highest chance just north of you
  (`nowcast_horizon`, what you could see low in the north).
- Example package: the night break-through needs clear skies (Met.no clouds < 70 %) and
  real darkness; the phone notification is skipped when tonight is forecast overcast and
  includes the expected cloud cover.

## 0.7.0
- Night versions of the pictures that show the sun: sunny → moon and stars,
  partly cloudy → crescent moon behind the cloud, summer → moonlit sea.
  Automatic after sunset (`sun.sun`), or `night: true/false` in `show_icon`.

## 0.6.2
- LICENSE is now the plain MIT text, so GitHub and HACS recognise it
  (the Bk-Light-AppBypass credit stays in NOTICE.md and the README).

## 0.6.1
- Captions in English and Polish: follow Home Assistant's language, or `language: en|pl` in `show_icon`.
- README gallery in English, Polish copy in `images/pictures_pl.png`.

## 0.6.0
- Aurora forecast (`show_aurora`) from the NOAA SWPC Kp forecast, old and new data formats.
- Adjustable animation pace (`frame_interval`).
- Stays connected; restores the picture after a dropped connection; identical frames are not re-sent.
- Night tint for the clock.

## 0.4.0
- Flip clock with flip animation.
- Nearest aircraft with the flag of the country of registration.

## 0.3.0
- Smooth graphics (supersampled, gradients, glow), big-digit clock, nearest aircraft from ADS-B.

## 0.2.0
- Built-in weather, moon, season, smog and heating pictures.

## 0.1.0
- First version: text, colours, images over Bluetooth.
