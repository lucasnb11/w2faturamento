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
  async function fetchAll(table, orderColumn='id', pageSize=1000){
    const out=[];
    for(let from=0;;from+=pageSize){
      const {data,error}=await state.client.from(table).select('*').order(orderColumn,{ascending:true}).range(from,from+pageSize-1);
      if(error)throw error;
      out.push(...(data||[]));
      if(!data||data.length<pageSize)break;
    }
    return out;
  }
  async function loadRemote(){
    if(!state.client||!state.authenticated)return {entregas:[],importacoes:[],pagamentos:[]};
    const [entregas,importacoes,pagamentos]=await Promise.all([
      fetchAll('entregas','id'), fetchAll('importacoes','id'), fetchAll('pagamentos_entregadores','id')
    ]);
    importacoes.sort((a,b)=>String(b.importado_em||'').localeCompare(String(a.importado_em||'')));
    pagamentos.sort((a,b)=>String(b.data_pagamento||'').localeCompare(String(a.data_pagamento||'')));
    return {entregas,importacoes,pagamentos};
  }
  async function countEntregas(){
    if(!state.client||!state.authenticated)return 0;
    const {count,error}=await state.client.from('entregas').select('id',{count:'exact',head:true});
    if(error)throw error; return count||0;
  }
  async function migrationStatus(){
    if(!state.client||!state.authenticated)return null;
    const {data,error}=await state.client.from('importacoes').select('*').eq('email_message_id','migration:datajs:v2.3').maybeSingle();
    if(error)throw error; return data||null;
  }
  async function migrateHistorical(rows,onProgress){
    if(!state.client||!state.authenticated)throw new Error('Sessão Supabase não autenticada.');
    const existing=await migrationStatus();
    if(existing?.status==='concluido')return {alreadyDone:true,importacao:existing,total:await countEntregas()};
    const before=await countEntregas();
    let imp=existing;
    if(!imp){
      const r=await state.client.from('importacoes').insert({email_message_id:'migration:datajs:v2.3',arquivo_nome:'data.js (base histórica)',origem:'migracao',registros_encontrados:rows.length,registros_novos:0,duplicados:0,status:'migrando'}).select().single();
      if(r.error)throw r.error; imp=r.data;
    }else{
      const r=await state.client.from('importacoes').update({registros_encontrados:rows.length,status:'migrando',erro:null}).eq('id',imp.id).select().single();
      if(r.error)throw r.error; imp=r.data;
    }
    const payload=rows.map(r=>({importacao_id:imp.id,caf_id:String(r.caf||''),awb:String(r.awb||''),data_abertura:r.data_abertura||null,data_finalizacao:r.data||null,peso:Number(r.peso||0),peso_cliente:Number(r.peso_cliente||0)||null,tipo_item:r.tipo_item,categoria:r.tamanho,valor_unitario:Number(r.valor_unitario||0),motorista_id:r.motorista_id||null,motorista:r.motorista||null,cidade:r.cidade||null,uf:r.uf||null,placa:r.placa||null,cliente:r.cliente||null,modelo_pagamento:r.modelo_pagamento||null}));
    try{
      const batch=400;
      for(let x=0;x<payload.length;x+=batch){
        const {error}=await state.client.from('entregas').upsert(payload.slice(x,x+batch),{onConflict:'caf_id,awb',ignoreDuplicates:true});
        if(error)throw error;
        onProgress?.(Math.min(x+batch,payload.length),payload.length);
      }
      const after=await countEntregas(), inserted=Math.max(0,after-before), duplicates=Math.max(0,rows.length-inserted);
      const {data:done,error}=await state.client.from('importacoes').update({registros_novos:inserted,duplicados:duplicates,status:'concluido',erro:null}).eq('id',imp.id).select().single();
      if(error)throw error;
      return {alreadyDone:false,importacao:done,before,after,inserted,duplicates,total:after};
    }catch(e){
      await state.client.from('importacoes').update({status:'erro',erro:String(e.message||e)}).eq('id',imp.id);
      throw e;
    }
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
  window.W2DB={state,init,loadRemote,toLocalEntrega,toLocalPayment,savePayment,saveImport,countEntregas,migrationStatus,migrateHistorical};
})();
