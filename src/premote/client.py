from __future__ import annotations

import os
import shutil
import subprocess
from typing import Sequence


class ContainerError(RuntimeError):
    pass


class ContainerClient:
    def __init__(self, account_id: str, container_name: str | None = None) -> None:
        self.account_id = account_id
        self.container_name = container_name or f"llm-account-hub-{account_id}"

    def ensure_docker(self) -> None:
        if shutil.which("docker") is None:
            raise ContainerError("Nie znaleziono polecenia 'docker' w PATH.")

    def is_running(self) -> bool:
        self.ensure_docker()
        cmd = ["docker", "ps", "--filter", f"name=^{self.container_name}$", "--format", "{{.Names}}"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return self.container_name in res.stdout.split()

    def run(
        self,
        command: Sequence[str],
        *,
        user: str = "tom",
        cwd: str = "/home/tom/github",
        env: dict[str, str] | None = None,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.ensure_docker()
        docker_cmd = [
            "docker", "exec",
            "-u", user,
            "-w", cwd,
        ]
        if env:
            for k, v in env.items():
                docker_cmd.extend(["-e", f"{k}={v}"])
        docker_cmd.append(self.container_name)
        docker_cmd.extend(command)

        res = subprocess.run(
            docker_cmd,
            capture_output=capture,
            text=True,
            check=False,
        )
        if check and res.returncode != 0:
            error_msg = (res.stderr or res.stdout or f"Kod błędu {res.returncode}").strip()
            raise ContainerError(f"Polecenie w kontenerze nie powiodło się: {error_msg}")
        return res

    def interactive_shell(
        self,
        shell_cmd: Sequence[str] | None = None,
        *,
        user: str = "tom",
        cwd: str = "/home/tom/github",
    ) -> int:
        self.ensure_docker()
        cmd = ["docker", "exec", "-it", "-u", user, "-w", cwd, self.container_name]
        cmd.extend(shell_cmd or ["/bin/bash", "-l"])
        return subprocess.run(cmd).returncode


def list_active_accounts() -> list[str]:
    if shutil.which("docker") is None:
        return []
    res = subprocess.run(
        ["docker", "ps", "--filter", "name=^llm-account-hub-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    accounts = []
    for line in res.stdout.strip().splitlines():
        name = line.strip()
        if name.startswith("llm-account-hub-"):
            accounts.append(name.replace("llm-account-hub-", ""))
    return sorted(accounts)
