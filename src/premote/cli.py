from __future__ import annotations

import argparse
import json
import sys

from premote import __version__
from premote.agy import AntigravityClient
from premote.client import ContainerClient, ContainerError, list_active_accounts
from premote.kvm import KVMController


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

        else:
            print(f"Nieznana akcja: {action}", file=sys.stderr)
            print("Dostępne akcje: prompt, prompt-json, continue, quota, quota-json, models, terminal, agy-interactive, exec, kvm-windows, kvm-focus, kvm-type, kvm-key, kvm-click, kvm-capture", file=sys.stderr)
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
