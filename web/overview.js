const byId=id=>document.getElementById(id);

async function loadOverview(){
  const button=byId('refresh');
  button.disabled=true;
  try{
    const response=await fetch('/api/public/dashboard',{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    byId('totalJobs').textContent=data.totals.jobs;
    byId('totalPages').textContent=data.totals.pages;
    byId('blocked').textContent=data.totals.blocked;
    byId('online').textContent=data.devices.online;
    byId('deviceSummary').textContent=`共 ${data.devices.total} 台；警告 ${data.devices.warning}、離線 ${data.devices.offline}`;
    byId('statusTitle').textContent='PrintGuard 運作正常';
    byId('statusMessage').textContent=`資料更新時間：${new Date().toLocaleString('zh-TW',{hour12:false})}`;
    byId('statusDot').className='status-dot online';
  }catch(error){
    byId('statusTitle').textContent='暫時無法取得總覽';
    byId('statusMessage').textContent=`請稍後重新整理（${error.message}）`;
    byId('statusDot').className='status-dot offline';
  }finally{
    button.disabled=false;
  }
}

byId('refresh').addEventListener('click',loadOverview);
loadOverview();
setInterval(loadOverview,30000);
