const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function scenario(role='administrador',state='assinada',confirmation=true,code='<img src=x>'){
  const elements=new Map(),calls=[];
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.disabled=false;this.listeners={}}
    append(...nodes){this.children.push(...nodes)}
    before(node){elements.set(node.id,node)}
    replaceChildren(){this.children=[]}
    setAttribute(){}
    addEventListener(event,callback){this.listeners[event]=callback}
    querySelectorAll(tag){return this.children.flatMap(n=>[...(n.tag===tag?[n]:[]),...n.querySelectorAll(tag)])}
    scrollIntoView(){}
    set innerHTML(value){throw new Error('HTML dinâmico proibido')}
  }
  elements.set('nfRecords',new Element('div'));
  const context={document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag)},location:{protocol:'https:'},AbortController,setTimeout,clearTimeout,
    window:{confirm:()=>confirmation,W2Auth:{role:()=>role},W2DB:{state:{client:{auth:{getSession:async()=>({data:{session:{access_token:'test-token'}}})}}}}},
    fetch:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,options,body});return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({ambiente:'homologacao',emissao_oficial_disponivel:false,aviso:'Somente teste',situacao:{estado:body.acao==='transmitir'?'pendente_consulta':state,erros_codigos:[code]},pendencias:[]})}}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('nfse-homologacao.js','utf8'),context);
  await context.window.W2Homologation.open({id:2,updated_at:'version',referencia:'1QMAIO26',dados_fiscais:{nao_enviar:'private'}});
  return {context,calls,root:elements.get('nfHomologationResult')};
}
(async()=>{
  assert.equal((await scenario('financeiro')).calls.length,0);
  const denied=await scenario('administrador','assinada',false);
  await denied.root.querySelectorAll('button').find(n=>n.textContent==='Transmitir somente em homologação').listeners.click();
  assert.equal(denied.calls.length,1);
  const yes=await scenario();
  await yes.root.querySelectorAll('button').find(n=>n.textContent==='Transmitir somente em homologação').listeners.click();
  assert.equal(yes.calls.length,2);assert.equal(yes.calls[1].body.confirmacao,'ENVIAR_SOMENTE_HOMOLOGACAO');
  assert.deepEqual(Object.keys(yes.calls[1].body).sort(),['acao','confirmacao','rascunho_id','versao']);
  assert.equal(yes.calls[1].options.redirect,'error');assert.equal(yes.calls[1].options.cache,'no-store');
  assert.equal(yes.root.querySelectorAll('button').find(n=>n.textContent==='Transmitir somente em homologação').disabled,true);
  assert.ok(yes.root.children.some(n=>n.textContent.includes('<img src=x>')));
  const clock=await scenario('administrador','pendente_consulta',true,'E0008');
  assert.equal(clock.calls.length,1);assert.ok(clock.root.children.some(n=>n.textContent.includes('data/hora de emissão')));
  assert.equal(clock.root.querySelectorAll('button').find(n=>n.textContent==='Transmitir somente em homologação').disabled,true);
  console.log('OK: homologação exige administrador e confirmação separada; resultado incerto bloqueia novo envio e dados fiscais não saem do navegador.');
})().catch(e=>{console.error(e);process.exitCode=1});
