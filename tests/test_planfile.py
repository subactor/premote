import tempfile
import unittest
from pathlib import Path
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

class TestPlanfile(unittest.TestCase):
    def test_load_planfile_and_list_tasks(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            tmp_path = f.name
        
        try:
            data = load_planfile(tmp_path)
            tasks = list_planfile_tasks(data)
            self.assertEqual(len(tasks), 1)
            t = tasks[0]
            self.assertEqual(t["sprint_id"], "sprint-1")
            self.assertEqual(t["id"], "ticket-101")
            self.assertEqual(t["name"], "Add auth")
            self.assertEqual(t["priority"], "high")
            self.assertEqual(t["files"], ["src/auth.py"])

            prompt = format_task_prompt(t)
            self.assertIn("ticket-101", prompt)
            self.assertIn("Add auth", prompt)
            self.assertIn("src/auth.py", prompt)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
