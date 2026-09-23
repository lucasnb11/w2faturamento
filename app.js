const PRICES={CARTÃO:4.5,PEQUENO:13,MÉDIO:18,GRANDE:30};
const BOX_PREFIXES=['AMZC','AMZB','TXAQ'];
const SPECIAL_PAY_CITIES=new Set(['LIMOEIRO DO AJURU','SALVATERRA','SOURE']);
const STORAGE={payments:'w2_payments_v2',imports:'w2_imports_v2',extra:'w2_extra_data_v2'};
// Utilitários precisam existir ANTES da normalização de INITIAL_DATA.
// Na V2.0.3, `norm`/`upper` eram const declaradas depois de `.map(enrichLegacy)`,
// causando ReferenceError na carga do app e interrompendo filtros e navegação.
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const brl=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'}), num=v=>Number(v||0).toLocaleString('pt-BR');
const norm=s=>String(s??'').trim(), upper=s=>norm(s).toLocaleUpperCase('pt-BR');
function safeLoad(key){try{const raw=window.localStorage?localStorage.getItem(key):null;if(!raw)return[];const parsed=JSON.parse(raw);return Array.isArray(parsed)?parsed:[]}catch(err){console.warn('W2: armazenamento local inválido em',key,err);try{localStorage.removeItem(key)}catch(_){}return[]}}
function safeSave(key,value){try{localStorage.setItem(key,JSON.stringify(value));return true}catch(err){console.warn('W2: não foi possível salvar localmente',key,err);return false}}
let base=[];
let extra=[];
let data=[], charts={}, imports=[];
let payments=safeLoad(STORAGE.payments), activePaymentCity=null, pendingImport=null;
function identifyType(awb){return BOX_PREFIXES.some(p=>upper(awb).startsWith(p))?'CAIXA':'CARTÃO'}
function classify(awb,peso){if(identifyType(awb)==='CARTÃO')return'CARTÃO';peso=Number(peso)||0;return peso<=1?'PEQUENO':peso<=10?'MÉDIO':'GRANDE'}
function deliveryRate(city){return SPECIAL_PAY_CITIES.has(upper(city))?8:5}
function parseDate(raw){if(!raw)return'';if(typeof raw==='number'&&window.XLSX){let x=XLSX.SSF.parse_date_code(raw);return x?`${x.y}-${String(x.m).padStart(2,'0')}-${String(x.d).padStart(2,'0')}`:''}if(raw instanceof Date&&!isNaN(raw))return raw.toISOString().slice(0,10);let s=String(raw);let m=s.match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);if(m)return`${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`;let iso=s.match(/(\d{4})-(\d{2})-(\d{2})/);return iso?iso[0]:''}
function dateParts(s){let m=String(s||'').match(/^(\d{4})-(\d{2})-(\d{2})/);return m?{year:+m[1],month:+m[2],quin:+m[3]<=15?1:2}:{} }
function enrichLegacy(r){let awb=norm(r.awb||r.awb1),peso=Number(r.peso||0),tipo=identifyType(awb),tamanho=classify(awb,peso);return{...r,caf:norm(r.caf||r.cafid1),awb,peso,tipo_item:tipo,tamanho,valor_unitario:PRICES[tamanho],data:parseDate(r.data||r.dt_finalizada_caf),cidade:norm(r.cidade),uf:norm(r.uf)}}
function dedupe(rows){let seen=new Set();return rows.filter(r=>{let k=`${upper(r.caf)}|${upper(r.awb)}`;if(!r.caf||!r.awb||seen.has(k))return false;seen.add(k);return true})}
function selectedMonths(){return $$('#monthMenu input[type=checkbox]:checked').map(o=>o.value)}
function updateMonthLabel(){let m=selectedMonths(),names=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];$('#monthToggle').childNodes[0].nodeValue=!m.length?'Todos os meses ':m.length===1?names[Number(m[0])-1]+' ':m.length===12?'Todos os meses ':m.length+' meses selecionados '}
function renderMonthMenu(){let names=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];$('#monthMenu').innerHTML=`<div class="month-actions"><button type="button" id="monthAll">Selecionar todos</button><button type="button" id="monthNone">Limpar</button></div>`+names.map((x,i)=>`<label class="month-option"><input type="checkbox" value="${i+1}"> <span>${x}</span></label>`).join('');updateMonthLabel()}
function filtered(){let months=selectedMonths();return data.filter(r=>{let p=dateParts(r.data);return(!$('#fAno').value||p.year==$('#fAno').value)&&(!months.length||months.includes(String(p.month)))&&(!$('#fQuinzena').value||p.quin==$('#fQuinzena').value)&&(!$('#fCidade').value||r.cidade==$('#fCidade').value)&&(!$('#fTamanho').value||r.tamanho==$('#fTamanho').value)})}
function populateFilters(){let years=[...new Set(data.map(r=>dateParts(r.data).year).filter(Boolean))].sort(),cities=[...new Set(data.map(r=>r.cidade).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));$('#fAno').innerHTML='<option value="">Todos os anos</option>'+years.map(x=>`<option>${x}</option>`).join('');renderMonthMenu();$('#fCidade').innerHTML='<option value="">Todas as cidades</option>'+cities.map(x=>`<option>${x}</option>`).join('')}
function makeChart(id,type,labels,values,label){if(typeof window.Chart==='undefined')return;if(charts[id])charts[id].destroy();const c=$(id);if(!c)return;charts[id]=new Chart(c.getContext('2d'),{type,data:{labels,datasets:[{label,data:values,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:200},plugins:{legend:{display:type==='doughnut'}},scales:type==='doughnut'?{}:{y:{beginAtZero:true,ticks:{callback:v=>label==='R$'?brl(v):num(v)}}}}})}
function table(headers,rows){return`<div class="tablewrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
function render(){let d=filtered();$('#kAwb').textContent=num(d.length);$('#kCaf').textContent=num(new Set(d.map(r=>r.caf)).size);$('#kCidade').textContent=num(new Set(d.map(r=>r.cidade)).size);$('#kPeso').textContent=num(d.reduce((s,r)=>s+r.peso,0).toFixed(2))+' kg';$('#kFat').textContent=brl(d.reduce((s,r)=>s+PRICES[r.tamanho],0));let cats=['CARTÃO','PEQUENO','MÉDIO','GRANDE'];makeChart('#chartCat','doughnut',cats,cats.map(c=>d.filter(r=>r.tamanho===c).length),'AWBs');let mm={};d.forEach(r=>{let p=dateParts(r.data),k=p.year+'-'+String(p.month).padStart(2,'0');mm[k]=(mm[k]||0)+PRICES[r.tamanho]});let ks=Object.keys(mm).sort();makeChart('#chartMes','bar',ks,ks.map(k=>mm[k]),'R$');let cm={};d.forEach(r=>cm[r.cidade]=(cm[r.cidade]||0)+1);let top=Object.entries(cm).sort((a,b)=>b[1]-a[1]).slice(0,10);makeChart('#chartCidade','bar',top.map(x=>x[0]),top.map(x=>x[1]),'AWBs');renderCities(d);renderBilling(d);renderPayments(d)}
function renderCities(d){let m={};d.forEach(r=>{let x=m[r.cidade]??={cafs:new Set(),awb:0,fat:0,pay:0};x.cafs.add(r.caf);x.awb++;x.fat+=PRICES[r.tamanho];x.pay+=deliveryRate(r.cidade)});let rows=Object.entries(m).sort((a,b)=>b[1].awb-a[1].awb).map(([c,x])=>`<tr><td>${c}</td><td>${x.cafs.size}</td><td>${num(x.awb)}</td><td>${brl(x.fat)}</td><td>${brl(x.pay)}</td></tr>`);$('#cityTable').innerHTML=table(['Cidade','CAFs','AWBs','Faturamento','Repasse'],rows)}
function renderBilling(d){let cats=['CARTÃO','PEQUENO','MÉDIO','GRANDE'];let rows=cats.map(c=>{let q=d.filter(r=>r.tamanho===c).length;return`<tr><td>${c}</td><td>${num(q)}</td><td>${brl(PRICES[c])}</td><td><b>${brl(q*PRICES[c])}</b></td></tr>`});$('#billingTable').innerHTML=table(['Categoria','Quantidade','Valor unitário','Total'],rows)}
function selectedPeriod(){return{year:$('#fAno').value,months:selectedMonths(),quin:$('#fQuinzena').value}}
function periodReady(){let p=selectedPeriod();return p.year&&p.months.length===1&&p.quin}
function periodLabel(){let p=selectedPeriod();return periodReady()?`${p.quin}ª quinzena ${String(p.months[0]).padStart(2,'0')}/${p.year}`:'período filtrado'}
function paymentMatches(p){let s=selectedPeriod();return(!s.year||p.year==s.year)&&(!s.months.length||s.months.includes(String(p.month)))&&(!s.quin||p.quin==s.quin)}
function paidFor(city){return payments.filter(p=>p.city===city&&paymentMatches(p)).reduce((s,p)=>s+Number(p.amount||0),0)}
function renderPayments(d=filtered()){let m={};d.forEach(r=>{let c=r.cidade||'NÃO INFORMADA',x=m[c]??={cafs:new Set(),awb:0,due:0};x.cafs.add(r.caf);x.awb++;x.due+=deliveryRate(c)});let due=Object.values(m).reduce((s,x)=>s+x.due,0),rev=d.reduce((s,r)=>s+PRICES[r.tamanho],0);$('#pAwb').textContent=num(d.length);$('#pCities').textContent=num(Object.keys(m).length);$('#pPay').textContent=brl(due);$('#pRevenue').textContent=brl(rev);$('#pMargin').textContent=brl(rev-due);let rows=Object.entries(m).sort((a,b)=>b[1].awb-a[1].awb).map(([c,x])=>{let paid=paidFor(c),debt=Math.max(0,x.due-paid),status=debt<=.005?'Pago':paid>0?'Parcial':'Pendente',cls=status.toLowerCase();return`<tr><td>${c}</td><td>${x.cafs.size}</td><td>${num(x.awb)}</td><td>${brl(deliveryRate(c))}</td><td>${brl(x.due)}</td><td class="paid">${brl(paid)}</td><td class="debt">${brl(debt)}</td><td><span class="status-pill status-${cls}">${status}</span></td><td><button class="pay-btn" data-city="${c}" ${periodReady()?'':'disabled'}>Registrar</button></td></tr>`});$('#paymentTable').innerHTML=(!periodReady()?'<div class="preview warn"><b>Para registrar pagamento, selecione um único mês, ano e quinzena.</b></div>':'')+table(['Cidade','CAFs','AWBs','Tarifa/AWB','Devido','Pago','Saldo','Status','Ação'],rows);renderPaymentHistory()}
function openPayment(city){if(!periodReady())return toast('Selecione um único mês, ano e quinzena.');let d=filtered().filter(r=>(r.cidade||'NÃO INFORMADA')===city),due=d.reduce((s,r)=>s+deliveryRate(city),0),paid=paidFor(city),debt=Math.max(0,due-paid);activePaymentCity=city;$('#paymentContext').textContent=`${city} • ${periodLabel()} • ${num(d.length)} AWBs • ${brl(deliveryRate(city))}/AWB`;$('#mDue').textContent=brl(due);$('#mPaid').textContent=brl(paid);$('#mDebt').textContent=brl(debt);$('#mAmount').value=debt.toFixed(2);$('#mDate').value=new Date().toISOString().slice(0,10);$('#mDriver').value=payments.find(x=>x.city===city)?.driver||'';$('#mNote').value='';$('#paymentModal').classList.add('open')}
function closePaymentModal(){$('#paymentModal').classList.remove('open');activePaymentCity=null}
async function registerPayment(){
  if(!activePaymentCity)return toast('Selecione uma cidade para registrar o pagamento.');
  if(!periodReady())return toast('Selecione um único ano, mês e quinzena.');
  if(!window.W2DB?.state?.authenticated)return toast('Sessão Supabase não autenticada. Faça login novamente.');
  const btn=$('#savePayment');
  const amount=Number(String($('#mAmount').value||'').replace(',','.'));
  const driver=$('#mDriver').value.trim();
  const date=$('#mDate').value;
  if(!driver||!date||!(amount>0))return toast('Preencha entregador, valor e data.');
  const d=filtered().filter(r=>(r.cidade||'NÃO INFORMADA')===activePaymentCity);
  const due=d.reduce((sum,r)=>sum+deliveryRate(activePaymentCity),0);
  const debt=Math.max(0,due-paidFor(activePaymentCity));
  if(amount>debt+.005)return toast('Valor maior que o saldo devedor.');
  const p=selectedPeriod();
  const payment={city:activePaymentCity,driver,amount,date,note:$('#mNote').value.trim(),year:+p.year,month:+p.months[0],quin:+p.quin};
  try{
    if(btn){btn.disabled=true;btn.textContent='Registrando…'}
    const saved=await W2DB.savePayment(payment);
    if(!saved)throw new Error('O Supabase não retornou o pagamento registrado.');
    payments.unshift(W2DB.toLocalPayment(saved));
    safeSave(STORAGE.payments,payments);
    closePaymentModal();
    render();
    toast('Pagamento registrado com sucesso.');
  }catch(e){
    console.error('W2: falha ao registrar pagamento',e);
    toast('Não foi possível registrar o pagamento: '+(e.message||e));
  }finally{
    if(btn){btn.disabled=false;btn.textContent='Registrar pagamento'}
  }
}
function renderPaymentHistory(){let list=payments.filter(paymentMatches).sort((a,b)=>(b.date||'').localeCompare(a.date||''));$('#paymentHistory').innerHTML=list.length?table(['Data','Cidade','Entregador','Período','Valor','Observação',''],list.map(x=>`<tr><td>${x.date.split('-').reverse().join('/')}</td><td>${x.city}</td><td>${x.driver}</td><td>${x.quin}ª ${String(x.month).padStart(2,'0')}/${x.year}</td><td>${brl(x.amount)}</td><td>${x.note||'—'}</td><td><button class="danger-link" onclick="deletePayment(${x.id})">Excluir</button></td></tr>`)):'<p>Nenhum pagamento no filtro atual.</p>'}
function deletePayment(id){if(confirm('Excluir este pagamento?')){payments=payments.filter(x=>x.id!==id);safeSave(STORAGE.payments,payments);render()}}window.deletePayment=deletePayment;
function searchCaf(){let q=upper($('#cafSearch').value);if(!q)return $('#cafResult').innerHTML='';let d=data.filter(r=>upper(r.caf).includes(q));if(!d.length)return $('#cafResult').innerHTML='<p>Nenhuma CAF encontrada.</p>';let exact=d.filter(r=>upper(r.caf)===q);if(exact.length)d=exact;let fat=d.reduce((s,r)=>s+PRICES[r.tamanho],0);$('#cafResult').innerHTML=`<div class="cards"><article><label>CAF</label><strong>${d[0].caf}</strong><small>${d[0].cidade}/${d[0].uf}</small></article><article><label>AWBs</label><strong>${d.length}</strong></article><article><label>Faturamento</label><strong>${brl(fat)}</strong></article></div>`+table(['AWB','Tipo','Data','Peso','Categoria','Valor'],d.slice(0,500).map(r=>`<tr><td>${r.awb}</td><td>${r.tipo_item}</td><td>${r.data}</td><td>${r.peso}</td><td>${r.tamanho}</td><td>${brl(PRICES[r.tamanho])}</td></tr>`))}
function getField(o,...names){let map=Object.fromEntries(Object.keys(o).map(k=>[upper(k),k]));for(let n of names){let k=map[upper(n)];if(k!==undefined)return o[k]}return''}
function toNumber(v){if(typeof v==='number')return Number.isFinite(v)?v:0;let s=String(v??'').trim();if(!s)return 0;s=s.replace(/R\$\s?/gi,'').replace(/\s/g,'');if(s.includes(',')&&s.includes('.'))s=s.replace(/\./g,'').replace(',','.');else s=s.replace(',','.');let n=Number(s);return Number.isFinite(n)?n:0}
function normalizeCAF(o){let awb=norm(getField(o,'awb1','awb')),peso=toNumber(getField(o,'peso'));let tamanho=classify(awb,peso);return{caf:norm(getField(o,'cafid1','caf')),data:parseDate(getField(o,'dt_finalizada_caf','dt_finalizada_caf_off','data')),data_abertura:parseDate(getField(o,'dt_abertura_caf')),entregues:toNumber(getField(o,'entregues')),awb,peso,peso_cliente:toNumber(getField(o,'peso_cliente')),tipo_item:identifyType(awb),tamanho,valor_unitario:PRICES[tamanho],motorista_id:norm(getField(o,'mot_id1')),motorista:norm(getField(o,'mot_nome1')),cnpj:norm(getField(o,'CNPJ')),razao_social:norm(getField(o,'motemp_razao_social')),placa:norm(getField(o,'vei_placa')),cidade:norm(getField(o,'cidade')),uf:norm(getField(o,'uf')),cliente:norm(getField(o,'nmfantasia')),tipo_produto:norm(getField(o,'ds_tipo_produto')),quinzena_original:norm(getField(o,'quinzena1')),modelo_pagamento:norm(getField(o,'ModeloPagamento'))}}
function findHeaderRow(ws,need,maxRows=12){let grid=XLSX.utils.sheet_to_json(ws,{header:1,defval:'',raw:true,range:0});for(let i=0;i<Math.min(maxRows,grid.length);i++){let row=grid[i].map(upper);if(need.every(n=>row.includes(upper(n))))return i+1}return 1}
function sheetJson(ws,headerRow=1){return XLSX.utils.sheet_to_json(ws,{range:headerRow-1,defval:'',raw:true})}
function sumAP(ap,...names){return ap.reduce((s,r)=>s+toNumber(getField(r,...names)),0)}
function extractOfficial(ap){return sumAP(ap,'Total Pagar','TOTAL PAGAR')}
function buildReconciliation(ap,systemCalc){
  const volume=sumAP(ap,'Valor Pago\n(Volume Entregas)','Valor Pago (Volume Entregas)','VALOR PAGO (VOLUME ENTREGAS)');
  const discounts=sumAP(ap,'Valor Descontos');
  const extras=sumAP(ap,'Extras');
  const transfer=sumAP(ap,'Valor Transferência Secundária');
  const edsp=sumAP(ap,'EDSP');
  const retro=sumAP(ap,'Retroativo');
  const credit=sumAP(ap,'Crédito\n(Extras)','Crédito (Extras)');
  const debit=sumAP(ap,'Débito');
  const official=sumAP(ap,'Total Pagar','TOTAL PAGAR');
  // A APURACAO é a fonte oficial para a composição financeira. A diferença entre
  // os AWBs recalculados e o volume oficial fica explícita como ajuste de classificação,
  // em vez de ser escondida dentro de uma tolerância.
  const classificationAdjustment=volume-systemCalc;
  const financialAdjustment=official-volume;
  const reconciled=systemCalc+classificationAdjustment+financialAdjustment;
  return{systemCalc,volume,discounts,extras,transfer,edsp,retro,credit,debit,official,classificationAdjustment,financialAdjustment,reconciled,difference:reconciled-official};
}
function reconciliationHtml(r){
  if(!r.official)return '<p class="warn">A aba APURACAO não trouxe um Total Pagar reconhecível.</p>';
  const row=(label,value,cls='')=>`<tr><td>${label}</td><td class="${cls}">${brl(value)}</td></tr>`;
  return `<div class="audit-box"><h4>Conciliação do fechamento</h4>${table(['Componente','Valor'],[
    row('Cálculo pelos AWBs do sistema',r.systemCalc),
    row('Volume oficial APURACAO',r.volume),
    row('Ajuste classificação/volume APURACAO',r.classificationAdjustment),
    row('Descontos informados',r.discounts),row('Extras',r.extras),row('Transferência secundária',r.transfer),row('EDSP',r.edsp),row('Retroativo',r.retro),row('Crédito (Extras)',r.credit),row('Débito',r.debit),
    row('Ajustes financeiros líquidos da APURACAO',r.financialAdjustment),
    row('Total conciliado',r.reconciled,'paid'),row('Total Pagar oficial',r.official,'paid'),row('Diferença final',r.difference,Math.abs(r.difference)<.01?'paid':'debt')
  ])}<p class="${auditClass(r.difference)}"><b>${Math.abs(r.difference)<.01?'Conciliação OK — diferença R$ 0,00':'Conciliação pendente'}</b></p><small>O ajuste de classificação/volume é mostrado separadamente para permitir auditoria quando a regra de AWB/peso do sistema divergir da classificação usada pela Total Express.</small></div>`;
}
function internalDedupe(rows){let seen=new Set(),out=[],dups=0;for(const r of rows){let k=`${upper(r.caf)}|${upper(r.awb)}`;if(seen.has(k)){dups++;continue}seen.add(k);out.push(r)}return{rows:out,dups}}
function parseWorkbook(wb,file){
  let cafSheet=wb.Sheets['CAFS']||wb.Sheets['CAF_Consolidado'];if(!cafSheet)throw new Error('Aba CAFS não encontrada. O arquivo deve conter a aba CAFS.');
  let headerRow=findHeaderRow(cafSheet,['cafid1','awb1']);let raw=sheetJson(cafSheet,headerRow);if(!raw.length)throw new Error('A aba CAFS está vazia.');
  let keys=Object.keys(raw[0]).map(upper),required=['cafid1','awb1','peso','cidade'];let missing=required.filter(k=>!keys.includes(upper(k)));if(missing.length)throw new Error('Colunas obrigatórias ausentes na CAFS: '+missing.join(', '));
  let normalized=raw.map(normalizeCAF).filter(r=>r.awb&&r.caf),inside=internalDedupe(normalized),incoming=inside.rows;
  let ap=[],apHeader=0;if(wb.Sheets['APURACAO']){apHeader=findHeaderRow(wb.Sheets['APURACAO'],['Total Pagar'],15);ap=sheetJson(wb.Sheets['APURACAO'],apHeader)}
  let official=extractOfficial(ap),calc=incoming.reduce((s,r)=>s+Number(r.valor_unitario||0),0),reconciliation=buildReconciliation(ap,calc),difference=official?reconciliation.difference:null;
  return{incoming,ap,official,calc,difference,reconciliation,fileName:file.name,internalDuplicates:inside.dups,headerRow,apHeader}
}
async function sha256(buffer){if(!crypto?.subtle)return null;let hash=await crypto.subtle.digest('SHA-256',buffer),bytes=[...new Uint8Array(hash)];return bytes.map(b=>b.toString(16).padStart(2,'0')).join('')}
function auditClass(diff){if(diff===null)return'warn';return Math.abs(diff)<0.01?'ok':'warn'}
function handleFile(file){
  if(!/\.xlsx?$/i.test(file.name))return toast('Selecione um arquivo Excel .xlsx ou .xls.');
  let reader=new FileReader();reader.onload=async e=>{try{
    let buffer=e.target.result,wb=XLSX.read(buffer,{type:'array',cellDates:true}),p=parseWorkbook(wb,file),hash=await sha256(buffer),existing=new Set(data.map(r=>`${upper(r.caf)}|${upper(r.awb)}`)),fresh=p.incoming.filter(r=>!existing.has(`${upper(r.caf)}|${upper(r.awb)}`)),dbDups=p.incoming.length-fresh.length,totalDups=dbDups+p.internalDuplicates;
    pendingImport={...p,fresh,dups:totalDups,dbDups,hash,found:p.incoming.length+p.internalDuplicates};
    let audit=p.official?reconciliationHtml(p.reconciliation):'<p class="warn">A aba APURACAO não trouxe um Total Pagar reconhecível. A importação pode prosseguir, mas ficará sem conciliação oficial.</p>';
    $('#preview').innerHTML=`<div class="preview"><h3>${file.name}</h3><p><b>${num(p.incoming.length)}</b> AWBs válidos • <b>${num(new Set(p.incoming.map(r=>r.caf)).size)}</b> CAFs • <b>${num(new Set(p.incoming.map(r=>r.cidade)).size)}</b> cidades</p>${audit}<p class="${totalDups?'warn':'ok'}">${num(p.internalDuplicates)} duplicados dentro do arquivo • ${num(dbDups)} já existentes no Supabase • <b>${num(fresh.length)} novos</b></p><p><small>CAFS: cabeçalho detectado na linha ${p.headerRow}${p.ap.length?` • APURACAO: linha ${p.apHeader}`:''}</small></p><button id="confirmImport" ${fresh.length?'':'disabled'}>${fresh.length?'Confirmar importação':'Nenhum registro novo'}</button></div>`;
    $('#confirmImport')?.addEventListener('click',confirmImport)
  }catch(err){console.error(err);toast(err.message||'Falha ao ler planilha.')}};reader.readAsArrayBuffer(file)
}
async function confirmImport(){
  if(!pendingImport)return;if(!window.W2DB?.state?.authenticated)return toast('Sessão Supabase não autenticada.');
  const btn=$('#confirmImport');if(btn){btn.disabled=true;btn.textContent='Importando…'}let p=pendingImport;
  try{
    await W2DB.saveImport({name:p.fileName,hash:p.hash,origin:'manual',duplicates:p.dups,found:p.found,calculated:p.calc,official:p.official,status:'concluido'},p.fresh);
    const remote=await W2DB.loadRemote();base=remote.entregas.map(W2DB.toLocalEntrega);extra=[];data=dedupe(base);payments=remote.pagamentos.map(W2DB.toLocalPayment);imports=remote.importacoes.map(x=>({id:x.id,arquivo:x.arquivo_nome,registros:x.registros_novos,duplicados:x.duplicados,status:x.status,calculado:Number(x.total_calculado||0),oficial:Number(x.total_oficial||0),data:x.importado_em}));
    pendingImport=null;populateFilters();render();renderHistory();$('#preview').innerHTML='<div class="preview ok"><b>Importação concluída e gravada no Supabase.</b></div>';toast('Importação concluída com sucesso.')
  }catch(e){console.error(e);if(btn){btn.disabled=false;btn.textContent='Tentar novamente'}toast('Falha ao gravar importação no Supabase: '+(e.message||e))}
}
function renderHistory(){let rows=imports.map(x=>`<tr><td>${x.data?new Date(x.data).toLocaleString('pt-BR'):'—'}</td><td>${x.arquivo}</td><td>${num(x.registros)}</td><td>${num(x.duplicados||0)}</td><td>${x.oficial?brl(x.oficial):'—'}</td><td>${x.status}</td></tr>`);$('#history').innerHTML=rows.length?table(['Data','Arquivo','Novos','Duplicados','Total oficial','Status'],rows):'<p>Nenhuma importação adicional nesta instalação.</p>'}
function toast(t){$('#toast').textContent=t;$('#toast').style.display='block';setTimeout(()=>$('#toast').style.display='none',3200)}
async function setupHistoricalMigration(){
  const panel=$('#migrationPanel'),btn=$('#migrateHistoricalBtn'),status=$('#migrationStatus'),bar=$('#migrationBar');
  if(!panel||!btn)return;
  const isAdmin=window.W2Auth?.role?.()==='administrador';
  panel.hidden=!isAdmin;
  if(!isAdmin)return;
  if(!window.W2DB?.state?.authenticated){status.textContent='Supabase não conectado.';btn.disabled=true;return}
  try{
    const [m,total]=await Promise.all([W2DB.migrationStatus(),W2DB.countEntregas()]);
    if(m?.status==='concluido'){
      status.textContent=`Migração concluída • ${num(total)} registros no Supabase • ${num(m.registros_novos||0)} novos • ${num(m.duplicados||0)} duplicados ignorados.`;
      bar.style.width='100%'; btn.disabled=true; btn.textContent='Migração concluída';
    }else{
      status.textContent=`Base local: ${num(base.length)} registros • Supabase: ${num(total)} registros.`;
    }
  }catch(e){status.textContent='Não foi possível verificar a migração: '+(e.message||e)}
  btn.addEventListener('click',runHistoricalMigration,{once:true});
}
async function runHistoricalMigration(){
  const btn=$('#migrateHistoricalBtn'),status=$('#migrationStatus'),bar=$('#migrationBar');
  if(window.W2Auth?.role?.()!=='administrador')return toast('Somente administradores podem executar a migração.');
  const source=dedupe((Array.isArray(window.INITIAL_DATA)?window.INITIAL_DATA:[]).map(enrichLegacy));
  if(!source.length){status.textContent='A base histórica data.js não foi encontrada.';return}
  btn.disabled=true;btn.textContent='Migrando…';
  try{
    const result=await W2DB.migrateHistorical(source,(done,total)=>{const pct=Math.round(done/total*100);bar.style.width=pct+'%';status.textContent=`Migrando ${num(done)} de ${num(total)} registros (${pct}%). Não feche esta página.`});
    if(result.alreadyDone){bar.style.width='100%';status.textContent=`Migração já concluída • ${num(result.total)} registros no Supabase.`}
    else{bar.style.width='100%';status.textContent=`Migração concluída • ${num(result.inserted)} novos • ${num(result.duplicates)} duplicados ignorados • ${num(result.after)} registros no Supabase.`}
    btn.textContent='Migração concluída';
    const remote=await W2DB.loadRemote();
    base=remote.entregas.map(W2DB.toLocalEntrega);extra=[];data=dedupe(base);imports=remote.importacoes.map(x=>({id:x.id,arquivo:x.arquivo_nome,registros:x.registros_novos,duplicados:x.duplicados,status:x.status,calculado:Number(x.total_calculado||0),oficial:Number(x.total_oficial||0),data:x.importado_em}));
    populateFilters();render();renderHistory();toast('Base histórica migrada para o Supabase.');
  }catch(e){console.error(e);status.textContent='Falha na migração: '+(e.message||e);btn.disabled=false;btn.textContent='Tentar novamente';btn.addEventListener('click',runHistoricalMigration,{once:true});toast('Falha ao migrar a base histórica.')}
}
function openTab(name){if(window.W2Auth&&!W2Auth.allowed(name)){toast('Seu perfil não possui acesso a esta área.');return}const page=$('#'+name);if(!page)return;$$('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab===name));$$('.page').forEach(x=>x.classList.toggle('active',x.id===name));if(name==='pagamentos')renderPayments();if(name==='importacoes')renderHistory()}
async function initApp(){
  try{
    if(window.W2Auth){const ok=await W2Auth.boot();if(!ok)return;}
    if(!window.W2DB?.state?.authenticated)throw new Error('Sessão Supabase não autenticada. Faça login novamente.');
    try{
      const remote=await W2DB.loadRemote();
      base=remote.entregas.map(W2DB.toLocalEntrega); extra=[]; data=dedupe(base);
      payments=remote.pagamentos.map(W2DB.toLocalPayment);
      imports=remote.importacoes.map(x=>({id:x.id,arquivo:x.arquivo_nome,registros:x.registros_novos,duplicados:x.duplicados,status:x.status,calculado:Number(x.total_calculado||0),oficial:Number(x.total_oficial||0),data:x.importado_em}));
    }catch(e){
      console.error('W2: falha ao carregar dados do Supabase',e);
      throw new Error('Não foi possível carregar a base do Supabase. Nenhum dado local foi usado. '+(e.message||e));
    }
    const nav=document.querySelector('nav');
    if(nav) nav.addEventListener('click',e=>{const b=e.target.closest('.tab');if(b){e.preventDefault();openTab(b.dataset.tab)}});
    $$('.filters select').forEach(x=>x.addEventListener('change',render));
    $('#clearFilters')?.addEventListener('click',()=>{$('#fAno').value='';$$('#monthMenu input[type=checkbox]').forEach(o=>o.checked=false);updateMonthLabel();$('#fQuinzena').value='';$('#fCidade').value='';$('#fTamanho').value='';render()});
    $('#cafSearch')?.addEventListener('input',searchCaf);
    $('#btnUpload')?.addEventListener('click',()=>{openTab('importacoes');$('#fileInput')?.click()});
    $('#drop')?.addEventListener('click',()=>$('#fileInput')?.click());
    $('#fileInput')?.addEventListener('change',e=>e.target.files[0]&&handleFile(e.target.files[0]));
    $('#drop')?.addEventListener('dragover',e=>e.preventDefault());
    $('#drop')?.addEventListener('drop',e=>{e.preventDefault();e.dataTransfer.files[0]&&handleFile(e.dataTransfer.files[0])});
    $('#monthToggle')?.addEventListener('click',e=>{e.stopPropagation();$('#monthMenu').classList.toggle('open');$('#monthToggle').classList.toggle('open')});
    $('#monthMenu')?.addEventListener('click',e=>e.stopPropagation());
    $('#monthMenu')?.addEventListener('change',e=>{if(e.target.matches('input[type=checkbox]')){updateMonthLabel();render()}});
    document.addEventListener('click',e=>{if(e.target.closest('#monthAll')){$$('#monthMenu input[type=checkbox]').forEach(o=>o.checked=true);updateMonthLabel();render();return}if(e.target.closest('#monthNone')){$$('#monthMenu input[type=checkbox]').forEach(o=>o.checked=false);updateMonthLabel();render();return}if(!e.target.closest('#monthFilter')){$('#monthMenu')?.classList.remove('open');$('#monthToggle')?.classList.remove('open')}});
    document.addEventListener('click',e=>{let b=e.target.closest('.pay-btn');if(b&&!b.disabled)return openPayment(b.dataset.city);if(e.target.closest('#closePaymentModal'))return closePaymentModal();if(e.target.closest('#savePayment')){e.preventDefault();return registerPayment();}if(e.target.closest('#payFull'))return $('#mAmount').value=Number($('#mDebt').textContent.replace(/[^0-9,]/g,'').replace(',','.')).toFixed(2);if(e.target.closest('#paymentHistoryBtn')){let h=$('#paymentHistory');h.style.display=h.style.display==='none'?'block':'none';renderPaymentHistory()}});
    $('#paymentModal')?.addEventListener('click',e=>{if(e.target===$('#paymentModal'))closePaymentModal()});
    populateFilters();render();renderHistory();
    console.info(`W2 V2.4.2 iniciado: ${data.length} AWBs carregados do Supabase.`);
  }catch(err){console.error('W2 init error',err);const t=$('#toast');if(t){t.textContent='Falha ao iniciar: '+(err.message||err);t.style.display='block'}}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initApp);else initApp();
