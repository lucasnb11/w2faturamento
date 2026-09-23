(function(){
  const cfg=window.W2_SUPABASE_CONFIG||{};
  const state={configured:false,connected:false,authenticated:false,client:null,user:null,error:null};
  function readyConfig(){return /^https:\/\/.+\.supabase\.co\/?$/i.test(String(cfg.url||'')) && String(cfg.anonKey||'').length>20}
  async function init(){
    state.configured=readyConfig();
    if(!state.configured||!window.supabase?.createClient)return state;
    try{
      state.client=window.supabase.createClient(cfg.url.replace(/\/$/,''),cfg.anonKey,{auth:{persistSession:true,autoRefreshToken:true}});
      const {data,error}=await state.client.auth.getSession();
      if(error)throw error;
      state.connected=true; state.user=data?.session?.user||null; state.authenticated=!!state.user;
    }catch(e){state.error=e;console.warn('W2 Supabase:',e)}
    return state;
  }
  async function loadRemote(){
    if(!state.client||!state.authenticated)return {entregas:[],importacoes:[],pagamentos:[]};
    const [e,i,p]=await Promise.all([
      state.client.from('entregas').select('*').order('id',{ascending:true}),
      state.client.from('importacoes').select('*').order('importado_em',{ascending:false}),
      state.client.from('pagamentos_entregadores').select('*').order('data_pagamento',{ascending:false})
    ]);
    for(const x of [e,i,p])if(x.error)throw x.error;
    return {entregas:e.data||[],importacoes:i.data||[],pagamentos:p.data||[]};
  }
  function toLocalEntrega(r){return {caf:r.caf_id,awb:r.awb,peso:Number(r.peso||0),peso_cliente:Number(r.peso_cliente||0),tipo_item:r.tipo_item,tamanho:r.categoria,valor_unitario:Number(r.valor_unitario||0),data:r.data_finalizacao||r.data_abertura||'',cidade:r.cidade||'',uf:r.uf||'',motorista:r.motorista||'',motorista_id:r.motorista_id||'',placa:r.placa||'',cliente:r.cliente||'',modelo_pagamento:r.modelo_pagamento||''}}
  function toLocalPayment(r){return {id:r.id,city:r.cidade,driver:r.entregador,year:r.ano,month:r.mes,quin:r.quinzena,amount:Number(r.valor||0),date:r.data_pagamento,note:r.observacao||'',createdAt:r.created_at}}
  async function savePayment(p){if(!state.client||!state.authenticated)return null;const row={cidade:p.city,entregador:p.driver,ano:+p.year,mes:+p.month,quinzena:+p.quin,valor:+p.amount,data_pagamento:p.date,observacao:p.note||null};const {data,error}=await state.client.from('pagamentos_entregadores').insert(row).select().single();if(error)throw error;return data}
  async function saveImport(meta,rows){
    if(!state.client||!state.authenticated)return null;
    const {data:imp,error:ie}=await state.client.from('importacoes').insert({arquivo_nome:meta.name||'W2 TRANSPORTES.xlsx',arquivo_hash:meta.hash||null,origem:meta.origin||'manual',registros_encontrados:rows.length,registros_novos:rows.length,duplicados:meta.duplicates||0,total_calculado:meta.calculated||null,total_oficial:meta.official||null,status:'importado'}).select().single();
    if(ie)throw ie;
    const payload=rows.map(r=>({importacao_id:imp.id,caf_id:String(r.caf||''),awb:String(r.awb||''),data_abertura:r.data_abertura||null,data_finalizacao:r.data||null,peso:Number(r.peso||0),peso_cliente:Number(r.peso_cliente||0)||null,tipo_item:r.tipo_item,categoria:r.tamanho,valor_unitario:Number(r.valor_unitario||0),motorista_id:r.motorista_id||null,motorista:r.motorista||null,cidade:r.cidade||null,uf:r.uf||null,placa:r.placa||null,cliente:r.cliente||null,modelo_pagamento:r.modelo_pagamento||null}));
    for(let x=0;x<payload.length;x+=500){const {error}=await state.client.from('entregas').upsert(payload.slice(x,x+500),{onConflict:'caf_id,awb',ignoreDuplicates:true});if(error)throw error}
    return imp;
  }
  window.W2DB={state,init,loadRemote,toLocalEntrega,toLocalPayment,savePayment,saveImport};
})();
