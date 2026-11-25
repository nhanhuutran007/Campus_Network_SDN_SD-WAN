"""Mọi file .py của bot phải biên dịch được — selftest không import telegram_bot.py, nên lỗi cú pháp
ở đó (30/10: f-string bị xuống dòng thật) làm bot chết lặp mà selftest vẫn 11/11."""
import ast
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SKIP = {"dist", "backups", "__pycache__", ".venv", "Mau"}


class TestSyntax(unittest.TestCase):
    def test_all_python_files_parse(self):
        bad = []
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in SKIP]
            for f in files:
                if f.endswith(".py"):
                    p = os.path.join(d, f)
                    try:
                        ast.parse(open(p, encoding="utf-8").read(), p)
                    except SyntaxError as e:
                        bad.append(f"{os.path.relpath(p, ROOT)}:{e.lineno} {e.msg}")
        self.assertEqual(bad, [])

    def test_llm_model_builds_without_network(self):
        os.environ.setdefault("API_KEY", "test")
        import main
        self.assertIn("/v1", str(main.model.openai_api_base))


if __name__ == "__main__":
    unittest.main()
