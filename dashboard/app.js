'use strict';
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function inline(text, path) {
  const tokens = [];
  const protect = value => { tokens.push(value); return `\u0000${tokens.length - 1}\u0000`; };
  let content = String(text).replace(/\u0000/g, '').replace(/`([^`]+)`/g, (_, code) => protect(`<code>${escapeHTML(code)}</code>`));
  content = content.replace(/\[([^\]]+)\]\(([^\s)]+)\)/g, (_, label, target) => {
    try {
      const url = new URL(target, `http://workspace.local/${path}`);
      if (!['http:', 'https:'].includes(url.protocol)) return label;
      if (url.origin === 'http://workspace.local') {
        const rel = decodeURIComponent(url.pathname.slice(1));
        return protect(`<a href="/api/document?path=${encodeURIComponent(rel)}" data-doc="${escapeHTML(rel)}">${escapeHTML(label)}</a>`);
      }
      return protect(`<a href="${escapeHTML(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHTML(label)} ↗</a>`);
    } catch { return label; }
  });
  return escapeHTML(content).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\u0000(\d+)\u0000/g, (_, n) => tokens[Number(n)]);
}
function markdown(text, path) {
  const lines = text.split('\n'), out = [];
  const cells = line => line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(x => x.trim().replace(/\\\|/g, '|'));
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*<!--.*-->\s*$/.test(line) || !line.trim()) continue;
    if (line.startsWith('```')) {
      const code = [];
      while (++i < lines.length && !lines[i].startsWith('```')) code.push(lines[i]);
      out.push(`<pre><code>${escapeHTML(code.join('\n'))}</code></pre>`); continue;
    }
    const heading = /^(#{1,6}) (.+)$/.exec(line);
    if (heading) { out.push(`<h${heading[1].length}>${inline(heading[2], path)}</h${heading[1].length}>`); continue; }
    if (line.startsWith('|') && /^\|[\s:|\-]+\|\s*$/.test(lines[i+1] || '')) {
      const head = cells(line).map(x => `<th>${inline(x,path)}</th>`).join('');
      const rows = []; i++;
      while (i+1 < lines.length && lines[i+1].startsWith('|')) rows.push(`<tr>${cells(lines[++i]).map(x=>`<td>${inline(x,path)}</td>`).join('')}</tr>`);
      out.push(`<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`); continue;
    }
    if (/^[-*] /.test(line)) {
      const items = [];
      do { items.push(`<li>${inline(lines[i].slice(2).replace(/^\[ \] /, '☐ ').replace(/^\[x\] /i, '☑ '),path)}</li>`); i++; } while (i < lines.length && /^[-*] /.test(lines[i]));
      i--; out.push(`<ul>${items.join('')}</ul>`); continue;
    }
    if (line.startsWith('> ')) { out.push(`<blockquote>${inline(line.slice(2),path)}</blockquote>`); continue; }
    if (/^---+$/.test(line)) { out.push('<hr>'); continue; }
    out.push(`<p>${inline(line,path)}</p>`);
  }
  return out.join('\n');
}

if (typeof document !== 'undefined') {
  const $ = id => document.getElementById(id);
  let state, viewed, tab = 'work', overridePath = null, timerBase, receivedAt, lastGood, busy = false;
  const cache = new Map();
  async function json(url) {
    const response = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(8000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '읽기 실패');
    return data;
  }
  function detailPath() {
    if (overridePath) return overridePath;
    if (tab === 'dump') return 'dump.md';
    if (tab === 'review') return 'validation/PLAN_REVIEW.md';
    if (!viewed) return null;
    return {work:`works/${viewed}/WORK.md`,check:`validation/${viewed}/CHECK.md`,result:`results/${viewed}/SUMMARY.md`}[tab];
  }
  async function renderDoc(id, path) {
    const el = $(id);
    if (!path) { el.textContent = '라운드 계획이 정해지면 이곳에 현재 작업과 대화가 표시됩니다.'; cache.delete(id); return; }
    try {
      const data = await json('/api/document?path=' + encodeURIComponent(path));
      if (id === 'detail' && path !== detailPath()) return;
      const key = path + '\n' + data.text;
      if (cache.get(id) !== key) { el.innerHTML = markdown(data.text, path); cache.set(id,key); }
    } catch (error) { el.textContent = `${path}: ${error.message}`; cache.delete(id); }
  }
  async function renderDetail() {
    const path = detailPath();
    $('doc-path').textContent = path || '라운드 미정';
    $('detail-title').textContent = tab === 'dump' ? '자유 메모' : tab === 'review' ? '계획 검토' : `${viewed || ''} 현재 작업`;
    await renderDoc('detail', path);
  }
  function renderState(s) {
    $('project').textContent = s.title;
    $('context').textContent = `진행 라운드 ${s.current_round || '미정'} · 완료 ${s.rounds.filter(r=>r.status==='done').length}/${s.rounds.length} · 승인자 ${s.approver || '미지정'}`;
    $('budget').textContent = `총 ${s.total_minutes}분 · 계획 ${s.planning_minutes}분 · 마무리 확보 ${s.reserve_minutes}분 · 배정 합계 ${s.allocated_minutes}분`;
    $('warning').hidden = !s.over_budget;
    $('warning').textContent = '전체 제한시간보다 배정 시간이 많습니다. 주담당과 범위 또는 시간을 조정하세요.';
    $('empty').hidden = s.rounds.length !== 0;
    if (!viewed || !s.rounds.some(r=>r.id===viewed)) viewed = s.current_round || s.rounds[0]?.id;
    $('selector').innerHTML = s.rounds.length ? s.rounds.map(r=>`<option value="${escapeHTML(r.id)}" ${r.id===viewed?'selected':''}>${escapeHTML(r.id)}</option>`).join('') : '<option>미정</option>';
    $('rounds').innerHTML = s.rounds.map(r=>`<tr class="${r.id===viewed?'selected':''}"><td><button class="round-button" data-round="${escapeHTML(r.id)}">${escapeHTML(r.id)}</button>${r.id===s.current_round?'<small>현재 진행</small>':''}</td><td>${escapeHTML(r.goal)}<small>${escapeHTML(r.done_when)}</small></td><td>${escapeHTML(r.depends.join(', ') || '—')}</td><td>${escapeHTML(r.difficulty)}</td><td>${r.minutes===null?'미정':escapeHTML(r.minutes)+'분'}</td><td>${escapeHTML(r.target_remaining || '미정')}</td><td><span class="pill ${escapeHTML(r.status)}">${escapeHTML(r.status_label)}</span></td><td><span class="pill ${escapeHTML(r.validation.result)}">${escapeHTML(r.validation_label)}</span></td></tr>`).join('');
    $('updated').textContent = `작업 기록 갱신 ${s.updated_at}`;
  }
  function clock() {
    if (timerBase === null || timerBase === undefined) { $('timer').textContent = '시작 전'; return; }
    const n = Math.max(0, Math.ceil(timerBase - (Date.now()-receivedAt)/1000));
    $('timer').textContent = [Math.floor(n/3600),Math.floor(n%3600/60),n%60].map(v=>String(v).padStart(2,'0')).join(':');
  }
  async function refresh() {
    if (busy) return; busy = true;
    try {
      state = await json('/api/state'); timerBase = state.remaining_seconds; receivedAt = Date.now(); lastGood = new Date().toLocaleTimeString('ko-KR');
      renderState(state); clock();
      $('connection').textContent = `● 연결됨 · 확인 ${lastGood}`; $('connection').className = '';
      await Promise.all([renderDoc('plan','docs/PLAN.md'),renderDetail()]);
    } catch { $('connection').textContent = `연결 끊김 · 마지막 확인 ${lastGood || '없음'} · 타이머는 추정값`; $('connection').className='error'; }
    finally { busy = false; }
  }
  function selectRound(rid) { viewed=rid; overridePath=null; if(state)renderState(state); renderDetail(); }
  $('selector').addEventListener('change', e => selectRound(e.target.value));
  $('rounds').addEventListener('click', e => { const b=e.target.closest('[data-round]'); if(b)selectRound(b.dataset.round); });
  $('tabs').addEventListener('click', e => {
    const b=e.target.closest('[data-tab]'); if(!b)return;
    tab=b.dataset.tab; overridePath=null;
    for(const item of $('tabs').querySelectorAll('button')) item.classList.toggle('active',item===b);
    renderDetail();
  });
  document.addEventListener('click', e => { const a=e.target.closest('[data-doc]'); if(a){e.preventDefault();overridePath=a.dataset.doc;renderDetail();} });
  refresh(); setInterval(refresh,3000); setInterval(clock,1000);
}
if (typeof module !== 'undefined') module.exports = {markdown, inline};
