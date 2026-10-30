const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
async function scenario(role,action='validate'){
  const elements=new Map();
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.dataset={}}
    setAttribute(){}
    append(el){this.children.push(el)}
    before(el){elements.set(el.id,el)}
    replaceChildren(){this.children=[]}
    scrollIntoView(){}
    set innerHTML(value){throw new Error('HTML dinâmico não é permitido na resposta fiscal')}
  }
  elements.set('nfRecords',new Element('div'));
  elements.set('nfConnectionTest',new Element('button'));
  const calls=[];
  const context={document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag)},
    location:{protocol:'https:'},AbortController,setTimeout,clearTimeout,
    window:{W2Auth:{role:()=>role},W2DB:{state:{client:{auth:{getSession:async()=>({data:{session:{access_token:'test-token'}}})}}}}},
    fetch:async(url,options)=>{calls.push({url,options});return{ok:true,headers:{get:()=> 'application/json'},json:async()=>({
      transmitido:false,emissao_oficial_disponivel:false,xsd_valido:false,a1_dentro_validade:true,
      ambiente:'homologacao',documentacao_http:200,consulta_convenio_http:200,contrato_recepcao_identificado:true,
      aviso:'Nenhuma DPS transmitida.',pendencias:[{mensagem:'<img src=x onerror=alert(1)>'}]
    })}}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('nfse-integracao.js','utf8'),context);
  if(action==='connection')await context.window.W2NfseIntegration.testConnection();
  else await context.window.W2NfseIntegration.validate({id:3,updated_at:'version-1',referencia:'1QMAIO26',dados_fiscais:{cliente:'não enviar'}});
  return {calls,elements};
}
(async()=>{
  const {calls,elements}=await scenario('administrador');assert.equal(calls.length,1);
  const {url,options}=calls[0];assert.equal(url,'/api/nfse/integracao');
  assert.equal(options.mode,'same-origin');assert.equal(options.credentials,'omit');
  assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');
  assert.deepEqual(JSON.parse(options.body),{rascunho_id:3,versao:'version-1'});
  const panel=elements.get('nfIntegrationResult');
  assert.ok(panel.children.some(el=>el.tag==='ul'&&el.children[0].textContent.startsWith('<img')));
  assert.equal((await scenario('financeiro')).calls.length,0);
  const connection=await scenario('administrador','connection');
  assert.equal(connection.calls[0].url,'/api/nfse/conexao');
  assert.deepEqual(JSON.parse(connection.calls[0].options.body),{acao:'testar_conexao'});
  assert.equal(connection.calls[0].options.redirect,'error');
  assert.equal(connection.elements.get('nfConnectionTest').disabled,false);
  assert.equal((await scenario('financeiro','connection')).calls.length,0);
  console.log('OK: validação envia somente versão do rascunho, exige administrador e trata mensagens como texto.');
})().catch(e=>{console.error(e);process.exitCode=1});
