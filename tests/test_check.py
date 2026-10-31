"""Integration tests of record gates; all approvals/logs below are synthetic fixtures."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checker_v3", KIT / "record_checks.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class Checks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="happyhouse v3 ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "작업 공간"
        for name in ("PROBLEM", "PLAN", "REVIEW", "RESUME", "PLAN_REVIEW"):
            self.write(f"docs/{name}.md", (KIT / f"templates/{name}.md").read_text())
        (self.root / "works").mkdir()

    def write(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def replace(self, name, old, new):
        p = self.root / name
        data = p.read_text()
        self.assertIn(old, data)
        p.write_text(data.replace(old, new))

    def command(self, *args):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = checker.main([*args, "--workspace", str(self.root)])
        return code, output.getvalue()

    def runs(self, rid="R1", edit=None):
        p = self.root / f"works/{rid}/validation/CHECK.md"
        data = p.read_text()
        records = checker.run_records(data)
        if edit:
            edit(records)
            data = re.sub(r"(```happyhouse-runs\n).*?(\n```)",
                          lambda m: m[1] + json.dumps(records) + m[2], data, flags=re.S)
            p.write_text(data)
        return records

    def add_round(self, rid="R1", product="src/app.py"):
        base = f"works/{rid}"
        self.write(product, "fixture product\n")
        self.write("problem.md", "Reject empty input.\n")
        self.write("ui.py", "fixture view\n")
        self.write(base + "/WORK.md", (KIT / "templates/WORK.md").read_text().replace("{{ROUND}}", rid))
        self.write(base + "/RECORD.md", f"""# Test fixture
## 기준
- 계획 기준: rev1
- 유효한 승인 범위: fixture only
- 승인 근거: [fixture](#{rid.lower()}-01)
- 변경 영향: fixture isolated
## 요구 조건
| 항목 | 내용 |
|---|---|
| 목표 | reject empty |
| 완료조건 | error |
| 연결 | none |
| 제외 범위 | upload |
## 결정 이력
### {rid}-01
Synthetic approval fixture, not a user authorization.
## 결과
- 추가한 기능: input
- 실행법: fixture
- 코드 위치: {product}
- 검증 근거: [CHECK](validation/CHECK.md)
- 한계: fixture only
""")
        self.write(base + "/validation/CHECK.md", f"""# Test fixture
## 판정
- 현재 판정: 통과
- 기록 점검: 충족
## 검사 항목
| 번호 | 행동·입력 | 기대결과 | 정답 근거 | 실제 결과 | 판정 |
|---|---|---|---|---|---|
| 01 | empty | error | problem.md | error | 통과 |
## 검사 기준
- 검증담당: fixture validator
- 계획 기준: rev1
- 기대결과 작성: 구현 열람 전 작성
- 코드 기준 파일: runs/basis-0001.json
- 영향 검토: fixture isolated
```happyhouse
{{"inputs": ["{product}", "problem.md", "ui.py"], "exclude": []}}
```
## 실행 근거
```happyhouse-runs
{{}}
```
""")
        (self.root / base / "validation/runs").mkdir()
        self.replace("docs/PLAN.md", "| | | | | | |", f"| {rid} | input | low / 10 | 02:00:00 | 검증 중 | 통과 |\n| | | | | | |")
        self.assertEqual(self.command("capture", rid)[0], 0)
        self.write(base + "/validation/runs/test.log", "Synthetic execution fixture: expected=error actual=error exit=0")
        self.runs(rid, lambda r: r.update({"01": {"basis": "runs/basis-0001.json",
            "ran_at": datetime.now(timezone.utc).isoformat(), "dependencies": [product, "problem.md"], "evidence": "runs/test.log"}}))
        self.write("docs/RESUME.md", f"""# fixture
## 현재
- 단계 / 라운드: {rid}
- 완료 / 미완료: input complete
- 유효한 실행 범위: fixture
- 다음 행동: next
- 근거: [record](../works/{rid}/RECORD.md)
- 갱신 시각 / 작성자: actual test / fixture
""")

    def new_basis(self):
        self.assertEqual(self.command("capture", "R1")[0], 0)
        self.replace("works/R1/validation/CHECK.md", "- 코드 기준 파일: runs/basis-0001.json", "- 코드 기준 파일: runs/basis-0002.json")

    def reuse(self, changed):
        self.runs(edit=lambda r: r["01"].update({"reuse": {
            "against": "runs/basis-0002.json", "changed_files": changed,
            "reason": "view changed, isolated core inputs unchanged", "reviewer": "fixture validator"}}))

    def test_empty_plan_ready_but_not_complete(self):
        self.assertEqual(self.command("ready")[0], 0)
        self.assertEqual(self.command("check", "--all")[0], 1)

    def test_missing_setup(self):
        (self.root / "docs/PROBLEM.md").unlink()
        self.assertEqual(self.command("ready")[0], 1)

    def test_malformed_plan_row(self):
        self.replace("docs/PLAN.md", "| | | | | | |", "| | task | | | | |")
        self.assertEqual(self.command("ready")[0], 1)

    def test_portable_nested_non_python_project(self):
        self.add_round(product="packages/web/main.js")
        self.assertEqual(self.command("check", "--all")[0], 0)

    def test_success_and_read_only(self):
        self.add_round()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.command("ready")[0], 0)
        code, out = self.command("check", "R1")
        self.assertEqual(code, 0, out)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_stale_code(self):
        self.add_round()
        self.write("src/app.py", "changed")
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_selective_reuse_with_explicit_review(self):
        self.add_round()
        self.write("ui.py", "changed")
        self.new_basis()
        self.reuse(["ui.py"])
        code, out = self.command("check", "R1")
        self.assertEqual(code, 0, out)

    def test_no_silent_reuse(self):
        self.add_round()
        self.new_basis()
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_incorrect_reuse_change_list(self):
        self.add_round()
        self.write("ui.py", "changed")
        self.new_basis()
        self.reuse([])
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_changed_dependency_cannot_be_reused(self):
        self.add_round()
        self.write("src/app.py", "changed")
        self.new_basis()
        self.reuse(["src/app.py"])
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_changed_expectation_cannot_be_reused(self):
        self.add_round()
        self.replace("works/R1/validation/CHECK.md", "| empty | error |", "| empty | warning |")
        self.new_basis()
        self.reuse([])
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_changed_contract_cannot_be_reused(self):
        self.add_round()
        self.replace("works/R1/RECORD.md", "| 완료조건 | error |", "| 완료조건 | warning |")
        self.new_basis()
        self.reuse([])
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_current_basis_cannot_relabel_earlier_run(self):
        self.add_round()
        self.new_basis()
        self.runs(edit=lambda r: r["01"].update(basis="runs/basis-0002.json"))
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_future_time(self):
        self.add_round()
        self.runs(edit=lambda r: r["01"].update(ran_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_missing_evidence(self):
        self.add_round()
        (self.root / "works/R1/validation/runs/test.log").unlink()
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_basis_is_not_execution_log(self):
        self.add_round()
        self.runs(edit=lambda r: r["01"].update(evidence="runs/basis-0001.json"))
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_fake_approval_anchor(self):
        self.add_round()
        self.replace("works/R1/RECORD.md", "### R1-01", "### different")
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_empty_approval_does_not_consume_next_field(self):
        self.add_round()
        self.replace("works/R1/RECORD.md", "승인 범위: fixture only", "승인 범위:")
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_case_not_executed(self):
        self.add_round()
        self.replace("works/R1/validation/CHECK.md", "| error | 통과 |", "| error | 미실행 |")
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_human_failure_blocks_and_is_not_changed(self):
        self.add_round()
        self.replace("works/R1/WORK.md", "- [ ] 안 된다", "- [x] 안 된다")
        self.assertEqual(self.command("check", "R1")[0], 1)
        self.assertIn("[x] 안 된다", (self.root / "works/R1/WORK.md").read_text())

    def test_two_human_choices_rejected(self):
        self.add_round()
        self.replace("works/R1/WORK.md", "- [ ] 된다", "- [x] 된다")
        self.replace("works/R1/WORK.md", "- [ ] 기타", "- [x] 기타")
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_capture_never_overwrites(self):
        self.add_round()
        p = self.root / "works/R1/validation/runs/basis-0001.json"
        before = p.read_bytes()
        self.new_basis()
        self.assertEqual(before, p.read_bytes())

    def test_completed_previous_round_is_checked(self):
        self.add_round()
        self.replace("docs/PLAN.md", "| 검증 중 | 통과 |", "| 완료 | 통과 |")
        self.add_round("R2", "other.js")
        self.write("src/app.py", "changed")
        code, out = self.command("check", "R2")
        self.assertEqual(code, 1)
        self.assertIn("R1:", out)

    def test_directory_addition_deletion(self):
        self.add_round()
        config = {"inputs": ["src"], "exclude": []}
        initial = checker.inventory(self.root, config)
        p = self.write("src/extra.py", "new")
        self.assertNotEqual(initial, checker.inventory(self.root, config))
        p.unlink()
        self.assertEqual(initial, checker.inventory(self.root, config))

    def test_unsafe_paths_and_symlinks(self):
        self.add_round()
        for path in (".", "../outside", "/tmp/outside", "C:/outside"):
            with self.subTest(path=path), self.assertRaises(checker.Invalid):
                checker.inventory(self.root, {"inputs": [path], "exclude": []})
        (self.root / "alias.py").symlink_to(self.root / "src/app.py")
        with self.assertRaises(checker.Invalid):
            checker.inventory(self.root, {"inputs": ["alias.py"], "exclude": []})

    def test_evidence_cannot_escape_runs(self):
        self.add_round()
        self.runs(edit=lambda r: r["01"].update(evidence="../../../problem.md"))
        self.assertEqual(self.command("check", "R1")[0], 1)

    def test_malformed_metadata_reports_failure(self):
        self.add_round()
        self.runs(edit=lambda r: r["01"].update(dependencies=None))
        self.assertEqual(self.command("check", "R1")[0], 1)


if __name__ == "__main__":
    unittest.main()
