"""Behavioral tests for missing evidence, stale bases, and portable layouts."""

from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


KIT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("happyhouse_check", KIT / "check.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="happyhouse test ")
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / "작업 공간").resolve()
        for folder in ("docs", "works", "validation", "results"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        for name, target in (("PLAN", "docs"), ("RESUME", "docs"), ("REVIEW", "docs"), ("PLAN_REVIEW", "validation")):
            shutil.copyfile(KIT / "templates" / f"{name}.md", self.root / target / f"{name}.md")

    def run_command(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = checker.main([*arguments, "--workspace", str(self.root)])
        return code, output.getvalue()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def replace(self, relative, old, new):
        path = self.root / relative
        content = path.read_text(encoding="utf-8")
        self.assertIn(old, content)
        path.write_text(content.replace(old, new), encoding="utf-8")

    def add_round(self, round_id="R1", product="app.py", complete=True):
        for name, folder in (("WORK", "works"), ("CHECK", "validation"), ("SUMMARY", "results")):
            self.write(f"{folder}/{round_id}/{name}.md", (KIT / "templates" / f"{name}.md").read_text().replace("{{ROUND}}", round_id))
        (self.root / f"validation/{round_id}/runs").mkdir()
        self.write(product, "example product content\n")
        self.write("problem.md", "빈 제목은 거부하고 할 일을 등록한다.\n")
        plan = self.root / "docs/PLAN.md"
        plan.write_text(plan.read_text().replace("|---|---|---|---|---|---|", "|---|---|---|---|---|---|\n"
            f"| {round_id} | 할 일 추가 | 보통 / 20분 | 02:00:00 | 검증 중 / 통과 | [WORK](../works/{round_id}/WORK.md) · [CHECK](../validation/{round_id}/CHECK.md) |", 1))
        work = f"works/{round_id}/WORK.md"
        for old, new in (
            ("- 목표 / 완료조건: 구체화 필요", "- 목표 / 완료조건: 할 일을 추가하면 목록에 한 개 표시"),
            ("- 계획 기준: 초안", "- 계획 기준: rev1"),
            ("- 유효한 승인 범위: 미승인", "- 유효한 승인 범위: 등록 기능 구현과 테스트"),
            ("- 승인 근거: 미작성", f"- 승인 근거: [사용자 요청](#{round_id.lower()}-01)"),
            ("- 변경 영향 / 추가 결정: 미작성", "- 변경 영향 / 추가 결정: 기존 범위 안 / 새 결정 없음"),
            ("- 갱신 시각 / 작성자:", "- 갱신 시각 / 작성자: 2026-10-31 / 주담당"),
            ("- 완료 / 미완료:", "- 완료 / 미완료: 구현 검증 완료 / 상태 반영 남음"),
            ("- 마지막 대화 번호 / 열린 질문:", f"- 마지막 대화 번호 / 열린 질문: {round_id}-01 / 없음"),
            ("- 다음 행동 / 현재 다른 세션이 쓰는 파일:", "- 다음 행동 / 현재 다른 세션이 쓰는 파일: 다음 라운드 / 없음"),
        ):
            self.replace(work, old, new)
        path = self.root / work
        content = path.read_text()
        content = content.replace("| 미정 |", "| 요구사항에 따라 등록 및 조회 |")
        content = content.replace("미정 — 사용하는 앞 라운드 / 이 출력을 사용할 뒤 라운드", "없음 / 다음 라운드 목록 사용")
        content = content.replace("| 구현 후 기록 |", f"| {product} |")
        content += f"\n### {round_id}-01\n테스트용 가상 승인: 등록 기능 구현과 테스트를 진행해줘.\n"
        path.write_text(content)
        check = f"validation/{round_id}/CHECK.md"
        self.replace(check, '{"inputs": [], "exclude": []}', json.dumps({"inputs": [product, "problem.md"], "exclude": []}))
        self.replace(check, "- 계획 기준: 초안", "- 계획 기준: rev1")
        if not complete:
            return
        code, output = self.run_command("capture", round_id)
        self.assertEqual(code, 0, output)
        self.write(f"validation/{round_id}/runs/test.txt", "input: 장보기; expected: 1; actual: 1; exit: 0\n")
        for old, new in (
            ("- 검증담당: 미작성", "- 검증담당: 검증 세션"),
            ("- 코드 기준 파일: 미지정", "- 코드 기준 파일: [기준](runs/basis-0001.json)"),
            ("- 마지막 실행 시각: 미작성", "- 마지막 실행 시각: " + datetime.now(timezone.utc).isoformat()),
            ("- 기대결과 작성: 미실시", "- 기대결과 작성: 구현 열람 전 작성"),
            ("- 현재 판정: 미실행", "- 현재 판정: 통과"),
            ("- 기록 점검: 미실시", "- 기록 점검: 충족"),
            ("|---|---|---|---|---|---|---|---|", "|---|---|---|---|---|---|---|---|\n| 01 | 정상 등록 | 장보기 | 한 개 | problem.md | 한 개 | 통과 | [로그](runs/test.txt) |"),
        ):
            self.replace(check, old, new)
        summary = self.root / f"results/{round_id}/SUMMARY.md"
        summary.write_text(summary.read_text().replace("미작성", "테스트용 결과 기록"))
        resume = self.root / "docs/RESUME.md"
        content = resume.read_text().replace("- 갱신 시각 / 작성자: 미작성", "- 갱신 시각 / 작성자: 2026-10-31 / 주담당")
        content = content.replace("- 상세 근거: 미작성", f"- 상세 근거: [작업](../works/{round_id}/WORK.md#{round_id.lower()}-01)")
        resume.write_text(content)

    def test_ready_before_problem_does_not_require_fake_completion(self):
        code, output = self.run_command("ready")
        self.assertEqual(code, 0, output)
        code, output = self.run_command("check", "--all")
        self.assertEqual(code, 1)
        self.assertIn("빈 계획", output)

    def test_ready_lists_missing_setup(self):
        (self.root / "docs/RESUME.md").unlink()
        code, output = self.run_command("ready")
        self.assertEqual(code, 1)
        self.assertIn("RESUME", output)

    def test_nonempty_plan_row_without_round_id_is_rejected(self):
        self.replace("docs/PLAN.md", "| | | | | | |", "| | 목표만 있고 라운드 없음 | | | | |")
        code, output = self.run_command("ready")
        self.assertEqual(code, 1)
        self.assertIn("라운드", output)

    def test_python_project_without_git_passes(self):
        self.add_round()
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 0, output)
        self.assertFalse((self.root / ".git").exists())

    def test_nested_javascript_layout(self):
        self.add_round(product="packages/web/src/main.js")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 0, output)

    def test_document_project(self):
        self.add_round(product="report/분석.md")
        code, output = self.run_command("check", "--all")
        self.assertEqual(code, 0, output)

    def test_placeholder_round_cannot_pass(self):
        self.add_round(complete=False)
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("통과", output)

    def test_empty_field_does_not_consume_next_line(self):
        self.add_round()
        self.replace("works/R1/WORK.md", "- 유효한 승인 범위: 등록 기능 구현과 테스트", "- 유효한 승인 범위:")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("유효한 승인 범위", output)

    def test_code_change_invalidates_result(self):
        self.add_round()
        self.write("app.py", "changed\n")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("기준 변경", output)

    def test_directory_addition_and_deletion_are_detected(self):
        self.add_round(product="src/app.js", complete=False)
        self.replace("validation/R1/CHECK.md", '"src/app.js"', '"src"')
        before = checker.basis(self.root, "R1")
        new = self.write("src/new.js", "new\n")
        self.assertNotEqual(before, checker.basis(self.root, "R1"))
        new.unlink()
        self.assertEqual(before, checker.basis(self.root, "R1"))
        (self.root / "src/app.js").unlink()
        with self.assertRaises(checker.Invalid):
            checker.basis(self.root, "R1")

    def test_requirement_or_contract_change_is_detected(self):
        self.add_round()
        self.replace("works/R1/WORK.md", "| 요구사항에 따라 등록 및 조회 |", "| 중복 입력도 허용 |")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("contract_sha256", output)

    def test_missing_or_empty_evidence_fails(self):
        self.add_round()
        evidence = self.root / "validation/R1/runs/test.txt"
        evidence.write_text("")
        self.assertEqual(self.run_command("check", "R1")[0], 1)
        evidence.unlink()
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("test.txt", output)

    def test_plan_and_check_status_must_agree(self):
        self.add_round()
        self.replace("validation/R1/CHECK.md", "- 현재 판정: 통과", "- 현재 판정: 미실행")
        self.assertEqual(self.run_command("check", "R1")[0], 1)

    def test_old_example_is_not_an_approval_anchor(self):
        self.add_round()
        self.replace("works/R1/WORK.md", "\n### R1-01\n테스트용 가상 승인", "\n### 실제기록없음\n테스트용 가상 승인")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("앵커", output)

    def test_capture_preserves_history(self):
        self.add_round()
        original = (self.root / "validation/R1/runs/basis-0001.json").read_bytes()
        code, output = self.run_command("capture", "R1")
        self.assertEqual(code, 0, output)
        self.assertTrue((self.root / "validation/R1/runs/basis-0002.json").is_file())
        self.assertEqual(original, (self.root / "validation/R1/runs/basis-0001.json").read_bytes())

    def test_recapture_does_not_revalidate_old_test(self):
        self.add_round()
        self.run_command("capture", "R1")
        self.replace("validation/R1/CHECK.md", "[기준](runs/basis-0001.json)", "[기준](runs/basis-0002.json)")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("과거 통과", output)

    def test_future_run_time_rejected(self):
        self.add_round()
        path = self.root / "validation/R1/CHECK.md"
        now = checker.fields(path.read_text(), "검증 기준")["마지막 실행 시각"]
        self.replace("validation/R1/CHECK.md", now, (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        self.assertEqual(self.run_command("check", "R1")[0], 1)

    def test_existing_completed_round_is_checked_with_next_round(self):
        self.add_round()
        self.replace("docs/PLAN.md", "검증 중 / 통과 | [WORK](../works/R1", "완료 / 통과 | [WORK](../works/R1")
        self.add_round("R2", product="other.js")
        self.write("app.py", "changed after R1\n")
        code, output = self.run_command("check", "R2")
        self.assertEqual(code, 1)
        self.assertIn("R1 ·", output)

    def test_check_is_read_only(self):
        self.add_round()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.run_command("ready")[0], 0)
        self.assertEqual(self.run_command("check", "R1")[0], 0)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_excluded_outputs_do_not_invalidate_basis(self):
        self.add_round(product="src/app.py", complete=False)
        self.replace("validation/R1/CHECK.md", '"src/app.py", "problem.md"', '"src", "problem.md"')
        self.replace("validation/R1/CHECK.md", '"exclude": []', '"exclude": ["src/output"]')
        before = checker.basis(self.root, "R1")
        self.write("src/output/report.txt", "generated\n")
        self.write("src/__pycache__/app.pyc", "cache\n")
        self.assertEqual(before, checker.basis(self.root, "R1"))

    def test_escape_and_root_wide_watch_rejected(self):
        self.add_round(complete=False)
        for invalid in ("../outside", "/tmp/outside", "C:/outside", "./"):
            with self.subTest(path=invalid), self.assertRaises(checker.Invalid):
                checker.inventory(self.root, {"inputs": [invalid], "exclude": []})

    def test_symlink_watch_rejected(self):
        self.add_round(complete=False)
        try:
            (self.root / "alias.py").symlink_to(self.root / "app.py")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(checker.Invalid):
            checker.inventory(self.root, {"inputs": ["alias.py"], "exclude": []})

    def test_scope_change_requires_new_test_basis(self):
        self.add_round()
        self.write("new.py", "new\n")
        self.replace("validation/R1/CHECK.md", '"exclude": []', '"exclude": ["new.py"]')
        self.assertEqual(self.run_command("check", "R1")[0], 1)

    def test_command_line_works_from_another_directory(self):
        result = subprocess.run([sys.executable, str(KIT / "check.py"), "ready", "--workspace", str(self.root)],
                                cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_malformed_configuration_is_actionable(self):
        self.add_round(complete=False)
        self.replace("validation/R1/CHECK.md", '"exclude": []', '"exclude": null')
        code, output = self.run_command("capture", "R1")
        self.assertEqual(code, 1)
        self.assertIn("exclude", output)
        self.assertNotIn("Traceback", output)

    def test_run_declared_pass_but_case_failed_is_rejected(self):
        self.add_round()
        self.replace("validation/R1/CHECK.md", "| 한 개 | 통과 | [로그]", "| 두 개 | 실패 | [로그]")
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 1)
        self.assertIn("사례 01", output)

    def test_new_pending_round_does_not_prevent_earlier_round_check(self):
        self.add_round()
        self.add_round("R2", product="other.js", complete=False)
        code, output = self.run_command("check", "R1")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.run_command("check", "--all")[0], 1)


if __name__ == "__main__":
    unittest.main()
