#!/usr/bin/env python3
"""Happyhouse record checks. Python 3.9+, standard library only.

ready/check are read-only. capture creates a new code-basis record before tests.
This tool does not run product tests, approve work, or change Markdown status.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote, urlsplit


ROUND = re.compile(r"R[1-9][0-9]*\Z")
LINK = re.compile(r"\[[^\]]*\]\((<[^>]+>|[^\s)]+)\)")
IGNORED = {".git", "_harness", "node_modules", ".venv", "venv", "__pycache__",
           ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EMPTY = re.compile(r"^(?:미작성|미확인|미지정|미기록|미승인|미실행|미실시|미검토|미정|초안|구현 후 기록|구체화 필요|TODO|TBD|아직)(?:\b|\s|$)", re.I)
CORE = ("docs/PROBLEM.md", "docs/PLAN.md", "docs/RESUME.md", "docs/REVIEW.md", "docs/PLAN_REVIEW.md")


class Invalid(ValueError):
    pass


def fail(message):
    raise Invalid(message)


def text(path):
    try:
        value = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        fail(f"읽을 수 없음: {path.name} ({exc})")
    if not value.strip():
        fail(f"빈 파일: {path.name}")
    return value


def section(document, title):
    matches = list(re.finditer(r"^## " + re.escape(title) + r"\s*$", document, re.M))
    if len(matches) != 1:
        fail(f"'## {title}' 절이 정확히 하나 필요합니다")
    start = matches[0].end()
    end = re.search(r"^## ", document[start:], re.M)
    return document[start:start + end.start()] if end else document[start:]


def fields(document, title):
    result = {}
    for key, value in re.findall(r"^- ([^:\n]+):[ \t]*([^\n]*)$", section(document, title), re.M):
        if key in result:
            fail(f"{title}: 중복 항목 '{key}'")
        result[key] = value.strip()
    return result


def filled(value, label):
    if not isinstance(value, str) or not value.strip() or value.strip() in {"-", "—", "...", "…"} or EMPTY.match(value.strip()) or "{{" in value:
        fail(f"{label}: 실제 내용으로 작성해야 합니다")
    return value


def table(document, title, columns):
    rows = []
    for line in section(document, title).splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) != columns:
            fail(f"{title}: 표는 {columns}열이어야 합니다 (셀의 |는 \\|로 표기)")
        rows.append(cells)
    if not rows:
        fail(f"{title}: 표가 없습니다")
    return rows[1:]


def safe_path(root, relative, must_exist=True):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        fail("경로는 Workspace 기준 상대 경로와 /를 사용해야 합니다")
    part = PurePosixPath(relative)
    if part.is_absolute() or ".." in part.parts or ":" in relative:
        fail(f"허용되지 않는 경로: {relative}")
    candidate = root.joinpath(*part.parts)
    current = root
    for component in part.parts:
        current = current / component
        if current.is_symlink():
            fail(f"심볼릭 링크는 검사 대상에 사용할 수 없습니다: {relative}")
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        fail(f"Workspace 밖의 경로: {relative}")
    if must_exist and not candidate.exists():
        fail(f"파일 또는 폴더 없음: {relative}")
    return candidate


def anchors(document):
    document = re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", document, flags=re.M | re.S)
    result = set(re.findall(r'<a\s+id=["\']([^"\']+)["\']\s*>', document))
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", document, re.M):
        result.add(re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-"))
    return result


def links(root, owner, value, required=True):
    targets = []
    for raw in LINK.findall(value):
        parsed = urlsplit(raw.strip("<>"))
        if parsed.scheme or parsed.netloc:
            fail("검사 근거는 Workspace 안의 로컬 파일로 연결해야 합니다")
        absolute = owner.parent / unquote(parsed.path) if parsed.path else owner
        try:
            relative = absolute.resolve().relative_to(root).as_posix()
        except ValueError:
            fail("근거 링크가 Workspace 밖을 가리킵니다")
        # Check the original lexical path too, so symlinks cannot hide behind resolve().
        if any(p.is_symlink() for p in [absolute, *absolute.parents] if p != root and root in p.parents):
            fail("근거 링크에 심볼릭 링크를 사용할 수 없습니다")
        target = safe_path(root, relative)
        if not target.is_file() or target.stat().st_size == 0:
            fail(f"비어 있거나 파일이 아닌 근거: {relative}")
        if parsed.fragment and unquote(parsed.fragment) not in anchors(text(target)):
            fail(f"근거의 제목/앵커를 찾을 수 없음: {relative}#{parsed.fragment}")
        targets.append(target)
    if required and not targets:
        fail("근거를 [설명](상대경로) 형식의 로컬 파일 링크로 작성해야 합니다")
    return targets


def settings(document):
    blocks = re.findall(r"^```happyhouse\s*\n(.*?)^```\s*$", document, re.M | re.S)
    if len(blocks) != 1:
        fail("CHECK에 happyhouse JSON 설정 블록이 정확히 하나 필요합니다")
    try:
        value = json.loads(blocks[0])
    except ValueError:
        fail("CHECK의 happyhouse 설정이 올바른 JSON이 아닙니다")
    if not isinstance(value, dict) or set(value) != {"inputs", "exclude"}:
        fail("검사 설정에는 inputs와 exclude만 필요합니다")
    for key in value:
        if not isinstance(value[key], list) or any(not isinstance(p, str) or not p for p in value[key]):
            fail(f"{key}는 경로 문자열의 목록이어야 합니다")
        if len(set(value[key])) != len(value[key]):
            fail(f"{key}에 중복 경로가 있습니다")
    if not value["inputs"]:
        fail("검증할 제품·테스트·요구사항·설정 경로를 inputs에 지정해야 합니다")
    return value


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root, config):
    excluded = []
    for relative in config["exclude"]:
        if PurePosixPath(relative) == PurePosixPath("."):
            fail("Workspace 전체를 제외할 수 없습니다")
        excluded.append(safe_path(root, relative, False))
    def ignored(item):
        return (any(part in IGNORED for part in item.relative_to(root).parts)
                or any(item == p or p in item.parents for p in excluded))

    def walk(base):
        if ignored(base):
            return
        if base.is_file():
            yield base
            return
        def walk_error(error):
            raise error
        for folder, dirs, names in os.walk(base, onerror=walk_error, followlinks=False):
            parent = Path(folder)
            dirs[:] = sorted(name for name in dirs if not ignored(parent / name))
            for name in dirs:
                if (parent / name).is_symlink():
                    fail(f"검사 대상의 심볼릭 링크: {(parent / name).relative_to(root)}")
            for name in sorted(names):
                if not ignored(parent / name):
                    yield parent / name

    result = {}
    for relative in config["inputs"]:
        if PurePosixPath(relative) == PurePosixPath("."):
            fail("inputs에는 . 대신 제품·테스트·원문 경로를 명시하세요")
        base = safe_path(root, relative)
        found = False
        for item in walk(base):
            rel = item.relative_to(root)
            if item.is_symlink():
                fail(f"검사 대상의 심볼릭 링크: {rel.as_posix()}")
            if item.is_file():
                found = True
                result[rel.as_posix()] = digest(item)
                if len(result) > 20000:
                    fail("검사 대상이 20,000개를 초과했습니다. 생성물·의존성 경로를 제외하세요")
        if not found:
            fail(f"실제 검사할 파일이 없는 inputs 항목: {relative}")
    return dict(sorted(result.items()))


def round_paths(root, round_id):
    if not ROUND.fullmatch(round_id):
        fail("라운드는 R1, R2 형식이어야 합니다")
    base = f"works/{round_id}"
    return {"work": safe_path(root, base + "/WORK.md"),
            "record": safe_path(root, base + "/RECORD.md"),
            "check": safe_path(root, base + "/validation/CHECK.md")}


def planned(root):
    result = {}
    for row in table(text(safe_path(root, "docs/PLAN.md")), "전체 진행표", 6):
        if not any(row):
            continue
        if not ROUND.fullmatch(row[0]) or row[0] in result:
            fail("PLAN 라운드 ID가 비었거나 중복되었습니다")
        result[row[0]] = row
    return result


def cases(document):
    result = {}
    for row in table(document, "검사 항목", 6):
        if not any(row):
            continue
        if not re.fullmatch(r"[0-9]{2,}", row[0]) or row[0] in result:
            fail("검사 번호는 중복 없는 01, 02 형식이어야 합니다")
        for value in row[:4]:
            filled(value, f"검사 {row[0]} 기대조건")
        result[row[0]] = row
    if not result:
        fail("검사 사례가 없습니다")
    return result


def case_hash(row):
    return hashlib.sha256(json.dumps(row[:4], ensure_ascii=False).encode()).hexdigest()


def basis(root, round_id):
    paths = round_paths(root, round_id)
    record, check = text(paths["record"]), text(paths["check"])
    r, c = fields(record, "기준"), fields(check, "검사 기준")
    revision = filled(r.get("계획 기준"), "계획 기준")
    if revision != c.get("계획 기준"):
        fail("RECORD와 CHECK 계획 기준이 다릅니다")
    config = settings(check)
    return {"schema": 3, "round": round_id, "plan_revision": revision,
            "config": config, "files": inventory(root, config),
            "contract_sha256": hashlib.sha256(section(record, "요구 조건").strip().encode()).hexdigest(),
            "cases": {key: case_hash(row) for key, row in cases(check).items()}}


def readiness(root):
    errors = []
    for name in CORE:
        try:
            text(safe_path(root, name))
        except Invalid as exc:
            errors.append(str(exc))
    for folder in ("docs", "works"):
        try:
            path = safe_path(root, folder)
            if not path.is_dir() or not os.access(path, os.W_OK):
                fail(f"쓰기 가능한 폴더가 아님: {folder}")
        except Invalid as exc:
            errors.append(str(exc))
    if not errors:
        try:
            for round_id in planned(root):
                paths = round_paths(root, round_id)
                for path in paths.values():
                    text(path)
                if not (paths["check"].parent / "runs").is_dir():
                    fail(f"{round_id}: runs 폴더가 없습니다")
                fields(text(paths["record"]), "기준")
                fields(text(paths["check"]), "검사 기준")
            fields(text(safe_path(root, "docs/RESUME.md")), "현재")
        except Invalid as exc:
            errors.append(str(exc))
    return errors


def capture(root, round_id):
    if round_id not in planned(root):
        fail(f"PLAN에 {round_id}가 없습니다")
    snapshot = basis(root, round_id)
    snapshot["captured_at"] = datetime.now(timezone.utc).isoformat()
    folder = round_paths(root, round_id)["check"].parent / "runs"
    safe_path(root, folder.relative_to(root).as_posix())
    for number in range(1, 100000):
        target = folder / f"basis-{number:04d}.json"
        try:
            with target.open("x", encoding="utf-8") as stream:
                json.dump(snapshot, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            return target
        except FileExistsError:
            continue
    fail("새 기준 파일 이름을 만들 수 없습니다")


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        if (result - datetime.now(timezone.utc)).total_seconds() > 300:
            fail("현재보다 미래인 실행 시각입니다")
        return result
    except (AttributeError, ValueError):
        fail("시간대가 있는 실제 ISO 시각이 필요합니다")


def local_file(root, owner, relative, folder=None):
    # Machine metadata uses owner-relative paths without traversal; evidence is kept in runs/.
    if not isinstance(relative, str):
        fail("근거 경로가 문자열이 아닙니다")
    part = PurePosixPath(relative)
    if part.is_absolute() or ".." in part.parts or "\\" in relative or ":" in relative:
        fail("근거는 CHECK 기준 runs/ 아래 경로여야 합니다")
    path = safe_path(root, (owner.parent / relative).relative_to(root).as_posix())
    if not path.is_file() or not path.stat().st_size:
        fail("근거 파일이 비어 있습니다")
    if folder and folder not in path.parents:
        fail("근거는 runs/ 안에 보존하세요")
    return path


def read_basis(root, owner, relative, round_id):
    path = local_file(root, owner, relative, owner.parent / "runs")
    value = json.loads(text(path))
    required = {"schema", "round", "plan_revision", "config", "files", "contract_sha256", "cases", "captured_at"}
    if not isinstance(value, dict) or set(value) != required or value["schema"] != 3 or value["round"] != round_id:
        fail("현재 라운드의 v3 capture 원본이 필요합니다")
    if not isinstance(value["files"], dict) or not value["files"] or not isinstance(value["cases"], dict):
        fail("기준 파일 목록·사례 형식 오류")
    timestamp(value["captured_at"])
    return value


def run_records(check):
    blocks = re.findall(r"^```happyhouse-runs\s*\n(.*?)^```\s*$", check, re.M | re.S)
    if len(blocks) != 1:
        fail("happyhouse-runs JSON 블록 하나가 필요합니다")
    result = json.loads(blocks[0])
    if not isinstance(result, dict):
        fail("사례별 실행 근거는 JSON 객체여야 합니다")
    return result


def inspect_round(root, round_id, row):
    paths = round_paths(root, round_id)
    record, check, work = text(paths["record"]), text(paths["check"]), text(paths["work"])
    r, c = fields(record, "기준"), fields(check, "검사 기준")
    verdict = fields(check, "판정")
    if row[4] not in ("검증 중", "완료") or row[5] != "통과":
        fail("PLAN은 검증 중/통과 또는 완료/통과여야 합니다")
    for key in ("계획 기준", "유효한 승인 범위", "승인 근거", "변경 영향"):
        filled(r.get(key), key)
    links(root, paths["record"], r["승인 근거"])
    contract_rows = table(record, "요구 조건", 2)
    if len(contract_rows) != 4 or {x[0] for x in contract_rows} != {"목표", "완료조건", "연결", "제외 범위"}:
        fail("RECORD 요구 조건 4개 항목이 필요합니다")
    for key, value in contract_rows:
        filled(value, key)
    for key in ("검증담당", "영향 검토"):
        filled(c.get(key), key)
    if c.get("기대결과 작성") != "구현 열람 전 작성":
        fail("독립 기대결과 작성 근거가 필요합니다")
    if verdict.get("현재 판정") != "통과" or verdict.get("기록 점검") != "충족":
        fail("기능 통과와 기록 점검 충족이 모두 필요합니다")

    # A human answer is never filled by this tool. Multiple choices are malformed.
    human = section(work, "직접 확인")
    for block in re.split(r"^### ", human, flags=re.M):
        checked = re.findall(r"^- \[[xX]\] (된다|안 된다|기타)\s*$", block, re.M)
        if len(checked) > 1:
            fail("직접 확인 항목마다 판정은 하나만 선택하세요")
        if "안 된다" in checked or "기타" in checked:
            fail("사람의 실패·기타 관찰이 남아 있습니다. 해결/확인 내용을 RECORD에 보존하고 다시 확인하세요")

    current = basis(root, round_id)
    current_ref = c.get("코드 기준 파일")
    snapshot = read_basis(root, paths["check"], current_ref, round_id)
    if any(snapshot[key] != value for key, value in current.items()):
        fail("현재 코드·요구·검사 기준이 달라졌습니다. 영향 확인 후 새 capture와 필요한 재검증을 수행하세요")
    spec = cases(check)
    runs = run_records(check)
    if set(runs) != set(spec):
        fail("모든 검사 사례에 실행 근거가 필요합니다")
    for case_id, cells in spec.items():
        filled(cells[4], f"{case_id} 실제 결과")
        if cells[5] != "통과":
            fail(f"검사 {case_id}가 통과하지 않았습니다")
        run = runs[case_id]
        if not isinstance(run, dict) or not {"basis", "ran_at", "dependencies", "evidence"} <= set(run):
            fail(f"{case_id}: 기준·실행 시각·의존 파일·로그가 필요합니다")
        old = read_basis(root, paths["check"], run["basis"], round_id)
        if timestamp(run["ran_at"]) < timestamp(old["captured_at"]):
            fail(f"{case_id}: capture 전 실행을 새 기준의 통과로 사용할 수 없습니다")
        evidence = local_file(root, paths["check"], run["evidence"], paths["check"].parent / "runs")
        if evidence.suffix == ".json" and evidence.name.startswith("basis-"):
            fail("capture 파일은 테스트 실행 로그가 아닙니다")
        for key in ("plan_revision", "config", "contract_sha256"):
            if old[key] != snapshot[key]:
                fail(f"{case_id}: {key} 변경으로 이전 실행을 재사용할 수 없습니다")
        if old["cases"].get(case_id) != current["cases"][case_id]:
            fail(f"{case_id}: 기대조건 변경 후 다시 실행해야 합니다")
        dependencies = run["dependencies"]
        if not isinstance(dependencies, list) or not dependencies or any(not isinstance(x, str) for x in dependencies):
            fail(f"{case_id}: 의존 파일을 구체적으로 지정하세요")
        for path in dependencies:
            if path not in old["files"] or path not in snapshot["files"] or old["files"][path] != snapshot["files"][path]:
                fail(f"{case_id}: 의존 파일 변경 또는 누락: {path}")
        if run["basis"] != current_ref:
            changed = sorted(key for key in set(old["files"]) | set(snapshot["files"])
                             if old["files"].get(key) != snapshot["files"].get(key))
            reuse = run.get("reuse")
            if not isinstance(reuse, dict) or reuse.get("against") != current_ref or reuse.get("changed_files") != changed:
                fail(f"{case_id}: 현재 기준과 실제 변경 파일에 대한 유지 검토가 필요합니다")
            for key in ("reason", "reviewer"):
                filled(reuse.get(key), f"{case_id} 유지 검토 {key}")
    result = fields(record, "결과")
    for key in ("추가한 기능", "실행법", "코드 위치", "검증 근거", "한계"):
        filled(result.get(key), key)
    if paths["check"] not in links(root, paths["record"], result["검증 근거"]):
        fail("결과는 현재 라운드 CHECK를 근거로 연결해야 합니다")
    resume_path = safe_path(root, "docs/RESUME.md")
    resume = fields(text(resume_path), "현재")
    for key in ("단계 / 라운드", "완료 / 미완료", "유효한 실행 범위", "다음 행동", "근거", "갱신 시각 / 작성자"):
        filled(resume.get(key), key)
    links(root, resume_path, resume["근거"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ready", "capture", "check"))
    parser.add_argument("round", nargs="?")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "ready" and (args.round or args.all):
        parser.error("ready에는 라운드나 --all을 쓰지 않습니다")
    if args.command == "capture" and (not args.round or args.all):
        parser.error("capture에는 라운드 하나가 필요합니다")
    if args.command == "check" and bool(args.round) == args.all:
        parser.error("check R1 또는 check --all을 사용하세요")
    root = Path(args.workspace).expanduser().resolve()
    try:
        if not root.is_dir():
            fail("Workspace 폴더가 없습니다")
        if args.command == "ready":
            errors = readiness(root)
            if not errors:
                print("기록 준비 완료. 제품 실행 환경과 기능은 검사하지 않았습니다.")
        elif args.command == "capture":
            path = capture(root, args.round)
            print(f"기준 저장: {path.relative_to(root)}\n이후 실제 테스트를 실행하고 CHECK에 기록하세요.")
            return 0
        else:
            rows = planned(root)
            if not rows:
                fail("계획된 라운드가 없습니다")
            if args.round and args.round not in rows:
                fail("요청한 라운드가 PLAN에 없습니다")
            selected = rows if args.all else {key: row for key, row in rows.items()
                                              if key == args.round or row[4] == "완료"}
            errors = []
            for round_id, row in selected.items():
                try:
                    inspect_round(root, round_id, row)
                    print(f"{round_id}: 기록·기준 검사 통과")
                except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append(f"{round_id}: {exc}")
            if not errors:
                print("제품 테스트·승인 진위·의존 범위의 충분성을 자동 보증하는 결과는 아닙니다.")
        for error in errors:
            print(f"보완 필요: {error}")
        return int(bool(errors))
    except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"보완 필요: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 이상이 필요합니다")
    sys.exit(main())


