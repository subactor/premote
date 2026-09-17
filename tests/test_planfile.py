import tempfile
from pathlib import Path
import pytest
from premote.planfile import load_planfile, list_planfile_tasks, format_task_prompt

SAMPLE_YAML = """
project: test-project
sprints:
  - id: sprint-1
    name: Core features
    task_patterns:
      - id: ticket-101
        name: Add auth
        description: Implement JWT authentication
        files:
          - src/auth.py
        priority: high
        rule_id: security
        count: 1
"""

def test_load_planfile_and_list_tasks():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        tmp_path = f.name
    
    try:
        data = load_planfile(tmp_path)
        tasks = list_planfile_tasks(data)
        assert len(tasks) == 1
        t = tasks[0]
        assert t["sprint_id"] == "sprint-1"
        assert t["id"] == "ticket-101"
        assert t["name"] == "Add auth"
        assert t["priority"] == "high"
        assert t["files"] == ["src/auth.py"]

        prompt = format_task_prompt(t)
        assert "ticket-101" in prompt
        assert "Add auth" in prompt
        assert "src/auth.py" in prompt
    finally:
        Path(tmp_path).unlink(missing_ok=True)
