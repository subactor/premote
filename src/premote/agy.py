from __future__ import annotations

import json
from typing import Any

from premote.client import ContainerClient
from premote.models import PromptResult, QuotaReport


class AntigravityClient:
    def __init__(self, container: ContainerClient) -> None:
        self.container = container

    def prompt(
        self,
        text: str,
        *,
        auto_approve: bool = True,
        output_format: str = "text",
        model: str | None = None,
        mode: str | None = None,
    ) -> PromptResult:
        cmd = ["agy", "-p", text, "--output-format", output_format]
        if auto_approve:
            cmd.append("--dangerously-skip-permissions")
        if model:
            cmd.extend(["--model", model])
        if mode:
            cmd.extend(["--mode", mode])

        res = self.container.run(
            cmd,
            env={"HOME": "/home/tom"},
            cwd="/home/tom/github",
        )
        stdout = res.stdout.strip()
        if output_format == "json":
            try:
                data = json.loads(stdout)
                return PromptResult(
                    response=data.get("response", ""),
                    conversation_id=data.get("conversation_id", ""),
                    status=data.get("status", "SUCCESS"),
                    duration_seconds=float(data.get("duration_seconds", 0.0)),
                    raw_json=data,
                )
            except Exception:
                pass
        return PromptResult(response=stdout)

    def continue_conversation(self, text: str, *, auto_approve: bool = True) -> PromptResult:
        cmd = ["agy", "-c", "-p", text]
        if auto_approve:
            cmd.append("--dangerously-skip-permissions")
        res = self.container.run(
            cmd,
            env={"HOME": "/home/tom"},
            cwd="/home/tom/github",
        )
        return PromptResult(response=res.stdout.strip())

    def quota(self) -> QuotaReport:
        res = self.container.run(
            ["agy", "-p", "/quota", "--output-format", "json"],
            env={"HOME": "/home/tom"},
            cwd="/home/tom/github",
        )
        try:
            data = json.loads(res.stdout)
            raw_text = data.get("response", "")
            return QuotaReport.from_json_dict(data, raw_text=raw_text)
        except Exception:
            return QuotaReport(groups=(), raw_text=res.stdout.strip())

    def models(self) -> str:
        res = self.container.run(
            ["agy", "models"],
            env={"HOME": "/home/tom"},
            cwd="/home/tom/github",
        )
        return res.stdout.strip()

    def interactive(self) -> int:
        return self.container.interactive_shell(
            ["agy", "--dangerously-skip-permissions"],
            user="tom",
            cwd="/home/tom/github",
        )
