"""
Model Context Protocol (MCP) server for premote.
Provides universal tool parity for AI coding agents to control containers, quotas, and KVM.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from premote import __version__
from premote.agy import AntigravityClient
from premote.client import ContainerClient, list_active_accounts
from premote.kvm import KVMController
from premote.nl_dsl import parse_nl_to_dsl


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    account = arguments.get("account", "prototypowanie")

    if name == "premote_list_accounts":
        accs = list_active_accounts()
        return {"accounts": accs, "count": len(accs)}

    container = ContainerClient(account)
    if not container.is_running():
        return {"error": f"Kontener dla konta '{account}' nie jest uruchomiony.", "account": account}

    if name == "premote_quota":
        agy = AntigravityClient(container)
        report = agy.get_quota()
        return {
            "account": account,
            "quota": report.to_dict(),
            "raw_text": report.raw_text,
        }

    if name == "premote_prompt":
        prompt_text = arguments.get("prompt", "")
        if not prompt_text:
            return {"error": "Parametr 'prompt' jest wymagany."}
        agy = AntigravityClient(container)
        resp = agy.run_prompt_json(prompt_text)
        return {
            "account": account,
            "prompt": prompt_text,
            "response": resp.to_dict(),
        }

    if name == "premote_kvm":
        action = arguments.get("action", "windows")
        kvm = KVMController(container)
        if action == "windows":
            wins = kvm.list_windows()
            return {"account": account, "windows": [w.to_dict() for w in wins]}
        elif action == "click":
            x = int(arguments.get("x", 100))
            y = int(arguments.get("y", 100))
            btn = int(arguments.get("button", 1))
            res = kvm.click(x, y, button=btn)
            return {"account": account, "action": "click", "x": x, "y": y, "success": res.returncode == 0}
        elif action == "type":
            text = arguments.get("text", "")
            res = kvm.type_text(text)
            return {"account": account, "action": "type", "text": text, "success": res.returncode == 0}
        elif action == "key":
            key = arguments.get("key", "Return")
            res = kvm.key_combo(key)
            return {"account": account, "action": "key", "key": key, "success": res.returncode == 0}
        elif action == "focus":
            pattern = arguments.get("pattern", "")
            res = kvm.focus_window(pattern)
            return {"account": account, "action": "focus", "pattern": pattern, "success": res.returncode == 0}
        elif action in {"capture", "screenshot"}:
            out_path = arguments.get("output_path", "/tmp/premote_screen.png")
            png_bytes = kvm.capture_screenshot()
            with open(out_path, "wb") as f:
                f.write(png_bytes)
            return {"account": account, "action": "capture", "saved_to": out_path, "size_bytes": len(png_bytes)}
        else:
            return {"error": f"Nieznana akcja KVM: {action}"}

    if name == "premote_execute_nl":
        instruction = arguments.get("instruction", "")
        if not instruction:
            return {"error": "Parametr 'instruction' jest wymagany."}
        start_time = time.time()
        dsl_cmd = parse_nl_to_dsl(instruction, account=account)
        elapsed = (time.time() - start_time) * 1000

        # Wykonaj rozpoznaną akcję
        action = dsl_cmd.action
        args = dsl_cmd.args
        result_data: dict[str, Any] = {
            "dsl_action": action,
            "dsl_args": args,
            "confidence": dsl_cmd.confidence,
            "source": dsl_cmd.source,
        }

        if action == "quota":
            agy = AntigravityClient(container)
            report = agy.get_quota()
            result_data["quota"] = report.to_dict()
        elif action == "prompt":
            agy = AntigravityClient(container)
            p_text = " ".join(args)
            resp = agy.run_prompt_json(p_text)
            result_data["response"] = resp.to_dict()
        elif action == "kvm-windows":
            kvm = KVMController(container)
            wins = kvm.list_windows()
            result_data["windows"] = [w.to_dict() for w in wins]
        elif action == "kvm-capture":
            kvm = KVMController(container)
            out_p = args[0] if args else "/tmp/premote_capture.png"
            b = kvm.capture_screenshot()
            with open(out_p, "wb") as f:
                f.write(b)
            result_data["saved_to"] = out_p
        elif action == "kvm-click" and len(args) >= 2:
            kvm = KVMController(container)
            kvm.click(int(args[0]), int(args[1]))
            result_data["clicked"] = [int(args[0]), int(args[1])]
        elif action == "kvm-type" and args:
            kvm = KVMController(container)
            kvm.type_text(" ".join(args))
            result_data["typed"] = " ".join(args)
        elif action == "kvm-key" and args:
            kvm = KVMController(container)
            kvm.key_combo(args[0])
            result_data["key"] = args[0]
        else:
            result_data["raw_action"] = action
            result_data["raw_args"] = args

        return {
            "success": True,
            "command": dsl_cmd.canonical_name,
            "status": "COMPLETED",
            "data": result_data,
            "errors": [],
            "meta": {
                "executionTimeMs": round(elapsed, 2),
                "instruction": instruction,
            }
        }

    return {"error": f"Nieobsługiwane narzędzie: {name}"}


TOOLS_DEFINITIONS = [
    {
        "name": "premote_list_accounts",
        "description": "Zwraca listę wszystkich aktywnych kontenerów i środowisk noVNC w klastrze.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "premote_quota",
        "description": "Odpytuje środowisko o aktualne kwoty modeli LLM (Gemini, Claude, GPT).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Identyfikator konta (np. prototypowanie)"},
            },
            "required": ["account"],
        },
    },
    {
        "name": "premote_prompt",
        "description": "Wykonuje prompt w Google Antigravity (agy) w wybranym środowisku kontenera.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Identyfikator konta (np. prototypowanie)"},
                "prompt": {"type": "string", "description": "Treść promptu dla asystenta agy"},
            },
            "required": ["account", "prompt"],
        },
    },
    {
        "name": "premote_kvm",
        "description": "Wykonuje akcję graficzną KVM (click, type, key, focus, windows, capture) na pulpicie noVNC.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Identyfikator konta"},
                "action": {"type": "string", "enum": ["windows", "click", "type", "key", "focus", "capture"]},
                "x": {"type": "integer", "description": "Współrzędna X dla kliknięcia"},
                "y": {"type": "integer", "description": "Współrzędna Y dla kliknięcia"},
                "text": {"type": "string", "description": "Tekst do wpisania"},
                "key": {"type": "string", "description": "Nazwa klawisza (np. Return, Tab)"},
                "pattern": {"type": "string", "description": "Nazwa okna do aktywacji"},
                "output_path": {"type": "string", "description": "Ścieżka do zapisu zrzutu ekranu"},
            },
            "required": ["account", "action"],
        },
    },
    {
        "name": "premote_execute_nl",
        "description": "Wykonuje instrukcję w języku naturalnym (PL/EN) zgodnie ze standardem wellmanifest/nl-dsl-llm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Identyfikator konta (np. prototypowanie)"},
                "instruction": {"type": "string", "description": "Polecenie w języku naturalnym (np. 'sprawdź limity w claude', 'zrób zrzut ekranu')"},
            },
            "required": ["account", "instruction"],
        },
    },
]


def run_stdio_server():
    """Uruchamia hermetyczny serwer JSON-RPC / MCP przez standardowe wejście/wyjście (stdio)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "premote-mcp",
                        "version": __version__,
                    },
                    "capabilities": {
                        "tools": {},
                    },
                },
            }
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOLS_DEFINITIONS,
                },
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            call_res = handle_tool_call(tool_name, tool_args)
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(call_res, ensure_ascii=False, indent=2),
                        }
                    ]
                },
            }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main():
    run_stdio_server()


if __name__ == "__main__":
    main()
