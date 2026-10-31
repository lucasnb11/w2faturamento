const assert=require('node:assert/strict');
const {recalculate,reuse}=require('../nfse-perfil.js');
// Synthetic values exercise rounding independently of any private tax document.
const row={id:20,updated_at:'v1',referencia:'TESTE',valor_rem:'50220.00',dados_fiscais:{
  competencia:'2026-05-16',iss_base:'50220,00',iss_aliquota:'5,00',iss_valor:'2511,00',pis_cofins_base:'50220,00',
  pis:'0,00',cofins:'0,00',irrf:'0,00',inss:'0,00',csll:'0,00',pis_debito:'0,00',cofins_debito:'0,00',
  desconto_incondicionado:'0,00',desconto_condicionado:'0,00',fiscal_confirmado:true,consolidacao_confirmada:true,
  competencia_confirmada:true,tomador_confirmado:true,prestador_endereco_confirmado:true,
  orientacao_contabil:'Apenas da competência anterior',uso_exclusivo_homologacao:true,
  referencia_documental:{arquivo:'exemplo.xml'},ibscbs_tratamento:'Pendente'
}};
const original=JSON.stringify(row);
const f=reuse(row,'15.169,50','2026-06-01');
assert.equal(f.iss_base,'15169,50');assert.equal(f.iss_valor,'758,48');assert.equal(f.pis_cofins_base,'15169,50');
assert.equal(f.competencia,'2026-06-01');assert.equal(f.orientacao_contabil,'');
for(const k of ['fiscal_confirmado','consolidacao_confirmada','competencia_confirmada','tomador_confirmado','prestador_endereco_confirmado'])assert.equal(f[k],false);
assert.equal(f.referencia_documental.arquivo,'exemplo.xml');assert.equal(f.uso_exclusivo_homologacao,true);
assert.equal(f.referencia_perfil.rascunho_id,20);assert.equal(f.ibscbs_tratamento,'Pendente');
assert.equal(JSON.stringify(row),original);
assert.equal(reuse(row,'11700,50','2026-06-01').iss_valor,'585,03');
assert.equal(reuse(row,'12951.00','2026-06-01').iss_valor,'647,55');
for(const value of ['', 'abc','-10','NaN','1,234','Infinity']){
 const x=reuse(row,value,'2026-06-01');assert.equal(x.iss_base,'');assert.equal(x.iss_valor,'');assert.equal(x.pis_cofins_base,'');
}
const unsupported=recalculate({...row.dados_fiscais,iss_base:'40000,00',irrf:'100,00',desconto_condicionado:'10,00'},row.valor_rem,'10000,00');
assert.equal(unsupported.iss_base,'');assert.equal(unsupported.iss_valor,'');assert.equal(unsupported.irrf,'');assert.equal(unsupported.desconto_condicionado,'');
assert.equal(recalculate({...row.dados_fiscais,iss_aliquota:'6'},row.valor_rem,'10000').iss_valor,'');
assert.equal(recalculate({...row.dados_fiscais,iss_aliquota:'2,50'},row.valor_rem,'10000').iss_valor,'250,00');
assert.equal(recalculate(row.dados_fiscais,row.valor_rem,'0').iss_base,'');
console.log('OK: perfil mantém referência, não confirma fiscal e recalcula bases integrais/ISS com arredondamento decimal.');
