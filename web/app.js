const $ = s => document.querySelector(s); let state = {};
const policyNames = {any:'不限模式', mono:'僅黑白', color:'僅彩色'};
const colorModes={auto:'自動偵測',mono:'實體僅黑白',color:'支援彩色'},duplexModes={auto:'自動偵測',simplex:'實體僅單面',duplex:'支援雙面'};
async function load(){ const [dashboard,violations]=await Promise.all([fetch('/api/dashboard').then(r=>r.json()),fetch('/api/violations').then(r=>r.json())]);state={...dashboard,violations};render();syncReportPrinters();loadReport(); }
function render(){ const {printers,jobs,totals}=state;
  $('#totalJobs').textContent=totals.jobs; $('#totalPages').textContent=totals.pages; $('#blocked').textContent=totals.blocked; $('#online').textContent=printers.filter(p=>p.status==='online').length;
  $('#printerGrid').innerHTML=printers.map(p=>`<article class="printer"><div class="printer-head"><div class="printer-icon">▣</div><div><h3>${esc(p.name)}</h3><p>${esc(p.driver_name||p.location)}</p><small>設備設定：${esc(p.profile_status||'待同步')}</small></div><i class="status ${p.status}"></i></div><div class="policy">${['any','mono','color'].map(x=>`<button class="${p.policy===x?'selected':''}" onclick="setPolicy(${p.id},'${x}')">${policyNames[x]}</button>`).join('')}</div>${p.profile_fingerprint?`<div class="profile-controls"><label>彩色能力<select onchange="setProfile(${p.id},'color_mode',this.value)">${Object.entries(colorModes).map(([v,n])=>`<option value="${v}" ${p.color_mode===v?'selected':''}>${n}</option>`).join('')}</select></label><label>雙面能力<select onchange="setProfile(${p.id},'duplex_mode',this.value)">${Object.entries(duplexModes).map(([v,n])=>`<option value="${v}" ${p.duplex_mode===v?'selected':''}>${n}</option>`).join('')}</select></label><label class="check"><input type="checkbox" ${p.trust_color_standard?'checked':''} onchange="setProfile(${p.id},'trust_color_standard',this.checked)">信任標準彩色欄位</label><label class="check"><input type="checkbox" ${p.trust_duplex_standard?'checked':''} onchange="setProfile(${p.id},'trust_duplex_standard',this.checked)">信任標準雙面欄位</label></div>`:'<small>等待 Agent 建立設備指紋</small>'}</article>`).join('');
  $('#jobRows').innerHTML=jobs.length?jobs.map(j=>`<tr><td>${esc(j.document)}<small>${esc(j.ad_identity||j.username)}</small><small>${jobLabel(j)}</small></td><td>${esc(j.printer_name)}</td><td>${j.pages} 頁 × ${j.copies||1} 份<small>${j.duplex_known?(j.sheets||j.pages)+' 張紙':'紙張數未知'}</small></td><td>${j.color_known?(j.effective_color?'彩色':'黑白'):'色彩未知'}<small>${j.duplex_known?(j.duplex?'雙面':'單面'):'面數未知'}</small></td><td><span class="badge ${j.status}">${j.status==='blocked'?'已攔截':j.status==='completed'?'已完成':'佇列中'}</span>${j.reason?`<small>${esc(j.reason)}</small>`:''}</td></tr>`).join(''):'<tr><td colspan="5">尚無列印工作</td></tr>';
  $('#violationRows').innerHTML=(state.violations||[]).length?state.violations.map(j=>`<tr><td>${new Date(j.created_at).toLocaleString('zh-TW',{hour12:false})}</td><td>${esc(j.ad_identity||j.username)}</td><td>${esc(j.printer_name)}</td><td>${esc(j.document)}</td><td>${policyNames[j.applied_policy]||esc(j.applied_policy||'未知')}</td><td>${esc(j.reason||'政策拒絕')}</td></tr>`).join(''):'<tr><td colspan="6">目前沒有已阻擋工作</td></tr>';
}
async function loadReport(){
  const group=$('#reportGroup').value,data=await fetch(`/api/reports/usage?${reportParams()}`).then(r=>r.json());
  const metrics=['工作','總頁數','黑白','彩色','單面','雙面','紙張','資料待補'];
  const headers=group==='user'?['資料來源','AD 使用者',...metrics,'使用印表機數']:group==='printer'?['資料來源','印表機',...metrics,'使用人數']:['資料來源','AD 使用者','印表機',...metrics];
  document.querySelector('.report thead tr').innerHTML=headers.map(x=>`<th>${x}</th>`).join('');
  const values=x=>[x.jobs,x.pages,x.mono_pages,x.color_pages,x.simplex_pages,x.duplex_pages,x.sheets,x.unknown_jobs];
  const cells=x=>group==='user'?[sourceName(x),x.identity,...values(x),x.printer_count]:group==='printer'?[sourceName(x),x.printer,...values(x),x.user_count]:[sourceName(x),x.identity,x.printer,...values(x)];
  $('#reportRows').innerHTML=data.length?data.map(x=>`<tr>${cells(x).map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">查無符合資料</td></tr>`;
}
function sourceName(x){return x.source==='device-import'?'印表機匯入':'PrintGuard'}
async function setPolicy(id,policy){ await fetch(`/api/printers/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({policy})}); load(); }
async function setProfile(id,key,value){await fetch(`/api/device-profiles/${id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value,profile_status:'verified'})});load()}
$('#refresh').onclick=load; $('#reportRefresh').onclick=loadReport;
const exportBar=document.createElement('div');exportBar.style.cssText='display:flex;align-items:end;gap:10px;flex-wrap:wrap;margin:0 0 18px';exportBar.innerHTML='<label>資料來源<select id="reportSource"><option value="printguard">PrintGuard 即時資料</option><option value="device">印表機 CSV 匯入</option><option value="combined">兩種來源並列</option></select></label><label>統計方式<select id="reportGroup"><option value="user">使用者彙總</option><option value="user_printer">使用者／印表機明細</option><option value="printer">印表機彙總</option></select></label><label>報表期間<select id="reportPeriod"><option value="daily">日報</option><option value="monthly">月報</option></select></label><label id="dayWrap">日期<input type="date" id="dailyDate"></label><label id="monthWrap" style="display:none">月份<input type="month" id="monthlyDate"></label><label>印表機<select id="reportPrinter"><option value="">全部印表機</option></select></label><label>使用者<input id="exportUser" placeholder="選填，例如 user01"></label><button id="reportQuery">查詢</button><button id="summaryCsv">匯出使用者彙總 CSV</button><button id="detailCsv">匯出使用者／印表機明細 CSV</button>';document.querySelector('.report .table-wrap').before(exportBar);
const today=new Date(); $('#dailyDate').value=today.toLocaleDateString('en-CA'); $('#monthlyDate').value=today.toLocaleDateString('en-CA').slice(0,7);
function reportParams(group=$('#reportGroup').value){const period=$('#reportPeriod').value,p=new URLSearchParams({period,group,source:$('#reportSource').value,user:$('#exportUser').value,printer_id:$('#reportPrinter').value});p.set(period==='daily'?'date':'month',period==='daily'?$('#dailyDate').value:$('#monthlyDate').value);return p}
function syncReportPrinters(){const select=$('#reportPrinter'),selected=select.value;select.innerHTML='<option value="">全部印表機</option>'+state.printers.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');select.value=selected}
$('#reportPeriod').onchange=()=>{const monthly=$('#reportPeriod').value==='monthly';$('#dayWrap').style.display=monthly?'none':'block';$('#monthWrap').style.display=monthly?'block':'none'};
$('#reportQuery').onclick=loadReport;$('#reportGroup').onchange=loadReport;
$('#summaryCsv').onclick=()=>window.location=`/api/reports/export.csv?${reportParams('user')}`;
$('#detailCsv').onclick=()=>window.location=`/api/reports/export.csv?${reportParams('user_printer')}`;
const importPanel=document.createElement('div');importPanel.className='import-panel';
importPanel.innerHTML='<div><p class="eyebrow">實體設備資料</p><h3>匯入印表機工作 CSV</h3><p>支援 SHARP 工作明細；重複匯入及重疊期間資料會自動略過。也可將定期匯出的 CSV 放入 C:\\ProgramData\\PrintGuard\\imports，系統每分鐘自動匯入。</p></div><div class="import-actions"><input id="deviceCsv" type="file" accept=".csv,text/csv"><button id="deviceImport">開始匯入</button></div><p id="importResult"></p><div id="importHistory"></div>';
document.querySelector('.report .section-title').after(importPanel);
async function loadImportHistory(){const data=await fetch('/api/device-imports').then(r=>r.json());$('#importHistory').innerHTML=data.length?'<small>最近匯入：'+data.slice(0,3).map(x=>`${esc(x.filename)}（新增 ${x.inserted_rows}、重複 ${x.duplicate_rows}）`).join('　')+'</small>':'<small>尚未匯入印表機 CSV</small>'}
$('#deviceImport').onclick=async()=>{const file=$('#deviceCsv').files[0];if(!file){$('#importResult').textContent='請先選擇 CSV 檔案';return}const button=$('#deviceImport');button.disabled=true;$('#importResult').textContent='匯入中…';try{const r=await fetch('/api/device-imports',{method:'POST',headers:{'Content-Type':'text/csv','X-Filename':encodeURIComponent(file.name)},body:await file.arrayBuffer()}),data=await r.json();$('#importResult').textContent=r.ok?`完成：共 ${data.total_rows} 筆，新增 ${data.inserted_rows} 筆，略過重複 ${data.duplicate_rows} 筆，錯誤 ${data.error_rows} 筆`:`匯入失敗：${data.error}`;loadImportHistory();loadReport()}catch(e){$('#importResult').textContent=`匯入失敗：${e.message}`}finally{button.disabled=false}};
loadImportHistory();
document.querySelector('nav').insertAdjacentHTML('beforeend','<a href="#reports">報表查詢／匯出</a>');document.querySelector('.report').id='reports';
document.querySelector('nav').insertAdjacentHTML('beforeend','<a href="#violations">政策攔截紀錄</a>');
document.querySelector('#jobs thead th:nth-child(3)').textContent='頁數／份數';
const compactStyle=document.createElement('style');compactStyle.textContent='.two-col{grid-template-columns:1fr;align-items:start}#jobs{width:100%;display:flex;flex-direction:column;min-height:0}#jobs th{padding-top:7px;padding-bottom:7px}#jobs td{padding-top:9px;padding-bottom:9px}#jobs .table-wrap{max-height:440px;overflow:auto}#jobs td:first-child{max-width:360px}.policy-note{color:#a66b00;font-size:11px;margin:10px 0 0}.profile-controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.profile-controls label{font-size:11px}.profile-controls select{padding:7px;font-size:11px}';document.head.appendChild(compactStyle);
document.querySelector('#printers .eyebrow').textContent='裝置政策';
document.querySelector('#printers .section-title').insertAdjacentHTML('beforeend','<p class="policy-note">政策會由已連線的 Print Server Native Agent 每 30 秒同步；強制測試仍只允許 _test 佇列</p>');
function jobLabel(j){const parts=(j.source_event_id||'').split('|'),jobId=parts.length>=3?parts[parts.length-2]:(j.source_event_id||j.id);const time=new Date(j.created_at).toLocaleString('zh-TW',{hour12:false});return `Job #${jobId} · ${time}`}
function esc(x){ const d=document.createElement('div'); d.textContent=x; return d.innerHTML; }
// Sidebar page navigation keeps each management area in its own viewport.
const main=$('main'),overview=document.createElement('div');
overview.id='overview';overview.className='page-view';
main.insertBefore(overview,main.firstChild);
overview.append(main.querySelector('header'),main.querySelector('.stats'));
const pageSections={overview,printers:$('#printers'),jobs:$('.two-col'),reports:$('#reports'),violations:$('#violations')};
Object.entries(pageSections).forEach(([name,element])=>{if(element){element.classList.add('page-view');element.dataset.page=name}});
const pageNames={overview:'總覽',printers:'印表機設定',jobs:'列印工作',reports:'報表分析',violations:'政策攔截'};
$('nav').innerHTML=Object.entries(pageNames).map(([key,label])=>`<a href="#${key}" data-route="${key}">${label}</a>`).join('');
function showPage(){
  const requested=location.hash.slice(1),page=pageSections[requested]?requested:'overview';
  Object.entries(pageSections).forEach(([name,element])=>element?.classList.toggle('active',name===page));
  document.querySelectorAll('nav a').forEach(link=>link.classList.toggle('active',link.dataset.route===page));
  if(page==='reports')loadReport();
  window.scrollTo({top:0,behavior:'instant'});
}
window.addEventListener('hashchange',showPage);showPage();
const pageStyle=document.createElement('style');
pageStyle.textContent='.page-view{display:none}.page-view.active{display:block}.page-view.two-col.active{display:grid}nav a{cursor:pointer}.page-view>.section-title:first-child{margin-bottom:8px}.import-panel{border:1px solid #dfe6f2;background:#f8faff;border-radius:12px;padding:16px;margin:0 0 18px}.import-panel h3{margin:4px 0}.import-panel p{color:#687894;font-size:12px}.import-actions{display:flex;align-items:end;gap:10px}.import-actions input{flex:1;background:#fff}.import-actions button{white-space:nowrap}#importResult{min-height:18px;color:#285fc8}@media(max-width:1000px){.page-view.two-col.active{display:block}}';
document.head.appendChild(pageStyle);
load(); setInterval(load,5000);
