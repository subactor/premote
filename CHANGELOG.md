# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-09-17

### Added
- **Autopilot module**: OCR-based screen watcher that automatically approves dialogs, (y/n) prompts, permission requests, and consent screens using pattern-matched xdotool keystroke injection
- 11 built-in rules covering agy, gemini, claude, aider, npm/pip confirmation prompts
- `premote <acc> autopilot` command with `--interval`, `--max-iterations`, `--quiet` options
- `premote <acc> tmux-run '<command>'` for running agents in detached tmux sessions
- `premote <acc> session-status [name]` for monitoring tmux session output
- 8 new unit tests for autopilot rule matching and cooldown logic
- Python API: `AutopilotRule`, `AutopilotSession`, `create_autopilot`

### Fixed
- VERSION file was out of sync with pyproject.toml (was 0.1.1, now 0.1.3)

## [0.1.2] - 2026-09-17

### Added
- `planfile-tasks`, `planfile-prompt`, `planfile-run`, `planfile-next` commands for structured task automation
- `auto-approve-all` command for zero-prompt agent configuration
- `screen-text` / `ocr` command for OCR text extraction from noVNC screens
- Planfile YAML parser with sprint/task pattern support

## [0.1.1] - 2026-09-17

### Docs
- Update README.md

### Other
- Update .env.example

