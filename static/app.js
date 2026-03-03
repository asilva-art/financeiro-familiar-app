const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

const el = {
  file: document.getElementById('csv-file'),
  uploadBtn: document.getElementById('upload-btn'),
  reloadBtn: document.getElementById('reload-btn'),
  uploadStatus: document.getElementById('upload-status'),
  kpis: document.getElementById('kpis'),
  q: document.getElementById('q'),
  banco: document.getElementById('banco'),
  produto: document.getElementById('produto'),
  titular: document.getElementById('titular'),
  faturaRef: document.getElementById('fatura_ref'),
  cartaoFinal: document.getElementById('cartao_final'),
  recoBody: document.getElementById('reco-body'),
  count: document.getElementById('count'),
  txBody: document.getElementById('tx-body'),
};

function n(v) {
  const x = Number(v || 0);
  return Number.isFinite(x) ? x : 0;
}

function setStatus(msg) {
  el.uploadStatus.textContent = msg;
}

function fillSelect(select, values, allLabel = 'Todos') {
  const opts = ['<option value="">' + allLabel + '</option>'];
  values.forEach(v => opts.push(`<option value="${v}">${v}</option>`));
  select.innerHTML = opts.join('');
}

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const msg = await r.text();
    throw new Error(msg || 'Erro na API');
  }
  return r.json();
}

async function loadFilters() {
  const data = await api('/api/filters');
  fillSelect(el.banco, data.bancos || []);
  fillSelect(el.produto, data.produtos || []);
  fillSelect(el.titular, data.titulares || []);
  fillSelect(el.faturaRef, data.faturas_ref || []);
  fillSelect(el.cartaoFinal, data.cartoes || []);
}

function renderKPIs(s) {
  const cards = [
    ['Registros', String(s.total_registros || 0)],
    ['Faturas', String(s.faturas_distintas || 0)],
    ['Saldo Líquido', money.format(n(s.saldo_liquido))],
    ['Débitos', money.format(n(s.debitos))],
    ['Créditos', money.format(n(s.creditos))],
    ['Parcelados', String(s.parcelados || 0)],
  ];
  el.kpis.innerHTML = cards.map(([l, v]) => `<div class="card k"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
}

function renderReco(rows) {
  if (!rows.length) {
    el.recoBody.innerHTML = '<tr><td colspan="7">Sem dados de conciliação.</td></tr>';
    return;
  }
  el.recoBody.innerHTML = rows.map(r => {
    const diff = n(r.diferenca);
    const statusClass = r.status === 'OK' ? 'ok' : 'warn';
    return `<tr>
      <td>${r.banco || ''}</td>
      <td>${r.ref || ''}</td>
      <td>${money.format(n(r.total_cartao))}</td>
      <td>${money.format(n(r.total_conta))}</td>
      <td class="mono">${money.format(diff)}</td>
      <td class="${statusClass}">${r.status}</td>
      <td title="${r.vinculos || ''}">${(r.vinculos || '').slice(0, 64)}</td>
    </tr>`;
  }).join('');
}

function paramsFromFilters() {
  const p = new URLSearchParams();
  const map = {
    q: el.q.value,
    banco: el.banco.value,
    produto: el.produto.value,
    titular: el.titular.value,
    fatura_ref: el.faturaRef.value,
    cartao_final: el.cartaoFinal.value,
    limit: '500',
    offset: '0',
  };
  Object.entries(map).forEach(([k, v]) => {
    if (String(v || '').trim()) p.set(k, String(v).trim());
  });
  return p;
}

function renderTx(data) {
  const rows = data.rows || [];
  el.count.textContent = `${data.total || 0} registros`;
  el.txBody.innerHTML = rows.map(r => {
    const sig = String(r.sinal || '').toUpperCase();
    const klass = sig === 'CREDITO' ? 'cre' : 'deb';
    return `<tr>
      <td class="mono">${r.data_compra_iso || ''}</td>
      <td>${r.fatura_referencia_vencimento || ''}</td>
      <td>${r.banco || ''}</td>
      <td>${r.produto || ''}</td>
      <td>${r.eixo_titular || ''}</td>
      <td>${r.categoria_macro || ''} / ${r.categoria_subcategoria || ''}</td>
      <td>${r.descricao_original || ''}</td>
      <td>${r.parcela_texto || ''}</td>
      <td><span class="tag ${klass}">${sig}</span></td>
      <td class="mono">${money.format(n(r.valor_brl))}</td>
      <td class="mono">${r.id_lancamento_sistema || ''}</td>
    </tr>`;
  }).join('');
}

async function loadAll() {
  const [stats, reco, tx] = await Promise.all([
    api('/api/stats'),
    api('/api/reconciliation'),
    api('/api/transactions?' + paramsFromFilters().toString()),
  ]);
  renderKPIs(stats);
  renderReco(reco);
  renderTx(tx);
}

async function handleUpload() {
  if (!el.file.files.length) {
    setStatus('Selecione um arquivo CSV.');
    return;
  }
  const fd = new FormData();
  fd.append('file', el.file.files[0]);
  setStatus('Importando...');
  try {
    const out = await api('/api/import/base-csv', { method: 'POST', body: fd });
    setStatus(`Importado: ${out.rows_inserted}/${out.rows_read} novos.`);
    await loadFilters();
    await loadAll();
  } catch (e) {
    setStatus('Falha no upload: ' + e.message);
  }
}

el.uploadBtn.addEventListener('click', handleUpload);
el.reloadBtn.addEventListener('click', () => loadAll().catch(err => setStatus(err.message)));
[el.q, el.banco, el.produto, el.titular, el.faturaRef, el.cartaoFinal].forEach(x => {
  const ev = x === el.q ? 'input' : 'change';
  x.addEventListener(ev, () => loadAll().catch(err => setStatus(err.message)));
});

(async function init() {
  try {
    await loadFilters();
    await loadAll();
  } catch (e) {
    setStatus('Erro ao carregar: ' + e.message);
  }
})();
