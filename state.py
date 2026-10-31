#!/usr/bin/env python3
"""SQLite state and Markdown views. Python 3.9+, no external packages."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

import record_checks as checks

KIT = Path(__file__).resolve().parent
DB = '.happyhouse/state.sqlite3'
SCHEMA = 1
STATES = {'계획 중', '구현 중', '검증 중', '수정 중', '완료', '보류'}

def now():
    return datetime.now(timezone.utc).isoformat()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()

def required(value, name):
    return checks.filled(value, name)

def cell(value):
    return str(value).replace('|', '\\|').replace('\n', '<br>').replace('\r', '')

def rows_table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(map(cell, headers)) + ' |',
                     '|' + '|'.join(['---'] * len(headers)) + '|'] +
                    ['| ' + ' | '.join(map(cell, row)) + ' |' for row in rows])

def connect(root):
    path = checks.safe_path(root, DB)
    con = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=10000')
    if con.execute('PRAGMA user_version').fetchone()[0] != SCHEMA:
        con.close()
        raise checks.Invalid('지원하지 않는 DB 버전입니다')
    return con

@contextmanager
def transaction(con):
    con.execute('BEGIN IMMEDIATE')
    try:
        yield
        con.execute('COMMIT')
    except BaseException:
        con.execute('ROLLBACK')
        raise

SCHEMA_SQL = '''
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO meta VALUES('revision','0');
CREATE TABLE rounds(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, budget TEXT NOT NULL DEFAULT '미정',
 target TEXT NOT NULL DEFAULT '미정', status TEXT NOT NULL DEFAULT '계획 중',
 validator TEXT NOT NULL DEFAULT '미작성', independent INTEGER NOT NULL DEFAULT 0 CHECK(independent IN(0,1)),
 review TEXT NOT NULL DEFAULT '미작성', records_ok INTEGER NOT NULL DEFAULT 0 CHECK(records_ok IN(0,1)),
 config TEXT NOT NULL DEFAULT '{"inputs": [], "exclude": []}', basis_ref TEXT,
 self_test TEXT, CHECK(status IN('계획 중','구현 중','검증 중','수정 중','완료','보류')));
CREATE TABLE requirements(id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES rounds(id),
 title TEXT NOT NULL, source TEXT NOT NULL);
CREATE TABLE dependencies(round_id TEXT NOT NULL REFERENCES rounds(id),
 predecessor TEXT NOT NULL REFERENCES rounds(id), PRIMARY KEY(round_id,predecessor), CHECK(round_id<>predecessor));
CREATE TABLE cases(round_id TEXT NOT NULL REFERENCES rounds(id), id TEXT NOT NULL,
 input TEXT NOT NULL, expected TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(round_id,id));
CREATE TABLE coverage(round_id TEXT NOT NULL, case_id TEXT NOT NULL, requirement TEXT NOT NULL REFERENCES requirements(id),
 PRIMARY KEY(round_id,case_id,requirement), FOREIGN KEY(round_id,case_id) REFERENCES cases(round_id,id));
CREATE TABLE snapshots(round_id TEXT NOT NULL REFERENCES rounds(id), ref TEXT NOT NULL,
 payload TEXT NOT NULL, model_hash TEXT NOT NULL, file_hash TEXT NOT NULL, PRIMARY KEY(round_id,ref));
CREATE TABLE runs(id INTEGER PRIMARY KEY AUTOINCREMENT, round_id TEXT NOT NULL, case_id TEXT NOT NULL,
 verdict TEXT NOT NULL CHECK(verdict IN('통과','실패','실행 불가')), actual TEXT NOT NULL,
 metadata TEXT NOT NULL, model_hash TEXT NOT NULL, evidence_hash TEXT NOT NULL, actor TEXT NOT NULL,
 recorded_at TEXT NOT NULL, FOREIGN KEY(round_id,case_id) REFERENCES cases(round_id,id));
CREATE TABLE reuse(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL REFERENCES runs(id),
 against TEXT NOT NULL, review TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, revision INTEGER NOT NULL,
 actor TEXT NOT NULL, role TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE views(path TEXT NOT NULL, block TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(path,block));
PRAGMA user_version=1;
'''

def revision(con):
    return int(con.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])

def event(con, actor, role, action, payload):
    rev = revision(con) + 1
    con.execute("UPDATE meta SET value=? WHERE key='revision'", (str(rev),))
    con.execute('INSERT INTO events(revision,actor,role,action,payload,recorded_at) VALUES(?,?,?,?,?,?)',
                (rev, actor, role, action, encoded(payload), now()))

def round_row(con, rid):
    if not checks.ROUND.fullmatch(rid):
        raise checks.Invalid('라운드는 R1, R2 형식입니다')
    row = con.execute('SELECT * FROM rounds WHERE id=?', (rid,)).fetchone()
    if row is None:
        raise checks.Invalid(f'{rid}: 등록되지 않은 라운드')
    return row

def round_ids(con):
    return sorted([x[0] for x in con.execute('SELECT id FROM rounds')], key=lambda x: int(x[1:]))

def upstream(con, rid):
    found = set()
    pending = [rid]
    while pending:
        cur = pending.pop()
        for row in con.execute('SELECT predecessor FROM dependencies WHERE round_id=?', (cur,)):
            if row[0] not in found:
                found.add(row[0]); pending.append(row[0])
    return sorted(found)

def model(con, rid):
    ids = sorted({rid, *upstream(con, rid)})
    return sha(encoded({
        'rounds': [{'id': x, 'title': round_row(con,x)['title'], 'config': round_row(con,x)['config']} for x in ids],
        'requirements': [dict(r) for x in ids for r in con.execute('SELECT * FROM requirements WHERE round_id=? ORDER BY id', (x,))],
        'dependencies': [dict(r) for x in ids for r in con.execute('SELECT * FROM dependencies WHERE round_id=? ORDER BY predecessor', (x,))],
        'cases': [dict(r) for r in con.execute('SELECT * FROM cases WHERE round_id=? ORDER BY id', (rid,))],
        'coverage': [dict(r) for r in con.execute('SELECT * FROM coverage WHERE round_id=? ORDER BY case_id,requirement', (rid,))]
    }))

def latest_runs(con, rid):
    return {r['case_id']: r for r in con.execute('SELECT * FROM runs WHERE id IN (SELECT MAX(id) FROM runs WHERE round_id=? GROUP BY case_id)', (rid,))}

def run_metadata(con, run, current_ref):
    meta = json.loads(run['metadata'])
    review = con.execute('SELECT * FROM reuse WHERE run_id=? AND against=? ORDER BY id DESC LIMIT 1', (run['id'], current_ref)).fetchone()
    if review:
        meta['reuse'] = json.loads(review['review'])
    return meta

def config(con, rid):
    configs = [json.loads(round_row(con,x)['config']) for x in [rid, *upstream(con,rid)]]
    # A downstream test watches upstream inputs as well. Common exclusions only:
    # one round cannot hide a file required by another round.
    excludes = set(configs[0]['exclude'])
    for item in configs[1:]: excludes.intersection_update(item['exclude'])
    return {'inputs': sorted({p for item in configs for p in item['inputs']}), 'exclude': sorted(excludes)}

def round_basis(root, con, rid):
    if not json.loads(round_row(con,rid)['config'])['inputs']:
        raise checks.Invalid(f'{rid}: 자체 검사 범위를 먼저 등록하세요')
    record = checks.text(checks.safe_path(root, f'works/{rid}/RECORD.md'))
    spec = con.execute('SELECT * FROM cases WHERE round_id=? ORDER BY id', (rid,)).fetchall()
    if not spec:
        raise checks.Invalid(f'{rid}: 검사 사례가 없습니다')
    return {'schema': 3, 'round': rid,
            'plan_revision': required(checks.fields(record, '기준').get('계획 기준'), '계획 기준'),
            'config': config(con, rid), 'files': checks.inventory(root, config(con, rid)),
            'contract_sha256': sha(checks.section(record, '요구 조건').strip()),
            'cases': {c['id']: checks.case_hash([c['id'], cell(c['input']), cell(c['expected']), cell(c['source'])]) for c in spec}}

def snapshot(con, rid, ref):
    row = con.execute('SELECT * FROM snapshots WHERE round_id=? AND ref=?', (rid, ref)).fetchone()
    if row is None:
        raise checks.Invalid(f'{rid}: DB에 없는 기준 {ref}')
    return row

def verify_snapshot_file(root, rid, row):
    path = checks.safe_path(root, f'works/{rid}/validation/{row["ref"]}')
    if checks.digest(path) != row['file_hash']:
        raise checks.Invalid(f'{rid}: 보존된 기준 JSON이 변경되었습니다')

def valid_run(root, con, rid, case, run, current):
    if run is None:
        raise checks.Invalid(f'{case["id"]}: 미실행')
    if run['verdict'] != '통과':
        raise checks.Invalid(f'{case["id"]}: {run["verdict"]} · {run["actual"]}')
    if run['model_hash'] != model(con, rid):
        raise checks.Invalid(f'{case["id"]}: 요구사항·관계·검사 변경 후 재검증 필요')
    row = round_row(con, rid)
    meta = run_metadata(con, run, row['basis_ref'])
    old_row = snapshot(con, rid, meta['basis'])
    verify_snapshot_file(root, rid, old_row)
    old = json.loads(old_row['payload'])
    if checks.timestamp(meta['ran_at']) < checks.timestamp(old['captured_at']):
        raise checks.Invalid('기준 저장 전 실행입니다')
    path = checks.local_file(root, checks.safe_path(root, f'works/{rid}/validation/CHECK.md'), meta['evidence'], root / f'works/{rid}/validation/runs')
    if checks.digest(path) != run['evidence_hash']:
        raise checks.Invalid(f'{case["id"]}: 실행 근거가 변경되었습니다')
    if path.name.startswith('basis-') and path.suffix == '.json':
        raise checks.Invalid('기준 JSON은 실행 근거가 아닙니다')
    for key in ('plan_revision', 'config', 'contract_sha256'):
        if old[key] != current[key]:
            raise checks.Invalid(f'{case["id"]}: {key} 변경 후 재검증 필요')
    if old['cases'].get(case['id']) != current['cases'][case['id']]:
        raise checks.Invalid('기대조건 변경 후 재검증 필요')
    deps = meta['dependencies']
    if not isinstance(deps, list) or not deps or any(not isinstance(p, str) for p in deps):
        raise checks.Invalid('구체적인 의존 파일이 필요합니다')
    for p in deps:
        if p not in old['files'] or p not in current['files'] or old['files'][p] != current['files'][p]:
            raise checks.Invalid(f'{case["id"]}: 의존 파일 변경 · {p}')
    if meta['basis'] != row['basis_ref']:
        changed = sorted(p for p in set(old['files']) | set(current['files']) if old['files'].get(p) != current['files'].get(p))
        reuse = meta.get('reuse', {})
        if reuse.get('against') != row['basis_ref'] or reuse.get('changed_files') != changed:
            raise checks.Invalid(f'{case["id"]}: 이전 실행 유지 근거가 필요합니다')
        required(reuse.get('reason'), '유지 이유'); required(reuse.get('reviewer'), '검토자')

def local_issues(root, con, rid):
    errors = []
    reqs = con.execute('SELECT id FROM requirements WHERE round_id=?', (rid,)).fetchall()
    if not reqs:
        errors.append('담당 요구사항 미등록')
    for req in reqs:
        covered = con.execute('SELECT 1 FROM coverage WHERE requirement=? AND round_id=?', (req[0], rid)).fetchone()
        if not covered:
            errors.append(f'{req[0]}: 담당 라운드 검사 연결 없음')
    for c in con.execute('SELECT id FROM cases WHERE round_id=?', (rid,)):
        if not con.execute('SELECT 1 FROM coverage WHERE round_id=? AND case_id=?', (rid, c[0])).fetchone():
            errors.append(f'{c[0]}: 요구사항 연결 없음')
    row = round_row(con, rid)
    if not row['basis_ref']:
        return errors + ['검사 기준 미저장']
    try:
        stored = snapshot(con, rid, row['basis_ref'])
        verify_snapshot_file(root, rid, stored)
        live = round_basis(root, con, rid)
        captured = json.loads(stored['payload'])
        if any(captured.get(k) != v for k, v in live.items()) or stored['model_hash'] != model(con, rid):
            errors.append('현재 코드·요구·관계 변경: 새 기준과 재검증 필요')
        runs = latest_runs(con, rid)
        for case in con.execute('SELECT * FROM cases WHERE round_id=? ORDER BY id', (rid,)):
            try:
                valid_run(root, con, rid, case, runs.get(case['id']), live)
            except (checks.Invalid, OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(str(exc))
    except (checks.Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return errors

def issues(root, con, rid):
    result = local_issues(root, con, rid)
    for parent in upstream(con, rid):
        if local_issues(root, con, parent) or round_row(con, parent)['status'] != '완료':
            result.append(f'{parent}: 선행 라운드 완료·현재 검증 확인 필요')
    return result

def verdict(root, con, rid):
    row = round_row(con, rid)
    runs = latest_runs(con, rid)
    if not runs:
        return '미실행'
    if any(r['verdict'] == '실패' for r in runs.values()):
        return '실패'
    if any(r['verdict'] == '실행 불가' for r in runs.values()):
        return '실행 불가'
    return '재검증 필요' if issues(root, con, rid) else '통과'

def status_display(root, con, rid):
    row = round_row(con, rid)
    return '재검증 필요' if row['status'] == '완료' and issues(root, con, rid) else row['status']

def file_scope_issues(root, con):
    # Only product files are enumerated; narrative and evidence have their own gates.
    covered = set()
    excluded = []
    for rid in round_ids(con):
        try:
            covered.update(checks.inventory(root, config(con, rid)))
            excluded.extend(checks.safe_path(root,p,False) for p in config(con,rid)['exclude'])
        except checks.Invalid:
            pass
    unknown = []
    ignored = checks.IGNORED | {'.happyhouse', 'docs', 'works'}
    for folder, dirs, files in os.walk(root, followlinks=False):
        base = Path(folder)
        dirs[:] = [d for d in dirs if d not in ignored]
        for d in dirs:
            if (base / d).is_symlink():
                unknown.append((base / d).relative_to(root).as_posix())
        for name in files:
            p = base / name
            rel = p.relative_to(root).as_posix()
            if rel in {'dump.md', '.gitignore', '.DS_Store'} or name.endswith(('.pyc', '.sqlite3-journal')):
                continue
            if rel not in covered and not any(p == ex or ex in p.parents for ex in excluded):
                unknown.append(rel)
    return [f'검사 범위 미연결: {p}' for p in sorted(unknown)]

def full_check(root, con, rid, require_views=True):
    errors = issues(root, con, rid) + file_scope_issues(root, con)
    try:
        own = json.loads(round_row(con,rid)['self_test'] or '{}')
        evidence = checks.safe_path(root, own.get('evidence',''))
        if not evidence.is_file() or checks.digest(evidence) != own.get('hash') or checks.inventory(root,config(con,rid)) != own.get('files'):
            raise checks.Invalid('자체 테스트 근거 누락·변경 또는 코드 변경 후 자체 테스트 필요')
    except (checks.Invalid,ValueError,OSError) as exc:
        errors.append(str(exc))
    if require_views:
        errors += view_issues(root, con)
    row = round_row(con, rid)
    try:
        checks.inspect_round(root, rid, [rid, row['title'], row['budget'], row['target'], '검증 중', verdict(root, con, rid)])
    except (checks.Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return list(dict.fromkeys(errors))

def ensure_round_files(root, rid):
    for source, dest in [('WORK.md', 'WORK.md'), ('RECORD.md', 'RECORD.md'), ('CHECK.md', 'validation/CHECK.md')]:
        path = checks.safe_path(root, f'works/{rid}/{dest}', False)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text((KIT / 'templates' / source).read_text().replace('{{ROUND}}', rid), encoding='utf-8')
    checks.safe_path(root, f'works/{rid}/validation/runs', False).mkdir(exist_ok=True)

def initialize(root):
    if checks.safe_path(root, DB, False).exists():
        raise checks.Invalid('DB가 이미 있습니다. 초기화하지 않고 status 또는 render를 사용하세요')
    plan = root / 'docs/PLAN.md'
    if plan.exists() and checks.planned(root):
        raise checks.Invalid('기존 라운드가 있는 Workspace는 자동 이관하지 않습니다. 새 Workspace에서 시작하세요')
    for name in ('PROBLEM', 'PLAN', 'PLAN_REVIEW', 'REVIEW', 'RESUME'):
        path = checks.safe_path(root, f'docs/{name}.md', False)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text((KIT / f'templates/{name}.md').read_text(), encoding='utf-8')
    checks.safe_path(root, 'works', False).mkdir(exist_ok=True)
    path = checks.safe_path(root, 'dump.md', False)
    if not path.exists():
        path.write_text((KIT / 'templates/dump.md').read_text(), encoding='utf-8')
    path = checks.safe_path(root, DB, False)
    path.parent.mkdir(exist_ok=True)
    # Reserve without replacing a concurrently created DB.
    with path.open('xb'):
        pass
    con = sqlite3.connect(str(path), isolation_level=None)
    try:
        con.executescript('BEGIN IMMEDIATE;\n' + SCHEMA_SQL + '\nCOMMIT;')
    finally:
        con.close()
    con = connect(root)
    try:
        render(root, con)
    finally:
        con.close()

# Named blocks are generated; all bytes outside them, notably human answers, are retained.
def marker(name, body):
    return f'<!-- happyhouse:{name}:start -->\n\n{body.rstrip()}\n\n<!-- happyhouse:{name}:end -->'

def extract(document, name):
    pattern = r'<!-- happyhouse:' + re.escape(name) + r':start -->\n.*?<!-- happyhouse:' + re.escape(name) + r':end -->'
    hits = list(re.finditer(pattern, document, re.S))
    if len(hits) != 1:
        raise checks.Invalid(f'생성 영역 {name}: 정확히 한 쌍의 표시가 필요합니다')
    return hits[0]

def replace_section(document, title, body):
    pattern = r'(^## ' + re.escape(title) + r'\s*\n).*?(?=^## |\Z)'
    if len(re.findall(r'^## ' + re.escape(title) + r'\s*$', document, re.M)) != 1:
        raise checks.Invalid(f'필요한 절 없음: {title}')
    return re.sub(pattern, lambda m: m[1] + '\n' + body + '\n\n', document, flags=re.M | re.S)

def desired_views(root, con):
    result = {}
    ids = round_ids(con)
    table = rows_table(['라운드', '만들 기능', '난이도·배정', '목표 잔여', '진행', '검증'],
                      [[rid, round_row(con,rid)['title'], round_row(con,rid)['budget'], round_row(con,rid)['target'], status_display(root,con,rid), verdict(root,con,rid)] for rid in ids])
    todo = []
    for rid in ids:
        todo.append(f'**{rid} · {round_row(con,rid)["title"]}**\n')
        for req in con.execute('SELECT * FROM requirements WHERE round_id=? ORDER BY id', (rid,)):
            linked = con.execute('SELECT case_id FROM coverage WHERE round_id=? AND requirement=?', (rid,req['id'])).fetchall()
            ok = bool(linked) and not issues(root,con,rid) and round_row(con,rid)['status']=='완료'
            todo.append(f'- [{"x" if ok else " "}] {req["title"]}')
        todo.append('')
    graph = ['```mermaid', 'flowchart LR']
    for rid in ids:
        label=html.escape(rid+' · '+round_row(con,rid)['title'],quote=True).replace('\n',' ')
        graph.append(f'    {rid}["{label}"]')
    for edge in con.execute('SELECT * FROM dependencies ORDER BY round_id,predecessor'):
        graph.append(f'    {edge["predecessor"]} --> {edge["round_id"]}')
    graph.append('```')
    result['docs/PLAN.md'] = {'plan': table + ('\n\n'+'\n'.join(graph) if ids else ''),
                              'features': '\n'.join(todo) if todo else '- [ ] 문제 이해 후 요구사항 등록'}
    for rid in ids:
        row = round_row(con,rid)
        current = verdict(root,con,rid)
        result[f'works/{rid}/WORK.md'] = {'progress': f'**진행:** {status_display(root,con,rid)} · **검증:** {current}\n\n'
            f'- [{"x" if row["self_test"] else " "}] 구현·자체 테스트\n'
            f'- [{"x" if current=="통과" else " "}] 독립 검증'}
        spec = con.execute('SELECT * FROM cases WHERE round_id=? ORDER BY id',(rid,)).fetchall()
        runs = latest_runs(con,rid)
        checks_rows, meta = [], {}
        for c in spec:
            run = runs.get(c['id'])
            v = run['verdict'] if run else '미실행'
            if run and v == '통과':
                try:
                    live = round_basis(root,con,rid)
                    valid_run(root,con,rid,c,run,live)
                except (checks.Invalid,OSError,ValueError,KeyError,TypeError):
                    v='재검증 필요'
            checks_rows.append([c['id'],c['input'],c['expected'],c['source'],run['actual'] if run else '미실행',v])
            if run:
                meta[c['id']] = run_metadata(con,run,row['basis_ref'])
        record = checks.text(checks.safe_path(root,f'works/{rid}/RECORD.md'))
        rev = checks.fields(record,'기준').get('계획 기준','초안')
        result[f'works/{rid}/validation/CHECK.md'] = {
            'verdict': f'- 현재 판정: {current}\n- 기록 점검: {"충족" if row["records_ok"] else "미실시"}\n- 다음 행동: {"완료 검사" if current=="통과" else "미실행·실패·변경 영향 확인"}',
            'cases': rows_table(['번호','행동·입력','기대결과','정답 근거','실제 결과','판정'],checks_rows),
            'basis': f'<details>\n<summary>검사 기준 보기</summary>\n\n- 검증담당: {row["validator"]}\n- 계획 기준: {rev}\n- 기대결과 작성: {"구현 열람 전 작성" if row["independent"] else "미실시"}\n- 코드 기준 파일: {row["basis_ref"] or "미지정"}\n- 영향 검토: {row["review"]}\n\n```happyhouse\n{encoded(config(con,rid))}\n```\n\n</details>',
            'runs': '<details>\n<summary>실행 근거 보기</summary>\n\n```happyhouse-runs\n'+json.dumps(meta,ensure_ascii=False,indent=2)+'\n```\n\n</details>'}
    return result

def prepare_view(root, con, path, blocks, repair=False):
    dest = checks.safe_path(root,path)
    old = checks.text(dest)
    new = old
    headings = {'plan':'전체 진행표','features':'완료할 기능','progress':'진행','verdict':'판정','cases':'검사 항목','basis':'검사 기준','runs':'실행 근거'}
    for name, body in blocks.items():
        known = con.execute('SELECT digest FROM views WHERE path=? AND block=?',(path,name)).fetchone()
        if known:
            hit = extract(new,name)
            if sha(hit[0]) != known['digest'] and not repair:
                raise checks.Invalid(f'{path}: 자동 생성 영역이 직접 수정되었습니다. 변경을 별도 메모에 보존하고 원래 영역을 복구하세요')
            new = new[:hit.start()] + marker(name,body) + new[hit.end():]
        else:
            # First ownership is allowed only on a fresh template, never silently import history.
            template_name = 'PLAN.md' if path=='docs/PLAN.md' else Path(path).name
            original = (KIT/'templates'/template_name).read_text()
            if checks.section(new,headings[name]).strip() != checks.section(original,headings[name]).strip():
                raise checks.Invalid(f'{path}: {headings[name]}에 기존 내용이 있어 자동 생성 영역으로 전환하지 않았습니다')
            new = replace_section(new,headings[name],marker(name,body))
    return old,new

def atomic_write(path, content):
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix='.happyhouse-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def render_locked(root,con,repair=False):
    # Save committed canonical records even if a later Markdown write fails.
    export_locked(root,con)
    desired=desired_views(root,con)
    updates=[]
    for path,blocks in desired.items():
        old,new=prepare_view(root,con,path,blocks,repair)
        updates.append((path,old,new,blocks))
    for path,old,new,blocks in updates:
        dest=checks.safe_path(root,path)
        if checks.text(dest)!=old:
            raise checks.Invalid('문서가 동시에 편집되었습니다. 저장을 마친 후 render를 다시 실행하세요')
        if new!=old:
            if repair:
                backup=checks.safe_path(root,'.happyhouse/recovery/'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'/'+path,False)
                backup.parent.mkdir(parents=True,exist_ok=True)
                backup.write_text(old,encoding='utf-8')
            atomic_write(dest,new)
        for name,body in blocks.items():
            con.execute('INSERT INTO views VALUES(?,?,?) ON CONFLICT(path,block) DO UPDATE SET digest=excluded.digest', (path,name,sha(marker(name,body))))
    export_locked(root,con)

def render(root,con,repair=False):
    with transaction(con):
        render_locked(root,con,repair)

def view_issues(root,con):
    problems=[]
    for path,blocks in desired_views(root,con).items():
        try:
            doc=checks.text(checks.safe_path(root,path))
            if any(extract(doc,name)[0]!=marker(name,body) for name,body in blocks.items()):
                problems.append(f'{path}: 화면 갱신 필요 (render)')
        except (checks.Invalid,OSError) as exc:
            problems.append(str(exc))
    return problems

def export_locked(root,con):
    tables=('meta','rounds','requirements','dependencies','cases','coverage','snapshots','runs','reuse','events','views')
    data={'schema':SCHEMA, 'tables':{t:[dict(r) for r in con.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}}
    atomic_write(checks.safe_path(root,'.happyhouse/state-export.json',False),json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def validate_graph(con):
    for rid in round_ids(con):
        if rid in upstream(con,rid):
            raise checks.Invalid('라운드 선행 관계에 순환이 있습니다')

OP_FIELDS={
 'round':({'id','title'},{'budget','target'}),
 'requirement':({'id','round','title','source'},set()),
 'depends':({'round','on'},set()),
 'status':({'round','value'},set()),
 'self_test':({'round','evidence'},set()),
 'case':({'round','id','input','expected','source','requirements'},set()),
 'config':({'round','inputs','exclude'},{'exclude_reason'}),
 'review':({'round','independent','records_ok','reason'},set()),
 'run':({'round','case','verdict','actual','basis','ran_at','dependencies','evidence'},set()),
 'reuse':({'run','against','reason','changed_files'},set())}
MAIN_OPS={'round','requirement','depends','status','self_test'}
VALIDATOR_OPS={'case','config','review','run','reuse'}

def apply_op(root,con,op,actor,role):
    if not isinstance(op,dict) or op.get('op') not in OP_FIELDS:
        raise checks.Invalid('알 수 없는 작업')
    kind=op['op']; needed,optional=OP_FIELDS[kind]
    if not needed <= set(op) or set(op)-needed-optional-{'op'}:
        raise checks.Invalid(f'{kind}: 필수 또는 알 수 없는 필드')
    if kind not in (MAIN_OPS if role=='main' else VALIDATOR_OPS):
        raise checks.Invalid(f'{role}: {kind} 기록 담당이 아닙니다')
    rid=op.get('round',op.get('id') if kind=='round' else None)
    if kind=='round':
        if not isinstance(rid,str) or not checks.ROUND.fullmatch(rid): raise checks.Invalid('잘못된 라운드 ID')
        required(op['title'],'라운드 목표')
        if 'target' in op and not re.fullmatch(r'\d{2}:\d{2}:\d{2}',op['target']): raise checks.Invalid('목표 잔여는 HH:MM:SS')
        if con.execute('SELECT 1 FROM rounds WHERE id=?',(rid,)).fetchone():
            con.execute('UPDATE rounds SET title=?,budget=COALESCE(?,budget),target=COALESCE(?,target) WHERE id=?',(op['title'],op.get('budget'),op.get('target'),rid))
        else:
            con.execute('INSERT INTO rounds(id,title,budget,target) VALUES(?,?,?,?)',(rid,op['title'],op.get('budget','미정'),op.get('target','미정')))
    elif kind=='requirement':
        round_row(con,rid)
        for k in ('id','title','source'): required(op[k],k)
        checks.links(root,root/'docs/PROBLEM.md',op['source'])
        con.execute('INSERT INTO requirements VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET round_id=excluded.round_id,title=excluded.title,source=excluded.source',(op['id'],rid,op['title'],op['source']))
    elif kind=='depends':
        round_row(con,rid)
        if not isinstance(op['on'],list) or any(not isinstance(x,str) for x in op['on']): raise checks.Invalid('on은 라운드 목록')
        con.execute('DELETE FROM dependencies WHERE round_id=?',(rid,))
        for pred in op['on']: con.execute('INSERT INTO dependencies VALUES(?,?)',(rid,pred))
    elif kind=='status':
        round_row(con,rid)
        if op['value'] not in STATES or op['value']=='완료': raise checks.Invalid('완료는 complete 명령의 검사 후에만 가능')
        con.execute('UPDATE rounds SET status=? WHERE id=?',(op['value'],rid))
    elif kind=='self_test':
        round_row(con,rid)
        p=checks.safe_path(root,op['evidence'])
        if not p.is_file() or not p.stat().st_size: raise checks.Invalid('자체 테스트 근거가 필요합니다')
        con.execute('UPDATE rounds SET self_test=? WHERE id=?',(encoded({'evidence':op['evidence'], 'hash':checks.digest(p), 'files':checks.inventory(root,config(con,rid))}),rid))
    elif kind=='case':
        round_row(con,rid)
        if not isinstance(op['id'],str) or not re.fullmatch(r'\d{2,}',op['id']): raise checks.Invalid('검사 번호는 01, 02 형식')
        for k in ('input','expected','source'): required(op[k],k)
        checks.links(root,root/f'works/{rid}/validation/CHECK.md',op['source'])
        if not isinstance(op['requirements'],list) or not op['requirements'] or any(not isinstance(x,str) for x in op['requirements']): raise checks.Invalid('검사할 요구사항 목록이 필요합니다')
        con.execute('INSERT INTO cases VALUES(?,?,?,?,?) ON CONFLICT(round_id,id) DO UPDATE SET input=excluded.input,expected=excluded.expected,source=excluded.source',(rid,op['id'],op['input'],op['expected'],op['source']))
        con.execute('DELETE FROM coverage WHERE round_id=? AND case_id=?',(rid,op['id']))
        for req in op['requirements']: con.execute('INSERT INTO coverage VALUES(?,?,?)',(rid,op['id'],req))
        con.execute('UPDATE rounds SET records_ok=0 WHERE id=?',(rid,))
    elif kind=='config':
        round_row(con,rid)
        value={k:op[k] for k in ('inputs','exclude')}
        if value['exclude']: required(op.get('exclude_reason'),'제외 이유')
        checks.settings('```happyhouse\n'+encoded(value)+'\n```')
        checks.inventory(root,value)
        con.execute('UPDATE rounds SET config=?,records_ok=0 WHERE id=?',(encoded(value),rid))
    elif kind=='review':
        round_row(con,rid)
        if type(op['independent']) is not bool or type(op['records_ok']) is not bool: raise checks.Invalid('검토 플래그는 true/false')
        required(op['reason'],'영향 검토 이유')
        con.execute('UPDATE rounds SET validator=?,independent=?,records_ok=?,review=? WHERE id=?',(actor,int(op['independent']),int(op['records_ok']),op['reason'],rid))
    elif kind=='run':
        row=round_row(con,rid)
        spec=con.execute('SELECT * FROM cases WHERE round_id=? AND id=?',(rid,op['case'])).fetchone()
        if spec is None: raise checks.Invalid('미등록 검사')
        snap=snapshot(con,rid,op['basis']); verify_snapshot_file(root,rid,snap)
        if op['basis']!=row['basis_ref'] or snap['model_hash']!=model(con,rid): raise checks.Invalid('현재 기준으로 실행을 기록하세요')
        live=round_basis(root,con,rid); original=json.loads(snap['payload'])
        if any(original[k]!=v for k,v in live.items()): raise checks.Invalid('실행 중 코드·기준이 변경되었습니다')
        if checks.timestamp(op['ran_at'])<checks.timestamp(original['captured_at']): raise checks.Invalid('capture 전 실행입니다')
        required(op['actual'],'실제 결과')
        meta={k:op[k] for k in ('basis','ran_at','dependencies','evidence')}
        deps=op['dependencies']
        if not isinstance(deps,list) or not deps or any(not isinstance(p,str) or p not in live['files'] for p in deps): raise checks.Invalid('기준에 포함된 의존 파일 목록 필요')
        p=checks.local_file(root,root/f'works/{rid}/validation/CHECK.md',op['evidence'],root/f'works/{rid}/validation/runs')
        if p.name.startswith('basis-') and p.suffix=='.json': raise checks.Invalid('기준 JSON은 실행 로그가 아닙니다')
        con.execute('INSERT INTO runs(round_id,case_id,verdict,actual,metadata,model_hash,evidence_hash,actor,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (rid,op['case'],op['verdict'],op['actual'],encoded(meta),model(con,rid),checks.digest(p),actor,now()))
        con.execute('UPDATE rounds SET records_ok=0 WHERE id=?',(rid,))
    elif kind=='reuse':
        run=con.execute('SELECT * FROM runs WHERE id=?',(op['run'],)).fetchone()
        if not run: raise checks.Invalid('실행 기록 없음')
        rid=run['round_id']; row=round_row(con,rid)
        if op['against']!=row['basis_ref']: raise checks.Invalid('현재 기준에 대한 유지 검토만 가능')
        required(op['reason'],'유지 검토 이유')
        value={'against':op['against'],'changed_files':op['changed_files'],'reason':op['reason'],'reviewer':actor}
        con.execute('INSERT INTO reuse(run_id,against,review,actor,recorded_at) VALUES(?,?,?,?,?)',(run['id'],op['against'],encoded(value),actor,now()))
        case=con.execute('SELECT * FROM cases WHERE round_id=? AND id=?',(rid,run['case_id'])).fetchone()
        valid_run(root,con,rid,case,run,round_basis(root,con,rid))


def apply(root,con,payload,actor,role):
    if not isinstance(payload,dict) or set(payload)!={'revision','operations'} or type(payload['revision']) is not int or not isinstance(payload['operations'],list) or not payload['operations']:
        raise checks.Invalid('revision 정수와 비어 있지 않은 operations 목록이 필요합니다')
    with transaction(con):
        if payload['revision']!=revision(con): raise checks.Invalid('다른 기록이 먼저 갱신되었습니다. status로 최신 revision을 읽고 변경을 다시 검토하세요')
        for op in payload['operations']: apply_op(root,con,op,actor,role)
        validate_graph(con)
        event(con,actor,role,'apply',payload['operations'])
    # DB is committed first. A failed view write never rolls back legitimate records.
    for rid in round_ids(con): ensure_round_files(root,rid)
    render(root,con)


def capture(root,con,rid,actor):
    with transaction(con):
        row=round_row(con,rid)
        if not row['independent']: raise checks.Invalid('구현 열람 전 기대결과 작성 여부를 검증담당이 먼저 기록하세요')
        payload=round_basis(root,con,rid); payload['captured_at']=now()
        folder=checks.safe_path(root,f'works/{rid}/validation/runs')
        for n in range(1,100000):
            path=folder/f'basis-{n:04d}.json'
            try:
                with path.open('x',encoding='utf-8') as f: f.write(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
                break
            except FileExistsError: continue
        else: raise checks.Invalid('기준 번호 소진')
        ref='runs/'+path.name
        con.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)',(rid,ref,encoded(payload),model(con,rid),checks.digest(path)))
        con.execute('UPDATE rounds SET basis_ref=?,records_ok=0 WHERE id=?',(ref,rid))
        event(con,actor,'validator','capture',{'round':rid,'basis':ref})
    render(root,con)
    return ref


def complete(root,con,rid,actor):
    with transaction(con):
        errors=full_check(root,con,rid)
        if errors: raise checks.Invalid('\n'.join(errors))
        con.execute("UPDATE rounds SET status='완료' WHERE id=?",(rid,))
        event(con,actor,'main','complete',{'round':rid})
    render(root,con)



def restore(root, export_path):
    """Rebuild only a missing DB; code, narrative, basis and log files are separate artifacts."""
    value=json.loads(export_path.read_text(encoding='utf-8'))
    expected={'meta','rounds','requirements','dependencies','cases','coverage','snapshots','runs','reuse','events','views'}
    if not isinstance(value,dict) or set(value)!={'schema','tables'} or value['schema']!=SCHEMA or set(value['tables'])!=expected:
        raise checks.Invalid('지원하는 state-export.json 형식이 아닙니다')
    path=checks.safe_path(root,DB,False)
    path.parent.mkdir(exist_ok=True)
    with path.open('xb'):
        pass
    con=sqlite3.connect(str(path),isolation_level=None)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        con.executescript('BEGIN IMMEDIATE;\n'+SCHEMA_SQL+'\nCOMMIT;')
        with transaction(con):
            con.execute('DELETE FROM meta')
            for table in ('meta','rounds','requirements','dependencies','cases','coverage','snapshots','runs','reuse','events','views'):
                columns=[r['name'] for r in con.execute(f'PRAGMA table_info({table})')]
                if not isinstance(value['tables'][table],list): raise checks.Invalid('복구 테이블 형식 오류')
                for row in value['tables'][table]:
                    if not isinstance(row,dict) or set(row)!=set(columns): raise checks.Invalid('복구 필드 형식 오류')
                    names=','.join('"'+c+'"' for c in columns)
                    marks=','.join('?' for c in columns)
                    con.execute(f'INSERT INTO {table}({names}) VALUES({marks})',[row[c] for c in columns])
            revision(con)
            validate_graph(con)
            if con.execute('PRAGMA foreign_key_check').fetchall(): raise checks.Invalid('복구 관계 오류')
    except BaseException:
        con.close(); path.unlink()
        raise
    else:
        con.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('init','status','apply','render','ready','capture','check','complete','export','restore'))
    p.add_argument('round',nargs='?')
    p.add_argument('--workspace',default='.')
    p.add_argument('--file')
    p.add_argument('--actor')
    p.add_argument('--role',choices=('main','validator'))
    p.add_argument('--all',action='store_true')
    p.add_argument('--repair',action='store_true',help='render: back up documents and repair generated blocks only')
    args=p.parse_args(argv)
    if args.repair and args.command!='render': p.error('--repair는 render에만 사용합니다')
    if args.all and args.command!='check': p.error('--all은 check에만 사용합니다')
    if args.round and args.command not in ('capture','check','complete'): p.error('이 명령에는 라운드를 쓰지 않습니다')
    if args.command in ('apply','capture','complete'):
        if not args.actor or not args.role: p.error('실제 --actor 이름과 --role 필요')
        try: required(args.actor,'기록자')
        except checks.Invalid as exc: p.error(str(exc))
    if args.command in ('apply','restore') and not args.file: p.error('apply --file 요청.json 필요')
    if args.command in ('capture','complete') and not args.round: p.error('라운드 필요')
    if args.command=='capture' and args.role!='validator': p.error('capture는 validator 담당')
    if args.command=='complete' and args.role!='main': p.error('complete는 main 담당')
    if args.command=='check' and bool(args.round)==args.all: p.error('check R1 또는 check --all')
    root=Path(args.workspace).expanduser().resolve()
    con=None
    try:
        if not root.is_dir(): raise checks.Invalid('Workspace 폴더가 없습니다')
        if args.command=='init':
            initialize(root); print('SQLite와 문서 준비 완료. 다음: PROBLEM으로 문제 이해.'); return 0
        if args.command=='restore':
            restore(root,Path(args.file)); print('DB 복구 완료. render와 check로 현재 파일을 다시 확인하세요.'); return 0
        con=connect(root)
        if args.command=='apply':
            apply(root,con,json.loads(Path(args.file).read_text(encoding='utf-8')),args.actor,args.role)
        elif args.command=='render': render(root,con,args.repair)
        elif args.command=='capture': print('기준 저장: '+capture(root,con,args.round,args.actor))
        elif args.command=='complete': complete(root,con,args.round,args.actor)
        elif args.command=='export':
            with transaction(con): export_locked(root,con)
        elif args.command=='status':
            print(f'revision: {revision(con)}')
            for rid in round_ids(con):
                print(f'{rid} | {status_display(root,con,rid)} | {verdict(root,con,rid)}')
                for error in issues(root,con,rid)[:5]: print('  '+error)
            for error in file_scope_issues(root,con): print('  '+error)
            return 0
        elif args.command=='ready':
            errors=checks.readiness(root)+view_issues(root,con)
            errors += [str(r) for r in con.execute('PRAGMA foreign_key_check')]
            if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok': errors.append('DB 무결성 검사 실패')
            for error in errors: print('보완 필요: '+error)
            if not errors: print('기록 준비 완료. 제품 실행·기능 검사는 별개입니다.')
            return int(bool(errors))
        elif args.command=='check':
            ids=round_ids(con)
            if not ids: raise checks.Invalid('계획된 라운드가 없습니다')
            if args.round: round_row(con,args.round)
            selected=ids if args.all else [rid for rid in ids if rid==args.round or round_row(con,rid)['status']=='완료']
            errors=[]
            for rid in selected:
                found=full_check(root,con,rid)
                errors.extend(f'{rid}: {e}' for e in found)
                if not found: print(f'{rid}: 기록·관계·기준 검사 통과')
            for error in errors: print('보완 필요: '+error)
            return int(bool(errors))
        print(f'기록 완료 · revision {revision(con)} · Markdown 갱신됨')
        return 0
    except (checks.Invalid,sqlite3.Error,OSError,ValueError,KeyError,TypeError) as exc:
        print(f'보완 필요: {exc}',file=sys.stderr)
        if con is not None and args.command in ('apply','capture','complete'):
            print('DB가 이미 저장되었을 수 있습니다. status 확인 후 render로 화면을 복구하세요. 같은 요청을 무조건 반복하지 마세요.',file=sys.stderr)
        return 1
    finally:
        if con: con.close()

if __name__=='__main__':
    sys.exit(main())
