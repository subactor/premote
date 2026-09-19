from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Sequence

from premote.client import ContainerClient, ContainerError
from premote.models import WindowInfo


def normalize_window_id(wid_str: str | int) -> str:
    raw = str(wid_str).strip()
    if raw.lower().startswith("0x"):
        val = int(raw, 16)
    else:
        val = int(raw)
    return f"0x{val:08x}"


class KVMController:
    def __init__(self, container: ContainerClient | None = None, display: str | None = None) -> None:
        self.container = container
        self.display = display or os.environ.get("DISPLAY", ":1")

    def _run_cmd(
        self,
        cmd: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        merged_env["DISPLAY"] = self.display
        if env:
            merged_env.update(env)

        if self.container is not None and self.container.is_running():
            return self.container.run(cmd, env=merged_env, check=check)
        else:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=merged_env,
                check=check,
            )

    def list_windows(self) -> list[WindowInfo]:
        res = self._run_cmd(["wmctrl", "-l", "-G"], check=False)
        windows: list[WindowInfo] = []
        for line in res.stdout.strip().splitlines():
            parts = line.split(None, 7)
            if len(parts) >= 8:
                wid, desk, x, y, w, h, _host, title = parts
                if desk == "-1" and ("xfce4-panel" in title or "Desktop" in title):
                    continue
                try:
                    norm_id = normalize_window_id(wid)
                except Exception:
                    norm_id = wid
                windows.append(
                    WindowInfo(
                        id=norm_id,
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
        search_res = self._run_cmd(["xdotool", "search", "--name", pattern], check=False)
        wids = search_res.stdout.strip().split()
        if not wids:
            raise ContainerError(f"Nie znaleziono okna pasującego do wzorca: {pattern}")
        wid = wids[0]
        self._run_cmd(["xdotool", "windowactivate", wid], check=True)
        return wid

    def type_text(self, text: str, delay_ms: int = 50) -> None:
        press_enter = text.endswith("\n")
        clean_text = text.rstrip("\r\n")
        if clean_text:
            self._run_cmd(["xdotool", "type", f"--delay={delay_ms}", clean_text], check=True)
        if press_enter:
            self._run_cmd(["xdotool", "key", "Return"], check=True)

    def key(self, key_name: str) -> None:
        self._run_cmd(["xdotool", "key", key_name], check=True)

    def click(self, x: int, y: int, button: int = 1) -> None:
        self._run_cmd(["xdotool", "mousemove", str(x), str(y), "click", str(button)], check=True)

    def capture(self, host_output_path: str) -> str:
        tmp_path = f"/tmp/capture-{os.getpid()}-{int(time.time() * 1000)}.png"
        try:
            self._run_cmd(["scrot", tmp_path], check=True)
            if self.container is not None and self.container.is_running():
                subprocess.run(
                    ["docker", "cp", f"{self.container.container_name}:{tmp_path}", host_output_path],
                    check=True,
                )
                self._run_cmd(["rm", "-f", tmp_path], check=False)
            else:
                if tmp_path != host_output_path:
                    import shutil

                    shutil.move(tmp_path, host_output_path)
            return host_output_path
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def get_available_ocr_langs(self) -> set[str]:
        try:
            res = self._run_cmd(["tesseract", "--list-langs"], check=False)
            return {line.strip() for line in res.stdout.splitlines()[1:] if line.strip()}
        except Exception:
            return {"eng"}

    def select_ocr_lang(self, requested: str | None = None) -> str:
        available = self.get_available_ocr_langs()
        if requested:
            parts = [p.strip() for p in requested.split("+") if p.strip()]
            valid = [p for p in parts if p in available]
            if valid:
                return "+".join(valid)
        if "pol" in available and "eng" in available:
            return "eng+pol"
        if "eng" in available:
            return "eng"
        return next(iter(available)) if available else "eng"

    def get_active_window_id(self) -> str | None:
        try:
            res = self._run_cmd(["xdotool", "getactivewindow"], check=False)
            raw = res.stdout.strip()
            if raw:
                return normalize_window_id(raw)
        except Exception:
            pass
        return None

    def get_current_desktop(self) -> str | None:
        try:
            res = self._run_cmd(["xdotool", "get_desktop"], check=False)
            raw = res.stdout.strip()
            if raw:
                return raw
        except Exception:
            pass
        return None

    def screen_text(
        self,
        window_id: str | None = None,
        lang: str | None = None,
        restore_focus: bool = True,
    ) -> str:
        chosen_lang = self.select_ocr_lang(lang)
        tmp_img = f"/tmp/ocr-{os.getpid()}-{int(time.time() * 1000)}.png"

        target_wid = window_id
        if not target_wid:
            target_wid = self.get_active_window_id()

        if not target_wid:
            # Capture entire screen as fallback
            try:
                self._run_cmd(["scrot", tmp_img], check=True)
                ocr_res = self._run_cmd(["tesseract", tmp_img, "stdout", "-l", chosen_lang], check=False)
                return ocr_res.stdout.strip()
            finally:
                self._run_cmd(["rm", "-f", tmp_img], check=False)

        try:
            norm_id = normalize_window_id(target_wid)
        except Exception:
            norm_id = str(target_wid).strip()

        # Query geometry via xwininfo
        xwin_res = self._run_cmd(["xwininfo", "-id", norm_id], check=False)
        if xwin_res.returncode != 0:
            available_wins = self.list_windows()
            lines = [f"Błąd: Nie znaleziono okna {norm_id}."]
            if available_wins:
                lines.append("Dostępne okna w sesji X11:")
                for w in available_wins:
                    lines.append(f"  {w.id}  [pulpit {w.desktop}]  {w.title}")
            return "\n".join(lines)

        info = xwin_res.stdout
        x_m = re.search(r"Absolute upper-left X:\s+(-?\d+)", info)
        y_m = re.search(r"Absolute upper-left Y:\s+(-?\d+)", info)
        w_m = re.search(r"Width:\s+(\d+)", info)
        h_m = re.search(r"Height:\s+(\d+)", info)

        if not (x_m and y_m and w_m and h_m):
            return f"Błąd: Nie udało się odczytać geometrii okna {norm_id}."

        x, y, w, h = int(x_m.group(1)), int(y_m.group(1)), int(w_m.group(1)), int(h_m.group(1))
        if w <= 0 or h <= 0:
            return f"Błąd: Nieprawidłowe wymiary okna {norm_id}: {w}x{h}."

        orig_desk = self.get_current_desktop()
        orig_active = self.get_active_window_id()

        try:
            # Activate window to ensure it is visible and rendered on current workspace
            self._run_cmd(["wmctrl", "-i", "-a", norm_id], check=False)
            time.sleep(0.25)

            # Scrot capture of rectangle
            crop_arg = f"{x},{y},{w},{h}"
            scrot_res = self._run_cmd(["scrot", "-a", crop_arg, tmp_img], check=False)
            if scrot_res.returncode != 0:
                return f"Błąd przechwytywania okna: {scrot_res.stderr or scrot_res.stdout}"

            ocr_res = self._run_cmd(["tesseract", tmp_img, "stdout", "-l", chosen_lang], check=False)
            return ocr_res.stdout.strip()
        finally:
            if restore_focus:
                if orig_desk is not None:
                    self._run_cmd(["xdotool", "set_desktop", orig_desk], check=False)
                if orig_active is not None:
                    self._run_cmd(["xdotool", "windowactivate", orig_active], check=False)
            self._run_cmd(["rm", "-f", tmp_img], check=False)
