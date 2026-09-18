# premote

Remote CLI & KVM controller for Google Antigravity (`agy`) and desktop applications in isolated Docker noVNC containers.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://python.org)


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.1.2-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.03-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-1.0h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.0271 (1 commits)
- 👤 **Human dev:** ~$100 (1.0h @ $100/h, 30min dedup)

Generated on 2026-09-17 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---



## Overview

`premote` allows you to control, monitor, and automate AI coding agents (specifically **Google Antigravity CLI `agy`**) and desktop GUI applications running inside Docker noVNC containers directly from your host PC terminal.

It provides two operation layers:
1. **Direct Headless / CLI Layer**: Fast, non-interactive execution of prompts with auto-approval of permissions (`--dangerously-skip-permissions`), JSON output, session continuation, and live quota queries (`/quota`).
2. **KVM / Desktop GUI Layer**: Live simulation of mouse and keyboard events on the X11 desktop displayed in noVNC (`http://127.0.0.1:<port>/vnc.html`), including window focus, keystrokes, mouse clicks, and screen capture.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/subactor/premote.git
cd premote

# Install locally in editable mode
pip install -e .
```

---

## Usage

### Syntax
```bash
premote <account> <command> [arguments...]
```

### CLI / Agent Commands

#### 1. Check Model Quotas & Limits
View live remaining quota percentages and reset timers (Gemini, Claude, GPT):
```bash
premote prototypowanie quota
```
*Output:*
```text
GRUPA / BUCKET                 POZOSTAŁO    RESET                   
--------------------------------------------------------------------
[Gemini Models]
  Weekly Limit Remaining       98%          2026-09-24T10:15:12Z    
  Five Hour Limit Remaining    90%          2026-09-17T15:15:12Z    

[Claude and GPT models]
  Weekly Limit Remaining       100%         2026-09-24T13:27:31Z    
  Five Hour Limit Remaining    100%         2026-09-17T18:27:31Z    
```

For automation / JSON parsing:
```bash
premote prototypowanie quota-json
```

#### 2. Execute Prompt with Auto-Approval
Run a prompt with `--dangerously-skip-permissions` so it never blocks waiting for confirmation:
```bash
premote prototypowanie prompt "Napisz oneliner w bashu sprawdzający zużycie dysku"
```

Structured JSON response with token usage and conversation ID:
```bash
premote prototypowanie prompt-json "Podaj 3 zalety Dockera"
```

#### 3. Continue Previous Conversation
```bash
premote prototypowanie continue "Rozwiń drugi punkt"
```

#### 4. List Available AI Models
```bash
premote prototypowanie models
```

#### 5. Interactive Terminal / TUI
```bash
# Interactive bash shell inside container
premote prototypowanie terminal

# Interactive agy TUI in your terminal
premote prototypowanie agy-interactive
```

---

### KVM / Desktop GUI Commands (noVNC)

#### 1. List Open Windows
```bash
premote prototypowanie kvm-windows
```

#### 2. Focus Window
```bash
premote prototypowanie kvm-focus "Terminal"
```

#### 3. Type Text into Active Window
```bash
premote prototypowanie kvm-type "echo 'Wpisane z PC' && agy models"
```

#### 4. Send Key Strokes (Navigation, Enter, Approvals)
```bash
# Press Enter
premote prototypowanie kvm-key Return

# Select option with Down arrow and Enter
premote prototypowanie kvm-key Down
premote prototypowanie kvm-key Return

# Approve with 'y'
premote prototypowanie kvm-key y
premote prototypowanie kvm-key Return
```

#### 5. Click at Coordinates (X, Y)
```bash
premote prototypowanie kvm-click 800 500
```

#### 6. Read Text from Screen (OCR)
Fast OCR extraction (under 4s) of terminal or any GUI window content:
```bash
# Read whole desktop
premote prototypowanie screen-text

# Read specific window by X11 window ID
premote prototypowanie screen-text 0x01600003
```

#### 7. Take Screenshot of noVNC Desktop
```bash
premote prototypowanie kvm-capture screen.png
```

---

### Unattended Execution & Permissions

To run fully autonomous agents without any user prompts for shell execution, package installation, or code edits:

```bash
# Automatically configures ~/.gemini/antigravity-cli/settings.json permissions
# and creates aliases (agy, gemini -y, claude, aider) for unattended operation:
premote prototypowanie auto-approve-all
```

---

### Planfile / Long-Cycle Task Automation

Execute structured multi-sprint task plans (`planfile.yaml`) autonomously:

```bash
# 1. List tasks in planfile.yaml
premote prototypowanie planfile-tasks [path/to/planfile.yaml]

# 2. View generated agent prompt for a specific task
premote prototypowanie planfile-prompt ticket-101 [path/to/planfile.yaml]

# 3. Execute specific task with Antigravity
premote prototypowanie planfile-run ticket-101 [path/to/planfile.yaml]

# 4. Automatically run the next task
premote prototypowanie planfile-next [path/to/planfile.yaml]
```

---

### Autopilot: Automatic Dialog & Consent Approval

The autopilot watches terminal screens via OCR and automatically approves dialogs, `(y/n)` prompts, permission requests, and consent screens:

```bash
# Start autopilot with default settings (5s poll, unlimited, LLM dialog decider)
premote prototypowanie autopilot

# Custom interval and max iterations
premote prototypowanie autopilot --interval 3 --max-iterations 100

# Legacy offline mode using built-in regex rules instead of the LLM decider
premote prototypowanie autopilot --decider regex

# Quiet mode (no verbose output)
premote prototypowanie autopilot --quiet
```

By default (`--decider llm`) each OCR snapshot is classified by a lightweight LLM/SLM
dialog-state decider that answers in a strict **NL -> Action DSL** (`state`, `decision`,
`action`, `value`, `reason`). Parsing is fail-closed: transport failures, malformed
answers or unsafe values never inject keystrokes. The decider uses any
OpenAI-compatible endpoint configured via environment variables:

```bash
PREMOTE_LLM_BASE_URL=https://openrouter.ai/api/v1
PREMOTE_LLM_MODEL=openrouter/qwen/qwen3-coder-next
PREMOTE_LLM_API_KEY=...            # falls back to OPENROUTER_API_KEY
```

The legacy regex rule set (agy, gemini, claude, aider, npm, pip prompts) remains
available as an explicit offline fallback via `--decider regex`.

#### How it works:
1. Every `--interval` seconds, autopilot runs OCR on the noVNC screen
2. The dialog decider classifies the screen into a canonical dialog state and returns one Action DSL decision
3. Valid approvals are injected after a per-state cooldown elapses
4. Stops on `Ctrl+C` or after `--max-iterations` cycles

---

### Tmux Session Management

Run agents in detached tmux sessions inside containers for long-running, resilient execution:

```bash
# Start an agent in a detached tmux session
premote prototypowanie tmux-run 'agy --dangerously-skip-permissions -p "Build the project"'

# Check session status and see recent output
premote prototypowanie session-status

# Attach to the running session interactively
premote prototypowanie exec tmux attach -t premote-auto
```

---

## Python API

You can also use `premote` directly inside Python applications:

```python
from premote import ContainerClient, AntigravityClient, KVMController, create_autopilot

# Connect to container
container = ContainerClient("prototypowanie")
agy = AntigravityClient(container)
kvm = KVMController(container)

# 1. Ask Antigravity a question
result = agy.prompt("Napisz prostą funkcję hello world w Pythonie")
print("Response:", result.response)

# 2. Check model limits
quota = agy.quota()
for group in quota.groups:
    print(f"Group: {group.name}")
    for bucket in group.buckets:
        print(f"  {bucket.name}: {bucket.remaining_percent}% (Resets: {bucket.reset_time})")

# 3. Simulate GUI typing in noVNC
kvm.focus("Terminal")
kvm.type_text("ls -la")
kvm.key("Return")

# 4. Start autopilot programmatically
session = create_autopilot("prototypowanie", poll_interval=5.0)
session.run()  # Blocks until Ctrl+C or max_iterations
```

---

## License

Licensed under Apache-2.0.

