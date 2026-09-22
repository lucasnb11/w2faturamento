(() => {
  const cfg=window.W2_SUPABASE_CONFIG||{};
  const screen=document.getElementById('authScreen'), setup=document.getElementById('authSetup');
  const form=document.getElementById('loginForm'), msg=document.getElementById('loginMessage');
  const emailInput=document.getElementById('loginEmail'), passInput=document.getElementById('loginPassword');
  const userEmail=document.getElementById('userEmail'), logout=document.getElementById('logoutButton');
  const configured=cfg.url&&cfg.anonKey&&!cfg.url.includes('COLE_AQUI')&&!cfg.anonKey.includes('COLE_AQUI');
  let validating=false;
  function setMessage(t,ok=false){if(!msg)return;msg.textContent=t||'';msg.className='auth-message '+(ok?'ok':'');}
  function showLogin(){document.body.classList.add('auth-pending');document.body.classList.remove('auth-ok');screen.style.display='flex';if(userEmail)userEmail.textContent='';}
  function showApp(session,perfil){document.body.classList.remove('auth-pending');document.body.classList.add('auth-ok');screen.style.display='none';if(userEmail)userEmail.textContent=(perfil?.nome||session?.user?.email||'Usuário')+(perfil?.perfil?' • '+perfil.perfil:'');window.W2_USER_PROFILE=perfil;}
  if(!configured||!window.supabase){setup.hidden=false;form.querySelectorAll('input,button').forEach(x=>x.disabled=true);setMessage('Configure o Supabase para liberar o acesso.');return;}
  const client=window.supabase.createClient(cfg.url,cfg.anonKey,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}});
  window.w2Supabase=client;
  async function authorize(session){
    if(!session){showLogin();return false;}
    if(validating)return false;
    validating=true;
    try{
      const {data:perfil,error}=await client.from('perfis').select('id,nome,email,perfil,ativo,acesso_dashboard').eq('id',session.user.id).maybeSingle();
      if(error){console.error('Falha ao consultar perfil:',error);await client.auth.signOut();showLogin();setMessage('Não foi possível validar seu perfil de acesso.');return false;}
      if(!perfil){await client.auth.signOut();showLogin();setMessage('Usuário sem perfil cadastrado.');return false;}
      if(perfil.ativo===false){await client.auth.signOut();showLogin();setMessage('Usuário desativado.');return false;}
      if(perfil.acesso_dashboard!==true){await client.auth.signOut();showLogin();setMessage('Usuário sem acesso ao Dashboard CAF.');return false;}
      showApp(session,perfil);setMessage('');return true;
    } finally {validating=false;}
  }
  client.auth.getSession().then(({data})=>authorize(data.session));
  client.auth.onAuthStateChange((event,session)=>{if(event==='SIGNED_OUT')showLogin();else if(session)authorize(session);});
  form.addEventListener('submit',async e=>{e.preventDefault();setMessage('Entrando...');const {data,error}=await client.auth.signInWithPassword({email:emailInput.value.trim(),password:passInput.value});if(error){setMessage('E-mail ou senha inválidos.');return;}passInput.value='';await authorize(data.session);});
  logout.addEventListener('click',async()=>{await client.auth.signOut();showLogin();});
})();
