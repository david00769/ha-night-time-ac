# Night time AC

A Home Assistant blueprint that keeps a room at or below a temperature limit
overnight, and keeps the air conditioner **off** the rest of the time.

[![Open your Home Assistant instance and show the blueprint import dialog with this blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/create-link/?redirect=blueprint_import&blueprint_url=https%3A%2F%2Fgithub.com%2Fdavid00769%2Fha-night-time-ac%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fdavid00769%2Fnight_time_ac.yaml)

## Why I built it

Our bedroom air conditioner (a Toshiba SMMS-i VRF indoor unit) runs its fan the
whole time it is on, even once the room is at its setpoint, and you hear the
refrigerant moving too. My wife doesn't like the noise, so she turns the AC off
at night. Then the room warms up, I wake up hot and turn it back on, and the noise
starts again.

What we wanted was neither "on all night" nor "off all night": **off, and quiet,
until the room actually gets too hot; then cool it back down and switch off again.**
A schedule can't do that, and the unit's own thermostat can't either, because it
keeps the fan running while it waits.

This blueprint does exactly that, and it is careful about whose air conditioner it
is: it only ever takes over a unit that is off, it puts the unit back the way it
found it, and when a person changes the unit it hands it back for the rest of the
night (after one to three minutes, so a passing glitch is not mistaken for a person).

## What it does

During the hours you set, for each room you switch on:

1. If the room has been **above the limit** (plus a small margin) for a few minutes,
   with its windows closed, it turns the air conditioner on in **cool** at the limit.
2. When the room is **back at the limit**, or the unit has **stopped cooling** for a
   while (it reports idle or fan, or its own reading has reached its setpoint), or the
   night ends, it turns the unit **off** and puts its setpoint back to what it was
   (when the unit reported one).
3. It waits a while before starting again, so it doesn't cycle the compressor.

It never heats (it only ever uses `cool`), never changes the fan, and never stops a
unit it didn't start.

## The rules

| Situation | What it does |
| --- | --- |
| Unit off, room over the limit for the hold time, windows closed | Starts it: `cool`, at the limit rounded down to the unit's own step |
| Unit already on, in any mode, at any setting | Leaves it alone |
| Room back at the limit | Off, then the earlier setpoint is restored |
| Unit it started has stopped cooling for the idle time | Off, so the room is quiet; starts again if the room warms |
| End of the hours, master switch off, or this room's switch off | Off, setpoint restored |
| Limit changed | Updates only units it started |
| Someone changes a unit it started | Hands it back and leaves it alone until the night ends or the room's switch goes off. A changed setpoint or fan counts after 90 seconds, another mode after 1 minute, off after 3 minutes |
| A window stays open | Won't start; a running unit is switched off |
| Another automation's flag is not off ("Leave alone while") | Won't start |
| Room sensor offline | Won't start; a running unit carries on until another stop applies |
| Unit offline, or a command not confirmed | Keeps it and retries from what the unit reports |
| Home Assistant restarts cleanly | Carries on from the stored state |
| Unit has no `cool` mode | Never started |

## Setup

### 1. Create the helpers

A blueprint can't remember anything by itself, so each room needs a small state
store, and the rooms share a few settings. The easiest way is a package
(`configuration.yaml`: `homeassistant: packages: !include_dir_named packages`),
using [`examples/night_time_ac_helpers.yaml`](examples/night_time_ac_helpers.yaml):

```yaml
input_boolean:
  night_ac:                 # master switch, shared
    name: Night time AC
    icon: mdi:weather-night
  night_ac_bedroom:         # this room on/off
    name: Night time AC - Bedroom
  night_ac_bedroom_owned:   # used only by the automation
    name: Night time AC - Bedroom owned

input_number:
  night_ac_limit:           # shared, in Home Assistant's temperature unit
    name: Night time AC limit
    min: 18                 # °F: 64
    max: 28                 # °F: 82
    step: 0.5               # °F: 1
    unit_of_measurement: °C # °F: °F

input_datetime:
  night_ac_start:
    name: Night time AC start
    has_time: true
  night_ac_end:
    name: Night time AC end
    has_time: true

input_text:
  night_ac_bedroom_state:   # used only by the automation
    name: Night time AC - Bedroom state
    max: 255                # required: the default of 100 is too short
  night_ac_last_action:     # optional, shared: what happened last, for the card
    name: Night time AC last action
    max: 255
```

Or create the same helpers in **Settings > Devices & services > Helpers**. The
state text needs **Maximum length 255**; the automation does nothing until it has.
Set the limit and the start and end times once created (for example 22 °C,
21:00 and 07:00).

Repeat the three per-room helpers (`night_ac_<room>`, `night_ac_<room>_owned`,
`night_ac_<room>_state`) for each room.

### 2. Import the blueprint

Use the button above, or **Settings > Automations & scenes > Blueprints > Import
blueprint** with
`https://github.com/david00769/ha-night-time-ac/blob/main/blueprints/automation/david00769/night_time_ac.yaml`.

### 3. Create one automation per room

**Create automation > Night time AC**, then pick the room's air conditioner, a
temperature sensor **in the room**, its window contacts, and the helpers. Rooms on
one outdoor unit: give each a different **Second of each minute to check** (0, 20,
40) so they don't start together.

### 4. Add a card

[`examples/dashboard_card.yaml`](examples/dashboard_card.yaml) is a tile for the
master switch, the limit and hours, and a switch per room.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| Air conditioner | yes | Any `climate` entity that supports `cool` |
| Room temperature sensor | for it to start | A sensor in the room. Empty: the room never starts |
| Windows and doors | no | `binary_sensor`s that are on when open |
| This room's switch | yes | `input_boolean` |
| This room's owned flag | yes | `input_boolean`, used only by this automation |
| This room's state store | yes | `input_text`, maximum length 255, used only by this automation |
| Master switch | yes | `input_boolean`, shared |
| Temperature limit | yes | `input_number`, shared, in Home Assistant's temperature unit |
| Start time, End time | yes | `input_datetime`, time only, shared. Equal means no hours |
| Margin | no | Default 0.5 above the limit before starting; at least 0.2, so it cannot start and stop around the limit |
| Minutes over the limit before starting | no | Default 5 |
| Minutes off before starting again | no | Default 15 |
| Minutes idle before switching off | no | Default 10; 0 keeps a started unit on until the room or night ends |
| Window minutes (open to stop, closed to start) | no | Default 2 and 5 |
| Second of each minute to check | no | Default 0 |
| Leave alone while | no | Entities that must all be **off** for a start; unavailable counts as not off |
| Last action text, battery and grid sensors | no | Only for the log |

## Things learned on real hardware

- **Use a sensor in the room, not the air conditioner's reading.** An idle ducted
  unit measures air at the unit, not in the room. Ours read about 14 °C overnight
  with the room at 20-22 °C, then matched the room within two minutes of the fan
  starting. So the room sensor decides when to start and stop; the unit's reading
  is only used, while it is running, to tell whether it has stopped cooling.
- **Put the setpoint back after switching off, not before.** A setpoint sent just
  before `off` was lost; one sent to a unit that was already off landed within
  seconds and left it off. The automation does it in that order and checks it.
- **Judge a manual change on what the unit reports, and give it time.** Readings lag
  commands and can drop out for a minute, so a change only counts when it holds, and
  a missing reading never counts as one.
- **Keep "I started this" in its own helper.** If the state store is wiped or a write
  to it fails, a unit this automation started must still be switched off rather than
  left cooling all night, so each room has an owned flag as well as the state store.

## Working with other automations

If something else may also run the same air conditioner (a solar-surplus routine,
say), put its "I own this unit" flag in **Leave alone while**. This automation then
won't start the unit while that flag is on or not yet loaded, and it never stops a
unit it didn't start.

## Limitations

- One air conditioner per automation; one room sensor per room.
- It checks once a minute, so starts and stops are a minute or so behind.
- It doesn't run the fan, change modes other than `cool`, or pre-cool.
- If the unit's own thermostat is satisfied before the room sensor reaches the limit,
  the idle stop switches it off and it starts again if the room stays over. On a hot
  night that can mean a few short runs instead of one long one: each at least the idle
  time on and the cooldown plus hold time off (by default 10 on, 20 off).
- After a power cut or crash, Home Assistant restores helpers as they were last saved
  (every 15 minutes and at shutdown). A unit started in the last few minutes before
  the cut can come back looking like someone else's and be left running. A clean
  restart is fine.
- If an integration reports a unit as `off` for three minutes during a fault and it
  then comes back cooling, it has already been handed back and is left running.
- A released room is freed when the night ends or its own switch goes off, not when
  the master switch goes off.
- Blueprints have no version number; see [CHANGELOG.md](CHANGELOG.md). Re-importing
  replaces the file under every automation that uses it.

## Development

```sh
uv run --group dev pytest
```

The tests render the blueprint's own templates against a stub of Home
Assistant's template functions. They are not Home Assistant, so a change is also
checked on a real instance before release.

## License

[MIT](LICENSE). Copyright (c) 2026 david00769.
