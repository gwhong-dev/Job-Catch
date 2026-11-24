import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml"


class WorkflowTest(unittest.TestCase):
    def test_config_passed_as_secret(self):
        # Variable(vars.*) 은 공개 실행 로그의 env 블록에 평문으로 찍힌다. Secret 만 가려진다.
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("JOBCATCH_CONFIG: ${{ secrets.JOBCATCH_CONFIG }}", text)
        self.assertNotIn("vars.", text)

    def test_gemini_key_passed_as_secret(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}", text)

    def test_force_input_passed_as_flag(self):
        # 손 실행에서만 다시 보내기: 예약 실행에는 inputs 가 없어 빈 문자열
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("force:", text)
        self.assertIn("type: boolean", text)
        self.assertIn("python run.py ${{ inputs.force && '--force' || '' }}", text)

    def test_sent_mark_cached_separately(self):
        # seen.json 캐시 경로를 바꾸면 캐시 버전이 달라져 보낸 기록을 잃는다: 따로 둔다
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("path: data/seen.json", text)
        self.assertEqual(text.count("path: data/sent.json"), 2)  # 불러오기 · 저장
        self.assertIn("key: sent-${{ github.run_id }}", text)
        self.assertIn("restore-keys: sent-", text)


if __name__ == "__main__":
    unittest.main()
