const PRICES={'CARTÃO':4.5,'PEQUENO':13,'MÉDIO':18,'GRANDE':30};
const DELIVERY_PAY=5;
let data=(window.INITIAL_DATA||[]), charts={}, imports=[{arquivo:'Consolidado_CAF_W2_Transportes.xlsx',registros:data.length,status:'Base inicial'}];
let payments=JSON.parse(localStorage.getItem('w2_payments_v1')||'[]');
let activePaymentCity=null;
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)], brl=v=>v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'}), num=v=>Number(v||0).toLocaleString('pt-BR');
function dateParts(s){let d=new Date((s||'')+'T00:00:00');return isNaN(d)?{}:{year:d.getFullYear(),month:d.getMonth()+1,quin:d.getDate()<=15?1:2}}
function filtered(){return data.filter(r=>{let p=dateParts(r.data);return(!$('#fAno').value||p.year==$('#fAno').value)&&(!$('#fMes').value||p.month==$('#fMes').value)&&(!$('#fQuinzena').value||p.quin==$('#fQuinzena').value)&&(!$('#fCidade').value||r.cidade==$('#fCidade').value)&&(!$('#fTamanho').value||r.tamanho==$('#fTamanho').value)})}
function populateFilters(){let years=[...new Set(data.map(r=>dateParts(r.data).year).filter(Boolean))].sort(), cities=[...new Set(data.map(r=>r.cidade).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));$('#fAno').innerHTML='<option value="">Todos os anos</option>'+years.map(x=>`<option>${x}</option>`).join('');$('#fMes').innerHTML='<option value="">Todos os meses</option>'+['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'].map((x,i)=>`<option value="${i+1}">${x}</option>`).join('');$('#fCidade').innerHTML='<option value="">Todas as cidades</option>'+cities.map(x=>`<option>${x}</option>`).join('')}
function makeChart(id,type,labels,values,label){if(charts[id]){charts[id].destroy();delete charts[id]}const canvas=$(id);if(!canvas)return;const ctx=canvas.getContext('2d');charts[id]=new Chart(ctx,{type,data:{labels,datasets:[{label,data:values,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,resizeDelay:150,animation:{duration:250},plugins:{legend:{display:type==='doughnut'}},scales:type==='doughnut'?{}:{y:{beginAtZero:true,ticks:{callback:v=>label==='R$'?brl(v):num(v)}}}}})}
function render(){let d=filtered();$('#kAwb').textContent=num(d.length);$('#kCaf').textContent=num(new Set(d.map(r=>r.caf)).size);$('#kCidade').textContent=num(new Set(d.map(r=>r.cidade)).size);$('#kPeso').textContent=num(d.reduce((s,r)=>s+Number(r.peso||0),0).toFixed(2))+' kg';$('#kFat').textContent=brl(d.reduce((s,r)=>s+(PRICES[r.tamanho]||0),0));let cats=['CARTÃO','PEQUENO','MÉDIO','GRANDE'];makeChart('#chartCat','doughnut',cats,cats.map(c=>d.filter(r=>r.tamanho===c).length),'AWBs');let mm={};d.forEach(r=>{let p=dateParts(r.data),k=p.year+'-'+String(p.month).padStart(2,'0');mm[k]=(mm[k]||0)+(PRICES[r.tamanho]||0)});let mkeys=Object.keys(mm).sort();makeChart('#chartMes','bar',mkeys,mkeys.map(k=>mm[k]),'R$');let cc={};d.forEach(r=>cc[r.cidade]=(cc[r.cidade]||0)+1);let top=Object.entries(cc).sort((a,b)=>b[1]-a[1]).slice(0,10);makeChart('#chartCidade','bar',top.map(x=>x[0]),top.map(x=>x[1]),'AWBs');renderCities();renderBilling();renderPayments()}
function table(headers,rows){return `<div class="tablewrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
function renderCities(){let m={};data.forEach(r=>{let x=m[r.cidade]||(m[r.cidade]={awb:0,cafs:new Set(),fat:0});x.awb++;x.cafs.add(r.caf);x.fat+=PRICES[r.tamanho]||0});let rows=Object.entries(m).sort((a,b)=>b[1].awb-a[1].awb).map(([c,x])=>`<tr><td>${c}</td><td>${x.awb}</td><td>${x.cafs.size}</td><td>${brl(x.fat)}</td></tr>`);$('#cityTable').innerHTML=table(['Cidade','AWBs','CAFs','Faturamento'],rows)}
function renderBilling(){let cats=['CARTÃO','PEQUENO','MÉDIO','GRANDE'],rows=cats.map(c=>{let q=data.filter(r=>r.tamanho===c).length;return `<tr><td>${c}</td><td>${q}</td><td>${brl(PRICES[c])}</td><td>${brl(q*PRICES[c])}</td></tr>`});$('#billingTable').innerHTML=table(['Categoria','Quantidade','Unitário','Total'],rows)}

function selectedPeriod(){return {year:$('#fAno').value,month:$('#fMes').value,quin:$('#fQuinzena').value}}
function periodReady(){let p=selectedPeriod();return !!(p.year&&p.month&&p.quin)}
function periodLabel(p=selectedPeriod()){let months=['','Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];return `${p.quin}ª quinzena de ${months[Number(p.month)]}/${p.year}`}
function paymentMatchesFilters(x,city){let p=selectedPeriod();return (!city||x.city===city)&&(!p.year||String(x.year)===String(p.year))&&(!p.month||String(x.month)===String(p.month))&&(!p.quin||String(x.quin)===String(p.quin))}
function paidFor(city){return payments.filter(x=>paymentMatchesFilters(x,city)).reduce((s,x)=>s+Number(x.amount||0),0)}
function savePayments(){localStorage.setItem('w2_payments_v1',JSON.stringify(payments))}
function paymentStatus(due,paid){let debt=Math.max(0,due-paid);return debt<.005?'Pago':paid>0?'Parcial':'Pendente'}
function renderPayments(){
  let d=filtered(),m={};
  d.forEach(r=>{let city=r.cidade||'NÃO INFORMADA',x=m[city]||(m[city]={awb:0,cafs:new Set(),fat:0});x.awb++;x.cafs.add(r.caf);x.fat+=PRICES[r.tamanho]||0});
  let totalAwb=d.length,totalPay=totalAwb*DELIVERY_PAY,totalRevenue=d.reduce((s,r)=>s+(PRICES[r.tamanho]||0),0),margin=totalRevenue-totalPay;
  $('#pAwb').textContent=num(totalAwb);$('#pCities').textContent=num(Object.keys(m).length);$('#pPay').textContent=brl(totalPay);$('#pRevenue').textContent=brl(totalRevenue);$('#pMargin').textContent=brl(margin);
  let ready=periodReady();
  let rows=Object.entries(m).sort((a,b)=>b[1].awb-a[1].awb).map(([c,x])=>{
    let due=x.awb*DELIVERY_PAY,paid=paidFor(c),debt=Math.max(0,due-paid),status=paymentStatus(due,paid),cls=status==='Pago'?'pago':status==='Parcial'?'parcial':'pendente';
    let safeCity=c.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    return `<tr><td>${safeCity}</td><td>${x.cafs.size}</td><td>${num(x.awb)}</td><td>${brl(due)}</td><td class="paid">${brl(paid)}</td><td class="debt">${brl(debt)}</td><td><span class="status-pill status-${cls}">${status}</span></td><td><button type="button" class="pay-btn" data-city="${safeCity}" ${ready?'':'disabled'}>${status==='Pendente'?'Registrar':status==='Parcial'?'Pagar saldo':'Novo pagamento'}</button></td></tr>`;
  });
  $('#paymentTable').innerHTML=(!ready?'<div class="preview warn"><b>Selecione Ano, Mês e Quinzena</b><p>Os valores devidos são exibidos, mas o registro de pagamentos só é liberado para um fechamento quinzenal específico.</p></div>':'')+table(['Cidade','CAFs','AWBs','Total devido','Já pago','Saldo devedor','Status','Ação'],rows);
  renderPaymentHistory();
}
function openPayment(city){
  if(!periodReady()){toast('Selecione Ano, Mês e Quinzena antes de registrar o pagamento.');return}
  let d=filtered().filter(r=>(r.cidade||'NÃO INFORMADA')===city),due=d.length*DELIVERY_PAY,paid=paidFor(city),debt=Math.max(0,due-paid);
  activePaymentCity=city;
  $('#paymentContext').textContent=`${city} • ${periodLabel()} • ${num(d.length)} AWBs × R$ 5,00`;
  $('#mDue').textContent=brl(due);$('#mPaid').textContent=brl(paid);$('#mDebt').textContent=brl(debt);
  let last=payments.find(x=>x.city===city);$('#mDriver').value=last?.driver||'';$('#mAmount').value=debt>0?debt.toFixed(2):'';$('#mDate').value=new Date().toISOString().slice(0,10);$('#mNote').value='';
  const modal=$('#paymentModal');modal.style.display='flex';modal.classList.add('open');document.body.classList.add('modal-open');
  setTimeout(()=>$('#mDriver').focus(),50);
}
function closePaymentModal(){const modal=$('#paymentModal');modal.classList.remove('open');modal.style.display='none';document.body.classList.remove('modal-open');activePaymentCity=null}
function registerPayment(){
  if(!activePaymentCity||!periodReady()){toast('Não foi possível identificar o fechamento.');return}
  let amount=Number($('#mAmount').value),driver=$('#mDriver').value.trim(),date=$('#mDate').value,note=$('#mNote').value.trim();
  if(!driver){toast('Informe o nome do entregador.');return}if(!date){toast('Informe a data do pagamento.');return}if(!(amount>0)){toast('Informe um valor de pagamento válido.');return}
  let d=filtered().filter(r=>(r.cidade||'NÃO INFORMADA')===activePaymentCity),due=d.length*DELIVERY_PAY,paid=paidFor(activePaymentCity),debt=Math.max(0,due-paid);
  if(amount>debt+.005&&debt>0){toast('O pagamento informado é maior que o saldo devedor.');return}
  let p=selectedPeriod();payments.unshift({id:Date.now(),city:activePaymentCity,driver,amount,date,note,year:Number(p.year),month:Number(p.month),quin:Number(p.quin)});savePayments();closePaymentModal();renderPayments();toast(`Pagamento de ${brl(amount)} registrado para ${activePaymentCity}.`)
}
function renderPaymentHistory(){let box=$('#paymentHistory');if(!box)return;let list=payments.filter(x=>paymentMatchesFilters(x)).sort((a,b)=>(b.date||'').localeCompare(a.date||''));let rows=list.map(x=>`<tr><td>${x.date?x.date.split('-').reverse().join('/'):''}</td><td>${x.city}</td><td>${x.driver}</td><td>${x.quin}ª quinzena ${String(x.month).padStart(2,'0')}/${x.year}</td><td><b>${brl(x.amount)}</b></td><td>${x.note||'—'}</td><td><button class="danger-link" onclick="deletePayment(${x.id})">Excluir</button></td></tr>`);box.innerHTML=`<div class="history-title"><div><h3>Histórico de pagamentos</h3><p>${list.length} lançamento(s) no filtro atual.</p></div></div>`+(rows.length?table(['Data','Cidade','Entregador','Fechamento','Valor pago','Observação',''],rows):'<p>Nenhum pagamento registrado neste filtro.</p>')}
function deletePayment(id){if(!confirm('Excluir este lançamento de pagamento?'))return;payments=payments.filter(x=>x.id!==id);savePayments();renderPayments();toast('Lançamento excluído.')}
window.deletePayment=deletePayment;
function searchCaf(){let q=$('#cafSearch').value.trim(),d=data.filter(r=>r.caf.includes(q));if(!q){$('#cafResult').innerHTML='';return}if(!d.length){$('#cafResult').innerHTML='<p>Nenhuma CAF encontrada.</p>';return}let exact=d.filter(r=>r.caf===q);if(exact.length)d=exact;let fat=d.reduce((s,r)=>s+(PRICES[r.tamanho]||0),0), cats={};d.forEach(r=>cats[r.tamanho]=(cats[r.tamanho]||0)+1);let summary=`<div class="cards"><article><label>CAF</label><strong>${d[0].caf}</strong><small>${d[0].cidade}/${d[0].uf}</small></article><article><label>AWBs</label><strong>${d.length}</strong><small>volumes</small></article><article><label>Faturamento</label><strong>${brl(fat)}</strong><small>estimado</small></article></div>`;let rows=d.slice(0,500).map(r=>`<tr><td>${r.awb}</td><td>${r.data}</td><td>${r.peso}</td><td>${r.tamanho}</td><td>${brl(PRICES[r.tamanho]||0)}</td></tr>`);$('#cafResult').innerHTML=summary+table(['AWB','Data','Peso','Categoria','Valor'],rows)}
function normalizeRow(o){let get=(...ks)=>{for(let k of ks){let key=Object.keys(o).find(x=>x.toLowerCase().trim()===k);if(key)return o[key]}return''};let raw=get('dt_finalizada_caf_off','dt_finalizada_caf','data'), dt='';if(typeof raw==='number'){let x=XLSX.SSF.parse_date_code(raw);dt=`${x.y}-${String(x.m).padStart(2,'0')}-${String(x.d).padStart(2,'0')}`}else if(raw instanceof Date)dt=raw.toISOString().slice(0,10);else{let s=String(raw||'');let m=s.match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);dt=m?`${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`:s.slice(0,10)}let peso=Number(String(get('peso')).replace(',','.'))||0;let tam=peso<=.02?'CARTÃO':peso<=3?'PEQUENO':peso<=10?'MÉDIO':'GRANDE';return{caf:String(get('cafid1','caf')||''),data:dt,entregues:Number(get('entregues'))||0,awb:String(get('awb1','awb')||''),peso,tamanho:tam,cidade:String(get('cidade')||''),uf:String(get('uf')||'')}}
function handleFile(file){let reader=new FileReader();reader.onload=e=>{try{let wb=XLSX.read(e.target.result,{type:'array',cellDates:true}),ws=wb.Sheets['CAF_Consolidado']||wb.Sheets[wb.SheetNames[0]],raw=XLSX.utils.sheet_to_json(ws,{defval:''}),incoming=raw.map(normalizeRow).filter(r=>r.awb&&r.caf);let existing=new Set(data.map(r=>r.caf+'|'+r.awb)),fresh=incoming.filter(r=>!existing.has(r.caf+'|'+r.awb)),dups=incoming.length-fresh.length,cafs=new Set(incoming.map(r=>r.caf)).size,cities=new Set(incoming.map(r=>r.cidade)).size,fat=incoming.reduce((s,r)=>s+(PRICES[r.tamanho]||0),0);$('#preview').innerHTML=`<div class="preview"><h3>${file.name}</h3><p><b>${incoming.length}</b> registros • <b>${cafs}</b> CAFs • <b>${cities}</b> cidades • ${brl(fat)}</p><p class="${dups?'warn':'ok'}">${dups} registros já existentes • ${fresh.length} novos registros</p><button id="confirmImport" ${fresh.length?'':'disabled'}>Confirmar importação</button></div>`;$('#confirmImport')?.addEventListener('click',()=>{data.push(...fresh);imports.unshift({arquivo:file.name,registros:fresh.length,status:'Importado'});
populateFilters();render();renderHistory();$('#preview').innerHTML='';toast(`${fresh.length} registros importados com sucesso.`)})}catch(err){toast('Não foi possível ler a planilha. Verifique o formato.') }};reader.readAsArrayBuffer(file)}
function renderHistory(){let rows=imports.map(x=>`<tr><td>${x.arquivo}</td><td>${x.registros}</td><td>${x.status}</td></tr>`);$('#history').innerHTML=table(['Arquivo','Novos registros','Status'],rows)}
function toast(t){$('#toast').textContent=t;$('#toast').style.display='block';setTimeout(()=>$('#toast').style.display='none',3000)}
$$('.tab').forEach(b=>b.onclick=()=>{$$('.tab').forEach(x=>x.classList.remove('active'));$$('.page').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#'+b.dataset.tab).classList.add('active')});$$('.filters select').forEach(x=>x.onchange=render);$('#clearFilters').onclick=()=>{$$('.filters select').forEach(x=>x.value='');render()};$('#cafSearch').oninput=searchCaf;$('#btnUpload').onclick=()=>{$$('.tab').find(x=>x.dataset.tab==='importacoes').click();$('#fileInput').click()};$('#drop').onclick=()=>$('#fileInput').click();$('#fileInput').onchange=e=>e.target.files[0]&&handleFile(e.target.files[0]);$('#drop').ondragover=e=>e.preventDefault();$('#drop').ondrop=e=>{e.preventDefault();e.dataTransfer.files[0]&&handleFile(e.dataTransfer.files[0])};

populateFilters();render();renderHistory();

// Pagamentos: listeners globais (funcionam mesmo após a tabela ser recriada pelos filtros)
document.addEventListener('click',function(e){
  const payButton=e.target.closest('.pay-btn');
  if(payButton){e.preventDefault();if(!payButton.disabled)openPayment(payButton.dataset.city);return;}
  if(e.target.closest('#closePaymentModal')){e.preventDefault();closePaymentModal();return;}
  if(e.target.closest('#savePayment')){e.preventDefault();registerPayment();return;}
  if(e.target.closest('#payFull')){e.preventDefault();if(!activePaymentCity)return;let d=filtered().filter(r=>(r.cidade||'NÃO INFORMADA')===activePaymentCity),debt=Math.max(0,d.length*DELIVERY_PAY-paidFor(activePaymentCity));$('#mAmount').value=debt.toFixed(2);return;}
  if(e.target.closest('#paymentHistoryBtn')){e.preventDefault();let h=$('#paymentHistory');h.style.display=h.style.display==='none'?'block':'none';renderPaymentHistory();return;}
});
$('#paymentModal').addEventListener('click',e=>{if(e.target===$('#paymentModal'))closePaymentModal()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#paymentModal').classList.contains('open'))closePaymentModal()});
