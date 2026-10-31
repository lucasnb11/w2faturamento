(function(){
  'use strict';
  let busy=false,draft=null,root=null;
  const labels={nao_reservada:'Sem DPS reservada',reservada:'Numeração reservada',falha_local:'Preparação interrompida',assinada:'DPS assinada localmente',enviando:'Envio em andamento',pendente_consulta:'Resultado pendente de consulta',autorizada:'Autorizada em homologação',rejeitada:'Rejeitada em homologação'};
  function text(value,tag='p'){const node=document.createElement(tag);node.textContent=value;root.append(node);return node}
  async function request(action){
    if(location.protocol!=='https:')throw new Error('Esta operação exige HTTPS.');
    const client=window.W2DB?.state?.client;
    if(!client)throw new Error('Entre novamente no sistema.');
    const {data,error}=await client.auth.getSession();
    if(error||!data?.session?.access_token)throw new Error('Entre novamente no sistema.');
    const body={acao:action,rascunho_id:draft.id,versao:draft.updated_at};
    if(action==='transmitir')body.confirmacao='ENVIAR_SOMENTE_HOMOLOGACAO';
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),125000);
    try{
      const response=await fetch('/api/nfse/homologacao',{method:'POST',mode:'same-origin',credentials:'omit',cache:'no-store',redirect:'error',signal:abort.signal,
        headers:{'Content-Type':'application/json',Authorization:'Bearer '+data.session.access_token},body:JSON.stringify(body)});
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('A função de homologação ainda não está disponível nesta publicação.');
      const result=await response.json();
      if(!response.ok)throw new Error(result.message||'Não foi possível concluir a operação.');
      return result;
    }finally{clearTimeout(timer)}
  }
  function button(label,action,disabled){const node=document.createElement('button');node.type='button';node.className='ghost';node.textContent=label;node.disabled=disabled;node.addEventListener('click',()=>run(action));return node}
  function render(result){
    if(result.ambiente!=='homologacao'||result.emissao_oficial_disponivel!==false)throw new Error('Resposta de homologação inesperada.');
    root.replaceChildren();text(`Homologação · ${draft.referencia}`,'h3');text(result.aviso);
    const s=result.situacao||{},state=s.estado;
    text(labels[state]||'Situação não identificada.');
    if(s.dps_id)text(`DPS: ${s.dps_id} · Série ${s.serie} · Número ${s.numero}.`);
    if(s.retorno_http)text(`Último retorno da API: HTTP ${s.retorno_http}.`);
    if(Array.isArray(s.erros_codigos)&&s.erros_codigos.length)text(`Códigos: ${s.erros_codigos.join(', ')}.`);
    if(Array.isArray(s.erros_codigos)&&s.erros_codigos.includes('E0008'))text('E0008: a API considerou a data/hora de emissão da DPS posterior à do processamento. Consulte o retorno desta tentativa; o XML assinado e o histórico serão preservados, sem reenvio automático.');
    if(s.chave_acesso)text(`Chave da NFS-e de homologação: ${s.chave_acesso}`);
    if(state==='pendente_consulta'||state==='enviando')text('O envio não será repetido. Consulte o retorno para conciliar esta DPS.');
    if(state==='rejeitada')text('A API rejeitou a assinatura ou o certificado. A tentativa foi preservada para análise; não há reenvio automático.');
    if(state==='assinada')text('Assinatura conferida localmente. A aceitação fiscal ainda será validada pela API de homologação.');
    if(result.pendencias?.length){text('Confira e salve os dados fiscais antes de preparar a DPS. Nenhum novo número foi reservado.');const list=document.createElement('ul');for(const issue of result.pendencias){const item=document.createElement('li');item.textContent=issue.mensagem;list.append(item)}root.append(list)}
    const actions=document.createElement('div');actions.className='nf-buttons';actions.append(
      button('Preparar DPS de homologação','preparar',!['nao_reservada','reservada','falha_local'].includes(state)),
      button('Transmitir somente em homologação','transmitir',state!=='assinada'),
      button('Consultar retorno','conciliar',!['enviando','pendente_consulta','autorizada','rejeitada'].includes(state)),
      button('Baixar XML de homologação','baixar_xml',state!=='autorizada'));
    root.append(actions);
    text('A preparação reserva numeração de teste e assina a DPS no servidor. A transmissão exige uma confirmação separada.');
  }
  async function run(action){
    if(busy)return;
    if(window.W2Auth?.role?.()!=='administrador')return text('Somente administradores podem operar a homologação.');
    if(action==='transmitir'&&!window.confirm(`Enviar a DPS de ${draft.referencia} exclusivamente para HOMOLOGAÇÃO? Este teste não emite nota fiscal de produção.`))return;
    busy=true;root.querySelectorAll('button').forEach(b=>b.disabled=true);
    const progress=text('Processando no servidor. Aguarde até dois minutos.');
    try{
      const result=await request(action);
      if(action==='baixar_xml'){
        if(!/^DPS[0-9]{42}-homologacao\.xml$/.test(result.nome||'')||typeof result.xml_base64!=='string'||result.xml_base64.length>750000)throw new Error('Resposta de download inesperada.');
        const bytes=Uint8Array.from(atob(result.xml_base64),c=>c.charCodeAt(0));
        const url=URL.createObjectURL(new Blob([bytes],{type:'application/xml'}));
        const link=document.createElement('a');link.href=url;link.download=result.nome;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        render(await request('status'));
      }else render(result);
    }catch(e){progress.textContent=e.name==='AbortError'?'O tempo de espera terminou. Consulte a situação; não repita a transmissão.':e.message;
      const refresh=button('Atualizar situação','status',false);root.append(refresh);
    }finally{busy=false;root.scrollIntoView({behavior:'smooth',block:'start'})}
  }
  async function open(saved){
    if(busy)return;
    draft=saved;root=document.getElementById('nfHomologationResult');
    if(!root){root=document.createElement('section');root.id='nfHomologationResult';root.className='nf-card';root.setAttribute('role','status');root.setAttribute('aria-live','polite');document.getElementById('nfRecords').before(root)}
    root.replaceChildren();text(`Homologação · ${saved.referencia}`,'h3');await run('status');
  }
  window.W2Homologation={open};
})();
