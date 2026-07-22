const $=selector=>document.querySelector(selector);let setup=false;
async function initialize(){
  const status=await fetch('/api/auth/status').then(response=>response.json());
  if(status.authenticated){location.replace('/');return}
  setup=!status.configured;
  $('#loginTitle').textContent=setup?'建立第一位管理員':'管理員登入';
  $('#loginHint').textContent=setup?'首次使用請自行建立帳號，以及至少 10 個字元的密碼。':'登入後才能查看列印工作、報表與管理設定。';
  $('#loginSubmit').textContent=setup?'建立並登入':'登入';
  if(setup)$('#username').value='admin';
}
$('#loginForm').onsubmit=async event=>{
  event.preventDefault();$('#loginError').textContent='';$('#loginSubmit').disabled=true;
  try{
    const response=await fetch(setup?'/api/auth/setup':'/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('#username').value,password:$('#password').value})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'認證失敗');location.replace('/');
  }catch(error){$('#loginError').textContent=error.message;$('#loginSubmit').disabled=false}
};
initialize().catch(error=>{$('#loginError').textContent=`無法連線：${error.message}`});
