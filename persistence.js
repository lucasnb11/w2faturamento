// W2 Dashboard V2.0 - persistência Supabase
(() => {
  const SEED_DATA = (window.INITIAL_DATA || []).map(r => ({...r, cidade: canonicalCity(r.cidade)}));
  let booting = false;
  const db = () => window.w2Supabase;
  const BATCH = 500;

  function toDb(r, importId=null){
    return {caf:String(r.caf||''), awb:String(r.awb||''), data:r.data||null, entregues:Number(r.entregues||0), peso:Number(r.peso||0), tamanho:r.tamanho||'', cidade:canonicalCity(r.cidade), uf:r.uf||'', importacao_id:importId};
  }
  function fromDb(r){return {caf:String(r.caf||''),awb:String(r.awb||''),data:r.data||'',entregues:Number(r.entregues||0),peso:Number(r.peso||0),tamanho:r.tamanho||'',cidade:canonicalCity(r.cidade),uf:r.uf||''}}
  async function chunks(items, fn){for(let i=0;i<items.length;i+=BATCH) await fn(items.slice(i,i+BATCH),i);}
  function showSync(title, text){const box=$('#preview');if(box)box.innerHTML=`<div class="preview"><h3>${title}</h3><p>${text}</p></div>`;}

  async function loadAllRows(){
    const out=[]; let from=0; const size=1000;
    while(true){
      const {data:rows,error}=await db().from('dashboard_cafs').select('caf,awb,data,entregues,peso,tamanho,cidade,uf').order('id',{ascending:true}).range(from,from+size-1);
      if(error) throw error; out.push(...(rows||[])); if(!rows || rows.length<size) break; from+=size;
    }
    return out.map(fromDb);
  }
  async function loadImports(){
    const {data:rows,error}=await db().from('dashboard_importacoes').select('arquivo,novos_registros,status,created_at').order('created_at',{ascending:false}).limit(100);
    if(error) throw error;
    return (rows||[]).map(x=>({arquivo:x.arquivo,registros:x.novos_registros,status:x.status==='concluida'?'Importado':x.status}));
  }
  async function loadPayments(){
    const {data:rows,error}=await db().from('dashboard_pagamentos').select('id,cidade,entregador,valor,data_pagamento,observacao,ano,mes,quinzena').order('created_at',{ascending:false});
    if(error) throw error;
    return (rows||[]).map(x=>({id:x.id,city:canonicalCity(x.cidade),driver:x.entregador,amount:Number(x.valor||0),date:x.data_pagamento,note:x.observacao||'',year:x.ano,month:x.mes,quin:x.quinzena}));
  }
  async function migrateSeedIfNeeded(){
    const {count,error}=await db().from('dashboard_cafs').select('*',{count:'exact',head:true});
    if(error) throw error;
    if((count||0)>0 || !SEED_DATA.length) return false;
    showSync('Preparando base inicial','Primeiro acesso à V2.0: migrando a base inicial para o Supabase. Não feche esta página.');
    await chunks(SEED_DATA, async batch=>{
      const {error:e}=await db().from('dashboard_cafs').upsert(batch.map(r=>toDb(r)),{onConflict:'caf,awb',ignoreDuplicates:true});
      if(e) throw e;
    });
    const {error:ie}=await db().from('dashboard_importacoes').insert({arquivo:'Consolidado_CAF_W2_Transportes.xlsx',registros_recebidos:SEED_DATA.length,novos_registros:SEED_DATA.length,duplicados:0,status:'concluida'});
    if(ie) console.warn('Base migrada, mas histórico inicial não foi registrado:',ie);
    return true;
  }
  async function boot(){
    if(booting || !db()) return; booting=true;
    try{
      showSync('Sincronizando dados','Carregando a base persistida do Supabase...');
      await migrateSeedIfNeeded();
      [data,imports,payments]=await Promise.all([loadAllRows(),loadImports(),loadPayments()]);
      populateFilters();render();renderHistory();
      if($('#preview')) $('#preview').innerHTML='';
      toast(`${num(data.length)} registros carregados do Supabase.`);
    }catch(e){console.error('Falha na sincronização Supabase:',e);showSync('Falha ao carregar dados',`Não foi possível acessar as tabelas da V2.0. Execute o arquivo SUPABASE_V2.sql no projeto Supabase e recarregue a página.`)}
    finally{booting=false;}
  }

  // Pagamentos agora são persistidos no banco.
  savePayments = function(){};
  registerPayment = async function(){
    if(!activePaymentCity||!periodReady()){toast('Não foi possível identificar o fechamento.');return}
    const amount=Number($('#mAmount').value),driver=$('#mDriver').value.trim(),date=$('#mDate').value,note=$('#mNote').value.trim();
    if(!driver){toast('Informe o nome do entregador.');return} if(!date){toast('Informe a data do pagamento.');return} if(!(amount>0)){toast('Informe um valor de pagamento válido.');return}
    const d=filtered().filter(r=>(r.cidade||'NÃO INFORMADA')===activePaymentCity),rate=deliveryRate(activePaymentCity),due=d.length*rate,paid=paidFor(activePaymentCity),debt=Math.max(0,due-paid);
    if(amount>debt+.005&&debt>0){toast('O pagamento informado é maior que o saldo devedor.');return}
    const p=selectedPeriod(); const btn=$('#savePayment'); btn.disabled=true;btn.textContent='Salvando...';
    try{
      const payload={cidade:activePaymentCity,entregador:driver,valor:amount,data_pagamento:date,observacao:note||null,ano:Number(p.year),mes:Number(p.month),quinzena:Number(p.quin)};
      const {data:row,error}=await db().from('dashboard_pagamentos').insert(payload).select('id,cidade,entregador,valor,data_pagamento,observacao,ano,mes,quinzena').single();
      if(error) throw error;
      payments.unshift({id:row.id,city:canonicalCity(row.cidade),driver:row.entregador,amount:Number(row.valor),date:row.data_pagamento,note:row.observacao||'',year:row.ano,month:row.mes,quin:row.quinzena});
      closePaymentModal();renderPayments();toast(`Pagamento de ${brl(amount)} registrado para ${activePaymentCity}.`);
    }catch(e){console.error(e);toast('Não foi possível salvar o pagamento no Supabase.');}
    finally{btn.disabled=false;btn.textContent='Registrar pagamento';}
  };
  deletePayment = async function(id){
    if(!confirm('Excluir este lançamento de pagamento?'))return;
    const {error}=await db().from('dashboard_pagamentos').delete().eq('id',id);
    if(error){console.error(error);toast('Não foi possível excluir o lançamento.');return}
    payments=payments.filter(x=>String(x.id)!==String(id));renderPayments();toast('Lançamento excluído.');
  };
  window.deletePayment=deletePayment;

  // Importação persistente: só confirma depois que o Supabase gravar os dados.
  handleFile = function(file){
    const reader=new FileReader();
    reader.onload=async e=>{try{
      const wb=XLSX.read(e.target.result,{type:'array',cellDates:true});
      const wsName=wb.SheetNames.find(name=>{const rows=XLSX.utils.sheet_to_json(wb.Sheets[name],{header:1,defval:'',range:0});const h=(rows[0]||[]).map(x=>String(x).trim().toLowerCase());return h.includes('cafid1')&&h.includes('awb1')&&h.includes('cidade')})||wb.SheetNames.find(name=>name.toUpperCase()==='CAFS')||wb.SheetNames.find(name=>name==='CAF_Consolidado')||wb.SheetNames[0];
      const raw=XLSX.utils.sheet_to_json(wb.Sheets[wsName],{defval:''});
      const incoming=raw.map(normalizeRow).filter(r=>r.awb&&r.caf);
      const existing=new Set(data.map(r=>r.caf+'|'+r.awb)); const seen=new Set();
      const fresh=incoming.filter(r=>{const k=r.caf+'|'+r.awb;if(existing.has(k)||seen.has(k))return false;seen.add(k);return true});
      const dups=incoming.length-fresh.length,cafs=new Set(incoming.map(r=>r.caf)).size,cities=new Set(incoming.map(r=>r.cidade)).size,fat=incoming.reduce((s,r)=>s+(PRICES[r.tamanho]||0),0);
      $('#preview').innerHTML=`<div class="preview"><h3>${file.name}</h3><p><b>${incoming.length}</b> registros • <b>${cafs}</b> CAFs • <b>${cities}</b> cidades • ${brl(fat)}</p><p class="${dups?'warn':'ok'}">${dups} registros já existentes/duplicados • ${fresh.length} novos registros</p><button id="confirmImport" ${fresh.length?'':'disabled'}>Confirmar importação</button></div>`;
      $('#confirmImport')?.addEventListener('click',async()=>{
        const btn=$('#confirmImport');if(!fresh.length||btn.disabled)return;btn.disabled=true;btn.textContent='Salvando no Supabase...';
        try{
          const {data:imp,error:impErr}=await db().from('dashboard_importacoes').insert({arquivo:file.name,registros_recebidos:incoming.length,novos_registros:fresh.length,duplicados:dups,status:'processando'}).select('id').single();
          if(impErr) throw impErr;
          let inserted=[];
          await chunks(fresh,async batch=>{const {data:rows,error}=await db().from('dashboard_cafs').upsert(batch.map(r=>toDb(r,imp.id)),{onConflict:'caf,awb',ignoreDuplicates:true}).select('caf,awb,data,entregues,peso,tamanho,cidade,uf');if(error)throw error;inserted.push(...(rows||[]).map(fromDb));});
          const actual=inserted.length;
          await db().from('dashboard_importacoes').update({novos_registros:actual,duplicados:incoming.length-actual,status:'concluida'}).eq('id',imp.id);
          data.push(...inserted);imports.unshift({arquivo:file.name,registros:actual,status:'Importado'});
          $('#preview').innerHTML=`<div class="preview ok"><h3>Importação concluída e salva</h3><p><b>${actual}</b> novos registros foram persistidos no Supabase.</p><p>Os dados permanecerão após atualizar ou sair do sistema.</p></div>`;
          renderHistory();populateFilters();render();toast(`${actual} registros salvos no Supabase.`);
        }catch(err){console.error('Falha na importação persistente:',err);btn.disabled=false;btn.textContent='Confirmar importação';toast('Falha ao salvar a importação no Supabase. Nenhum status de sucesso foi confirmado.');}
      });
    }catch(err){console.error(err);toast('Não foi possível ler a planilha. Verifique o formato.')}};
    reader.readAsArrayBuffer(file);
  };

  window.addEventListener('w2-auth-ready',boot,{once:false});
  if(document.body.classList.contains('auth-ok') && db()) boot();
})();
