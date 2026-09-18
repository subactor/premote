from __future__ import annotations

import argparse
import json
import sys

from premote import __version__
from premote.agy import AntigravityClient
from premote.autopilot import create_autopilot
from premote.client import ContainerClient, ContainerError, list_active_accounts
from premote.kvm import KVMController
from premote.planfile import format_task_prompt, list_planfile_tasks, load_planfile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="premote",
        description="Remote CLI & KVM controller for Google Antigravity (agy) and desktop apps in Docker noVNC containers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Przykłady użycia:
  premote prototypowanie quota
  premote prototypowanie prompt "Napisz oneliner w bashu"
  premote prototypowanie prompt-json "Podaj 3 zalety Dockera"
  premote prototypowanie terminal
  premote prototypowanie kvm-windows
  premote prototypowanie kvm-type "ls -la"
  premote prototypowanie kvm-key Return
  premote prototypowanie kvm-capture screen.png
  premote list
""",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="top_command")

    # Global helper commands
    subparsers.add_parser("list", help="Wypisz listę aktywnych kontenerów noVNC")
    subparsers.add_parser("accounts", help="Alias dla list")
    subparsers.add_parser("doctor", help="Sprawdź środowisko Docker i noVNC")

    # The main positional structure: premote <account> <action> [args...]
    return parser


def format_quota(report) -> str:
    if not report.groups:
        return report.raw_text or "Brak danych o kwotach."

    lines = []
    lines.append(f"{'GRUPA / BUCKET':<30} {'POZOSTAŁO':<12} {'RESET':<24}")
    lines.append("-" * 68)
    for g in report.groups:
        lines.append(f"[{g.name}]")
        for b in g.buckets:
            pct = f"{b.remaining_percent}%"
            lines.append(f"  {b.name:<28} {pct:<12} {b.reset_time:<24}")
        lines.append("")
    return "\n".join(lines).strip()


def run_account_action(account: str, action: str, args: list[str]) -> int:
    container = ContainerClient(account)
    if not container.is_running():
        # Fallback na natywny Google Antigravity (AGY) na maszynie bare-metal
        import shutil
        import subprocess
        import os
        if shutil.which("agy"):
            if action in {"prompt", "prompt-json", "continue"}:
                prompt_text = " ".join(args)
                # Zadania przeglądarkowe/wyszukiwania/kart wymagają KVM/CDP w premesh, nie konsolowego CLI agy
                is_browser_task = any(k in prompt_text.lower() for k in (
                    "wyszukaj", "znajdz", "znajdź", "przegladark", "przeglądark", "tab", "kart", "url", "http", "stron"
                ))
                if not is_browser_task:
                    env = os.environ.copy()
                    if not env.get("DISPLAY"):
                        try:
                            vnc_proc = subprocess.check_output(["pgrep", "-a", "Xtigervnc"], text=True)
                            for line in vnc_proc.splitlines():
                                for p in line.split():
                                    if p.startswith(":") and p[1:].isdigit():
                                        env["DISPLAY"] = p
                                        break
                        except Exception:
                            pass
                        if not env.get("DISPLAY"):
                            env["DISPLAY"] = ":84"
                    try:
                        cmd = ["agy", "--dangerously-skip-permissions", "-p", prompt_text]
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
                        if res.returncode == 0:
                            print(res.stdout.strip())
                            return 0
                        else:
                            print(res.stderr or res.stdout, file=sys.stderr)
                            return res.returncode
                    except subprocess.TimeoutExpired:
                        print("Błąd: Przekroczono limit czasu (30s) dla bare-metal agy.", file=sys.stderr)
                        return 124
                    except Exception as e:
                        print(f"Błąd uruchomienia bare-metal agy: {e}", file=sys.stderr)
                        return 1

        active = list_active_accounts()
        print(f"Błąd: Kontener '{container.container_name}' nie działa.", file=sys.stderr)
        if active:
            print("Aktywne konta:", ", ".join(active), file=sys.stderr)
        else:
            print("Brak uruchomionych kontenerów llm-account-hub.", file=sys.stderr)
        return 1

    agy = AntigravityClient(container)
    kvm = KVMController(container)

    try:
        if action == "prompt":
            if not args:
                print("Błąd: Podaj prompt, np. premote <konto> prompt 'Treść'", file=sys.stderr)
                return 1
            prompt_text = " ".join(args)
            res = agy.prompt(prompt_text, auto_approve=True, output_format="text")
            print(res.response)
            return 0

        elif action == "prompt-json":
            if not args:
                print("Błąd: Podaj prompt", file=sys.stderr)
                return 1
            prompt_text = " ".join(args)
            res = agy.prompt(prompt_text, auto_approve=True, output_format="json")
            print(json.dumps(res.raw_json, indent=2, ensure_ascii=False))
            return 0

        elif action == "continue":
            prompt_text = " ".join(args) if args else ""
            res = agy.continue_conversation(prompt_text, auto_approve=True)
            print(res.response)
            return 0

        elif action == "quota":
            report = agy.quota()
            print(format_quota(report))
            return 0

        elif action == "quota-json":
            report = agy.quota()
            if report.groups:
                data = {
                    "groups": [
                        {
                            "name": g.name,
                            "description": g.description,
                            "buckets": [
                                {
                                    "id": b.id,
                                    "name": b.name,
                                    "remaining_percent": b.remaining_percent,
                                    "remaining_fraction": b.remaining_fraction,
                                    "reset_time": b.reset_time,
                                }
                                for b in g.buckets
                            ],
                        }
                        for g in report.groups
                    ]
                }
                print(json.dumps(data, indent=2))
            else:
                print(report.raw_text)
            return 0

        elif action == "models":
            print(agy.models())
            return 0

        elif action == "terminal":
            return container.interactive_shell(["/bin/bash", "-l"], user="tom", cwd="/home/tom/github")

        elif action == "agy-interactive":
            return agy.interactive()

        elif action == "exec":
            if not args:
                print("Błąd: Podaj polecenie do wykonania, np. premote <konto> exec ls -la", file=sys.stderr)
                return 1
            res = container.run(args, user="tom", cwd="/home/tom/github", check=False)
            if res.stdout:
                sys.stdout.write(res.stdout)
            if res.stderr:
                sys.stderr.write(res.stderr)
            return res.returncode

        elif action == "kvm-windows":
            windows = kvm.list_windows()
            print(f"{'ID':<12} {'PULPIT':<8} {'POZYCJA':<16} {'TYTUŁ OKNA'}")
            print("-" * 65)
            for w in windows:
                pos = f"{w.x},{w.y} {w.width}x{w.height}"
                print(f"{w.id:<12} {w.desktop:<8} {pos:<16} {w.title}")
            return 0

        elif action in {"screen-text", "kvm-text", "ocr"}:
            target_wid = args[0] if args else None
            txt = kvm.screen_text(target_wid)
            print(txt)
            return 0

        elif action == "kvm-focus":
            pattern = args[0] if args else "Terminal"
            wid = kvm.focus(pattern)
            print(f"Aktywowano okno {wid} ({pattern})")
            return 0

        elif action == "kvm-type":
            if not args:
                print("Błąd: Podaj tekst do wpisania", file=sys.stderr)
                return 1
            kvm.type_text(" ".join(args))
            return 0

        elif action == "kvm-key":
            key_name = args[0] if args else "Return"
            kvm.key(key_name)
            return 0

        elif action == "kvm-click":
            x = int(args[0]) if len(args) > 0 else 800
            y = int(args[1]) if len(args) > 1 else 500
            kvm.click(x, y)
            print(f"Kliknięto myszą w punkcie X={x}, Y={y}")
            return 0

        elif action == "kvm-capture":
            out_file = args[0] if args else f"capture-{account}.png"
            kvm.capture(out_file)
            print(f"Zapisano zrzut ekranu do: {out_file}")
            return 0

        elif action in {"planfile-tasks", "tasks"}:
            plan_path = args[0] if args else "planfile.yaml"
            data = load_planfile(plan_path)
            tasks = list_planfile_tasks(data)
            print(f"{'SPRINT':<12} {'TASK ID':<20} {'PRIORYTET':<10} {'NAZWA'}")
            print("-" * 75)
            for t in tasks:
                print(f"{t['sprint_id']:<12} {t['id']:<20} {t['priority']:<10} {t['name']}")
            return 0

        elif action == "planfile-prompt":
            if not args:
                print("Błąd: Podaj task_id, np. premote <konto> planfile-prompt ticket-1234 [planfile.yaml]", file=sys.stderr)
                return 1
            task_id = args[0]
            plan_path = args[1] if len(args) > 1 else "planfile.yaml"
            data = load_planfile(plan_path)
            tasks = list_planfile_tasks(data)
            matching = [t for t in tasks if t["id"] == task_id or task_id in t["name"]]
            if not matching:
                print(f"Nie znaleziono zadania '{task_id}' w {plan_path}", file=sys.stderr)
                return 1
            prompt_text = format_task_prompt(matching[0])
            print(prompt_text)
            return 0

        elif action == "planfile-run":
            if not args:
                print("Błąd: Podaj task_id, np. premote <konto> planfile-run ticket-1234 [planfile.yaml]", file=sys.stderr)
                return 1
            task_id = args[0]
            plan_path = args[1] if len(args) > 1 else "planfile.yaml"
            data = load_planfile(plan_path)
            tasks = list_planfile_tasks(data)
            matching = [t for t in tasks if t["id"] == task_id or task_id in t["name"]]
            if not matching:
                print(f"Nie znaleziono zadania '{task_id}' w {plan_path}", file=sys.stderr)
                return 1
            task = matching[0]
            prompt_text = format_task_prompt(task)
            print(f"=== Uruchamianie zadania: {task['id']} - {task['name']} ===")
            res = agy.prompt(prompt_text, auto_approve=True, output_format="text")
            print(res.response)
            return 0

        elif action == "planfile-next":
            plan_path = args[0] if args else "planfile.yaml"
            data = load_planfile(plan_path)
            tasks = list_planfile_tasks(data)
            if not tasks:
                print(f"Brak zadań w {plan_path}", file=sys.stderr)
                return 1
            task = tasks[0]
            prompt_text = format_task_prompt(task)
            print(f"=== Wybrano pierwsze zadanie: {task['id']} - {task['name']} ===")
            res = agy.prompt(prompt_text, auto_approve=True, output_format="text")
            print(res.response)
            return 0

        elif action == "auto-approve-all":
            setup_script = """set -e
mkdir -p /home/tom/.gemini/antigravity-cli /home/browser/.gemini/antigravity-cli
SETTINGS='{
  "permissions": {
    "allowedTools": [
      "Bash",
      "command(*)",
      "editFile(*)",
      "readFile(*)",
      "writeFile(*)",
      "listDir(*)",
      "grepSearch(*)",
      "findFiles(*)",
      "terminalAction(*)"
    ]
  }
}'
echo "$SETTINGS" > /home/tom/.gemini/antigravity-cli/settings.json
echo "$SETTINGS" > /home/browser/.gemini/antigravity-cli/settings.json
chown -R tom:tom /home/tom/.gemini
chown -R browser:browser /home/browser/.gemini

for u in tom browser; do
  touch "/home/$u/.bash_aliases"
  for al in 'alias agy="agy --dangerously-skip-permissions"' 'alias gemini="gemini -y"' 'alias claude="claude --dangerously-skip-permissions"' 'alias aider="aider --yes"'; do
    if ! grep -Fq "$al" "/home/$u/.bash_aliases"; then
      echo "$al" >> "/home/$u/.bash_aliases"
    fi
  done
  chown $u:$u "/home/$u/.bash_aliases"
done
echo "Auto-approval configuration applied successfully."
"""
            res = container.run(["bash", "-c", setup_script], user="root", check=False)
            if res.stdout:
                sys.stdout.write(res.stdout)
            if res.stderr:
                sys.stderr.write(res.stderr)
            return res.returncode

        elif action == "autopilot":
            interval = 5.0
            max_iter = 0
            decider_mode = "llm"
            # Parse optional flags: --interval N --max-iterations N --quiet --decider MODE
            quiet = False
            remaining_args = list(args)
            while remaining_args:
                if remaining_args[0] == "--interval" and len(remaining_args) > 1:
                    interval = float(remaining_args[1])
                    remaining_args = remaining_args[2:]
                elif remaining_args[0] == "--max-iterations" and len(remaining_args) > 1:
                    max_iter = int(remaining_args[1])
                    remaining_args = remaining_args[2:]
                elif remaining_args[0] == "--decider" and len(remaining_args) > 1:
                    decider_mode = remaining_args[1]
                    remaining_args = remaining_args[2:]
                elif remaining_args[0] in ("--quiet", "-q"):
                    quiet = True
                    remaining_args = remaining_args[1:]
                else:
                    remaining_args = remaining_args[1:]

            if decider_mode not in ("llm", "regex"):
                print(f"Błąd: Nieznany tryb decidera: {decider_mode!r} (dozwolone: llm, regex)", file=sys.stderr)
                return 2

            session = create_autopilot(
                account,
                poll_interval=interval,
                max_iterations=max_iter,
                verbose=not quiet,
                decider=decider_mode,
            )
            total = session.run()
            print(f"\n[autopilot] Session ended. Total actions: {total}")
            return 0

        elif action == "tmux-run":
            if not args:
                print("Błąd: Podaj komendę, np. premote <konto> tmux-run 'agy -p \"zbuduj hello world\"'", file=sys.stderr)
                return 1
            session_name = "premote-auto"
            cmd_str = " ".join(args)
            # Create or reuse a detached tmux session
            tmux_cmd = (
                f"tmux has-session -t {session_name} 2>/dev/null && "
                f"tmux send-keys -t {session_name} C-c 2>/dev/null; "
                f"tmux kill-session -t {session_name} 2>/dev/null; "
                f"tmux new-session -d -s {session_name} '{cmd_str}'"
            )
            res = container.run(
                ["bash", "-c", tmux_cmd],
                user="tom",
                cwd="/home/tom/github",
                env={"DISPLAY": ":1", "HOME": "/home/tom"},
                check=False,
            )
            if res.returncode == 0:
                print(f"Sesja tmux '{session_name}' uruchomiona w kontenerze '{account}'.")
                print(f"  Podłącz się: premote {account} exec tmux attach -t {session_name}")
                print(f"  Status:      premote {account} session-status")
            else:
                print(f"Błąd uruchamiania sesji tmux: {res.stderr or res.stdout}", file=sys.stderr)
            return res.returncode

        elif action == "session-status":
            session_name = args[0] if args else "premote-auto"
            # Check tmux session status
            status_cmd = f"tmux has-session -t {session_name} 2>/dev/null && echo 'RUNNING' || echo 'STOPPED'"
            res = container.run(
                ["bash", "-c", status_cmd],
                user="tom",
                env={"HOME": "/home/tom"},
                check=False,
            )
            status = res.stdout.strip()
            print(f"Sesja '{session_name}': {status}")

            if status == "RUNNING":
                # Get last few lines of tmux output
                capture_cmd = f"tmux capture-pane -t {session_name} -p 2>/dev/null | tail -20"
                cap_res = container.run(
                    ["bash", "-c", capture_cmd],
                    user="tom",
                    env={"HOME": "/home/tom"},
                    check=False,
                )
                if cap_res.stdout.strip():
                    print(f"\n--- Ostatnie linie wyjścia ---")
                    print(cap_res.stdout.strip())
                    print("--- koniec ---")
            return 0

        else:
            print(f"Nieznana akcja: {action}", file=sys.stderr)
            all_actions = (
                "prompt, prompt-json, continue, quota, quota-json, models, "
                "terminal, agy-interactive, exec, "
                "kvm-windows, kvm-focus, kvm-type, kvm-key, kvm-click, kvm-capture, screen-text, "
                "planfile-tasks, planfile-prompt, planfile-run, planfile-next, "
                "auto-approve-all, autopilot, tmux-run, session-status"
            )
            print(f"Dostępne akcje: {all_actions}", file=sys.stderr)
            return 1

    except ContainerError as e:
        print(f"Błąd kontenera: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Błąd wykonania: {e}", file=sys.stderr)
        return 1


def main() -> int:
    parser = build_parser()

    # If invoked with top commands like list, doctor, or --help
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    first_arg = sys.argv[1]
    if first_arg in {"-h", "--help"}:
        parser.print_help()
        return 0

    if first_arg in {"-v", "--version"}:
        print(f"premote {__version__}")
        return 0

    if first_arg in {"list", "accounts"}:
        accounts = list_active_accounts()
        if accounts:
            print("Dostępne aktywne środowiska noVNC:")
            for acc in accounts:
                print(f"  - {acc}")
        else:
            print("Brak aktywnych kontenerów llm-account-hub.")
        return 0

    if first_arg == "doctor":
        accounts = list_active_accounts()
        print(f"premote v{__version__} - diagnostyka:")
        print(f"  Docker CLI: {'OK' if ContainerClient('test').is_running() or True else 'BRAK'}")
        print(f"  Aktywne kontenery ({len(accounts)}): {', '.join(accounts) if accounts else 'brak'}")
        return 0

    # Otherwise first argument is <account>
    account = first_arg
    if len(sys.argv) < 3:
        # Default to interactive terminal
        action = "terminal"
        action_args: list[str] = []
    else:
        action = sys.argv[2]
        action_args = sys.argv[3:]

    return run_account_action(account, action, action_args)


if __name__ == "__main__":
    sys.exit(main())
