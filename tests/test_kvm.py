from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from premote.kvm import KVMController, normalize_window_id
from premote.nl_dsl import parse_nl_to_dsl


class TestKVMController(unittest.TestCase):
    def test_normalize_window_id(self):
        self.assertEqual(normalize_window_id("0x1c0002e"), "0x01c0002e")
        self.assertEqual(normalize_window_id("0x01c0002e"), "0x01c0002e")
        self.assertEqual(normalize_window_id("29360174"), "0x01c0002e")
        self.assertEqual(normalize_window_id(0x1C0002E), "0x01c0002e")

    def test_list_windows_parsing(self):
        sample_wmctrl = (
            "0x00e00003 -1 0 0 1600 24 host xfce4-panel\n"
            "0x01c00003  1 0 75 1600 849 host Terminal - Desktop\n"
            "0x01c0002e  4 0 75 1600 849 host Terminal - premesh\n"
        )
        ctrl = KVMController(container=None)
        with patch.object(ctrl, "_run_cmd") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["wmctrl"], returncode=0, stdout=sample_wmctrl, stderr=""
            )
            wins = ctrl.list_windows()
            self.assertEqual(len(wins), 2)
            self.assertEqual(wins[0].id, "0x01c00003")
            self.assertEqual(wins[0].desktop, 1)
            self.assertEqual(wins[0].title, "Terminal - Desktop")
            self.assertEqual(wins[1].id, "0x01c0002e")
            self.assertEqual(wins[1].desktop, 4)

    def test_select_ocr_lang(self):
        ctrl = KVMController(container=None)
        with patch.object(ctrl, "get_available_ocr_langs", return_value={"eng", "osd"}):
            self.assertEqual(ctrl.select_ocr_lang(), "eng")
            self.assertEqual(ctrl.select_ocr_lang("eng+pol"), "eng")

        with patch.object(ctrl, "get_available_ocr_langs", return_value={"eng", "pol", "osd"}):
            self.assertEqual(ctrl.select_ocr_lang(), "eng+pol")
            self.assertEqual(ctrl.select_ocr_lang("pol"), "pol")

    def test_screen_text_missing_window(self):
        ctrl = KVMController(container=None)
        with patch.object(ctrl, "select_ocr_lang", return_value="eng"):
            with patch.object(ctrl, "_run_cmd") as mock_run:
                mock_run.side_effect = [
                    # xwininfo call fails
                    subprocess.CompletedProcess(args=["xwininfo"], returncode=1, stdout="", stderr="No such window"),
                    # list_windows call
                    subprocess.CompletedProcess(
                        args=["wmctrl"],
                        returncode=0,
                        stdout="0x01c0002e  4 0 75 1600 849 host Terminal - premesh\n",
                        stderr="",
                    ),
                ]
                result = ctrl.screen_text("0x01c000ce")
                self.assertIn("Błąd: Nie znaleziono okna 0x01c000ce", result)
                self.assertIn("0x01c0002e", result)

    def test_screen_text_success_flow(self):
        ctrl = KVMController(container=None)
        xwininfo_output = """
xwininfo: Window id: 0x1c0002e "Terminal - premesh"
  Absolute upper-left X:  0
  Absolute upper-left Y:  75
  Width: 1600
  Height: 849
"""
        with patch.object(ctrl, "select_ocr_lang", return_value="eng"):
            with patch.object(ctrl, "_run_cmd") as mock_run:
                mock_run.side_effect = [
                    # xwininfo
                    subprocess.CompletedProcess(args=["xwininfo"], returncode=0, stdout=xwininfo_output, stderr=""),
                    # xdotool get_desktop
                    subprocess.CompletedProcess(args=["xdotool"], returncode=0, stdout="1\n", stderr=""),
                    # xdotool getactivewindow
                    subprocess.CompletedProcess(args=["xdotool"], returncode=0, stdout="0x01c00003\n", stderr=""),
                    # wmctrl -i -a
                    subprocess.CompletedProcess(args=["wmctrl"], returncode=0, stdout="", stderr=""),
                    # scrot
                    subprocess.CompletedProcess(args=["scrot"], returncode=0, stdout="", stderr=""),
                    # tesseract
                    subprocess.CompletedProcess(args=["tesseract"], returncode=0, stdout="Sample OCR Text\nLine 2", stderr=""),
                    # xdotool set_desktop
                    subprocess.CompletedProcess(args=["xdotool"], returncode=0, stdout="", stderr=""),
                    # xdotool windowactivate
                    subprocess.CompletedProcess(args=["xdotool"], returncode=0, stdout="", stderr=""),
                    # rm tmp
                    subprocess.CompletedProcess(args=["rm"], returncode=0, stdout="", stderr=""),
                ]
                with patch("time.sleep"):
                    text = ctrl.screen_text("0x01c0002e", restore_focus=True)
                    self.assertEqual(text, "Sample OCR Text\nLine 2")

    def test_nl_dsl_screen_text(self):
        cmd1 = parse_nl_to_dsl("screen-text 0x01c0002e")
        self.assertIsNotNone(cmd1)
        self.assertEqual(cmd1.action, "screen-text")
        self.assertEqual(cmd1.args, ["0x01c0002e"])

        cmd2 = parse_nl_to_dsl("odczytaj tekst z okna 0x01c0002e")
        self.assertIsNotNone(cmd2)
        self.assertEqual(cmd2.action, "screen-text")
        self.assertEqual(cmd2.args, ["0x01c0002e"])

        cmd3 = parse_nl_to_dsl("ocr")
        self.assertIsNotNone(cmd3)
        self.assertIn(cmd3.action, {"screen-text", "ocr"})


if __name__ == "__main__":
    unittest.main()
