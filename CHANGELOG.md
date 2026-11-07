# Changelog

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
