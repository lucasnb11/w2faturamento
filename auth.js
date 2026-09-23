(function(){
  const A={user:null,profile:null};
  const $=s=>document.querySelector(s);
  function role(){return String(A.profile?.perfil||'operador').toLowerCase()}
  function allowed(tab){const r=role();if(r==='administrador')return true;if(r==='financeiro')return !['cafs','cidades'].includes(tab);return ['dashboard','cafs','cidades'].includes(tab)}
  function applyAccess(){
    document.querySelectorAll('.tab').forEach(b=>b.hidden=!allowed(b.dataset.tab));
    const canImport=['administrador','financeiro'].includes(role());
    const up=$('#btnUpload'); if(up)up.hidden=!canImport;
    document.body.dataset.role=role();
    $('#userName') && ($('#userName').textContent=A.profile?.nome||A.user?.email||'Usuário');
    $('#userRole') && ($('#userRole').textContent=role());
  }
  async function profile(){
    const c=window.W2DB?.state?.client;if(!c||!A.user)return null;
    let {data,error}=await c.from('perfis').select('*').eq('id',A.user.id).maybeSingle();
    if(error)throw error;
    A.profile=data||{id:A.user.id,nome:A.user.email,perfil:'operador',sistema_faturamento:true,ativo:true};
    if(A.profile.ativo===false||A.profile.sistema_faturamento===false)throw new Error('Usuário sem acesso ao Sistema de Faturamento.');
    return A.profile;
  }
  async function boot(){
    const st=await window.W2DB.init();
    A.user=st.user;
    if(!A.user){showLogin();return false}
    try{await profile();hideLogin();applyAccess();return true}catch(e){showLogin(e.message);return false}
  }
  function showLogin(msg=''){$('#loginGate')?.classList.add('open');$('#loginError') && ($('#loginError').textContent=msg);}
  function hideLogin(){$('#loginGate')?.classList.remove('open')}
  async function login(){
    const email=$('#loginEmail').value.trim(),password=$('#loginPassword').value;
    $('#loginError').textContent='';
    if(!email||!password)return $('#loginError').textContent='Informe e-mail e senha.';
    const c=window.W2DB.state.client;if(!c)return $('#loginError').textContent='Supabase não configurado.';
    const {data,error}=await c.auth.signInWithPassword({email,password});
    if(error)return $('#loginError').textContent='Falha no login: '+error.message;
    A.user=data.user;window.W2DB.state.user=A.user;window.W2DB.state.authenticated=true;
    try{await profile();hideLogin();applyAccess();window.dispatchEvent(new CustomEvent('w2-auth-ready'));}catch(e){await c.auth.signOut();showLogin(e.message)}
  }
  async function logout(){const c=window.W2DB?.state?.client;if(c)await c.auth.signOut();location.reload()}
  document.addEventListener('DOMContentLoaded',()=>{$('#loginBtn')?.addEventListener('click',login);$('#loginPassword')?.addEventListener('keydown',e=>e.key==='Enter'&&login());$('#logoutBtn')?.addEventListener('click',logout)});
  window.W2Auth={A,boot,role,allowed,applyAccess};
})();
