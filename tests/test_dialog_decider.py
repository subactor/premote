"""Tests for the NL -> Action DSL dialog decider."""
from __future__ import annotations

import json

from premote.autopilot import AutopilotSession
from premote.dialog_decider import (
    ACTION_DSL_SCHEMA,
    DialogAction,
    DialogDecider,
    extract_json_object,
    parse_action_dsl,
)


class FakeKVM:
    """Minimal KVM stub recording injected actions."""

    def __init__(self, screen: str = "") -> None:
        self.screen = screen
        self.calls: list[tuple[str, str]] = []

    def screen_text(self) -> str:
        return self.screen

    def key(self, name: str) -> None:
        self.calls.append(("key", name))

    def type_text(self, text: str, delay_ms: int = 0) -> None:
        self.calls.append(("type", text))

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", f"{x},{y}"))


def fixed_decider(raw_or_error, model: str = "test-model") -> DialogDecider:
    """Build a decider whose transport returns a fixed payload or raises."""

    def complete(_prompt: str) -> str:
        if isinstance(raw_or_error, Exception):
            raise raw_or_error
        return raw_or_error

    return DialogDecider(model=model, complete=complete)


def test_schema_lists_decisions_and_states() -> None:
    assert "approve" in ACTION_DSL_SCHEMA["decision"]
    assert "none" in ACTION_DSL_SCHEMA["decision"]
    assert "agy-allow-once" in ACTION_DSL_SCHEMA["state"]
    assert "no-dialog" in ACTION_DSL_SCHEMA["state"]


def test_parse_valid_approval() -> None:
    action = parse_action_dsl(
        {"state": "agy-yes-no-y", "decision": "approve", "action": "type", "value": "y", "reason": "(y/n)"}
    )
    assert action.is_approval
    assert action.state == "agy-yes-no-y"


def test_parse_none_decision_must_be_empty() -> None:
    ok = parse_action_dsl({"state": "no-dialog", "decision": "none", "action": "", "value": "", "reason": ""})
    assert not ok.is_approval
    bad = parse_action_dsl({"state": "no-dialog", "decision": "none", "action": "key", "value": "Return"})
    assert not bad.is_approval
    assert "invalid-dsl" in bad.reason


def test_parse_rejects_unknown_enums() -> None:
    for payload in (
        {"state": "definitely-not-a-state", "decision": "approve", "action": "key", "value": "Return"},
        {"state": "agy-allow-once", "decision": "maybe", "action": "key", "value": "Return"},
        {"state": "agy-allow-once", "decision": "approve", "action": "wave", "value": "Return"},
    ):
        action = parse_action_dsl(payload)
        assert not action.is_approval
        assert "invalid-dsl" in action.reason


def test_parse_rejects_unsafe_values() -> None:
    too_long = parse_action_dsl(
        {"state": "agy-yes-no-y", "decision": "approve", "action": "type", "value": "y" * 200}
    )
    assert not too_long.is_approval
    empty = parse_action_dsl(
        {"state": "agy-yes-no-y", "decision": "approve", "action": "type", "value": ""}
    )
    assert not empty.is_approval
    bad_click = parse_action_dsl(
        {"state": "select-option-1", "decision": "approve", "action": "click", "value": "12"}
    )
    assert not bad_click.is_approval
    good_click = parse_action_dsl(
        {"state": "select-option-1", "decision": "approve", "action": "click", "value": "640,480"}
    )
    assert good_click.is_approval


def test_parse_non_object_is_rejected() -> None:
    assert not parse_action_dsl("approve").is_approval
    assert not parse_action_dsl([1, 2, 3]).is_approval
    assert not parse_action_dsl(None).is_approval


def test_extract_json_tolerates_fences_and_prose() -> None:
    raw = 'Sure!\n```json\n{"state":"npm-proceed","decision":"approve","action":"type","value":"y"}\n```'
    payload = extract_json_object(raw)
    assert isinstance(payload, dict)
    assert payload["state"] == "npm-proceed"
    assert extract_json_object("no json here at all") is None


def test_decide_approves_yn_prompt() -> None:
    raw = json.dumps(
        {"state": "agy-yes-no-y", "decision": "approve", "action": "type", "value": "y", "reason": "(y/n)"}
    )
    decider = fixed_decider(raw)
    action = decider.decide("Proceed? (y/n) ")
    assert action.is_approval
    assert action.value == "y"


def test_decide_fail_closed_on_transport_error() -> None:
    decider = fixed_decider(RuntimeError("connection refused"))
    action = decider.decide("Anything on screen")
    assert not action.is_approval
    assert "decider-unavailable" in action.reason


def test_decide_fail_closed_on_garbage() -> None:
    decider = fixed_decider("I would press y maybe?")
    action = decider.decide("Proceed? (y/n)")
    assert not action.is_approval
    assert "invalid-dsl" in action.reason


def test_decide_respects_model_refusal() -> None:
    raw = json.dumps({"state": "other-dialog", "decision": "none", "action": "", "value": "", "reason": "destructive warning"})
    decider = fixed_decider(raw)
    assert not decider.decide("rm -rf / -- are you sure?").is_approval


def test_session_uses_decider_and_cooldown() -> None:
    raw = json.dumps(
        {"state": "agy-allow-once", "decision": "approve", "action": "key", "value": "Return", "reason": "allow once"}
    )
    decider = fixed_decider(raw)
    kvm = FakeKVM("Do you want to allow? [Allow once] [Allow always]")
    session = AutopilotSession(kvm=kvm, decider=decider, verbose=False)

    triggered = session.run_once()
    assert triggered == "agy-allow-once"
    assert kvm.calls == [("key", "Return")]

    # Same state inside the cooldown window must not fire again.
    kvm.calls.clear()
    assert session.run_once() is None
    assert kvm.calls == []


def test_session_decider_none_decision_does_not_act() -> None:
    raw = json.dumps({"state": "no-dialog", "decision": "none", "action": "", "value": "", "reason": ""})
    kvm = FakeKVM("plain build output, no dialog")
    session = AutopilotSession(kvm=kvm, decider=fixed_decider(raw), verbose=False)
    assert session.run_once() is None
    assert kvm.calls == []


def test_session_decider_click_coordinates() -> None:
    raw = json.dumps(
        {"state": "select-option-1", "decision": "approve", "action": "click", "value": "300, 420", "reason": "option 1"}
    )
    kvm = FakeKVM("Select an option:\n 1) Allow")
    session = AutopilotSession(kvm=kvm, decider=fixed_decider(raw), verbose=False)
    assert session.run_once() == "select-option-1"
    assert kvm.calls == [("click", "300,420")]


def test_dialog_action_defaults_are_inert() -> None:
    assert not DialogAction().is_approval
