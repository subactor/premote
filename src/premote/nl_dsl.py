"""
Wellmanifest NL-DSL-LLM standard implementation for premote.
Complies with wellmanifest/nl-dsl-llm specification:
  - Layer 1: Rule-based localized NL Fast-Path Parser (Polish & English, <1ms, 0 tokens)
  - Layer 2: Canonical DSL Command Engine & Standard Execution Envelope
  - Layer 3: Adaptive LLM Translation Fallback compiler
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class DSLCommand:
    """Canonical DSL command definition."""
    canonical_name: str
    action: str
    args: list[str] = field(default_factory=list)
    confidence: float = 1.0
    source: str = "rule_fastpath"


@dataclass
class ExecutionEnvelope:
    """Standardized wellmanifest/nl-dsl-llm response envelope."""
    success: bool
    command: str
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NLIntentParser:
    """
    Layer 1 Deterministic Fast-Path NL Parser.
    Zero-token, sub-millisecond intent matching for Polish & English commands.
    """

    PATTERNS: list[tuple[re.Pattern[str], str, Callable[[re.Match[str]], list[str]]]] = [
        # Quota
        (
            re.compile(r"^(?:sprawd[zź]|poka[zż]|ile(?:\s+mam)?|status|zu[zż]ycie|check|show|view|get|\s)*(?:limit[a-zęóąśłżźćńu]*|token[a-zęóąśłżźćńu]*|kwot[a-z]*|quota)[s]?(?:\s+(?:w|dla)?\s*(?:model[a-z]*|claude|gpt|gemini))?$", re.I),
            "account.quota",
            lambda m: ["quota"],
        ),
        # Screenshots / Capture
        (
            re.compile(r"^(?:zr[oó]b|wykonaj|pobierz|take|make|capture)?\s*(?:zrzut(?:\s+ekranu)?|screenshot|screen(?:\s*capture)?|snapshot)(?:\s+(?:do\s+)?([^\s]+))?$", re.I),
            "kvm.capture",
            lambda m: ["kvm-capture", m.group(1)] if m.group(1) else ["kvm-capture"],
        ),
        # Windows listing
        (
            re.compile(r"^(?:poka[zż]|wypisz|jakie|list|show|get)\s*(?:okna|aplikacje|windows|apps)$", re.I),
            "kvm.windows",
            lambda m: ["kvm-windows"],
        ),
        # KVM Click
        (
            re.compile(r"^(?:kliknij|click)(?:\s+(?:w|at))?\s*(\d+)[,\s]+(\d+)$", re.I),
            "kvm.click",
            lambda m: ["kvm-click", m.group(1), m.group(2)],
        ),
        # KVM Type
        (
            re.compile(r"^(?:wpisz|napisz|type)\s*[\"']?([^\"']+)[\"']?$", re.I),
            "kvm.type",
            lambda m: ["kvm-type", m.group(1)],
        ),
        # KVM Key
        (
            re.compile(r"^(?:naci[sś]nij|press|key)\s*([a-zA-Z0-9_\-]+)$", re.I),
            "kvm.key",
            lambda m: ["kvm-key", m.group(1)],
        ),
        # KVM Focus
        (
            re.compile(r"^(?:aktywuj|prze[lł][aą]cz na|focus)(?:\s+okno)?\s*[\"']?([^\"']+)[\"']?$", re.I),
            "kvm.focus",
            lambda m: ["kvm-focus", m.group(1)],
        ),
        # Autopilot / Auto-Approve
        (
            re.compile(r"^(?:zatwierd[zź]|auto[ -]?approve|autopilot|akceptuj)(?:\s+dialogi|\s+wszystko)?$", re.I),
            "dialog.autopilot",
            lambda m: ["autopilot"],
        ),
        # Terminal
        (
            re.compile(r"^(?:otw[oó]rz\s+)?(?:terminal|konsol[eęa]|bash|shell)$", re.I),
            "account.terminal",
            lambda m: ["terminal"],
        ),
        # Models
        (
            re.compile(r"^(?:jakie|poka[zż]|list[a]?|dost[eę]pne)?\s*(?:modele|models)$", re.I),
            "account.models",
            lambda m: ["models"],
        ),
        # Explicit agent prompt commands
        (
            re.compile(r"^(?:zapytaj|napisz|wykonaj|stw[oó]rz|zr[oó]b|ask|prompt|run|execute|generate)\s+(.+)$", re.I),
            "agent.prompt",
            lambda m: ["prompt", m.group(1)],
        ),
    ]

    CANONICAL_ACTION_MAP: dict[str, str] = {
        "quota": "account.quota",
        "quota-json": "account.quota",
        "prompt": "agent.prompt",
        "prompt-json": "agent.prompt",
        "continue": "agent.continue",
        "models": "account.models",
        "terminal": "account.terminal",
        "kvm-windows": "kvm.windows",
        "kvm-focus": "kvm.focus",
        "kvm-click": "kvm.click",
        "kvm-type": "kvm.type",
        "kvm-key": "kvm.key",
        "kvm-capture": "kvm.capture",
        "autopilot": "dialog.autopilot",
        "auto-approve-all": "dialog.autopilot",
    }

    def parse(self, text: str) -> DSLCommand | None:
        cleaned = text.strip()
        if not cleaned:
            return None

        # Check direct canonical actions
        parts = cleaned.split()
        if parts and parts[0] in self.CANONICAL_ACTION_MAP:
            return DSLCommand(
                canonical_name=self.CANONICAL_ACTION_MAP[parts[0]],
                action=parts[0],
                args=parts[1:],
                confidence=1.0,
                source="canonical_direct",
            )

        for pattern, canon_name, extractor in self.PATTERNS:
            m = pattern.match(cleaned)
            if m:
                extracted_args = extractor(m)
                action = extracted_args[0]
                args = extracted_args[1:]
                return DSLCommand(
                    canonical_name=canon_name,
                    action=action,
                    args=args,
                    confidence=1.0,
                    source="rule_fastpath",
                )

        return None


def complete_translation_via_llm(nl_prompt: str, account: str) -> DSLCommand | None:
    """
    Layer 3 Adaptive LLM Translation Fallback.
    Translates an unrecognized NL query into canonical premote DSL command.
    """
    # 1. Próba bezpośredniego użycia biblioteki subllm
    try:
        from subllm import complete
        prompt = (
            "You are an NL-to-DSL compiler for the 'premote' tool.\n"
            "Map the following user instruction to one of the canonical actions: "
            "[quota, prompt, kvm-windows, kvm-capture, kvm-click, kvm-type, kvm-key, kvm-focus, autopilot, terminal, models].\n"
            f"User instruction: \"{nl_prompt}\"\n\n"
            "Output strictly valid JSON with keys: \"canonical_name\", \"action\", \"args\" (array of strings).\n"
            "Example: {\"canonical_name\": \"account.quota\", \"action\": \"quota\", \"args\": []}"
        )
        res = complete("premote", "nl-dsl", [{"role": "user", "content": prompt}], timeout_seconds=10.0)
        if res and res.content:
            data = json.loads(res.content.strip().strip("```json").strip("```"))
            return DSLCommand(
                canonical_name=data.get("canonical_name", "agent.prompt"),
                action=data.get("action", "prompt"),
                args=data.get("args", [nl_prompt]),
                confidence=0.85,
                source="llm_translation_subllm",
            )
    except Exception:
        pass

    # 2. Fallback: treat unbounded conversational queries as an agy prompt
    return DSLCommand(
        canonical_name="agent.prompt",
        action="prompt",
        args=[nl_prompt],
        confidence=0.7,
        source="unbounded_prompt_fallback",
    )


def parse_nl_to_dsl(text: str, account: str = "prototypowanie") -> DSLCommand:
    """Translates NL query to canonical DSL command through tripartite architecture."""
    parser = NLIntentParser()
    cmd = parser.parse(text)
    if cmd:
        return cmd

    # Adaptive fallback
    llm_cmd = complete_translation_via_llm(text, account)
    if llm_cmd:
        return llm_cmd

    return DSLCommand(
        canonical_name="agent.prompt",
        action="prompt",
        args=[text],
        confidence=0.5,
        source="default_fallback",
    )
