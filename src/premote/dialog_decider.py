"""Dialog-state decider: NL -> Action DSL classification for autopilot.

Replaces the rigid DEFAULT_RULES regex heuristics with a lightweight
LLM/SLM classifier. The model reads the OCR screen text, classifies the
dialog state into one of the canonical approval categories and answers
with a strict Action DSL document. Parsing is fail-closed: any invalid,
missing or out-of-bound model output yields decision "none" and never
injects keystrokes.

Action DSL schema (NL -> Action DSL):

    {
      "state": "<one of DIALOG_STATES>",
      "decision": "approve" | "none",
      "action": "key" | "type" | "click" | "",
      "value": "<keystroke or text, empty for decision=none>",
      "reason": "<short evidence from the screen text>"
    }

Transport is any OpenAI-compatible /chat/completions endpoint,
configured through environment variables:

    PREMOTE_LLM_BASE_URL   (default: https://openrouter.ai/api/v1)
    PREMOTE_LLM_MODEL      (fallback: LLM_MODEL, then a small SLM default)
    PREMOTE_LLM_API_KEY    (fallback: OPENROUTER_API_KEY)
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

# Canonical dialog states (semantic labels kept from the retired regex
# rules so callbacks, logs and cooldowns stay comparable).
DIALOG_STATES = (
    "agy-allow-once",
    "agy-yes-no-y",
    "agy-yes-no-yes",
    "agy-proceed-yn",
    "press-enter-continue",
    "claude-allow-tool",
    "gemini-confirm",
    "aider-apply-edit",
    "npm-proceed",
    "allow-always",
    "select-option-1",
    "other-dialog",
    "no-dialog",
)

ACTION_DSL_SCHEMA: dict = {
    "state": DIALOG_STATES,
    "decision": ("approve", "none"),
    "action": ("key", "type", "click", ""),
    "value": "non-empty string when decision=approve, else empty",
    "reason": "short evidence string",
}

# Safety bounds for injected values (fail-closed beyond these).
_MAX_VALUE_CHARS = 64
_MAX_CLICK_COORD = 10000
_MAX_SCREEN_CHARS = 4000
_MAX_REASON_CHARS = 200

_DEFAULT_MODEL = "openrouter/qwen/qwen3-coder-next"

SYSTEM_PROMPT = """You classify terminal dialogs for an unattended-agent autopilot.
Read the OCR screen text and decide whether it shows a confirmation dialog
that should be approved, and which single keystroke or text approves it.

Answer with ONE JSON object only, no prose, matching this Action DSL:
{
  "state": one of """ + json.dumps(list(DIALOG_STATES)) + """,
  "decision": "approve" or "none",
  "action": "key", "type", "click" or "" (empty when decision is none),
  "value": the exact keystroke(s) or text to send (empty when decision is none),
  "reason": short evidence quoted from the screen text
}

Rules:
- "key" values are xdotool key names or "+"-joined combos, e.g. "Return", "ctrl+c".
- "type" values are short typed answers, e.g. "y", "yes\\n", "1\\n".
- "click" values are "x,y" integer coordinates.
- Approve ONLY consent/confirmation prompts (permission asks, y/n questions,
  "press Enter to continue", option selectors). Never approve when the screen
  shows no dialog, an unreadable state, or a destructive/irreversible warning
  you cannot attribute to a consent flow: use decision "none".
- Prefer the least restrictive approval the dialog offers (e.g. "allow always"
  over "allow once" when both are visible and selectable with one action)."""


@dataclass(frozen=True)
class DialogAction:
    """One validated Action DSL decision (fail-closed default: none)."""

    state: str = "no-dialog"
    decision: str = "none"
    action: str = ""
    value: str = ""
    reason: str = ""

    @property
    def is_approval(self) -> bool:
        return self.decision == "approve" and bool(self.action) and bool(self.value)


def _reject(reason: str) -> DialogAction:
    return DialogAction(state="other-dialog", decision="none", action="", value="", reason=reason[:_MAX_REASON_CHARS])


def parse_action_dsl(payload: object) -> DialogAction:
    """Validate one parsed JSON payload against the Action DSL contract.

    Any violation returns decision "none" (fail-closed) instead of raising.
    """
    if not isinstance(payload, dict):
        return _reject("invalid-dsl: not an object")

    state = payload.get("state", "no-dialog")
    if state not in DIALOG_STATES:
        return _reject(f"invalid-dsl: unknown state {state!r}")

    decision = payload.get("decision", "none")
    if decision not in ("approve", "none"):
        return _reject(f"invalid-dsl: unknown decision {decision!r}")

    action = payload.get("action", "")
    if action not in ("key", "type", "click", ""):
        return _reject(f"invalid-dsl: unknown action {action!r}")

    value = payload.get("value", "")
    reason = str(payload.get("reason", ""))[:_MAX_REASON_CHARS]

    if decision == "none":
        if action or value:
            return _reject("invalid-dsl: action/value present with decision none")
        return DialogAction(state=state, decision="none", action="", value="", reason=reason)

    if not action:
        return _reject("invalid-dsl: approve without action")
    if not isinstance(value, str) or not value:
        return _reject("invalid-dsl: approve without value")
    if len(value) > _MAX_VALUE_CHARS:
        return _reject("invalid-dsl: value too long")

    if action == "click":
        parts = value.split(",")
        if len(parts) != 2:
            return _reject("invalid-dsl: click value must be 'x,y'")
        try:
            x, y = int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            return _reject("invalid-dsl: click coordinates not integers")
        if not (0 <= x <= _MAX_CLICK_COORD and 0 <= y <= _MAX_CLICK_COORD):
            return _reject("invalid-dsl: click coordinates out of bounds")
    elif action == "key":
        keys = [k.strip() for k in value.split("+")]
        if not keys or any(not k for k in keys):
            return _reject("invalid-dsl: empty key combo element")

    return DialogAction(state=state, decision=decision, action=action, value=value, reason=reason)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(raw: str) -> object | None:
    """Extract the first JSON object from a model answer (fences tolerated)."""
    if not raw:
        return None
    fenced = _JSON_FENCE_RE.search(raw)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    bracket = _JSON_OBJECT_RE.search(raw)
    if bracket:
        candidates.append(bracket.group(0))
    candidates.append(raw.strip())
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


class DialogDecider:
    """Lightweight LLM/SLM dialog-state classifier producing Action DSL."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 12.0,
        temperature: float = 0.0,
        complete: Callable[[str], str] | None = None,
    ) -> None:
        self.model = (
            model
            or os.environ.get("PREMOTE_LLM_MODEL")
            or os.environ.get("LLM_MODEL")
            or _DEFAULT_MODEL
        )
        self.base_url = (
            base_url
            or os.environ.get("PREMOTE_LLM_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("PREMOTE_LLM_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        )
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        # Injectable transport keeps the decider testable without network.
        self._complete = complete or self._chat_completions

    def _chat_completions(self, user_prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as error:
            raise RuntimeError(f"dialog-decider transport failed: {error}") from error
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(f"dialog-decider malformed response: {error}") from error

    def decide(self, screen_text: str) -> DialogAction:
        """Classify one OCR screen snapshot into an Action DSL decision."""
        bounded = screen_text[-_MAX_SCREEN_CHARS:] if screen_text else ""
        user_prompt = (
            "OCR screen text (newest lines at the end):\n"
            + (bounded if bounded.strip() else "<empty screen>")
        )
        try:
            raw = self._complete(user_prompt)
        except Exception as error:  # fail-closed: never act on transport failure
            return _reject(f"decider-unavailable: {error}")
        payload = extract_json_object(raw)
        if payload is None:
            return _reject("invalid-dsl: model answer is not JSON")
        return parse_action_dsl(payload)
