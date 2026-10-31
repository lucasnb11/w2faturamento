(function(root){
  'use strict';
  const confirmations=['prestador_endereco_confirmado','tomador_confirmado','fiscal_confirmado','consolidacao_confirmada','competencia_confirmada'];
  const amounts=['irrf','inss','pis','cofins','csll','pis_debito','cofins_debito','ibs','cbs','desconto_incondicionado','desconto_condicionado'];
  function cents(value){
    let text=String(value??'').trim();
    if(text.includes(','))text=text.replace(/\./g,'').replace(',','.');
    if(!/^\d+(?:\.\d{1,2})?$/.test(text))return null;
    const [whole,fraction='']=text.split('.');
    return BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));
  }
  function localized(value){return `${value/100n},${String(value%100n).padStart(2,'0')}`}
  function recalculate(source,oldAmount,newAmount){
    const f={...source},old=cents(oldAmount),next=cents(newAmount);
    const supported=old!==null&&old>0n&&next!==null&&next>0n&&['desconto_incondicionado','desconto_condicionado'].every(k=>cents(source[k])===null||cents(source[k])===0n);
    for(const key of ['iss_base','pis_cofins_base'])f[key]=supported&&cents(source[key])===old?localized(next):'';
    const rate=cents(source.iss_aliquota),base=cents(f.iss_base);
    f.iss_valor=base!==null&&rate!==null&&rate<=500n?localized((base*rate+5000n)/10000n):'';
    // Zero remains zero; fixed amounts from another invoice require a fresh review.
    for(const key of amounts)f[key]=cents(source[key])===0n?'0,00':'';
    for(const key of confirmations)f[key]=false;
    return f;
  }
  function reuse(row,newAmount,competence){
    const f=recalculate(row.dados_fiscais||{},row.valor_rem,newAmount);
    f.competencia=competence;
    f.orientacao_contabil='';
    f.referencia_perfil={rascunho_id:row.id,versao:row.updated_at||null,referencia:row.referencia||'',aviso:'Cadastro reaproveitado; valores recalculados são de referência e exigem conferência por competência.'};
    return f;
  }
  const api={recalculate,reuse};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.W2NfseProfile=api;
})(typeof window==='object'?window:globalThis);
