# Changelog

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
