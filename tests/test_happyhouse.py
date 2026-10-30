import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('happyhouse', SOURCE / 'happyhouse.py')
hh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hh)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_command(self, *args):
        return hh.mutate(self.root, hh.parser().parse_args(list(args)))

    def setup_round(self, rid='R1', *args):
        hh.initialize(self.root)
        self.run_command('add-round', rid, '--title', '입력 검사', *args)

    def pass_round(self, rid='R1'):
        self.run_command('checkpoint', rid, '--basis', 'code-1')
        r = hh.find_round(hh.read_state(self.root), rid)
        rel = f'validation/{rid}/runs/01.txt'
        (self.root / rel).write_text('input=[]; expected=error; actual=error; exit=0', encoding='utf8')
        self.run_command('check', rid, '--result', 'pass', '--revision', str(r['revision']), '--basis', 'code-1', '--evidence', rel, '--by', 'validator')
        self.run_command('status', rid, '--set', 'done')

    def test_init_preserves_originals_and_repeat_work(self):
        for name in ['README.md', 'AGENTS.md', 'dump.md']:
            (self.root / name).write_text('original-' + name)
        hh.initialize(self.root)
        plan = self.root / 'docs/PLAN.md'
        plan.write_text(plan.read_text() + '\n사람이 작성한 메모\n')
        hh.initialize(self.root)
        for name in ['README.md', 'AGENTS.md', 'dump.md']:
            self.assertEqual((self.root / name).read_text(), 'original-' + name)
        self.assertIn('사람이 작성한 메모', plan.read_text())
        state = hh.read_state(self.root)
        self.assertEqual(state['rounds'], [])
        self.assertIsNone(state['deadline'])
        self.assertEqual(list((self.root / 'works').iterdir()), [])

    def test_unknown_collision_is_preserved_before_writes(self):
        (self.root / 'docs').mkdir()
        (self.root / 'docs/PLAN.md').write_text('unrelated')
        with self.assertRaises(ValueError): hh.initialize(self.root)
        self.assertEqual((self.root / 'docs/PLAN.md').read_text(), 'unrelated')
        self.assertFalse((self.root / '.happyhouse').exists())

    def test_symlink_target_rejected(self):
        outside = self.root / 'outside'; outside.mkdir()
        (self.root / 'docs').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): hh.initialize(self.root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_harness_cannot_be_workspace(self):
        with self.assertRaises(ValueError): hh.validate_workspace(SOURCE)

    def test_round_creation_and_duplicate_preservation(self):
        self.setup_round()
        for rel in ['works/R1/WORK.md', 'validation/R1/CHECK.md', 'results/R1/SUMMARY.md']:
            self.assertTrue((self.root / rel).is_file())
        work = self.root / 'works/R1/WORK.md'
        work.write_text('real discussion')
        with self.assertRaises(ValueError): self.run_command('add-round', 'R1', '--title', 'duplicate')
        self.assertEqual(work.read_text(), 'real discussion')

    def test_cycle_and_missing_dependency_do_not_save(self):
        self.setup_round()
        self.run_command('add-round', 'R2', '--title', 'connect', '--depends', 'R1')
        before = hh.read_state(self.root)
        with self.assertRaises(ValueError): self.run_command('update-round', 'R1', '--depends', 'R2', '--reason', 'bad cycle')
        with self.assertRaises(ValueError): self.run_command('add-round', 'R3', '--title', 'missing', '--depends', 'R8')
        self.assertEqual(hh.read_state(self.root), before)
        self.assertFalse((self.root / 'works/R3').exists())

    def test_countdown_budget_and_unknown_time(self):
        self.setup_round('R1', '--minutes', '35')
        self.run_command('add-round', 'R2', '--title', 'unknown')
        s = hh.snapshot(hh.read_state(self.root))
        self.assertEqual(s['rounds'][0]['target_remaining'], '02:05:00')
        self.assertIsNone(s['rounds'][1]['target_remaining'])
        self.run_command('update-round', 'R2', '--minutes', '110', '--reason', 'budget')
        self.assertTrue(hh.snapshot(hh.read_state(self.root))['over_budget'])
        self.assertIn('초과', (self.root / 'docs/PLAN.md').read_text())

    def test_timer_is_explicit_and_syncable(self):
        hh.initialize(self.root)
        self.run_command('timer', 'start', '--remaining', '02:40:00')
        self.assertAlmostEqual(hh.snapshot(hh.read_state(self.root))['remaining_seconds'], 9600, delta=2)
        with self.assertRaises(ValueError): self.run_command('timer', 'start', '--remaining', '03:00:00')
        with self.assertRaises(ValueError): self.run_command('timer', 'sync', '--remaining', '04:00:00')
        self.run_command('timer', 'sync', '--remaining', '02:00:00')
        self.assertAlmostEqual(hh.snapshot(hh.read_state(self.root))['remaining_seconds'], 7200, delta=2)
        for invalid in ['-1:00:00', '00:60:00', '5 min']:
            with self.assertRaises(ValueError): hh.parse_duration(invalid)

    def test_done_requires_current_executed_evidence(self):
        self.setup_round()
        with self.assertRaises(ValueError): self.run_command('status', 'R1', '--set', 'done')
        self.pass_round()
        s = hh.read_state(self.root)
        self.assertEqual(s['rounds'][0]['status'], 'done')
        self.assertEqual(s['rounds'][0]['validation']['by'], 'validator')
        self.assertNotIn('approved', s['rounds'][0])

    def test_code_change_invalidates_transitive_results(self):
        self.setup_round()
        self.run_command('add-round', 'R2', '--title', 'connect', '--depends', 'R1')
        self.run_command('add-round', 'R3', '--title', 'end', '--depends', 'R2')
        for rid in ['R1', 'R2', 'R3']: self.pass_round(rid)
        self.run_command('checkpoint', 'R1', '--basis', 'code-2')
        for r in hh.read_state(self.root)['rounds']:
            self.assertEqual(r['validation']['result'], 'stale')
            self.assertNotEqual(r['status'], 'done')
        self.assertTrue((self.root / 'validation/R1/runs/01.txt').exists())
        events = (self.root / '.happyhouse/events.jsonl').read_text()
        self.assertIn('code-1', events)
        self.assertIn('code-2', events)

    def test_plan_revision_rejects_old_result(self):
        self.setup_round(); self.pass_round()
        self.run_command('update-round', 'R1', '--goal', 'new contract', '--reason', 'user changed input')
        self.assertEqual(hh.read_state(self.root)['rounds'][0]['revision'], 2)
        with self.assertRaises(ValueError):
            self.run_command('check', 'R1', '--result', 'pass', '--revision', '1', '--basis', 'code-1', '--evidence', 'validation/R1/runs/01.txt', '--by', 'validator')

    def test_evidence_missing_empty_outside_rejected(self):
        self.setup_round()
        (self.root / 'validation/R1/runs/empty.txt').touch()
        for path in ['validation/R1/runs/missing.txt', 'validation/R1/runs/empty.txt', '../secret.txt', 'README.md']:
            with self.assertRaises(ValueError): hh.evidence(self.root, path)

    def test_lock_prevents_overlapping_writer(self):
        hh.initialize(self.root)
        with hh.lock(self.root):
            with self.assertRaises(ValueError): self.run_command('configure', '--title', 'overlap')
        self.run_command('configure', '--title', 'after lock')
        self.assertEqual(hh.read_state(self.root)['title'], 'after lock')

    def test_fixed_layout_cli_and_source_unchanged(self):
        kit = self.root / '_harness/happyhouse'
        shutil.copytree(SOURCE, kit, ignore=shutil.ignore_patterns('__pycache__', '.git'))
        before = {str(p.relative_to(kit)): p.read_bytes() for p in kit.rglob('*') if p.is_file()}
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        p = subprocess.run([sys.executable, str(kit / 'happyhouse.py'), 'init'], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / 'docs/PLAN.md').exists())
        after = {str(p.relative_to(kit)): p.read_bytes() for p in kit.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_http_is_read_only_and_allowlisted(self):
        self.setup_round()
        server = hh.LocalServer(('127.0.0.1', 0), hh.handler_for(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for path in ['/', '/app.js', '/style.css', '/api/state', '/api/document?path=docs/PLAN.md']:
                with urlopen(base + path, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertGreater(len(response.read()), 0)
            for path in ['/api/document?path=../secrets', '/api/document?path=.env', '/happyhouse.py']:
                with self.assertRaises(HTTPError) as ctx: urlopen(base + path, timeout=5)
                ctx.exception.close()
            with self.assertRaises(HTTPError) as ctx: urlopen(Request(base + '/api/state', data=b'{}', method='POST'), timeout=5)
            self.assertEqual(ctx.exception.code, 501)
            ctx.exception.close()
            outside = self.root / 'secret.txt'; outside.write_text('secret')
            (self.root / 'validation/R1/runs/leak.txt').symlink_to(outside)
            with self.assertRaises(HTTPError) as ctx: urlopen(base + '/api/document?path=validation/R1/runs/leak.txt', timeout=5)
            ctx.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
