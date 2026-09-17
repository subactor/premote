from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_planfile(path: str | Path = "planfile.yaml") -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku planfile: {file_path}")
    
    # Try yaml parsing, fallback to basic parser if yaml not installed
    try:
        import yaml
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback simple reader or json
        raise RuntimeError("Wymagany moduł PyYAML do odczytu planfile.yaml")


def list_planfile_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = []
    for sprint in plan.get("sprints", []):
        sprint_id = sprint.get("id", "sprint")
        for t in sprint.get("task_patterns", []):
            tasks.append({
                "sprint_id": sprint_id,
                "id": t.get("id", ""),
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "files": t.get("files", []),
                "priority": t.get("priority", "medium"),
                "rule_id": t.get("rule_id", ""),
                "count": t.get("count", 1),
            })
    return tasks


def format_task_prompt(task: dict[str, Any]) -> str:
    files_str = ", ".join(task.get("files", []))
    prompt = (
        f"Zadanie z planfile ({task.get('id')}): {task.get('name')}\n"
        f"Opis: {task.get('description')}\n"
        f"Pliki do modyfikacji: {files_str}\n"
        f"Reguła: {task.get('rule_id')} (wystąpienia: {task.get('count')})\n\n"
        f"Instrukcje wykonawcze:\n"
        f"1. Przeanalizuj wskazane pliki i zidentyfikuj problematyczne miejsca.\n"
        f"2. Zastosuj poprawki zachowując pełną zgodność wsteczną i funkcjonalność.\n"
        f"3. Uruchom testy jednostkowe i upewnij się, że nie ma regresji.\n"
        f"4. Zwróć podsumowanie zmian."
    )
    return prompt
