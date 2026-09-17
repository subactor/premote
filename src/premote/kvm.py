from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Sequence

from premote.client import ContainerClient, ContainerError
from premote.models import WindowInfo


class KVMController:
    def __init__(self, container: ContainerClient, display: str = ":1") -> None:
        self.container = container
        self.display = display

    def list_windows(self) -> list[WindowInfo]:
        res = self.container.run(
            ["wmctrl", "-l", "-G"],
            env={"DISPLAY": self.display},
            check=False,
        )
        windows = []
        for line in res.stdout.strip().splitlines():
            parts = line.split(None, 7)
            if len(parts) >= 8:
                wid, desk, x, y, w, h, _host, title = parts
                windows.append(
                    WindowInfo(
                        id=wid,
                        desktop=int(desk),
                        x=int(x),
                        y=int(y),
                        width=int(w),
                        height=int(h),
                        title=title,
                    )
                )
        return windows

    def focus(self, pattern: str) -> str:
        search_res = self.container.run(
            ["xdotool", "search", "--name", pattern],
            env={"DISPLAY": self.display},
            check=False,
        )
        wids = search_res.stdout.strip().split()
        if not wids:
            raise ContainerError(f"Nie znaleziono okna pasującego do wzorca: {pattern}")
        wid = wids[0]
        self.container.run(
            ["xdotool", "windowactivate", "--sync", wid],
            env={"DISPLAY": self.display},
            check=True,
        )
        return wid

    def type_text(self, text: str, delay_ms: int = 50) -> None:
        self.container.run(
            ["xdotool", "type", f"--delay={delay_ms}", text],
            env={"DISPLAY": self.display},
            check=True,
        )

    def key(self, key_name: str) -> None:
        self.container.run(
            ["xdotool", "key", key_name],
            env={"DISPLAY": self.display},
            check=True,
        )

    def click(self, x: int, y: int, button: int = 1) -> None:
        self.container.run(
            ["xdotool", "mousemove", str(x), str(y), "click", str(button)],
            env={"DISPLAY": self.display},
            check=True,
        )

    def capture(self, host_output_path: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_container_path = f"/tmp/capture-{os.getpid()}.png"
            tmp_host_path = tmp.name

        try:
            self.container.run(
                ["scrot", tmp_container_path],
                env={"DISPLAY": self.display},
                check=True,
            )
            # Copy from container to host
            subprocess.run(
                ["docker", "cp", f"{self.container.container_name}:{tmp_container_path}", host_output_path],
                check=True,
            )
            self.container.run(
                ["rm", "-f", tmp_container_path],
                check=False,
            )
            return host_output_path
        finally:
            if os.path.exists(tmp_host_path):
                os.remove(tmp_host_path)
