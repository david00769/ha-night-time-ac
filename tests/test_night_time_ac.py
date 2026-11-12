"""Behaviour of the Night time AC blueprint.

The templates are rendered from the blueprint file itself against a stub of the
Home Assistant template functions they use, so a regression in the YAML fails.
Run on a real Home Assistant before a release as well: the stub is not HA.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_FILE = ROOT / "blueprints/automation/david00769/night_time_ac.yaml"


class Input(str):
    pass


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))
BLUEPRINT = yaml.load(BLUEPRINT_FILE.read_text(), Loader=Loader)
ACTIONS = BLUEPRINT["actions"]
STEP = next(a["variables"] for a in ACTIONS if "variables" in a)
DECISION = STEP["decision"]
CHOOSE = next(a["choose"] for a in ACTIONS if "choose" in a)

NOW = datetime(2026, 11, 7, 23, 0, tzinfo=timezone(timedelta(hours=11)))
CLOCK = NOW.timestamp()
UNIT = "climate.bedroom"
SENSOR = "sensor.bedroom_temperature"
WINDOW = "binary_sensor.bedroom_window"
OTHER = "input_boolean.other_automation_owns_bedroom"
ROOM = {
    "climate_entity": UNIT,
    "room_sensor": SENSOR,
    "windows": [WINDOW],
    "room_switch": "input_boolean.night_ac_bedroom",
    "owned_flag": "input_boolean.night_ac_bedroom_owned",
    "state_store": "input_text.night_ac_bedroom_state",
    "margin": 0.5,
    "hold_minutes": 5,
    "cooldown_minutes": 15,
    "window_open_minutes": 2,
    "window_closed_minutes": 5,
    "skip_while": [OTHER],
    "idle_stop_minutes": 10,
}


class States:
    def __init__(self, values, changed):
        self.values, self.changed = values, changed

    def __call__(self, entity_id):
        return self.values.get(entity_id, "unknown")

    def __getitem__(self, entity_id):
        if entity_id not in self.values:
            return None
        seconds = self.changed.get(entity_id, 3600)
        updated = self.changed.get(entity_id + "#updated", seconds)
        return SimpleNamespace(state=self(entity_id), last_changed=NOW - timedelta(seconds=seconds),
                               last_updated=NOW - timedelta(seconds=updated))


def from_json(text, default=None):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def is_number(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def render(template, values=None, attrs=None, changed=None, now=NOW, **variables):
    attrs = attrs or {}
    states = States(values or {}, changed or {})

    def is_state(entity_id, value):
        return states(entity_id) in (value if isinstance(value, list) else [value])

    env = jinja2.Environment()
    env.filters["from_json"] = from_json
    env.filters["to_json"] = json.dumps
    env.tests["is_state"] = is_state
    env.globals.update(states=states, is_state=is_state, is_number=is_number, now=lambda: now,
                       state_attr=lambda entity_id, name: attrs.get(entity_id, {}).get(name))
    return env.from_string(template).render(**variables).strip()


def decide(mode="off", room="23.0", setpoint=24.0, fan="auto", limit=22.0, master_on=True, in_hours=True,
           selected="on", owned="off", state=None, window="off", window_held=3600, unit_held=3600,
           unit_updated=None, missing_window=False, other="off", room_vars=None, action="cooling", unit_reading=None, step=None, modes=("off", "cool", "heat", "fan_only")):
    room_vars = {**ROOM, **(room_vars or {})}
    values = {UNIT: mode, room_vars["room_switch"]: selected, room_vars["owned_flag"]: owned,
              room_vars["state_store"]: json.dumps(state or {}), OTHER: other}
    if room_vars["room_sensor"]:
        values[room_vars["room_sensor"]] = room
    changed = {UNIT: unit_held, WINDOW: window_held}
    if unit_updated is not None:
        changed[UNIT + "#updated"] = unit_updated
    if not missing_window:
        values[WINDOW] = window
    if other is None:
        del values[OTHER]
    attrs = {UNIT: {"temperature": setpoint, "fan_mode": fan, "hvac_action": action,
                  "current_temperature": unit_reading,
                  "target_temp_step": step, "hvac_modes": list(modes)}}
    # As in Home Assistant, the target is worked out first in the same variables block.
    step = float(render(STEP["step"], values, attrs, changed, limit_entity="input_number.limit", **room_vars))
    target = float(render(STEP["target"], values, attrs, changed, limit=limit, step=step, **room_vars))
    return render(DECISION, values, attrs, changed, limit=limit, step=step, target=target, master_on=master_on,
                  in_hours=in_hours, **room_vars)


OVER = {"over_since": CLOCK - 301}
RUNNING = {"temperature": 24.0, "running_fan": "auto", "expected": 22.0, "commanded_at": CLOCK - 600, "settled": True}
RUN = {"mode": "cool", "setpoint": 22.0, "owned": "on", "state": RUNNING, "unit_held": 600}


# -- starting ---------------------------------------------------------------

def test_an_off_room_over_the_limit_starts_after_the_hold():
    assert decide() == "mark_over"
    assert decide(state={"over_since": CLOCK - 299}) == "hold"
    assert decide(state=OVER) == "start"
    assert decide(state={"over_since": CLOCK - 599}, room_vars={"hold_minutes": 10}) == "hold"


def test_the_margin_stops_it_starting_at_the_limit():
    assert decide(room="22.4", state=OVER) == "clear_over"
    assert decide(room="22.5", state=OVER) == "start"
    assert decide(room="22.4", room_vars={"margin": 0.3}, state=OVER) == "start"


@pytest.mark.parametrize("mode", ["cool", "heat_cool", "heat", "dry", "fan_only"])
@pytest.mark.parametrize("setpoint", [20.0, 24.0])
def test_a_unit_someone_else_turned_on_is_never_touched(mode, setpoint):
    assert decide(mode=mode, setpoint=setpoint, room="26.0") == "hold"
    assert decide(mode=mode, setpoint=setpoint, room="26.0", state=OVER) == "clear_over"


@pytest.mark.parametrize("gate", [
    {"master_on": False}, {"in_hours": False}, {"selected": "off"}, {"other": "on"}, {"other": "unavailable"},
    {"other": None}, {"window": "on"}, {"window": "unavailable"}, {"window_held": 299}, {"room": "unavailable"},
    {"mode": "unavailable"}, {"state": {"released": True}},
])
def test_nothing_starts_when_a_gate_is_closed(gate):
    state = gate.pop("state", None)
    assert decide(state={**OVER, **(state or {})}, **gate) != "start"
    assert decide(state=state, **gate) != "mark_over"


def test_leave_alone_while_needs_every_entity_off_and_unavailable_blocks():
    assert decide(state=OVER, other="off") == "start"
    for blocking in ("on", "unavailable", "unknown", None):
        assert decide(state=OVER, other=blocking) != "start"


def test_the_room_sensor_alone_decides_start_and_stop_never_the_units_reading():
    # An idle ducted unit can read far below the room; its reading only judges idle.
    assert decide(room_vars={"room_sensor": ""}, unit_reading=30.0, state=OVER) == "clear_over"
    assert decide(room="21.0", unit_reading=30.0, **RUN) == "stop"
    assert decide(room="25.0", unit_reading=30.0, **RUN) == "hold"


def test_a_stopped_room_waits_the_cooldown():
    assert decide(room="25.0", state={"stopped_at": CLOCK - 899}) == "hold"
    assert decide(room="25.0", state={"stopped_at": CLOCK - 901}) == "mark_over"
    assert decide(room="25.0", state={"stopped_at": CLOCK - 61}, room_vars={"cooldown_minutes": 1}) == "mark_over"


# -- running and stopping ---------------------------------------------------

def test_the_room_reaching_the_limit_returns_the_unit_to_off():
    assert decide(room="22.0", **RUN) == "stop"
    assert decide(room="22.1", **RUN) == "hold"


@pytest.mark.parametrize("gate", [{"master_on": False}, {"in_hours": False}, {"selected": "off"}])
def test_end_of_hours_master_off_or_room_off_restores_the_unit(gate):
    assert decide(room="25.0", **RUN, **gate) == "stop"


def test_a_stop_is_confirmed_by_readback_and_resent_if_dropped():
    stopping = dict(RUNNING, stopping=True, commanded_at=CLOCK - 30)
    assert decide(mode="off", owned="on", setpoint=24.0, state=stopping) == "finish"
    assert decide(mode="cool", owned="on", setpoint=22.0, state=stopping) == "hold"
    assert decide(mode="cool", owned="on", setpoint=22.0, state=dict(stopping, commanded_at=CLOCK - 121)) == "stop"


def test_the_setpoint_goes_back_after_off_and_is_confirmed():
    stopping = dict(RUNNING, stopping=True, commanded_at=CLOCK - 60)
    common = {"mode": "off", "owned": "on"}
    assert decide(setpoint=22.0, state=stopping, **common) == "restore_setpoint"
    assert decide(setpoint=24.0, state=stopping, **common) == "finish"
    assert decide(setpoint=None, state=stopping, **common) == "finish"
    assert decide(setpoint=22.0, state=dict(stopping, temperature=None), **common) == "finish"
    assert decide(setpoint=22.0, state=dict(stopping, commanded_at=CLOCK - 601), **common) == "finish"


def test_a_start_is_confirmed_by_readback_and_resent_if_dropped():
    fresh = dict(RUNNING, settled=False, commanded_at=CLOCK - 30)
    assert decide(mode="off", owned="on", room="24.0", state=fresh) == "hold"
    assert decide(mode="cool", owned="on", room="24.0", setpoint=22.0, state=fresh) == "settle"
    assert decide(mode="off", owned="on", room="24.0", state=dict(fresh, commanded_at=CLOCK - 121)) == "resend"


def test_changing_the_limit_updates_only_a_unit_this_automation_started():
    assert decide(room="25.0", limit=23.0, **RUN) == "retarget"
    assert decide(mode="cool", setpoint=24.0, room="25.0", limit=23.0) == "hold"
    pending = dict(RUNNING, expected=23.0, settled=False, commanded_at=CLOCK - 30)
    assert decide(mode="cool", setpoint=22.0, room="25.0", limit=23.0, owned="on", state=pending) == "hold"


def test_an_open_window_stops_a_running_unit_only_after_it_stays_open():
    assert decide(room="25.0", window="on", window_held=119, **RUN) == "hold"
    assert decide(room="25.0", window="on", window_held=120, **RUN) == "stop"


def test_a_lost_room_sensor_keeps_a_running_unit_going_until_the_night_ends():
    assert decide(room="unavailable", **RUN) == "hold"
    assert decide(room="unavailable", in_hours=False, **RUN) == "stop"


def test_an_offline_unit_keeps_its_ownership_and_is_retried():
    assert decide(room="21.0", **{**RUN, "mode": "unavailable"}) == "hold"


def test_a_lost_state_store_turns_an_owned_unit_off_rather_than_leaving_it_on():
    # The owned flag is its own helper for exactly this case.
    assert decide(mode="cool", owned="on", room="25.0", setpoint=22.0, state={}) == "stop"
    assert decide(mode="off", owned="on", room="25.0", state={}) == "stop"


def test_a_removed_window_sensor_blocks_the_start_without_raising():
    assert decide(state=OVER, missing_window=True) == "clear_over"
    assert decide(room="21.0", missing_window=True, **RUN) == "stop"


# -- people -----------------------------------------------------------------

@pytest.mark.parametrize("change", [
    {"mode": "off", "unit_held": 180}, {"mode": "heat", "unit_held": 60}, {"mode": "dry", "unit_held": 60},
    {"setpoint": 19.0, "state": dict(RUNNING, changed_since=CLOCK - 90)},
    {"fan": "high", "state": dict(RUNNING, changed_since=CLOCK - 90)},
])
def test_a_manual_change_releases_the_unit_for_the_night(change):
    assert decide(room="25.0", **{**RUN, **change}) == "release"
    assert decide(room="21.0", **{**RUN, **change}) == "release"


def test_a_setpoint_or_fan_change_is_timed_from_when_it_was_first_seen():
    # Not from the unit's last update: a unit that reports often would never be judged,
    # and while it waits nothing stops it.
    assert decide(room="25.0", **{**RUN, "setpoint": 19.0}) == "mark_change"
    assert decide(room="25.0", unit_updated=1, **{**RUN, "setpoint": 19.0, "state": dict(RUNNING, changed_since=CLOCK - 89)}) == "hold"
    assert decide(room="25.0", unit_updated=1, **{**RUN, "setpoint": 19.0, "state": dict(RUNNING, changed_since=CLOCK - 90)}) == "release"
    # The change went away: forget it, then carry on as before.
    assert decide(room="25.0", **{**RUN, "state": dict(RUNNING, changed_since=CLOCK - 30)}) == "clear_change"


def test_a_passing_odd_mode_is_not_a_manual_change():
    assert decide(room="25.0", **{**RUN, "mode": "fan_only", "unit_held": 59}) == "hold"
    assert decide(room="25.0", **{**RUN, "mode": "fan_only", "unit_held": 60}) == "release"
    fresh = dict(RUNNING, settled=False, commanded_at=CLOCK - 30)
    assert decide(mode="dry", owned="on", room="25.0", unit_held=10, state=fresh) == "hold"


def test_setpoints_compare_within_half_the_units_step():
    # A 1-degree unit reports 22 for a 22.4 limit; a Fahrenheit system re-rounds.
    fresh = dict(RUNNING, expected=22.0, settled=False, commanded_at=CLOCK - 30)
    assert decide(mode="cool", owned="on", room="24.0", setpoint=22.0, limit=22.4, step=1, state=fresh) == "settle"
    assert decide(room="25.0", limit=22.4, step=1, **RUN) == "hold"
    assert decide(room="25.0", limit=22.2, step=None, **{**RUN, "setpoint": 22.1}) == "hold"
    assert decide(room="25.0", limit=23.0, step=1, **RUN) == "retarget"


def _target(attrs, values=None, **kw):
    values = values or {}
    step = render(STEP["step"], values, attrs, climate_entity=UNIT, limit_entity=kw.get("limit_entity", "input_number.limit"))
    return render(STEP["target"], values, attrs, climate_entity=UNIT, step=float(step), **kw)


def test_the_target_sent_is_the_limit_rounded_to_the_units_step_and_range():
    attrs = lambda step, lo=7, hi=35: {UNIT: {"target_temp_step": step, "min_temp": lo, "max_temp": hi}}
    # Rounded down, so the unit is never asked to stop short of the limit.
    assert _target(attrs(1), limit=22.4) == "22.0"
    assert _target(attrs(1), limit=22.6) == "22.0"
    assert _target(attrs(0.5), limit=22.3) == "22.0"
    assert _target(attrs(0.5), limit=22.5) == "22.5"
    assert _target(attrs(0.1), limit=22.7) == "22.7"
    assert _target(attrs(None), limit=22.3) == "22.0"
    assert _target(attrs(1, lo=18), limit=16.0) == "18.0"


def test_a_fahrenheit_unit_that_reports_no_step_is_treated_as_whole_degrees():
    attrs = {"input_number.limit": {"unit_of_measurement": "°F"}, UNIT: {"min_temp": 60, "max_temp": 90}}
    assert _target(attrs, limit=72.6) == "72.0"


def test_a_flapping_reading_cannot_hold_off_a_stop():
    assert decide(room="21.0", **{**RUN, "state": dict(RUNNING, changed_since=CLOCK - 30)}) == "stop"


def test_a_unit_without_cool_is_never_started():
    assert decide(state=OVER, modes=("off", "heat", "fan_only")) != "start"


def test_the_margin_cannot_be_zero():
    margin = BLUEPRINT["blueprint"]["input"]["tuning"]["input"]["margin"]["selector"]["number"]
    assert margin["min"] > 0


def test_one_bad_reading_is_not_a_manual_change():
    assert decide(room="25.0", **{**RUN, "mode": "off", "unit_held": 60}) == "hold"
    for reading in (None, "unknown", "unavailable", ""):
        assert decide(room="25.0", **{**RUN, "fan": reading}) == "hold"
    assert decide(room="25.0", **{**RUN, "setpoint": None}) == "hold"


@pytest.mark.parametrize("gate", [{"room": "22.0"}, {"master_on": False}, {"in_hours": False}])
def test_a_persons_recent_change_is_never_undone_while_it_is_being_judged(gate):
    assert decide(**{**RUN, "mode": "off", "unit_held": 60}, **gate) == "hold"
    assert decide(**{**RUN, "mode": "off", "unit_held": 180}, **gate) == "release"
    assert decide(**{**RUN, "mode": "heat", "unit_held": 60}, **gate) == "release"


def test_a_person_changing_mode_during_a_start_or_a_stop_is_not_overridden():
    assert decide(mode="heat", owned="on", room="25.0", state=dict(RUNNING, settled=False, commanded_at=CLOCK - 121)) == "release"
    assert decide(mode="heat", owned="on", setpoint=22.0, state=dict(RUNNING, stopping=True, commanded_at=CLOCK - 121)) == "release"


def test_a_released_room_stays_alone_until_the_night_ends_or_its_switch_goes_off():
    released = {"released": True}
    assert decide(room="26.0", state=released) == "hold"
    assert decide(in_hours=False, state=released) == "clear_release"
    assert decide(selected="off", state=released) == "clear_release"


# -- hours and loading ------------------------------------------------------

@pytest.mark.parametrize("start, end, clock, expected", [
    ("21:00:00", "07:00:00", (23, 0), True), ("21:00:00", "07:00:00", (3, 0), True),
    ("21:00:00", "07:00:00", (7, 0), False), ("21:00:00", "07:00:00", (20, 59), False),
    ("01:00:00", "05:00:00", (3, 0), True), ("01:00:00", "05:00:00", (6, 0), False),
    ("21:00:00", "21:00:00", (21, 0), False),
])
def test_hours_cross_midnight(start, end, clock, expected):
    values = {"input_datetime.start": start, "input_datetime.end": end}
    now = NOW.replace(hour=clock[0], minute=clock[1])
    assert render(STEP["in_hours"], values, now=now, start_entity="input_datetime.start",
                  end_entity="input_datetime.end") == str(expected)


def _guard(**over):
    values = {"input_boolean.master": "off", "input_boolean.owned": "off", "input_boolean.room": "on",
              "input_number.limit": "22.0", "input_datetime.start": "21:00:00", "input_datetime.end": "07:00:00",
              "input_text.state": "{}"}
    values.update(over.pop("values", {}))
    attrs = {"input_text.state": {"max": over.pop("max", 255)}}
    return render(BLUEPRINT["conditions"][0]["value_template"], values, attrs, master_switch="input_boolean.master",
                  owned_flag="input_boolean.owned", room_switch="input_boolean.room", limit_entity="input_number.limit",
                  start_entity="input_datetime.start", end_entity="input_datetime.end", state_store="input_text.state")


def test_nothing_acts_until_every_helper_has_loaded():
    assert _guard() == "True"
    for entity in ("input_boolean.master", "input_boolean.owned", "input_boolean.room", "input_text.state"):
        assert _guard(values={entity: "unavailable"}) == "False"
    assert _guard(values={"input_number.limit": "unknown"}) == "False"
    assert _guard(values={"input_datetime.start": "unknown"}) == "False"
    assert _guard(values={"input_number.limit": "16.0"}) == "True"  # any number, any unit


def test_a_state_store_too_short_for_the_saved_state_stops_everything():
    assert _guard(max=100) == "False"


# -- commands ---------------------------------------------------------------

def _branch(decision):
    for option in CHOOSE:
        if option["conditions"] == "{{ decision == '%s' }}" % decision:
            return option["sequence"]
    raise AssertionError(decision)


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


DECISIONS = ("start", "resend", "settle", "retarget", "stop", "restore_setpoint", "finish", "release",
             "clear_release", "mark_over", "clear_over", "mark_idle", "clear_idle", "mark_change", "clear_change")


def test_every_decision_has_a_command_and_hold_does_nothing():
    for decision in DECISIONS:
        assert _branch(decision)
    assert {"condition": "template", "value_template": "{{ decision != 'hold' }}"} in ACTIONS


def test_it_cools_and_can_never_heat():
    modes = {n["data"]["hvac_mode"] for n in _walk(CHOOSE) if isinstance(n.get("data"), dict) and "hvac_mode" in n["data"]}
    assert modes == {"cool", "off"}


def test_a_start_acts_on_a_fresh_decision_with_no_delay_before_it():
    assert not any("delay" in n for n in _walk(BLUEPRINT["actions"]))


def test_the_start_saves_what_it_will_put_back_before_commanding():
    start = _branch("start")
    assert start[0]["action"] == "input_text.set_value"
    assert start[1]["action"] == "input_boolean.turn_on"
    saved = json.loads(render(start[0]["data"]["value"], attrs={UNIT: {"temperature": 24.0}}, climate_entity=UNIT,
                              target=22.0, stamp=CLOCK))
    assert saved == {"temperature": 24.0, "expected": 22.0, "commanded_at": CLOCK, "settled": False}


def test_the_setpoint_goes_back_only_after_off():
    assert [s["action"] for s in _branch("stop")] == ["input_text.set_value", "climate.set_hvac_mode"]
    restore = _branch("restore_setpoint")
    assert render(restore[0]["data"]["temperature"], saved={"temperature": 24.0}) == "24.0"


def test_the_longest_saved_state_fits_the_state_store():
    longest = {"temperature": 29.5, "expected": 26.5, "commanded_at": 4102444800.0, "settled": True,
               "running_fan": "medium-high", "stopping": True, "stopped_at": 4102444800.0, "over_since": 4102444800.0,
               "idle_since": 4102444800.0, "changed_since": 4102444800.0}
    assert len(json.dumps(longest)) < 255


def test_a_release_hands_the_unit_back_and_remembers_it_for_the_night():
    release = _branch("release")
    assert release[0] == {"action": "input_boolean.turn_off", "target": {"entity_id": "{{ owned_flag }}"}}
    assert json.loads(release[1]["data"]["value"]) == {"released": True}


def test_the_log_names_battery_and_grid_only_when_given():
    assert render(STEP["energy"], {}, battery_level="", grid_power="") == ""
    assert render(STEP["energy"], {"sensor.b": "80", "sensor.g": "120"}, battery_level="sensor.b",
                  grid_power="sensor.g") == "(battery 80%, grid 120 W)"


# -- blueprint shape --------------------------------------------------------

def test_a_single_entity_given_where_a_list_belongs_is_not_split_into_characters():
    template = BLUEPRINT["variables"]["windows"]
    assert render(template, windows_input="binary_sensor.window") == "['binary_sensor.window']"
    assert render(template, windows_input=["a", "b"]) == "['a', 'b']"
    assert render(template, windows_input=[]) == "[]"


def test_every_input_is_declared_and_mapped():
    declared = {k for section in BLUEPRINT["blueprint"]["input"].values() for k in section["input"]}
    used = {str(v) for v in BLUEPRINT["variables"].values() if isinstance(v, Input)}
    used |= {str(v) for n in _walk(BLUEPRINT["triggers"]) for v in n.values() if isinstance(v, Input)}
    used |= {str(v) for t in BLUEPRINT["triggers"] for v in t.get("entity_id", []) if isinstance(v, Input)}
    assert used == declared


def test_the_blueprint_carries_what_a_published_blueprint_needs():
    meta = BLUEPRINT["blueprint"]
    assert meta["source_url"].startswith("https://github.com/david00769/ha-night-time-ac/")
    assert meta["homeassistant"]["min_version"]
    assert BLUEPRINT["mode"] == "single"
    assert not any("service" in n for n in _walk(BLUEPRINT["actions"]))  # current `action:` syntax


# SHA-256 prefixes of words that identify the author's home and family. Hashed so this
# guard does not publish what it guards. The unit's make is named on purpose.
PRIVATE = {'164689c5087c88d1', '26d87ab917c12973', '407ec3a40f987c65', '6c22ff4b5316f965', '93c5730961fcfe68', 'c59840c7ddb81e38', 'dea7cd279319a43d'}


def test_nothing_private_is_published():
    import hashlib
    import re

    skip = {".git", ".venv", "__pycache__", ".pytest_cache"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or skip & set(path.relative_to(ROOT).parts):
            continue
        text = path.read_bytes().decode("utf-8", "ignore").lower()
        for word in set(re.findall(r"[a-z0-9]+", text)):
            assert hashlib.sha256(word.encode()).hexdigest()[:16] not in PRIVATE, path.name
