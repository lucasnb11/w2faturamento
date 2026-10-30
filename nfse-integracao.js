(function(){
  'use strict';
  let busy=false;
  function output(){
    let panel=document.getElementById('nfIntegrationResult');
    if(!panel){
      panel=document.createElement('section');panel.id='nfIntegrationResult';panel.className='nf-card';
      panel.setAttribute('role','status');panel.setAttribute('aria-live','polite');
      document.getElementById('nfRecords').before(panel);
    }
    panel.replaceChildren();return panel;
  }
  function text(root,value,tag='p'){const el=document.createElement(tag);el.textContent=value;root.append(el);return el}
  async function requestJson(path,body,timeout){
    if(location.protocol!=='https:')throw new Error('Esta operação exige HTTPS.');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
    try{
      const client=window.W2DB?.state?.client;
      if(!client)throw new Error('Entre novamente no sistema.');
      const {data,error}=await client.auth.getSession();
      if(error||!data?.session?.access_token)throw new Error('Entre novamente no sistema.');
      const response=await fetch(path,{method:body===undefined?'GET':'POST',mode:'same-origin',credentials:'omit',redirect:'error',cache:'no-store',
        signal:controller.signal,headers:{'Content-Type':'application/json',Authorization:'Bearer '+data.session.access_token},body:body===undefined?undefined:JSON.stringify(body)});
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('Esta função ainda não está disponível nesta publicação.');
      const result=await response.json();
      if(!response.ok)throw new Error(result.message||'Não foi possível concluir a operação.');
      return result;
    }finally{clearTimeout(timer)}
  }
  async function validate(draft){
    if(busy)return;
    const root=output();
    text(root,`Integração · rascunho salvo ${draft.referencia}`,'h3');
    if(window.W2Auth?.role?.()!=='administrador'){text(root,'Entre como administrador para validar a integração.');return}
    text(root,'Verificando os dados salvos no servidor. Alterações ainda não salvas no formulário não entram nesta validação.');
    busy=true;
    try{
      const result=await requestJson('/api/nfse/integracao',{rascunho_id:draft.id,versao:draft.updated_at},25000);
      if(result.transmitido!==false||result.emissao_oficial_disponivel!==false||!Array.isArray(result.pendencias))throw new Error('Resposta de validação inesperada.');
      text(root,result.aviso);
      text(root,result.a1_dentro_validade?'A1 cadastrado e dentro da validade.':'A1 ausente ou fora da validade.');
      text(root,result.xsd_valido?'Estrutura da simulação compatível com o XSD oficial de homologação de 20/10/2026.':'A simulação ainda não passou pela validação do XSD oficial.');
      if(result.pendencias.length){
        text(root,`${result.pendencias.length} pendência(s) no rascunho salvo.`);
        const list=document.createElement('ul');
        for(const issue of result.pendencias)text(list,issue.mensagem,'li');
        root.append(list);
      }
      text(root,'Assinatura, reserva de numeração, transmissão e homologação com a API nacional ainda precisam ser concluídas. Nenhuma nota foi emitida.');
      root.scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){text(root,e.name==='AbortError'?'A validação excedeu o tempo de resposta. Nenhuma DPS foi transmitida.':e.message)}
    finally{busy=false}
  }
  async function testConnection(){
    if(busy)return;
    const root=output();text(root,'Conexão nacional · homologação','h3');
    if(window.W2Auth?.role?.()!=='administrador'){text(root,'Entre como administrador para testar a conexão.');return}
    const button=document.getElementById('nfConnectionTest');
    busy=true;if(button)button.disabled=true;
    const progress=text(root,'Testando o A1 cadastrado no servidor. A consulta não emite notas. Aguarde até 50 segundos.');
    try{
      const result=await requestJson('/api/nfse/conexao',{acao:'testar_conexao'},50000);
      if(result.transmitido!==false||result.emissao_oficial_disponivel!==false||result.ambiente!=='homologacao')throw new Error('Resposta de diagnóstico inesperada.');
      text(root,result.aviso);
      text(root,`Documentação da Sefin: HTTP ${result.documentacao_http??'sem resposta'}. Documentação de parâmetros do ADN: HTTP ${result.parametros_documentacao_http??'sem resposta'}.`);
      text(root,result.consulta_convenio_rota_confirmada?`Consulta municipal pela rota declarada no ADN: ${result.consulta_convenio_rota} · HTTP ${result.consulta_convenio_http??'sem resposta'}.`:'A rota de consulta do convênio municipal ainda não foi identificada na documentação do ADN.');
      if(Array.isArray(result.consulta_convenio_erro_codigos)&&result.consulta_convenio_erro_codigos.length)text(root,`Códigos retornados pela API municipal: ${result.consulta_convenio_erro_codigos.join(', ')}.`);
      text(root,result.contrato_recepcao_identificado?'Campo de recepção identificado na documentação retornada pela API.':'O contrato de recepção ainda não foi confirmado pela documentação da API.');
      text(root,result.a1_prova_assinatura_local===true?'A1: assinatura de desafio aleatório conferida localmente. Este teste não assina DPS e não valida o perfil XMLDSig da API.':'A prova local de assinatura com o A1 ainda não foi confirmada.');
      text(root,'A habilitação do contribuinte, o perfil de assinatura, a numeração e a transmissão ainda precisam ser validados.');
    }catch(e){text(root,e.name==='AbortError'?'O diagnóstico excedeu o tempo de resposta. Nenhuma DPS foi enviada.':e.message)}
    finally{progress.textContent='Tentativa de conexão finalizada.';busy=false;if(button)button.disabled=false;root.scrollIntoView({behavior:'smooth',block:'start'})}
  }
  async function preparation(){
    if(busy)return;
    const root=output();text(root,'Preparação da DPS · homologação','h3');
    if(window.W2Auth?.role?.()!=='administrador'){text(root,'Entre como administrador para verificar a preparação.');return}
    const button=document.getElementById('nfPreparationTest');
    busy=true;if(button)button.disabled=true;
    try{
      const result=await requestJson('/api/nfse/integracao',undefined,50000);
      if(result.ambiente!=='homologacao'||result.emissao_oficial_disponivel!==false||result.transmissao_disponivel!==false)throw new Error('Resposta de preparação inesperada.');
      text(root,result.a1_dentro_validade?'A1 cadastrado e dentro da validade.':'Pendência: cadastre um A1 da W2 dentro da validade.');
      const numbering=result.numeracao;
      text(root,numbering?.numeracao_pronta===true?`Série de homologação: ${numbering.serie}. Próximo número: ${numbering.proximo_numero}. Nenhum número foi reservado nesta consulta.`:'Pendência: definir série própria de homologação entre 1 e 49.999 e conferir o próximo número livre.');
      text(root,result.possui_rascunho===true?'Há rascunho salvo. Abra-o e use Validar integração para conferir os dados fiscais.':'Pendência: salve um rascunho da quinzena escolhida para homologação e confirme os dados fiscais.');
      text(root,'A série 70.000 da nota de exemplo pertence ao emissor web e não será reutilizada pelo aplicativo.');
      text(root,'O perfil XMLDSig e a habilitação ainda dependem de validação na API. Esta consulta não reserva números, não assina DPS e não emite notas.');
    }catch(e){text(root,e.name==='AbortError'?'A consulta excedeu o tempo de resposta. Tente novamente.':e.message)}
    finally{busy=false;if(button)button.disabled=false;root.scrollIntoView({behavior:'smooth',block:'start'})}
  }
  function init(){
    const button=document.getElementById('nfConnectionTest');
    if(button&&!button.dataset.bound){button.dataset.bound='true';button.addEventListener('click',testConnection)}
    const preparationButton=document.getElementById('nfPreparationTest');
    if(preparationButton&&!preparationButton.dataset.bound){preparationButton.dataset.bound='true';preparationButton.addEventListener('click',preparation)}
  }
  window.W2NfseIntegration={validate,testConnection,preparation,init};
})();
