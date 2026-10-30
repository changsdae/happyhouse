#!/usr/bin/env python3
"""Happyhouse: dependency-free local workspace setup and read-only dashboard."""
import argparse
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import parse_qs, urlparse

VERSION = '1.0.0'
KIT = Path(__file__).resolve().parent
RID = re.compile(r'R[1-9][0-9]*\Z')
STATUSES = {'planning': '계획 중', 'ready': '준비됨', 'implementing': '구현 중',
            'validating': '검증 중', 'fixing': '수정 중', 'done': '완료', 'blocked': '보류'}
RESULTS = {'pending': '미실행', 'pass': '통과', 'fail': '실패', 'blocked': '실행 불가', 'stale': '재검증 필요'}
MARKER = '<!-- happyhouse:managed -->'
BEGIN, END = '<!-- happyhouse:overview:start -->', '<!-- happyhouse:overview:end -->'


def stamp():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec='seconds')


def safe_path(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Workspace 내부의 상대 경로를 사용하세요.')
    target = root / rel
    resolved = target.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Workspace 밖으로 연결된 경로는 사용할 수 없습니다.')
    # Symlinks are never used as write/read targets by the harness.
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('심볼릭 링크 경로는 사용하지 않습니다: ' + str(rel))
    return target


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.hh-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextlib.contextmanager
def lock(root):
    path = safe_path(root, '.happyhouse/write.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('다른 기록 갱신 중입니다. 잠시 뒤 재시도하세요. 중단된 작업의 lock은 실행 여부 확인 후 제거하세요.')
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def read_state(root):
    p = safe_path(root, '.happyhouse/state.json')
    if not p.exists():
        raise ValueError('먼저 init을 실행하세요.')
    state = json.loads(p.read_text(encoding='utf-8'))
    if state.get('schema') != 1:
        raise ValueError('지원하지 않는 상태 파일 버전입니다.')
    return state


def save_state(root, state, event):
    state['updated_at'] = stamp()
    # State is authoritative for metadata; generated Markdown is a recoverable projection.
    atomic_write(safe_path(root, '.happyhouse/state.json'), json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    history = safe_path(root, '.happyhouse/events.jsonl')
    with history.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'at': state['updated_at'], **event}, ensure_ascii=False) + '\n')
    sync_plan(root, state)


def hms(seconds):
    n = max(0, int(seconds))
    return f'{n // 3600:02d}:{n % 3600 // 60:02d}:{n % 60:02d}'


def parse_duration(value):
    if not re.fullmatch(r'\d{2,3}:[0-5]\d:[0-5]\d', value):
        raise ValueError('시간은 HH:MM:SS 형식으로 입력하세요.')
    h, m, s = map(int, value.split(':'))
    return h * 3600 + m * 60 + s


def snapshot(state):
    s = json.loads(json.dumps(state))
    elapsed = s['planning_minutes'] * 60
    unknown = False
    for r in s['rounds']:
        if r['minutes'] is None:
            unknown = True
        if not unknown:
            elapsed += r['minutes'] * 60
            r['target_remaining'] = hms(s['total_minutes'] * 60 - elapsed)
        else:
            r['target_remaining'] = None
        r['status_label'] = STATUSES[r['status']]
        r['validation_label'] = RESULTS[r['validation']['result']]
    total = sum(r['minutes'] or 0 for r in s['rounds']) + s['planning_minutes'] + s['reserve_minutes']
    s['allocated_minutes'] = total
    s['over_budget'] = total > s['total_minutes']
    s['remaining_seconds'] = max(0, s['deadline'] - time.time()) if s['deadline'] is not None else None
    s['server_epoch'] = time.time()
    return s


def cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def sync_plan(root, state):
    p = safe_path(root, 'docs/PLAN.md')
    if not p.exists():
        return
    text = p.read_text(encoding='utf-8')
    if BEGIN not in text or END not in text:
        raise ValueError('PLAN의 자동 표 표시가 없습니다. 본문은 보존되었습니다. 표시를 복원하고 sync하세요.')
    s = snapshot(state)
    lines = [BEGIN, f"갱신: {state['updated_at']} · 현재 라운드: {state['current_round'] or '미정'}",
             '', '| 라운드 | 구현 과제 | 완료조건 | 선행 | 난이도 | 배정 | 목표 종료 잔여 | 상태 | 검증 |',
             '|---|---|---|---|---|---|---|---|---|']
    for r in s['rounds']:
        vals = [f"[{r['id']}](../works/{r['id']}/WORK.md)", r['goal'], r['done_when'],
                ', '.join(r['depends']) or '없음', r['difficulty'],
                f"{r['minutes']}분" if r['minutes'] is not None else '미정',
                r['target_remaining'] or '미정', r['status_label'], r['validation_label']]
        lines.append('| ' + ' | '.join(cell(v) for v in vals) + ' |')
    lines += ['', f"전체 {s['total_minutes']}분 · 초기 계획 {s['planning_minutes']}분 · 최종 점검/제출 확보 {s['reserve_minutes']}분"]
    if s['over_budget']:
        lines.append('**배정 시간이 전체 제한시간을 초과합니다. 계획을 다시 조정하세요.**')
    lines += ['', '진행 중인 타이머는 대시보드에서 표시합니다. 실제 시험 타이머를 기준으로 보정하세요.', END]
    before, tail = text.split(BEGIN, 1)
    _, after = tail.split(END, 1)
    atomic_write(p, before + '\n'.join(lines) + after)


def template(name, rid=''):
    return (KIT / 'templates' / name).read_text(encoding='utf-8').replace('{{ROUND}}', rid)


def validate_workspace(root):
    if not root.exists() or not root.is_dir():
        raise ValueError('존재하는 Workspace 폴더를 지정하세요.')
    if root == KIT or root.is_relative_to(KIT):
        raise ValueError('하네스 원본 안에는 작업 기록을 생성하지 않습니다. Workspace를 사용하세요.')


def initialize(root):
    validate_workspace(root)
    targets = {'docs/PLAN.md': 'PLAN.md', 'docs/RESUME.md': 'RESUME.md',
               'validation/PLAN_REVIEW.md': 'PLAN_REVIEW.md', 'dump.md': 'dump.md'}
    contents = {rel: template(name) for rel, name in targets.items()}
    # Preflight all paths before creating anything, including collisions with files/links.
    for directory in ['docs', 'works', 'validation', 'results', '.happyhouse']:
        p = safe_path(root, directory)
        if p.exists() and not p.is_dir():
            raise ValueError('폴더와 충돌하는 파일이 있습니다: ' + directory)
    safe_path(root, '.happyhouse/state.json')
    for rel in targets:
        p = safe_path(root, rel)
        if p.exists() and (not p.is_file() or (rel != 'dump.md' and MARKER not in p.read_text(encoding='utf-8'))):
            raise ValueError('기존 파일을 보존합니다. 충돌을 먼저 확인하세요: ' + rel)
    with lock(root):
        state_path = safe_path(root, '.happyhouse/state.json')
        if state_path.exists():
            state = read_state(root)
        else:
            state = {'schema': 1, 'kit_version': VERSION, 'title': '새 프로젝트', 'approver': '',
                     'total_minutes': 180, 'planning_minutes': 20, 'reserve_minutes': 30,
                     'deadline': None, 'current_round': None, 'updated_at': stamp(), 'rounds': []}
        for rel, name in targets.items():
            p = safe_path(root, rel)
            if not p.exists():
                atomic_write(p, contents[rel])
        for name in ['works', 'results']:
            safe_path(root, name).mkdir(exist_ok=True)
        save_state(root, state, {'kind': 'init', 'note': '기존 기록 보존; 승인/테스트 결과 생성 없음'})
    return '초기 준비 완료. docs/PLAN.md와 docs/RESUME.md를 확인하세요. 제품·제공 지침·하네스 원본은 수정하지 않았습니다.'


def find_round(state, rid):
    for r in state['rounds']:
        if r['id'] == rid:
            return r
    raise ValueError('등록되지 않은 라운드: ' + rid)


def check_dependencies(state):
    graph = {r['id']: r['depends'] for r in state['rounds']}
    def visit(key, stack):
        if key not in graph:
            raise ValueError('선행 라운드를 먼저 등록하세요: ' + key)
        if key in stack:
            raise ValueError('라운드 의존관계에 순환이 있습니다.')
        for nxt in graph[key]:
            visit(nxt, stack | {key})
    for key in graph:
        visit(key, set())


def evidence(root, rel):
    p = safe_path(root, rel)
    if Path(rel).parts[0] not in {'validation', 'works', 'results'} or not p.is_file() or p.stat().st_size == 0:
        raise ValueError('validation/works/results 아래 실제 내용이 있는 증거 파일이 필요합니다.')
    return rel


def invalidate(state, rid, reason):
    affected = {rid}
    while True:
        expanded = affected | {r['id'] for r in state['rounds'] if affected.intersection(r['depends'])}
        if expanded == affected:
            break
        affected = expanded
    for r in state['rounds']:
        if r['id'] in affected:
            r['validation'] = {'result': 'stale', 'reason': reason if r['id'] == rid else rid + ' 변경 영향 재검토'}
            if r['status'] == 'done':
                r['status'] = 'validating'
    return sorted(affected)


def mutate(root, args):
    with lock(root):
        state = read_state(root)
        event = {'kind': args.command}
        if args.command == 'configure':
            for field in ['title', 'approver', 'total_minutes', 'planning_minutes', 'reserve_minutes']:
                val = getattr(args, field)
                if val is not None:
                    state[field] = val
            if state['total_minutes'] <= 0 or min(state['planning_minutes'], state['reserve_minutes']) < 0:
                raise ValueError('시간 설정을 확인하세요.')
        elif args.command == 'add-round':
            if not RID.fullmatch(args.round):
                raise ValueError('라운드 이름은 R1, R2 형식을 사용하세요.')
            if any(r['id'] == args.round for r in state['rounds']):
                raise ValueError('이미 등록된 라운드입니다. update-round를 사용하세요.')
            if args.minutes is not None and args.minutes <= 0:
                raise ValueError('배정 시간은 양수여야 합니다.')
            r = {'id': args.round, 'title': args.title, 'goal': args.goal or args.title,
                 'done_when': args.done_when or '구체화 필요', 'depends': args.depends,
                 'difficulty': args.difficulty, 'minutes': args.minutes, 'status': 'planning',
                 'revision': 1, 'basis': '', 'validation': {'result': 'pending'}, 'note': ''}
            state['rounds'].append(r)
            check_dependencies(state)
            targets = {f'works/{args.round}/WORK.md': 'WORK.md',
                       f'validation/{args.round}/CHECK.md': 'CHECK.md',
                       f'results/{args.round}/SUMMARY.md': 'SUMMARY.md'}
            contents = {rel: template(name, args.round) for rel, name in targets.items()}
            for rel in targets:
                if safe_path(root, rel).exists():
                    raise ValueError('기존 라운드 파일을 보존합니다: ' + rel)
            for rel, name in targets.items():
                atomic_write(safe_path(root, rel), contents[rel])
            safe_path(root, f'validation/{args.round}/runs').mkdir(exist_ok=True)
            state['current_round'] = state['current_round'] or args.round
            event['round'] = args.round
        elif args.command == 'update-round':
            r = find_round(state, args.round)
            event['before'] = json.loads(json.dumps(r))
            changed = False
            for field in ['title', 'goal', 'done_when', 'minutes', 'difficulty', 'depends']:
                val = getattr(args, field)
                if val is not None and val != r[field]:
                    if field == 'minutes' and val <= 0:
                        raise ValueError('배정 시간은 양수여야 합니다.')
                    r[field] = val
                    changed = True
            check_dependencies(state)
            if changed:
                r['revision'] += 1
                event['affected'] = invalidate(state, args.round, args.reason)
                r['note'] = args.reason
            event.update(round=args.round, reason=args.reason)
        elif args.command == 'select':
            find_round(state, args.round)
            state['current_round'] = args.round
        elif args.command == 'checkpoint':
            r = find_round(state, args.round)
            event['before'] = json.loads(json.dumps(r))
            if r['basis'] != args.basis:
                r['basis'] = args.basis
                event['affected'] = invalidate(state, args.round, '코드 기준 변경')
            event.update(round=args.round, basis=args.basis)
        elif args.command == 'status':
            r = find_round(state, args.round)
            if args.set == 'done':
                v = r['validation']
                if v['result'] != 'pass' or v.get('revision') != r['revision'] or not r['basis'] or v.get('basis') != r['basis']:
                    raise ValueError('현재 계획 개정·코드 기준의 검증 통과 기록이 필요합니다.')
                for dep in r['depends']:
                    if find_round(state, dep)['status'] != 'done':
                        raise ValueError('선행 라운드가 완료되지 않았습니다: ' + dep)
            r['status'], r['note'] = args.set, args.note
        elif args.command == 'check':
            r = find_round(state, args.round)
            if args.revision != r['revision'] or not r['basis'] or args.basis != r['basis']:
                raise ValueError('검증 대상의 계획 개정/코드 기준이 현재와 다릅니다. 기준을 다시 확인하세요.')
            ev = evidence(root, args.evidence)
            r['validation'] = {'result': args.result, 'revision': args.revision, 'basis': args.basis,
                               'evidence': ev, 'by': args.by, 'at': stamp()}
            r['status'] = 'fixing' if args.result == 'fail' else 'validating'
            event['check'] = r['validation']
        elif args.command == 'timer':
            duration = parse_duration(args.remaining)
            if duration > state['total_minutes'] * 60:
                raise ValueError('남은 시간이 전체 제한시간보다 큽니다. configure를 먼저 확인하세요.')
            if args.action == 'start' and state['deadline'] is not None:
                raise ValueError('타이머가 이미 시작됐습니다. 실제 시험 값에 맞출 때는 timer sync를 사용하세요.')
            state['deadline'] = time.time() + duration
            event['remaining'] = args.remaining
        elif args.command == 'sync':
            pass
        event['after'] = json.loads(json.dumps(state))
        save_state(root, state, event)
    return '기록 갱신 완료. 상태 변경은 사람의 실행 승인과 별개입니다.'


def readable_doc(root, rel):
    patterns = [r'docs/(PLAN|RESUME)\.md', r'dump\.md', r'validation/PLAN_REVIEW\.md',
                r'works/R[1-9][0-9]*/WORK\.md', r'results/R[1-9][0-9]*/SUMMARY\.md',
                r'validation/R[1-9][0-9]*/CHECK\.md',
                r'validation/R[1-9][0-9]*/runs/[^/]+\.(md|txt|log|json|csv)']
    if not any(re.fullmatch(p, rel) for p in patterns):
        raise ValueError('공개할 작업 문서 경로가 아닙니다.')
    p = safe_path(root, rel)
    if not p.is_file():
        raise ValueError('아직 작성되지 않은 문서입니다.')
    if p.stat().st_size > 1024 * 1024:
        raise ValueError('1 MiB보다 큰 로그는 에디터에서 확인하세요.')
    return p.read_text(encoding='utf-8')


class LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        # The dashboard does not need a reverse-DNS lookup of the local hostname.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def handler_for(root):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, body, kind):
            raw = body.encode('utf-8') if isinstance(body, str) else body
            self.send_response(code)
            self.send_header('Content-Type', kind + '; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            url = urlparse(self.path)
            try:
                if url.path == '/api/state':
                    body = json.dumps(snapshot(read_state(root)), ensure_ascii=False)
                    self.respond(200, body, 'application/json')
                elif url.path == '/api/document':
                    rel = parse_qs(url.query).get('path', [''])[0]
                    self.respond(200, json.dumps({'path': rel, 'text': readable_doc(root, rel)}, ensure_ascii=False), 'application/json')
                elif url.path in {'/', '/app.js', '/style.css'}:
                    filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
                    kind = {'/': 'text/html', '/app.js': 'text/javascript', '/style.css': 'text/css'}[url.path]
                    self.respond(200, (KIT / 'dashboard' / filename).read_bytes(), kind)
                else:
                    self.respond(404, 'Not found', 'text/plain')
            except (ValueError, OSError, json.JSONDecodeError) as e:
                self.respond(400, json.dumps({'error': str(e)}, ensure_ascii=False), 'application/json')
    return Handler


def parser():
    p = argparse.ArgumentParser(description='Happyhouse — Workspace 기록과 조회용 대시보드')
    p.add_argument('--workspace', type=Path, help='기본: _harness/happyhouse의 상위 Workspace')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    c = sub.add_parser('configure')
    c.add_argument('--title'); c.add_argument('--approver')
    c.add_argument('--total-minutes', type=int); c.add_argument('--planning-minutes', type=int); c.add_argument('--reserve-minutes', type=int)
    for command in ['add-round', 'update-round']:
        a = sub.add_parser(command)
        a.add_argument('round'); a.add_argument('--title', required=command == 'add-round')
        a.add_argument('--goal'); a.add_argument('--done-when'); a.add_argument('--minutes', type=int)
        a.add_argument('--difficulty', choices=['미정', '하', '중', '상'], default='미정' if command == 'add-round' else None)
        a.add_argument('--depends', nargs='*', default=[] if command == 'add-round' else None)
        if command == 'update-round':
            a.add_argument('--reason', required=True)
    a = sub.add_parser('select'); a.add_argument('round')
    a = sub.add_parser('checkpoint'); a.add_argument('round'); a.add_argument('--basis', required=True)
    a = sub.add_parser('status'); a.add_argument('round'); a.add_argument('--set', choices=STATUSES, required=True); a.add_argument('--note', default='')
    a = sub.add_parser('check'); a.add_argument('round'); a.add_argument('--result', choices=['pass', 'fail', 'blocked'], required=True)
    a.add_argument('--revision', type=int, required=True); a.add_argument('--basis', required=True); a.add_argument('--evidence', required=True); a.add_argument('--by', required=True)
    a = sub.add_parser('timer'); a.add_argument('action', choices=['start', 'sync']); a.add_argument('--remaining', required=True)
    sub.add_parser('sync'); sub.add_parser('show')
    a = sub.add_parser('serve'); a.add_argument('--host', default='127.0.0.1'); a.add_argument('--port', type=int, default=8765)
    return p


def main():
    args = parser().parse_args()
    if args.workspace:
        root = args.workspace.expanduser().resolve()
    elif KIT.name == 'happyhouse' and KIT.parent.name == '_harness':
        root = KIT.parent.parent
    else:
        raise SystemExit('다른 위치에서 시험할 때는 --workspace PATH를 지정하세요. Workspace/_harness/happyhouse에서는 경로가 자동 결정됩니다.')
    try:
        validate_workspace(root)
        if args.command == 'init':
            print(initialize(root))
        elif args.command == 'show':
            print(json.dumps(snapshot(read_state(root)), ensure_ascii=False, indent=2))
        elif args.command == 'serve':
            read_state(root)
            server = LocalServer((args.host, args.port), handler_for(root))
            print(f'Happyhouse http://{args.host}:{server.server_port} · 읽기 전용 · 종료 Ctrl+C', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        else:
            print(mutate(root, args))
    except (ValueError, OSError, json.JSONDecodeError) as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    main()
