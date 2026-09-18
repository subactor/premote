"""Autopilot: Automated KVM steering for unattended agent sessions.

Watches terminal screens via OCR and automatically approves dialogs, selects
least-restrictive options, and types confirmations using xdotool keystroke
injection. Designed for long-cycle autonomous LLM agent operation in Docker
noVNC containers.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

from premote.client import ContainerClient
from premote.dialog_decider import DialogAction, DialogDecider
from premote.kvm import KVMController


@dataclass
class AutopilotRule:
    """A single autopilot pattern-action rule."""

    name: str
    pattern: re.Pattern[str]
    action: str  # "key", "type", "click"
    value: str  # e.g. "y", "Return", "yes\nReturn"
    priority: int = 0
    cooldown_seconds: float = 3.0
    last_triggered: float = 0.0

    def matches(self, text: str) -> bool:
        return bool(self.pattern.search(text))

    def can_trigger(self, now: float) -> bool:
        return (now - self.last_triggered) >= self.cooldown_seconds


# Default rules for common LLM agent confirmation dialogs.
# Legacy decision path: kept only as an explicit opt-in for offline use
# (`decider="regex"` / `--decider regex`). The default path is the
# NL -> Action DSL dialog decider in premote.dialog_decider.
DEFAULT_RULES: list[dict] = [
    # Antigravity / agy permission prompts
    {
        "name": "agy-allow-once",
        "pattern": r"(?i)(allow|permit|approve)\s*(once|this\s*time)",
        "action": "key",
        "value": "Return",
        "priority": 10,
    },
    {
        "name": "agy-yes-no-y",
        "pattern": r"(?i)\(y/n\)\s*$",
        "action": "type",
        "value": "y",
        "priority": 20,
    },
    {
        "name": "agy-yes-no-yes",
        "pattern": r"(?i)\[yes/no\]\s*$",
        "action": "type",
        "value": "yes\n",
        "priority": 20,
    },
    {
        "name": "agy-proceed-yn",
        "pattern": r"(?i)proceed\?\s*\[?[yY]/[nN]\]?\s*$",
        "action": "type",
        "value": "y",
        "priority": 20,
    },
    # Generic "press Enter to continue" patterns
    {
        "name": "press-enter-continue",
        "pattern": r"(?i)(press\s*(enter|return)|nacisnij\s*enter)",
        "action": "key",
        "value": "Return",
        "priority": 5,
    },
    # Claude Code permission prompts
    {
        "name": "claude-allow-tool",
        "pattern": r"(?i)allow\s+.*tool\s*\?",
        "action": "type",
        "value": "y",
        "priority": 15,
    },
    # Gemini CLI confirmation
    {
        "name": "gemini-confirm",
        "pattern": r"(?i)(run\s+this\s+command|execute\s+command)\s*\?\s*\[?[yY]",
        "action": "type",
        "value": "y",
        "priority": 15,
    },
    # Aider confirmation
    {
        "name": "aider-apply-edit",
        "pattern": r"(?i)apply\s+(this\s+)?(edit|change)\s*\?",
        "action": "type",
        "value": "y",
        "priority": 15,
    },
    # npm / pip install confirmations
    {
        "name": "npm-proceed",
        "pattern": r"(?i)(proceed|continue)\?\s*\(y\)",
        "action": "type",
        "value": "y",
        "priority": 10,
    },
    # Safety: "Allow always" / most permissive option select
    {
        "name": "allow-always",
        "pattern": r"(?i)(allow\s*always|always\s*allow|trust\s*this)",
        "action": "key",
        "value": "Return",
        "priority": 25,
    },
    # Common selector: numbered option, select "1" (least restrictive)
    {
        "name": "select-option-1",
        "pattern": r"(?i)(select|choose|pick)\s*(an?\s*)?option.*\n\s*1[.\)]\s*(allow|yes|accept|approve)",
        "action": "type",
        "value": "1\n",
        "priority": 30,
    },
]


def build_default_rules() -> list[AutopilotRule]:
    """Build the default set of autopilot rules."""
    rules = []
    for r in DEFAULT_RULES:
        rules.append(
            AutopilotRule(
                name=r["name"],
                pattern=re.compile(r["pattern"], re.MULTILINE | re.DOTALL),
                action=r["action"],
                value=r["value"],
                priority=r.get("priority", 0),
                cooldown_seconds=r.get("cooldown_seconds", 3.0),
            )
        )
    return sorted(rules, key=lambda x: -x.priority)


@dataclass
class AutopilotSession:
    """A running autopilot session that polls OCR and applies rules."""

    kvm: KVMController
    rules: list[AutopilotRule] = field(default_factory=build_default_rules)
    poll_interval: float = 5.0
    max_iterations: int = 0  # 0 = unlimited
    verbose: bool = True
    on_action: Callable[[str, str, str], None] | None = None  # callback(rule_name, action, text_snippet)
    decider: DialogDecider | None = field(default_factory=DialogDecider)
    decider_cooldown_seconds: float = 3.0
    _decider_last_triggered: dict[str, float] = field(default_factory=dict)

    def _apply_action(self, rule: AutopilotRule) -> None:
        """Apply the action defined by a rule."""
        if rule.action == "key":
            self.kvm.key(rule.value.strip())
        elif rule.action == "type":
            self.kvm.type_text(rule.value, delay_ms=30)
        elif rule.action == "click":
            parts = rule.value.split(",")
            if len(parts) == 2:
                self.kvm.click(int(parts[0]), int(parts[1]))
        else:
            if self.verbose:
                print(f"  [autopilot] Unknown action type: {rule.action}")

    def _apply_dialog_action(self, dialog: DialogAction) -> None:
        """Apply one Action DSL decision produced by the dialog decider."""
        if dialog.action == "key":
            self.kvm.key(dialog.value.strip())
        elif dialog.action == "type":
            self.kvm.type_text(dialog.value, delay_ms=30)
        elif dialog.action == "click":
            parts = dialog.value.split(",")
            if len(parts) == 2:
                self.kvm.click(int(parts[0].strip()), int(parts[1].strip()))

    def _run_once_decider(self, screen: str, now: float) -> str | None:
        """One poll cycle through the NL -> Action DSL dialog decider."""
        dialog = self.decider.decide(screen) if self.decider else None
        if dialog is None or not dialog.is_approval:
            return None

        last = self._decider_last_triggered.get(dialog.state, 0.0)
        if (now - last) < self.decider_cooldown_seconds:
            return None

        if self.verbose:
            snippet = screen[-120:].replace("\n", " ")
            print(f"  [autopilot] Decider: {dialog.state} → {dialog.action}({dialog.value!r}) [{dialog.reason}]")
            print(f"              Screen tail: ...{snippet}")

        self._apply_dialog_action(dialog)
        self._decider_last_triggered[dialog.state] = now

        if self.on_action:
            self.on_action(dialog.state, dialog.action, screen[-200:])

        return dialog.state

    def run_once(self) -> str | None:
        """Run a single poll cycle. Returns the triggered rule name, or None."""
        try:
            screen = self.kvm.screen_text()
        except Exception as e:
            if self.verbose:
                print(f"  [autopilot] OCR error: {e}")
            return None

        if not screen.strip():
            return None

        now = time.time()

        if self.decider is not None:
            return self._run_once_decider(screen, now)

        for rule in self.rules:
            if rule.matches(screen) and rule.can_trigger(now):
                if self.verbose:
                    snippet = screen[-120:].replace("\n", " ")
                    print(f"  [autopilot] Triggered: {rule.name} → {rule.action}({rule.value!r})")
                    print(f"              Screen tail: ...{snippet}")

                self._apply_action(rule)
                rule.last_triggered = now

                if self.on_action:
                    self.on_action(rule.name, rule.action, screen[-200:])

                return rule.name

        return None

    def run(self) -> int:
        """Run the autopilot loop. Returns total number of actions taken."""
        actions_taken = 0
        iteration = 0

        if self.verbose:
            print(f"[autopilot] Starting with {len(self.rules)} rules, interval={self.poll_interval}s")
            if self.max_iterations:
                print(f"[autopilot] Max iterations: {self.max_iterations}")
            print("[autopilot] Press Ctrl+C to stop\n")

        try:
            while True:
                iteration += 1
                if self.max_iterations and iteration > self.max_iterations:
                    if self.verbose:
                        print(f"\n[autopilot] Reached max iterations ({self.max_iterations}). Stopping.")
                    break

                triggered = self.run_once()
                if triggered:
                    actions_taken += 1

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            if self.verbose:
                print(f"\n[autopilot] Stopped by user. Actions taken: {actions_taken}")

        return actions_taken


def create_autopilot(
    account: str,
    *,
    poll_interval: float = 5.0,
    max_iterations: int = 0,
    verbose: bool = True,
    extra_rules: list[dict] | None = None,
    decider: str = "llm",
) -> AutopilotSession:
    """Create an autopilot session for a container account.

    Args:
        account: Container account ID (e.g. "prototypowanie").
        poll_interval: Seconds between OCR polls.
        max_iterations: Max poll cycles (0=unlimited).
        verbose: Print action logs to stdout.
        extra_rules: Additional rules as dicts with name/pattern/action/value
            (legacy regex path only).
        decider: Decision path - "llm" (default) classifies dialogs with the
            NL -> Action DSL dialog decider; "regex" keeps the legacy
            rule-matching path for offline use.

    Returns:
        AutopilotSession ready to be started with .run() or .run_once().
    """
    container = ContainerClient(account)
    kvm = KVMController(container)

    session_decider: DialogDecider | None = None
    if decider == "llm":
        session_decider = DialogDecider()
    elif decider != "regex":
        raise ValueError(f"Unknown decider mode: {decider!r} (expected 'llm' or 'regex')")

    rules = build_default_rules()
    if extra_rules:
        for r in extra_rules:
            rules.append(
                AutopilotRule(
                    name=r["name"],
                    pattern=re.compile(r["pattern"], re.MULTILINE | re.DOTALL),
                    action=r["action"],
                    value=r["value"],
                    priority=r.get("priority", 0),
                    cooldown_seconds=r.get("cooldown_seconds", 3.0),
                )
            )
        rules.sort(key=lambda x: -x.priority)

    return AutopilotSession(
        kvm=kvm,
        rules=rules,
        poll_interval=poll_interval,
        max_iterations=max_iterations,
        verbose=verbose,
        decider=session_decider,
    )
