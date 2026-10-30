const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ids=['nfA1Panel','nfA1Status','nfA1Metadata','nfA1File','nfA1Password','nfA1Save','nfA1Refresh','nfA1Form'];
const els=Object.fromEntries(ids.map(id=>[id,{
  value:'',disabled:false,hidden:false,handlers:{},children:[],
  addEventListener(k,fn){this.handlers[k]=fn},
  replaceChildren(){this.children=[]},append(x){this.children.push(x)}
}]));
let requests=[];
const context={
  window:{
    W2Auth:{role:()=> 'administrador'},
    W2DB:{state:{client:{auth:{getSession:async()=>({data:{session:{access_token:'test-session-token'}}})}}}}
  },
  document:{getElementById:id=>els[id],createElement:()=>({textContent:''})},
  location:{protocol:'https:'},setTimeout,clearTimeout,AbortController,Uint8Array,Date,
  confirm:()=>true,btoa:s=>Buffer.from(s,'binary').toString('base64'),
  fetch:async(url,options)=>{
    requests.push({url,...options});
    return {
      ok:true,headers:{get:()=> 'application/json'},
      json:async()=>({servidor_pronto:true,certificado:options.method==='POST'?{cnpj:'46167015000140',valido_ate:'2027-10-30',updated_at:'test'}:null})
    };
  }
};
Object.defineProperty(context,'localStorage',{get(){throw new Error('Não armazenar segredos no navegador')}});
vm.createContext(context);
vm.runInContext(fs.readFileSync(new URL('../nfse-a1.js',`file://${__filename}`),'utf8'),context);
(async()=>{
  context.window.W2A1.init();assert(els.nfA1File.disabled);
  await context.window.W2A1.refresh();assert(!els.nfA1File.disabled);
  els.nfA1File.files=[{name:'teste.pfx',size:3,arrayBuffer:async()=>Uint8Array.from([1,2,3]).buffer}];
  els.nfA1File.value='file';els.nfA1Password.value='senha apenas de teste';
  await els.nfA1Form.handlers.submit({preventDefault(){}});
  const post=requests.find(r=>r.method==='POST');assert(post);
  assert.equal(post.url,'/api/nfse/certificado');assert.equal(post.redirect,'error');
  assert.equal(post.mode,'same-origin');assert.equal(JSON.parse(post.body).senha,'senha apenas de teste');
  assert.equal(els.nfA1Password.value,'');assert.equal(els.nfA1File.value,'');
  context.window.W2Auth.role=()=> 'financeiro';context.window.W2A1.init();assert(els.nfA1Panel.hidden);
  console.log('OK: verificação do servidor, envio à mesma origem, limpeza de senha e restrição de perfil.');
})().catch(error=>{console.error(error);process.exitCode=1});
