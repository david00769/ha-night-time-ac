# Night time AC

A Home Assistant blueprint that keeps a room at or below a temperature limit
overnight, and keeps its air conditioner **off, and quiet,** the rest of the time.

[![Open your Home Assistant instance and show the blueprint import dialog with this blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/create-link/?redirect=blueprint_import&blueprint_url=https%3A%2F%2Fgithub.com%2Fdavid00769%2Fha-night-time-ac%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fdavid00769%2Fnight_time_ac.yaml)

## What it does

During the hours you set, for each room you switch on:

1. If the room has been **above your limit** (plus a small margin) for a few minutes,
   with its windows closed, it turns the air conditioner on in **cool**.
2. When the room is **back at the limit**, or the unit has **stopped cooling**, or the
   night ends, it switches the unit **off** and puts its earlier temperature setting
   back.
3. It waits a while before starting again, so it doesn't keep cycling.

It only cools, never heats. It only takes over a unit that is off, and it hands a unit
back to you as soon as you change it.

## Why I built it

Our bedroom air conditioner is a ducted Toshiba unit (an SMMS-i VRF system: one
outdoor unit serving several rooms). Even once the room reaches its setpoint (the
temperature the unit is set to), it keeps its fan running and you can hear the
refrigerant moving. My wife doesn't like the noise, so she turns the AC off at night.
Then the room warms up, I wake up hot, I turn it back on, and the noise starts again.

We wanted neither "on all night" nor "off all night", but **off and quiet until the
room is actually too hot, then cool it and switch off again.** A schedule can't do
that, and the unit's own thermostat can't either, because it keeps the fan running
while it waits.

## The rules

| Situation | What it does |
| --- | --- |
| Unit off, room over the limit for the hold time, windows closed | Starts it in `cool`, at the limit rounded down to the unit's own setting step |
| Unit already on, in any mode, at any setting | Leaves it alone |
| Room back at the limit | Switches off, then restores the earlier setting |
| A unit it started has stopped cooling for the idle time | Switches off, so the room is quiet; starts again if the room warms |
| End of the hours, master switch off, or this room's switch off | Switches off and restores the earlier setting |
| Limit changed | Updates only units it started |
| Someone changes a unit it started | Hands it back until the night ends or the room's switch goes off. A changed setpoint or fan counts after 90 seconds, another mode after 1 minute, off after 3 minutes |
| A window stays open | Won't start; a running unit is switched off |
| "Leave alone while" entity not off | Won't start |
| Room sensor offline, probing off | Won't start; a running unit carries on until another stop applies |
| Room has no reading, probing on | Probes it (below) |
| Unit offline, or a command not confirmed | Keeps it and retries from what the unit reports |
| Unit has no `cool` mode | Never started |
| Home Assistant restarts cleanly | Carries on from where it was |

## Probing a room with no reading (optional)

If a room has no room sensor, or its sensor is offline, the blueprint can **probe** it.
It runs the unit's fan for a few minutes and then reads the unit's own sensor. An idle
unit measures the air inside itself, but once air is moving its reading follows the
room.

- **When:** only during your hours, when nothing else would stop a start, and at most
  every *Probe every* minutes.
- **What happens:** it switches the unit to **fan only**. Once the unit reports it is
  running, it notes the fan setting and turns the fan down to the probe speed (`low` by
  default). Then it waits *Probe length* minutes.
- **Too hot:** if the reading is at or above the limit plus the margin, it goes
  straight to cooling. The fan stays on the quiet speed and is put back before the
  unit switches off.
- **Fine:** otherwise it puts the fan back while the unit is still running, confirms
  it, and switches off.
- **Interrupted:** a person switching the unit to another mode gets it, as usual, with
  the fan still at the probe speed. If someone switches it off (an off reading has to
  hold for 2 minutes to count), the room is left alone until the next night. The fan is
  then left at the probe speed, because setting the fan on an off unit can switch it
  back on.
- **Commands that don't land** are resent. A probe that never starts is sent `off` after
  5 minutes, a fan that won't go back is given 3 minutes, and if cooling isn't confirmed
  within 5 minutes the probe winds down to off. When in doubt, it ends with the unit off.

Measured on a ducted unit on low fan: the reading was 1 °C off the room until about
150 seconds, then matched. So the default probe length is 3 minutes, and the reading is
only used at the end, because an idle unit can read either high or low. Each probe is a
few minutes of fan noise, so it is off by default. A room sensor is better; probing is
the backup.

## Setup

### 1. Create the helpers

A blueprint can't remember anything by itself. So each room needs three helpers, and
all rooms share four (five with the optional last-action text).

**As a package (YAML).**
1. In `configuration.yaml`, add:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. Copy [`examples/night_time_ac_helpers.yaml`](examples/night_time_ac_helpers.yaml)
   to `/config/packages/`, and repeat its three per-room helpers for each room.
3. Restart Home Assistant.

**Or in the UI:** **Settings > Devices & services > Helpers > Create helper**.

| Helper | Type in the UI | Settings |
| --- | --- | --- |
| Night time AC | Toggle | Shared master switch |
| Night time AC limit | Number | Shared. Min 18, max 28, step 0.5, unit °C (Fahrenheit: 64, 82, 1, °F) |
| Night time AC start, Night time AC end | Date and/or time | Shared. **Time** only |
| Night time AC last action (optional) | Text | Shared. Max length 255 |
| Night time AC - Bedroom | Toggle | This room on or off |
| Night time AC - Bedroom owned | Toggle | Used only by the automation; leave it alone |
| Night time AC - Bedroom state | Text | Used only by the automation. **Max length 255** |

New helpers start at their minimum: a limit of 18 °C, and start and end both at
00:00, which means "no hours" so nothing runs. Set the limit and the hours, for
example 22 °C, 21:00 and 07:00.

### 2. Import the blueprint

Use the button above, or **Settings > Automations & scenes > Blueprints > Import
blueprint** with
`https://github.com/david00769/ha-night-time-ac/blob/main/blueprints/automation/david00769/night_time_ac.yaml`.

### 3. Create one automation per room

**Create automation > Night time AC**, then choose the room's air conditioner, a
temperature sensor **in the room**, its window contacts, and the helpers.

If several rooms share one outdoor unit (a multi-split or VRF system), give each room a
different **Second of each minute to check** so they don't start together: 0, 20, 40 for
three rooms, or 0, 12, 24, 36, 48 for five.

### 4. Add a card

[`examples/dashboard_card.yaml`](examples/dashboard_card.yaml): a tile for the master
switch, the limit and hours, a switch per room, and a status line.

## Inputs

The names are as the automation editor shows them.

| Input | Required | Notes |
| --- | --- | --- |
| Air conditioner | yes | A `climate` entity that offers `cool` |
| Room temperature sensor | for it to start | A sensor with the temperature device class. Empty: the room only starts through probing |
| Windows and doors | no | `binary_sensor`s that are on when open |
| This room's switch | yes | Toggle |
| This room's owned flag | yes | Toggle, used only by this automation |
| This room's state store | yes | Text, max length 255, used only by this automation |
| Master switch | yes | Toggle, shared |
| Temperature limit | yes | Number, shared, in Home Assistant's temperature unit |
| Start time, End time | yes | Date and/or time, time only, shared. Equal start and end: never runs |
| Margin above the limit before starting | no | Default 0.5, at least 0.2, in the limit's unit (Fahrenheit: use 1) |
| Minutes over the limit before starting | no | Default 5 |
| Minutes off before starting again | no | Default 15 |
| Minutes idle before switching a running unit off | no | Default 10; 0 keeps it on until the room or the night ends |
| Probe a room with no reading every (minutes) | no | Default 0 (off) |
| Probe length (minutes) | no | Default 3 |
| Probe fan speed | no | Default `low` |
| Minutes a window stays open before a running unit stops | no | Default 2 |
| Minutes every window must be closed before starting | no | Default 5 |
| Second of each minute to check | no | Default 0 |
| Leave alone while | no | Entities that must all be off for a start; unavailable counts as not off |
| Last action text | no | Text helper for the card |
| Battery level sensor, Grid power sensor | no | Only added to the log |

## Things learned on real hardware

- **Use a sensor in the room, not the air conditioner's reading.** An idle ducted unit
  measures the air inside itself. Ours read about 14 °C overnight with the room at
  20-22 °C, and another read 1 °C above its room. Both matched within a few minutes of
  the fan starting. So the room sensor decides when to start and stop, and the unit's
  reading is only used while air is moving.
- **Put the setpoint back after switching off; put the fan back before.** A setpoint
  sent just before `off` was lost, but one sent to an off unit landed within seconds.
  The fan is the other way round: one sent to an off unit may switch it back on. The
  automation does both in the safe order, and checks them.
- **Judge a manual change by what the unit reports, and give it time.** Readings lag
  commands and can drop out for a minute, so a change only counts once it holds, and a
  missing reading never counts as one.
- **Keep "I started this" in its own helper.** If the state store is wiped or a write
  to it fails, a unit this automation started must still be switched off rather than
  left cooling all night. So each room has an owned flag as well as the state store.

## Working with other automations

If something else may also run the same air conditioner (a solar-surplus routine,
say), put its "I own this unit" flag in **Leave alone while**. This automation then
won't start the unit while that flag is on or not yet loaded, and it never stops a unit
it didn't start.

## Limitations

- One `climate` entity per automation. A zoned ducted system with one entity for several
  rooms needs one automation, with one room sensor.
- **Integrations that can't see the unit.** IR-blaster integrations (SmartIR, Broadlink)
  only assume a state, so a person using the remote is never noticed. Some cloud
  integrations switch a unit on when sent a setpoint, which can briefly restart it as
  the setting is restored. Test a cycle with your integration before relying on it.
- It checks once a minute, so starts and stops lag by about a minute.
- If the unit's own thermostat is satisfied before the room sensor reaches the limit,
  the idle stop switches it off, and it starts again if the room stays over. On a hot
  night that can mean a few short runs instead of one long one: each at least the idle
  time on, and the cooldown plus hold time off (by default 10 minutes on, 20 off).
- After a power cut or crash, Home Assistant restores helpers as they were last saved
  (every 15 minutes, and at shutdown). A unit started in the last few minutes before
  the cut can come back looking like someone else's, and be left running. A clean
  restart is fine.
- If an integration reports a unit as `off` for three minutes during a fault, and the
  unit then comes back cooling, it has already been handed back and is left running.
- A released room is freed when the night ends or its own switch goes off, not when
  the master switch goes off.
- A person changing the fan during a probe, or in the 3 minutes while the fan is being
  put back, has it put back.
- After a restart, a room sensor that hasn't reported yet counts as no reading, so the
  room may be probed once.
- With *Minutes idle before switching a running unit off* set to 0, a room cooled after a
  probe has no room reading to stop on, so it cools until the night ends. Keep the idle
  stop on if you probe.
- Blueprints have no version number; see [CHANGELOG.md](CHANGELOG.md). Re-importing
  replaces the file under every automation that uses it.

## Development

```sh
uv run --group dev pytest
```

The tests render the blueprint's own templates against a stand-in for Home Assistant's
template functions. They are not Home Assistant, so every release is also checked on a
real instance.

## License

[MIT](LICENSE). Copyright (c) 2026 david00769.
