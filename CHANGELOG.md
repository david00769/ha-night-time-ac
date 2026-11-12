# Changelog

Re-importing the blueprint replaces it under every automation that uses it, so
any change to inputs or behaviour is listed here, and a change that needs you to
edit your automations is marked **Breaking**. Releases are git tags.

## 1.0.0 (2026-11-12)

First release. Behaviour commissioned on a Toshiba VRF bedroom unit: start on a
room sensor, cool to the limit, switch off when the room is back at the limit or
the unit has stopped cooling, restore the setpoint after off, hand a unit back on
any manual change after it has held (90 seconds for setpoint or fan, a minute for
another mode, three minutes for off). Setpoints are rounded to the unit's step and
compared within half of it.
