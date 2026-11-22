import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml"


class WorkflowTest(unittest.TestCase):
    def test_config_passed_as_secret(self):
        # Variable(vars.*) 은 공개 실행 로그의 env 블록에 평문으로 찍힌다. Secret 만 가려진다.
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("JOBCATCH_CONFIG: ${{ secrets.JOBCATCH_CONFIG }}", text)
        self.assertNotIn("vars.", text)


if __name__ == "__main__":
    unittest.main()
