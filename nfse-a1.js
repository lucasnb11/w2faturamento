(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  const MAX_FILE=256*1024;
  let certificate=null,ready=false,busy=false;
  const message=text=>{$('nfA1Status').textContent=text};
  function setReady(value){ready=value;['nfA1File','nfA1Password','nfA1Save'].forEach(id=>$(id).disabled=!value||busy)}
  async function call(method,body){
    if(location.protocol!=='https:')throw new Error('O cadastro do A1 exige o site publicado com HTTPS.');
    const client=window.W2DB?.state?.client;
    if(!client)throw new Error('Entre no sistema para configurar o A1.');
    const {data,error}=await client.auth.getSession();
    if(error||!data?.session?.access_token)throw new Error('Sessão expirada. Entre novamente no sistema.');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),55000);
    try{
      const response=await fetch('/api/nfse/certificado',{method,headers:{Authorization:'Bearer '+data.session.access_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,cache:'no-store',credentials:'omit',redirect:'error',mode:'same-origin',signal:controller.signal});
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('Publique a versão completa com a função de cadastro do A1 e configure as variáveis do servidor.');
      const result=await response.json();
      if(!response.ok)throw new Error(result.message||'Não foi possível configurar o A1.');
      return result;
    }finally{clearTimeout(timer)}
  }
  function showMetadata(){
    const root=$('nfA1Metadata');root.replaceChildren();
    if(!certificate){root.textContent='Nenhum certificado cadastrado.';return}
    const info=document.createElement('p');
    const expiry=new Date(certificate.valido_ate),expired=expiry.getTime()<=Date.now();
    info.textContent=`A1 armazenado para o CNPJ 46.167.015/0001-40 · ${expired?'Vencido em':'Validade até'} ${expiry.toLocaleDateString('pt-BR')}. A autorização de emissão ainda depende de integração e homologação.`;
    root.append(info);
  }
  async function refresh(){
    if(busy)return;setReady(false);$('nfA1Refresh').disabled=true;message('Verificando a configuração do servidor…');
    try{const result=await call('GET');certificate=result.certificado||null;setReady(result.servidor_pronto===true);showMetadata();message('Servidor disponível. O arquivo e a senha serão enviados somente ao servidor deste sistema.')}catch(e){setReady(false);message(e.name==='AbortError'?'O servidor não respondeu a tempo.':e.message)}finally{$('nfA1Refresh').disabled=false}
  }
  function base64(bytes){let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text)}
  async function save(event){
    event.preventDefault();if(!ready||busy)return;
    const file=$('nfA1File').files?.[0],password=$('nfA1Password').value;
    if(!file||!password)return message('Selecione o arquivo .pfx/.p12 e informe a senha do A1.');
    if(!/\.(pfx|p12)$/i.test(file.name)||file.size>MAX_FILE||file.size===0)return message('Selecione um arquivo .pfx/.p12 com até 256 KB.');
    if(certificate&&!confirm('Substituir o A1 atualmente cadastrado? O sistema passará a usar o novo certificado quando a integração de emissão for habilitada.'))return;
    busy=true;setReady(ready);$('nfA1Refresh').disabled=true;message('Validando e protegendo o A1 no servidor…');
    try{
      const bytes=new Uint8Array(await file.arrayBuffer()),encoded=base64(bytes);bytes.fill(0);$('nfA1Password').value='';
      const result=await call('POST',{pfx_base64:encoded,senha:password,substituir:!!certificate,versao_anterior:certificate?.updated_at||null});
      certificate=result.certificado;showMetadata();message('A1 salvo com proteção criptográfica. Nenhuma nota foi emitida.');
    }catch(e){message(e.name==='AbortError'?'O envio não foi confirmado. Atualize a situação antes de tentar novamente.':e.message)}finally{busy=false;$('nfA1Password').value='';$('nfA1File').value='';setReady(ready);$('nfA1Refresh').disabled=false}
  }
  function init(){const panel=$('nfA1Panel');if(!panel)return;const admin=window.W2Auth?.role?.()==='administrador';panel.hidden=!admin;if(!admin)return;setReady(false);$('nfA1Form').addEventListener('submit',save);$('nfA1Refresh').addEventListener('click',refresh);message('Verifique a configuração do servidor para habilitar o envio do A1.');showMetadata()}
  window.W2A1={init,refresh};
})();
