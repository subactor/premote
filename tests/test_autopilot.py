"""Tests for the autopilot module."""
from __future__ import annotations

import re
import unittest

from premote.autopilot import AutopilotRule, build_default_rules


class TestAutopilotRule(unittest.TestCase):
    def test_matches_yn_prompt(self) -> None:
        rule = AutopilotRule(
            name="test-yn",
            pattern=re.compile(r"\(y/n\)\s*$", re.IGNORECASE),
            action="type",
            value="y",
        )
        assert rule.matches("Do you want to continue? (y/n) ")
        assert rule.matches("Proceed? (Y/N) ")
        assert not rule.matches("No prompts here")

    def test_matches_allow_once(self) -> None:
        rule = AutopilotRule(
            name="test-allow",
            pattern=re.compile(r"(?i)(allow|permit)\s*(once|this\s*time)"),
            action="key",
            value="Return",
        )
        assert rule.matches("Allow once")
        assert rule.matches("Permit this time")
        assert not rule.matches("Deny all")

    def test_cooldown(self) -> None:
        rule = AutopilotRule(
            name="test-cd",
            pattern=re.compile(r"test"),
            action="key",
            value="Return",
            cooldown_seconds=2.0,
            last_triggered=100.0,
        )
        assert not rule.can_trigger(101.0)  # Only 1s passed, need 2s
        assert rule.can_trigger(102.5)  # 2.5s passed

    def test_matches_yes_no_bracket(self) -> None:
        rule = AutopilotRule(
            name="test-yesno",
            pattern=re.compile(r"(?i)\[yes/no\]\s*$"),
            action="type",
            value="yes\n",
        )
        assert rule.matches("Are you sure? [yes/no] ")
        assert rule.matches("Confirm? [Yes/No] ")
        assert not rule.matches("Not a prompt")


class TestDefaultRules(unittest.TestCase):
    def test_default_rules_build(self) -> None:
        rules = build_default_rules()
        assert len(rules) > 0
        # Check they are sorted by priority (descending)
        priorities = [r.priority for r in rules]
        assert priorities == sorted(priorities, reverse=True)

    def test_all_rules_have_names(self) -> None:
        rules = build_default_rules()
        for r in rules:
            assert r.name, f"Rule without a name: {r}"

    def test_yn_rule_matches(self) -> None:
        rules = build_default_rules()
        yn_rules = [r for r in rules if r.name == "agy-yes-no-y"]
        assert len(yn_rules) == 1
        assert yn_rules[0].matches("Proceed? (y/n) ")

    def test_press_enter_rule(self) -> None:
        rules = build_default_rules()
        enter_rules = [r for r in rules if r.name == "press-enter-continue"]
        assert len(enter_rules) == 1
        assert enter_rules[0].matches("Press Enter to continue")
        assert enter_rules[0].matches("Nacisnij Enter aby kontynuować")
