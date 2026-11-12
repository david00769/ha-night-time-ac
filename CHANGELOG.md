# Changelog

Re-importing the blueprint replaces it under every automation that uses it, so
any change to inputs or behaviour is listed here, and a change that needs you to
edit your automations is marked **Breaking**. Releases are git tags.

## 1.1.0 (2026-11-13)

- **Probing (new, off by default):** a room with no room reading can be probed: run the
  fan for a few minutes, read the unit's own sensor, and cool if it is over. New inputs:
  *Probe a room with no reading every (minutes)*, *Probe length (minutes)*, *Probe fan
  speed*. Existing automations are unchanged until you set *Probe every*.
- The fan is put back while the unit is still running, before it switches off.
- Clearer input descriptions; the margin shows its unit; README reorganised, with a UI
  helper table.

## 1.0.0 (2026-11-12)

First release. Tested on a Toshiba VRF bedroom unit: start on a
room sensor, cool to the limit, switch off when the room is back at the limit or
the unit has stopped cooling, restore the setpoint after off, hand a unit back on
any manual change after it has held (90 seconds for setpoint or fan, a minute for
another mode, three minutes for off). Setpoints are rounded to the unit's step and
compared within half of it.
