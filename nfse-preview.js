(function(){
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money=value=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  function amount(value){
    let text=String(value??'').trim().replace(/R\$|\s/g,'');
    if(!text)return null;
    if(text.includes(','))text=text.replace(/\./g,'').replace(',','.');
    const number=Number(text);return Number.isFinite(number)?number:null;
  }
  function cell(label,value='—',span=1,cls=''){
    return `<div class="danf-cell ${cls}" style="grid-column:span ${span}"><small>${esc(label)}</small><span>${esc(value===''||value===undefined||value===null?'Pendente':value)}</span></div>`;
  }
  const title=value=>`<h3 class="danf-block-title">${esc(value)}</h3>`;
  const block=content=>`<section class="danf-block"><div class="danf-grid">${content}</div></section>`;
  function render(row,defaults,totals){
    const f={...defaults,...(row.dados_fiscais||{})};
    f.tomador_nome=row.tomador_nome||f.tomador_nome;f.tomador_cnpj=row.tomador_cnpj||f.tomador_cnpj;
    const t=totals({...row,dados_fiscais:f});
    const tax=key=>amount(f[key])===null?'Pendente':money(amount(f[key]));
    const percent=key=>amount(f[key])===null?'Pendente':amount(f[key]).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})+' %';
    const date=/^\d{4}-\d{2}-\d{2}$/.test(f.competencia||'')?f.competencia.split('-').reverse().join('/'):'Pendente';
    const ibsNA=f.ibscbs_tratamento==='Não aplicável conforme validação contábil';
    const ibsValue=key=>ibsNA?'—':tax(key);
    const ibsMeta=value=>ibsNA?'—':value||'Pendente';
    const ibs=amount(f.ibs),cbs=amount(f.cbs);
    const ibsTotal=ibsNA?0:ibs!==null&&cbs!==null?ibs+cbs:null;
    const totalRet=t.retained===null?'Pendente':money(t.retained);
    const liquid=t.net===null?'Pendente':money(t.net);
    const codeDescription=f.codigo_nacional?.replace(/\D/g,'')==='260101'?'Serviços de coleta, remessa ou entrega de correspondências, documentos, objetos, bens ou valores, inclusive pelos correios e suas agências franqueadas.':'Descrição do código: conferir enquadramento fiscal.';
    const approximate=['federais','estaduais','municipais'].map(name=>`${name[0].toUpperCase()+name.slice(1)}: ${percent('total_tributos_'+name)}`).join('; ');
    const social=f.pis_cofins_retencao==='0 · Não retidos'?'0 - PIS/COFINS/CSLL Não Retidos':'Pendente';
    const provider=block(title('PRESTADOR / FORNECEDOR')+cell('CNPJ / CPF / NIF','46.167.015/0001-40')+cell('Indicador Municipal (Inscrição)',f.prestador_im)+cell('Telefone',f.prestador_telefone||'—')
      +cell('Nome / Nome Empresarial','W2 TRANSPORTES LTDA',2)+cell('Município / Sigla UF','Ananindeua / PA')+cell('Código IBGE / CEP',`${f.prestador_municipio_ibge||'Pendente'} / ${f.prestador_cep||'Pendente'}`)
      +cell('Endereço',f.prestador_endereco,2)+cell('E-mail',f.prestador_email||'—',2)
      +cell('Simples Nacional na Data de Competência',f.simples)+cell('Regime de Apuração Tributária pelo SN',f.regime,3));
    const customer=block(title('TOMADOR / ADQUIRENTE')+cell('CNPJ / CPF / NIF',f.tomador_cnpj)+cell('Indicador Municipal (Inscrição)',f.tomador_im||'—')+cell('Telefone',f.tomador_telefone||'—')
      +cell('Nome / Nome Empresarial',f.tomador_nome,2)+cell('Município / Sigla UF',f.tomador_municipio)+cell('Código IBGE / CEP',`${f.tomador_municipio_ibge||'Pendente'} / ${f.tomador_cep||'Pendente'}`)
      +cell('Endereço',f.tomador_endereco,2)+cell('E-mail',f.tomador_email||'—',2));
    const service=block(title('SERVIÇO PRESTADO')+cell('Código de Tributação Nacional/Municipal',`${f.codigo_nacional||'Pendente'} / ${f.codigo_municipal||'—'}`)+cell('Código da NBS',f.nbs)+cell('Local da Prestação / Sigla UF / País',`${f.local_prestacao||'Pendente'} / —`)
      +`<p class="danf-code-description">${esc(codeDescription)}</p>`+cell('Descrição do Serviço',row.descricao,4));
    const municipal=block(title('TRIBUTAÇÃO MUNICIPAL (ISSQN)')+cell('Tipo de Tributação do ISSQN',f.iss_tipo)+cell('Município / Sigla UF / País de Incidência do ISSQN',`${f.municipio_incidencia||'Pendente'} / —`,2)
      +cell('BC ISSQN',tax('iss_base'))+cell('Alíquota Aplicada',percent('iss_aliquota'))+cell('Retenção do ISSQN',f.iss_retencao)+cell('ISSQN Apurado',tax('iss_valor')));
    const federal=block(title('TRIBUTAÇÃO FEDERAL (EXCETO CBS)')+cell('IRRF',tax('irrf'))+cell('Contribuição Previdenciária - Retida',tax('inss'))+cell('Contribuições Sociais - Retidas',['pis','cofins','csll'].every(k=>amount(f[k])!==null)?money(['pis','cofins','csll'].reduce((s,k)=>s+amount(f[k]),0)):'Pendente')
      +cell('PIS - Débito Apuração Própria',tax('pis_debito'))+cell('COFINS - Débito Apuração Própria',tax('cofins_debito'))+cell('Descrição Contrib. Sociais - Retidas',social,2));
    const ibsBlock=block(title('TRIBUTAÇÃO IBS/CBS')+cell('CST / cClassTrib',ibsMeta(f.cst&&f.cclass?`${f.cst} / ${f.cclass}`:null))+cell('Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF',ibsMeta(f.indicador_operacao?`${f.indicador_operacao} / ${f.municipio_incidencia_ibge||'Pendente'} / ${f.municipio_incidencia||'Pendente'}`:null),2)
      +cell('Exclusões e Reduções da Base de Cálculo',ibsValue('ibs_exclusoes'))+cell('Base de Cálculo Após Exclusões e Reduções',ibsValue('ibs_base'))+cell('Red. Alíquota IBS / Red. Alíquota CBS',ibsMeta())+cell('Alíquota - IBS UF / IBS Mun',ibsMeta())
      +cell('Alíq. Efetiva Municipal - IBS',ibsMeta())+cell('Valor Apurado Municipal - IBS',ibsValue('ibs_municipal'))+cell('Alíq. Efetiva Estadual - IBS',ibsMeta())+cell('Valor Apurado Estadual - IBS',ibsValue('ibs_estadual'))
      +cell('Valor Total Apurado - IBS',ibsValue('ibs'))+cell('Alíquota - CBS',ibsMeta())+cell('Alíquota Efetiva - CBS',ibsMeta())+cell('Valor Total Apurado - CBS',ibsValue('cbs')));
    const values=block(title('VALOR TOTAL DA NFS-e')+cell('VALOR DA OPERAÇÃO / SERVIÇO',money(row.valor_rem))+cell('Desconto Incondicionado',tax('desconto_incondicionado'))+cell('Desconto Condicionado',tax('desconto_condicionado'))
      +cell('Total das Retenções (ISSQN / Federais)',totalRet)+cell('VALOR LÍQUIDO DA NFS-e',liquid)+cell('Total do IBS/CBS',ibsTotal===null?'Pendente':money(ibsTotal))+cell('VALOR LÍQUIDO DA NFS-e + IBS/CBS',t.net===null||ibsTotal===null?'Pendente':money(t.net+ibsTotal),1,'danf-total'));
    return `<article class="danf-sheet"><div class="danf-warning">PRÉVIA DE TESTE · SEM VALIDADE FISCAL · NÃO EMITIDA</div>
      <header class="danf-header"><img src="https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/logos-da-nfs-e/Logo%20-%20NFS-e%20-%20Horizontal.png" alt="NFS-e — Nota Fiscal de Serviço eletrônica"><div><h2>DANFSe v2.0 · prévia</h2><p>Documento Auxiliar da NFS-e</p></div><div>Município: Ananindeua - PA<br>Ambiente Gerador: simulação local<br>Tipo de Ambiente: homologação / prévia</div></header>
      <section class="danf-identification"><div class="danf-key"><small>CHAVE DE ACESSO DA NFS-e</small><span>Não gerada — rascunho sem emissão</span></div><div class="danf-identification-grid">
      ${cell('NÚMERO DA NFS-e','Não emitida')+cell('COMPETÊNCIA DA NFS-e',date)+cell('DATA E HORA DA EMISSÃO DA NFS-e','Não transmitida')+cell('NÚMERO DA DPS','Não atribuído')+cell('SÉRIE DA DPS','Não atribuída ao rascunho')+cell('DATA E HORA DA EMISSÃO DA DPS','Não assinada')+cell('EMITENTE DA NFS-e','Prestador',1,'danf-shaded')+cell('SITUAÇÃO DA NFS-e','Rascunho de teste',1,'danf-shaded')+cell('FINALIDADE','Conferência · sem emissão')}
      </div><aside class="danf-authenticity"><div class="danf-qr-placeholder">SEM QR<br>FISCAL</div><p>A chave de acesso e o QR Code fiscal estarão disponíveis somente após autorização da NFS-e.</p></aside></section>
      ${provider}${customer}<div class="danf-strip">DESTINATÁRIO DA OPERAÇÃO: ${esc(f.destinatario_proprio?'PRÓPRIO TOMADOR':'PENDENTE DE CONFERÊNCIA')}</div><div class="danf-strip">${esc(f.intermediario_nome?'INTERMEDIÁRIO: '+f.intermediario_nome+' · '+(f.intermediario_documento||'Pendente'):'INTERMEDIÁRIO DA OPERAÇÃO NÃO INFORMADO')}</div>
      ${service}${municipal}${federal}${ibsBlock}${values}
      <section class="danf-complementary"><h3>INFORMAÇÕES COMPLEMENTARES</h3><p>${esc(f.complementares||'Não informadas.')}</p><p>Totais aproximados dos Tributos: ${esc(approximate)}.</p><p>Referência: ${esc(row.referencia)} · Código do contratante: ${esc(row.codigo_contratante||'—')}.</p><p class="danf-validation">Conferência fiscal: ${esc(f.fiscal_confirmado?'confirmada pelo usuário':'pendente')}. Consolidação por quinzena: ${esc(f.consolidacao_confirmada?'confirmada pelo usuário':'pendente')}. Data de competência: ${esc(f.competencia_confirmada?'conferida pelo usuário':'pendente de confirmação')}.</p></section>
      <footer class="danf-receipt"><div><b>DATA CIENTIFICAÇÃO:</b><span>—</span></div><div><b>IDENTIFICAÇÃO E ASSINATURA</b><span>Prévia para conferência</span></div><div><b>Nº NFS-e / CHAVE NFS-e</b><span>Não emitida / Não gerada</span></div></footer><p class="danf-footer">PRÉVIA SEM VALIDADE FISCAL. Nenhuma DPS foi assinada ou transmitida. Campos pendentes não representam valores zero.</p></article>`;
  }
  window.W2Danfse={render};
})();
