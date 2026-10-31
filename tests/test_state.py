"""Synthetic fixtures only; never real approvals or product execution evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(KIT))
import state as s

class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='happyhouse sqlite 한글 ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        s.initialize(self.root)
        self.db=s.connect(self.root)
        self.addCleanup(self.db.close)

    def write(self,path,text):
        p=self.root/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8'); return p

    def apply(self,ops,role='main',rev=None):
        s.apply(self.root,self.db,{'revision':s.revision(self.db) if rev is None else rev,'operations':ops},'fixture '+role,role)

    def setup_round(self,rid='R1',depends=()):
        self.write('problem.md','Synthetic fixture: reject empty input.\n')
        self.write(f'src/{rid}.py','fixture code\n')
        ops=[{'op':'round','id':rid,'title':'빈 입력 거부','budget':'낮음·10분','target':'02:30:00'},
             {'op':'requirement','id':rid+'-req','round':rid,'title':'빈 입력에 오류 표시','source':'[원문](../problem.md)'}]
        if depends: ops.append({'op':'depends','round':rid,'on':list(depends)})
        self.apply(ops)
        self.write(f'works/{rid}/RECORD.md',f'''# Synthetic record
## 기준
- 계획 기준: rev1
- 유효한 승인 범위: fixture only
- 승인 근거: [synthetic](#{rid.lower()}-01)
- 변경 영향: fixture isolated
## 요구 조건
| 항목 | 내용 |
|---|---|
| 목표 | reject empty |
| 완료조건 | error |
| 연결 | earlier fixture |
| 제외 범위 | real data |
## 결정 이력
### {rid}-01
Synthetic fixture approval, not actual authorization.
## 결과
- 추가한 기능: fixture input
- 실행법: fixture only
- 코드 위치: src/{rid}.py
- 검증 근거: [CHECK](validation/CHECK.md)
- 한계: synthetic
''')
        self.write('docs/RESUME.md',f'''# fixture
## 현재
- 단계 / 라운드: {rid}
- 완료 / 미완료: fixture in progress
- 유효한 실행 범위: fixture
- 다음 행동: check
- 근거: [record](../works/{rid}/RECORD.md)
- 갱신 시각 / 작성자: fixture at actual test time
''')
        self.apply([{'op':'case','round':rid,'id':'01','input':'empty','expected':'error','source':'[원문](../../../problem.md)','requirements':[rid+'-req']},
                    {'op':'config','round':rid,'inputs':[f'src/{rid}.py','problem.md'],'exclude':[]},
                    {'op':'review','round':rid,'independent':True,'records_ok':False,'reason':'fixture independent expectations'}],'validator')
        self.apply([{'op':'status','round':rid,'value':'검증 중'}])

    def record_pass(self,rid='R1',verdict='통과',suffix='1'):
        ref=s.capture(self.root,self.db,rid,'fixture validator')
        evidence=f'runs/exec-{suffix}.log'
        self.write(f'works/{rid}/validation/{evidence}','Synthetic run fixture: input=empty expected=error actual=error exit=0\n')
        self.apply([{'op':'run','round':rid,'case':'01','basis':ref,'ran_at':datetime.now(timezone.utc).isoformat(),
                     'dependencies':list(s.checks.inventory(self.root,s.config(self.db,rid))), 'evidence':evidence,
                     'actual':'error','verdict':verdict},
                    {'op':'review','round':rid,'independent':True,'records_ok':True,'reason':'fixture current impact and records reviewed'}],'validator')
        self.write(f'works/{rid}/self.log','Synthetic self-test fixture only\n')
        self.apply([{'op':'self_test','round':rid,'evidence':f'works/{rid}/self.log'}])
        return ref

    def test_init_empty_and_preserves_original(self):
        self.assertEqual(s.checks.readiness(self.root),[])
        self.assertEqual(s.round_ids(self.db),[])
        with self.assertRaises(s.checks.Invalid): s.initialize(self.root)

    def test_pass_and_complete(self):
        self.setup_round(); self.record_pass()
        self.assertEqual(s.full_check(self.root,self.db,'R1'),[])
        s.complete(self.root,self.db,'R1','fixture main')
        self.assertEqual(s.round_row(self.db,'R1')['status'],'완료')
        self.assertIn('| 완료 | 통과 |',(self.root/'docs/PLAN.md').read_text())

    def test_stale_writer_no_lost_update(self):
        rev=s.revision(self.db)
        other=s.connect(self.root)
        try:
            self.apply([{'op':'round','id':'R1','title':'first'}])
            with self.assertRaises(s.checks.Invalid):
                s.apply(self.root,other,{'revision':rev,'operations':[{'op':'round','id':'R2','title':'stale'}]},'fixture','main')
            self.assertEqual(s.round_ids(other),['R1'])
        finally: other.close()

    def test_atomic_invalid_batch(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply([{'op':'round','id':'R1','title':'first'},{'op':'depends','round':'R1','on':['R99']}])
        self.assertEqual(s.round_ids(self.db),[])
        self.assertEqual(s.revision(self.db),0)

    def test_roles(self):
        self.setup_round()
        with self.assertRaises(s.checks.Invalid):
            self.apply([{'op':'review','round':'R1','independent':True,'records_ok':True,'reason':'wrong role'}])
        with self.assertRaises(s.checks.Invalid):
            self.apply([{'op':'status','round':'R1','value':'完成'}],'validator')

    def test_cannot_directly_complete(self):
        self.setup_round()
        with self.assertRaises(s.checks.Invalid): self.apply([{'op':'status','round':'R1','value':'완료'}])
        with self.assertRaises(s.checks.Invalid): s.complete(self.root,self.db,'R1','fixture')

    def test_cycle_rolls_back(self):
        self.apply([{'op':'round','id':'R1','title':'one'},{'op':'round','id':'R2','title':'two'}])
        with self.assertRaises(s.checks.Invalid):
            self.apply([{'op':'depends','round':'R1','on':['R2']},{'op':'depends','round':'R2','on':['R1']}])
        self.assertEqual(s.upstream(self.db,'R1'),[])

    def test_manual_notes_and_checks_survive(self):
        self.setup_round(); self.record_pass()
        p=self.root/'works/R1/WORK.md'
        text=p.read_text().replace('- [ ] 기타','- [x] 기타').replace('**메모:**','**메모:** 사람이 작성한 메모 | 삭제 금지')
        p.write_text(text)
        s.render(self.root,self.db)
        self.assertIn('사람이 작성한 메모 | 삭제 금지',p.read_text())
        self.assertIn('- [x] 기타',p.read_text())
        self.assertTrue(any('관찰' in e for e in s.full_check(self.root,self.db,'R1')))

    def test_generated_edit_detected(self):
        self.setup_round()
        p=self.root/'docs/PLAN.md'
        p.write_text(p.read_text().replace('| 검증 중 |','| 완료 |'))
        with self.assertRaises(s.checks.Invalid): s.render(self.root,self.db)
        self.assertTrue(s.view_issues(self.root,self.db))

    def test_product_change_invalidates_complete(self):
        self.setup_round(); self.record_pass(); s.complete(self.root,self.db,'R1','fixture')
        self.write('src/R1.py','changed')
        self.assertEqual(s.status_display(self.root,self.db,'R1'),'재검증 필요')
        self.assertTrue(s.full_check(self.root,self.db,'R1'))
        s.render(self.root,self.db)
        self.assertIn('재검증 필요',(self.root/'docs/PLAN.md').read_text())

    def test_downstream_inherits_watched_files(self):
        self.setup_round('R1'); self.record_pass('R1'); s.complete(self.root,self.db,'R1','fixture')
        self.setup_round('R2',['R1']); self.record_pass('R2'); s.complete(self.root,self.db,'R2','fixture')
        self.write('src/R1.py','changed shared input')
        self.assertTrue(s.issues(self.root,self.db,'R2'))
        self.record_pass('R1',suffix='2'); s.complete(self.root,self.db,'R1','fixture')
        self.assertTrue(s.issues(self.root,self.db,'R2'))

    def test_requirement_change_stales_runs(self):
        self.setup_round(); self.record_pass()
        self.apply([{'op':'requirement','id':'R1-req','round':'R1','title':'new meaning','source':'[원문](../problem.md)'}])
        self.assertTrue(any('변경' in e for e in s.issues(self.root,self.db,'R1')))

    def test_uncovered_requirement_blocks(self):
        self.setup_round(); self.record_pass()
        self.apply([{'op':'requirement','id':'extra','round':'R1','title':'extra requirement','source':'[원문](../problem.md)'}])
        self.assertTrue(any('extra' in e for e in s.issues(self.root,self.db,'R1')))

    def test_unknown_product_file_blocks(self):
        self.setup_round(); self.record_pass()
        self.write('src/unknown.py','unregistered source')
        self.assertTrue(any('unknown.py' in e for e in s.full_check(self.root,self.db,'R1')))

    def test_immutable_run_history(self):
        self.setup_round(); self.record_pass(verdict='실패')
        self.record_pass(suffix='2')
        self.assertEqual([r[0] for r in self.db.execute('SELECT verdict FROM runs ORDER BY id')],['실패','통과'])
        self.assertEqual(s.full_check(self.root,self.db,'R1'),[])

    def test_modified_evidence_blocks(self):
        self.setup_round(); self.record_pass()
        self.write('works/R1/validation/runs/exec-1.log','tampered')
        self.assertTrue(any('근거가 변경' in e for e in s.issues(self.root,self.db,'R1')))

    def test_modified_basis_blocks(self):
        self.setup_round(); ref=self.record_pass()
        p=self.root/f'works/R1/validation/{ref}'; p.write_text(p.read_text()+' ')
        self.assertTrue(any('JSON이 변경' in e for e in s.issues(self.root,self.db,'R1')))

    def test_export_contains_history_not_second_input(self):
        self.setup_round(); self.record_pass()
        exported=json.loads((self.root/'.happyhouse/state-export.json').read_text())
        self.assertEqual(exported['schema'],1)
        self.assertEqual(len(exported['tables']['runs']),1)
        self.assertTrue(exported['tables']['events'])

    def test_no_silent_import_existing_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/'docs').mkdir()
            (root/'docs/PLAN.md').write_text((KIT/'templates/PLAN.md').read_text().replace('| | | | | | |','| R1 | existing | low | 02:00:00 | 완료 | 통과 |'))
            with self.assertRaises(s.checks.Invalid): s.initialize(root)

    def test_read_only_check(self):
        self.setup_round(); self.record_pass()
        before=(self.root/s.DB).read_bytes(); files={p:p.read_bytes() for p in self.root.rglob('*.md')}
        self.assertEqual(s.full_check(self.root,self.db,'R1'),[])
        self.assertEqual(before,(self.root/s.DB).read_bytes())
        self.assertEqual(files,{p:p.read_bytes() for p in files})

    def test_repair_preserves_human_and_saves_backup(self):
        self.setup_round()
        p=self.root/'works/R1/WORK.md'
        p.write_text(p.read_text().replace('**메모:**','**메모:** 중요한 사용자 원문').replace('**진행:** 검증 중','**진행:** 임의변경'))
        s.render(self.root,self.db,repair=True)
        self.assertIn('중요한 사용자 원문',p.read_text())
        backups=list((self.root/'.happyhouse/recovery').rglob('WORK.md'))
        self.assertTrue(backups)
        self.assertIn('임의변경',backups[0].read_text())

    def test_restore_and_missing_evidence_not_faked(self):
        self.setup_round(); self.record_pass()
        exported=self.root/'.happyhouse/state-export.json'
        with tempfile.TemporaryDirectory() as d:
            import shutil
            root=Path(d).resolve()
            shutil.copytree(self.root/'docs',root/'docs')
            shutil.copytree(self.root/'works',root/'works')
            shutil.copytree(self.root/'src',root/'src')
            shutil.copy(self.root/'problem.md',root/'problem.md')
            s.restore(root,exported)
            db=s.connect(root)
            try:
                self.assertEqual(s.full_check(root,db,'R1'),[])
                (root/'works/R1/validation/runs/exec-1.log').unlink()
                self.assertTrue(s.full_check(root,db,'R1'))
                with self.assertRaises(FileExistsError): s.restore(root,exported)
            finally: db.close()

    def test_bad_restore_removes_partial_db(self):
        payload=json.loads((self.root/'.happyhouse/state-export.json').read_text())
        payload['tables']['meta']=[]
        bad=self.write('bad.json',json.dumps(payload))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            with self.assertRaises((TypeError,s.checks.Invalid)): s.restore(root,bad)
            self.assertFalse((root/s.DB).exists())

    def test_selective_reuse_retains_original_run(self):
        self.setup_round()
        self.write('ui.py','initial UI')
        self.apply([{'op':'config','round':'R1','inputs':['src/R1.py','problem.md','ui.py'],'exclude':[]}],'validator')
        ref=s.capture(self.root,self.db,'R1','fixture validator')
        self.write('works/R1/validation/runs/exec.log','Synthetic fixture only')
        self.apply([{'op':'run','round':'R1','case':'01','basis':ref,'ran_at':datetime.now(timezone.utc).isoformat(),'dependencies':['src/R1.py','problem.md'],'evidence':'runs/exec.log','actual':'error','verdict':'통과'}],'validator')
        old=dict(s.latest_runs(self.db,'R1')['01'])
        self.write('ui.py','changed UI')
        current=s.capture(self.root,self.db,'R1','fixture validator')
        self.assertTrue(s.issues(self.root,self.db,'R1'))
        self.apply([{'op':'reuse','run':old['id'],'against':current,'changed_files':['ui.py'],'reason':'fixture pure parser test does not execute UI'}],'validator')
        self.assertEqual(s.issues(self.root,self.db,'R1'),[])
        self.assertEqual(dict(s.latest_runs(self.db,'R1')['01']),old)

    def test_cli_ready_and_missing_db_fails(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            self.assertEqual(s.main(['ready','--workspace',str(self.root)]),0)
            self.assertEqual(s.main(['check','--all','--workspace',str(self.root)]),1)
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(s.main(['ready','--workspace',d]),1)

    def test_concurrent_writers_use_revision_gate(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(2)
        def writer(rid):
            db=s.connect(self.root)
            try:
                barrier.wait()
                try:
                    s.apply(self.root,db,{'revision':0,'operations':[{'op':'round','id':rid,'title':'fixture concurrent'}]},'fixture','main')
                    return 'saved'
                except s.checks.Invalid:
                    return 'conflict'
            finally: db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(writer,['R1','R2']))
        self.assertEqual(sorted(results),['conflict','saved'])
        self.assertEqual(s.revision(self.db),1)
        self.assertEqual(len(s.round_ids(self.db)),1)

    def test_partial_render_failure_preserves_db_and_recovers(self):
        from unittest.mock import patch
        self.setup_round()
        original=s.atomic_write
        count=[0]
        def interrupted(path,content):
            if path.suffix=='.md':
                count[0]+=1
                if count[0]==2: raise OSError('synthetic interrupted render')
            return original(path,content)
        with patch.object(s,'atomic_write',side_effect=interrupted):
            with self.assertRaises(OSError):
                self.apply([{'op':'status','round':'R1','value':'수정 중'}])
        self.assertEqual(s.round_row(self.db,'R1')['status'],'수정 중')
        exported=json.loads((self.root/'.happyhouse/state-export.json').read_text())
        self.assertEqual(exported['tables']['rounds'][0]['status'],'수정 중')
        s.render(self.root,self.db,repair=True)
        self.assertEqual(s.view_issues(self.root,self.db),[])

if __name__=='__main__': unittest.main()
