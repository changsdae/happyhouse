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
CORE = ("docs/PLAN.md", "docs/RESUME.md", "docs/REVIEW.md", "validation/PLAN_REVIEW.md")


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
        fail("라운드는 R1, R2처럼 지정하세요")
    return {"work": safe_path(root, f"works/{round_id}/WORK.md"),
            "check": safe_path(root, f"validation/{round_id}/CHECK.md"),
            "summary": safe_path(root, f"results/{round_id}/SUMMARY.md")}


def planned(root):
    rows = table(text(safe_path(root, "docs/PLAN.md")), "전체 진행표", 6)
    result = {}
    for row in rows:
        if not ROUND.fullmatch(row[0]) or row[0] in result:
            fail("PLAN의 라운드는 중복 없이 R1, R2 형식이어야 합니다")
        result[row[0]] = row
    return result


def readiness(root):
    errors = []
    for relative in CORE:
        try:
            text(safe_path(root, relative))
        except Invalid as exc:
            errors.append(str(exc))
    for relative in ("docs", "works", "validation", "results"):
        try:
            if not safe_path(root, relative).is_dir():
                fail(f"폴더가 아님: {relative}")
            if not os.access(root / relative, os.W_OK):
                fail(f"기록 폴더에 쓰기 권한이 없습니다: {relative}")
        except Invalid as exc:
            errors.append(str(exc))
    if not errors:
        try:
            for round_id in planned(root):
                paths = round_paths(root, round_id)
                for path in paths.values():
                    text(path)
                if not safe_path(root, f"validation/{round_id}/runs").is_dir():
                    fail(f"{round_id}: runs 폴더가 없습니다")
                section(text(paths["work"]), "지금 볼 것")
                section(text(paths["check"]), "검증 기준")
            section(text(safe_path(root, "docs/RESUME.md")), "현재 인계")
        except Invalid as exc:
            errors.append(str(exc))
    return errors


def basis(root, round_id):
    paths = round_paths(root, round_id)
    work, check = text(paths["work"]), text(paths["check"])
    w, c = fields(work, "지금 볼 것"), fields(check, "검증 기준")
    revision = filled(w.get("계획 기준"), "WORK 계획 기준")
    if revision != c.get("계획 기준"):
        fail("WORK와 CHECK의 계획 기준이 다릅니다")
    config = settings(check)
    return {"schema": 1, "round": round_id, "plan_revision": revision,
            "config": config, "files": inventory(root, config),
            "contract_sha256": hashlib.sha256(section(work, "라운드 계약").strip().encode("utf-8")).hexdigest()}


def capture(root, round_id):
    if round_id not in planned(root):
        fail(f"PLAN에 {round_id}가 없습니다")
    data = basis(root, round_id)
    data["captured_at"] = datetime.now(timezone.utc).isoformat()
    folder = safe_path(root, f"validation/{round_id}/runs")
    for number in range(1, 100000):
        target = folder / f"basis-{number:04d}.json"
        try:
            with target.open("x", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            return target.relative_to(root).as_posix(), len(data["files"])
        except FileExistsError:
            continue
    fail("새 코드 기준 파일 이름을 만들 수 없습니다")


def timestamp(value):
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError()
        return when
    except (ValueError, AttributeError):
        fail("실행 시각은 시간대가 있는 ISO 형식이어야 합니다: 2026-10-31T10:30:00+09:00")


def inspect_round(root, round_id, row):
    errors = []

    def inspect(label, operation):
        try:
            operation()
        except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{label}: {exc}")

    paths = round_paths(root, round_id)
    work, check = text(paths["work"]), text(paths["check"])
    w, c = fields(work, "지금 볼 것"), fields(check, "검증 기준")
    for key in ("목표 / 완료조건", "계획 기준", "유효한 승인 범위", "승인 근거", "변경 영향 / 추가 결정", "다음 행동"):
        inspect("WORK", lambda key=key: filled(w.get(key), key))
    inspect("승인 근거", lambda: links(root, paths["work"], w.get("승인 근거", "")))

    def contract():
        rows = table(work, "라운드 계약", 2)
        required = {"입력 → 처리 → 출력", "선행·연결점", "완료조건", "검증할 정상·경계·실패", "제외 범위와 이유", "핵심 코드 위치 / 검증 대상 기준"}
        if {r[0] for r in rows} != required or len(rows) != len(required):
            fail("라운드 계약의 필수 행을 유지하세요")
        for key, value in rows:
            filled(value, key)
    inspect("완료조건·연결", contract)
    for key in ("검증담당", "계획 기준", "코드 기준 파일", "마지막 실행 시각"):
        inspect("CHECK", lambda key=key: filled(c.get(key), key))
    for key, expected in (("현재 판정", "통과"), ("기록 점검", "충족"), ("기대결과 작성", "구현 열람 전 작성")):
        if c.get(key) != expected:
            errors.append(f"CHECK {key}: '{expected}' 상태가 아닙니다")
    if row[4] not in ("검증 중 / 통과", "완료 / 통과"):
        errors.append("PLAN: 완료 후보는 '검증 중 / 통과', 완료 후에는 '완료 / 통과'로 표시하세요")

    def plan_links():
        targets = links(root, safe_path(root, "docs/PLAN.md"), row[5])
        if paths["work"] not in targets or paths["check"] not in targets:
            fail("해당 라운드의 WORK와 CHECK로 연결해야 합니다")
    inspect("PLAN 바로가기", plan_links)

    def cases():
        rows = table(check, "문제 유형과 기대결과", 8)
        if not rows:
            fail("실행한 검증 사례가 없습니다")
        ids = set()
        for cells in rows:
            if cells[0] in ids:
                fail(f"중복 사례 번호: {cells[0]}")
            ids.add(cells[0])
            for value in cells:
                filled(value, f"사례 {cells[0]}")
            if cells[6] != "통과":
                fail(f"사례 {cells[0]}가 통과하지 않았습니다")
            links(root, paths["check"], cells[7])
    inspect("검증 사례·근거", cases)

    def compare_basis():
        targets = links(root, paths["check"], c.get("코드 기준 파일", ""))
        if len(targets) != 1 or targets[0].parent != paths["check"].parent / "runs":
            fail("runs의 코드 기준 JSON 한 개를 연결하세요")
        stored = json.loads(text(targets[0]))
        current = basis(root, round_id)
        if not isinstance(stored, dict) or set(stored) != set(current) | {"captured_at"}:
            fail("코드 기준 파일의 형식이 맞지 않습니다. capture로 만든 원본을 사용하세요")
        changed = [key for key in current if current[key] != stored[key]]
        if changed:
            fail("검증 기준 변경 감지 (" + ", ".join(changed) + "). 영향 확인 후 새 기준으로 재검증하세요")
        ran = timestamp(c.get("마지막 실행 시각"))
        if ran < timestamp(stored["captured_at"]):
            fail("기준을 저장하기 전에 실행한 결과입니다. 새 기준 저장만으로 과거 통과를 재사용할 수 없습니다")
        if (ran - datetime.now(timezone.utc)).total_seconds() > 300:
            fail("마지막 실행 시각이 현재보다 미래입니다")
    inspect("코드·요구·계획 기준", compare_basis)

    def handoff():
        resume = safe_path(root, "docs/RESUME.md")
        values = fields(text(resume), "현재 인계")
        for key in ("현재 단계 / 라운드", "갱신 시각 / 작성자", "다음 행동", "상세 근거"):
            filled(values.get(key), key)
        links(root, resume, values["상세 근거"])
        local = fields(work, "인계")
        for key in ("갱신 시각 / 작성자", "완료 / 미완료", "마지막 대화 번호 / 열린 질문", "다음 행동 / 현재 다른 세션이 쓰는 파일"):
            filled(local.get(key), key)
    inspect("인계", handoff)

    def summary():
        content = text(paths["summary"])
        rows = table(content, "결과", 2)
        if len(rows) != 7:
            fail("SUMMARY의 결과 표 7개 항목을 작성하세요")
        for key, value in rows:
            filled(value, key)
        values = dict(rows)
        targets = links(root, paths["summary"], values.get("검증 결과와 로그", ""))
        if paths["check"] not in targets:
            fail("SUMMARY는 해당 라운드의 CHECK를 연결해야 합니다")
    inspect("결과 요약", summary)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ready", "capture", "check"))
    parser.add_argument("round", nargs="?")
    parser.add_argument("--workspace", default=".", help="작업 폴더. 기본값: 현재 폴더")
    parser.add_argument("--all", action="store_true", help="최종 점검: 계획된 모든 라운드 검사")
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
                print("준비 확인: 작업 폴더·문서 구조를 읽을 수 있습니다.")
                print("제품 실행 환경·요구사항·내용 완성도는 검사하지 않았습니다.")
        elif args.command == "capture":
            path, count = capture(root, args.round)
            print(f"검증 전 기준 저장: {path} ({count}개 파일)")
            print("CHECK에 이 파일을 연결하고 지금부터 테스트하세요. 상태는 자동 변경하지 않습니다.")
            return 0
        else:
            rows = planned(root)
            if not rows:
                fail("계획된 라운드가 없습니다. 빈 계획은 완료로 판정하지 않습니다")
            if args.round and args.round not in rows:
                fail(f"PLAN에 {args.round}가 없습니다")
            selected = rows if args.all else {key: row for key, row in rows.items()
                                              if key == args.round or row[4].startswith("완료")}
            errors = []
            for round_id, row in selected.items():
                try:
                    findings = inspect_round(root, round_id, row)
                except (Invalid, OSError) as exc:
                    findings = [str(exc)]
                errors.extend(f"{round_id} · {item}" for item in findings)
                if not findings:
                    print(f"{round_id}: 필수 기록·근거 파일·검증 대상 기준 일치")
            if not errors:
                print("검사 통과. 제품 정답·승인 진위·검증 범위의 충분성을 보증하는 결과는 아닙니다.")
        for error in errors:
            print(f"보완 필요: {error}")
        return 1 if errors else 0
    except (Invalid, OSError, ValueError) as exc:
        print(f"보완 필요: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 이상이 필요합니다")
    sys.exit(main())
