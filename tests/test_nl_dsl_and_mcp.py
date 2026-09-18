"""
Unit tests for wellmanifest/nl-dsl-llm implementation in premote:
  - NLIntentParser (Polish & English fast path)
  - Canonical DSL Command mapping
  - Model Context Protocol (MCP) server integration
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from premote.mcp_server import handle_tool_call, TOOLS_DEFINITIONS
from premote.nl_dsl import NLIntentParser, parse_nl_to_dsl, DSLCommand, ExecutionEnvelope


class TestPremoteNLIntentParser(unittest.TestCase):
    def setUp(self):
        self.parser = NLIntentParser()

    def test_quota_intents_polish_and_english(self):
        queries = [
            "quota",
            "sprawdź limity",
            "pokaż quota",
            "ile mam limitu",
            "check limits",
            "show quota",
            "view quotas",
        ]
        for q in queries:
            cmd = self.parser.parse(q)
            self.assertIsNotNone(cmd, f"Failed to parse query: {q}")
            self.assertEqual(cmd.action, "quota")
            self.assertEqual(cmd.canonical_name, "account.quota")
            self.assertEqual(cmd.confidence, 1.0)

    def test_capture_intents_polish_and_english(self):
        queries = [
            "zrób zrzut ekranu",
            "screenshot",
            "screen capture",
            "pobierz zrzut /tmp/screen.png",
            "take screenshot screen.png",
        ]
        for q in queries:
            cmd = self.parser.parse(q)
            self.assertIsNotNone(cmd, f"Failed to parse: {q}")
            self.assertEqual(cmd.action, "kvm-capture")
            self.assertEqual(cmd.canonical_name, "kvm.capture")

    def test_kvm_windows_intent(self):
        for q in ["pokaż okna", "jakie okna", "list windows", "show windows"]:
            cmd = self.parser.parse(q)
            self.assertIsNotNone(cmd, f"Failed: {q}")
            self.assertEqual(cmd.action, "kvm-windows")
            self.assertEqual(cmd.canonical_name, "kvm.windows")

    def test_kvm_click_intent(self):
        cmd = self.parser.parse("kliknij w 500 300")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.action, "kvm-click")
        self.assertEqual(cmd.args, ["500", "300"])

        cmd_en = self.parser.parse("click at 120, 450")
        self.assertIsNotNone(cmd_en)
        self.assertEqual(cmd_en.action, "kvm-click")
        self.assertEqual(cmd_en.args, ["120", "450"])

    def test_kvm_type_and_key_intents(self):
        cmd_type = self.parser.parse("wpisz 'ls -la'")
        self.assertIsNotNone(cmd_type)
        self.assertEqual(cmd_type.action, "kvm-type")
        self.assertEqual(cmd_type.args, ["ls -la"])

        cmd_key = self.parser.parse("naciśnij Return")
        self.assertIsNotNone(cmd_key)
        self.assertEqual(cmd_key.action, "kvm-key")
        self.assertEqual(cmd_key.args, ["Return"])

    def test_autopilot_intent(self):
        for q in ["zatwierdź dialogi", "auto-approve", "autopilot"]:
            cmd = self.parser.parse(q)
            self.assertIsNotNone(cmd)
            self.assertEqual(cmd.action, "autopilot")

    def test_terminal_intent(self):
        for q in ["otwórz terminal", "terminal", "konsola", "bash"]:
            cmd = self.parser.parse(q)
            self.assertIsNotNone(cmd)
            self.assertEqual(cmd.action, "terminal")

    def test_agent_prompt_intent(self):
        cmd = self.parser.parse("zapytaj jak działa docker")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.action, "prompt")
        self.assertEqual(cmd.args, ["jak działa docker"])

    def test_fallback_unbounded_prompt(self):
        cmd = parse_nl_to_dsl("jak skonfigurować routing sieciowy w linuxie?")
        self.assertEqual(cmd.action, "prompt")
        self.assertIn("routing", cmd.args[0])


class TestPremoteMCPServer(unittest.TestCase):
    def test_tools_definitions_presence(self):
        tool_names = [t["name"] for t in TOOLS_DEFINITIONS]
        self.assertIn("premote_list_accounts", tool_names)
        self.assertIn("premote_quota", tool_names)
        self.assertIn("premote_prompt", tool_names)
        self.assertIn("premote_kvm", tool_names)
        self.assertIn("premote_execute_nl", tool_names)

    @patch("premote.mcp_server.list_active_accounts", return_value=["prototypowanie", "dev"])
    def test_handle_list_accounts(self, mock_list):
        res = handle_tool_call("premote_list_accounts", {})
        self.assertEqual(res["count"], 2)
        self.assertIn("prototypowanie", res["accounts"])

    @patch("premote.mcp_server.ContainerClient")
    def test_handle_quota(self, mock_container_cls):
        mock_container = MagicMock()
        mock_container.is_running.return_value = True
        mock_container_cls.return_value = mock_container

        with patch("premote.mcp_server.AntigravityClient") as mock_agy_cls:
            mock_agy = MagicMock()
            mock_report = MagicMock()
            mock_report.to_dict.return_value = {"groups": []}
            mock_report.raw_text = "All quotas OK"
            mock_agy.get_quota.return_value = mock_report
            mock_agy_cls.return_value = mock_agy

            res = handle_tool_call("premote_quota", {"account": "prototypowanie"})
            self.assertEqual(res["account"], "prototypowanie")
            self.assertEqual(res["raw_text"], "All quotas OK")

    @patch("premote.mcp_server.ContainerClient")
    def test_handle_execute_nl_quota(self, mock_container_cls):
        mock_container = MagicMock()
        mock_container.is_running.return_value = True
        mock_container_cls.return_value = mock_container

        with patch("premote.mcp_server.AntigravityClient") as mock_agy_cls:
            mock_agy = MagicMock()
            mock_report = MagicMock()
            mock_report.to_dict.return_value = {"groups": []}
            mock_agy.get_quota.return_value = mock_report
            mock_agy_cls.return_value = mock_agy

            res = handle_tool_call("premote_execute_nl", {"account": "prototypowanie", "instruction": "sprawdź ile mam limitu"})
            self.assertTrue(res["success"])
            self.assertEqual(res["command"], "account.quota")
            self.assertEqual(res["data"]["dsl_action"], "quota")
            self.assertEqual(res["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
