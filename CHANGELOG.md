# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Autopilot dialog decider (STARTER-131)**: default decision path is now a lightweight
  LLM/SLM dialog-state classifier (`premote.dialog_decider.DialogDecider`) answering in a
  strict fail-closed NL -> Action DSL (`state`/`decision`/`action`/`value`/`reason`),
  replacing the 11 rigid `DEFAULT_RULES` regex heuristics on the default path
- `premote <acc> autopilot --decider llm|regex` selects the decision mode (default `llm`);
  the legacy regex rule set stays available as an explicit offline fallback
- Decider transport is any OpenAI-compatible endpoint (`PREMOTE_LLM_BASE_URL`,
  `PREMOTE_LLM_MODEL`, `PREMOTE_LLM_API_KEY` / `OPENROUTER_API_KEY`)

### Added
- `premote.dialog_decider` module: Action DSL schema, fail-closed validator, JSON
  extraction tolerant of fenced model answers, per-state cooldown in `AutopilotSession`
- 15 unit tests for decider validation, fail-closed behaviour and session integration

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

