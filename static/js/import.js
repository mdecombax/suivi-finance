/**
 * Import d'ordres assisté par IA — logique des 3 étapes
 * (dépôt → prévisualisation éditable → confirmation)
 */
(function () {
    'use strict';

    const state = {
        files: [],
        models: [],
        defaultModel: null,
        rows: [],
        declaredTotal: null,
        metrics: null,
        currencyWarning: null,
    };

    // ----------------------------------------------------------------------
    // Étapes
    // ----------------------------------------------------------------------
    function goToStep(n) {
        document.querySelectorAll('.import-step').forEach((el) => {
            const s = parseInt(el.dataset.step, 10);
            el.classList.toggle('active', s === n);
            el.classList.toggle('done', s < n);
        });
        document.getElementById('stepUpload').style.display = n === 1 ? '' : 'none';
        document.getElementById('stepPreview').style.display = n === 2 ? '' : 'none';
        document.getElementById('stepDone').style.display = n === 3 ? '' : 'none';
    }

    // ----------------------------------------------------------------------
    // Étape 1 — modèles + dépôt
    // ----------------------------------------------------------------------
    async function loadModels() {
        const select = document.getElementById('modelSelect');
        try {
            const reg = await apiGet('/api/import/models');
            state.models = reg.models || [];
            state.defaultModel = reg.default;
            select.innerHTML = state.models.map((m) => {
                const dispo = m.available ? '' : ' — clé manquante';
                const sel = m.key === reg.default ? ' selected' : '';
                return `<option value="${m.key}"${sel}>${m.label} (${m.priceIn}/${m.priceOut} $)${dispo}</option>`;
            }).join('');
            updateModelNote();
        } catch (e) {
            console.error('Chargement modèles échoué', e);
            select.innerHTML = '<option value="">Erreur de chargement</option>';
        }
    }

    function selectedModel() {
        const key = document.getElementById('modelSelect').value;
        return state.models.find((m) => m.key === key) || null;
    }

    function updateModelNote() {
        const m = selectedModel();
        const note = document.getElementById('modelNote');
        if (!m) { note.textContent = ''; return; }
        let txt = m.note || '';
        if (!m.multimodal) txt += ' Limité aux fichiers texte/CSV.';
        if (!m.available) txt += ' ⚠️ Clé API non configurée côté serveur.';
        note.textContent = txt;
    }

    function handleFiles(fileList) {
        const added = Array.from(fileList || []);
        if (!added.length) return;
        state.files = state.files.concat(added);
        renderChosenFiles();
        document.getElementById('parseBtn').disabled = state.files.length === 0;
    }

    function renderChosenFiles() {
        const chosen = document.getElementById('fileChosen');
        if (!state.files.length) { chosen.style.display = 'none'; chosen.innerHTML = ''; return; }
        chosen.style.display = 'block';
        chosen.innerHTML = state.files.map((f, i) =>
            `<div class="import-file-item">📎 ${f.name} <span>(${(f.size / 1024).toFixed(0)} Ko)</span>` +
            `<button class="import-file-remove" data-i="${i}" title="Retirer">✕</button></div>`
        ).join('');
    }

    function wireDropzone() {
        const dz = document.getElementById('dropzone');
        const input = document.getElementById('fileInput');
        const chosen = document.getElementById('fileChosen');
        dz.addEventListener('click', () => input.click());
        input.addEventListener('change', (e) => { handleFiles(e.target.files); input.value = ''; });
        ['dragenter', 'dragover'].forEach((ev) =>
            dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('dragover'); }));
        ['dragleave', 'drop'].forEach((ev) =>
            dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('dragover'); }));
        dz.addEventListener('drop', (e) => {
            if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
        });
        chosen.addEventListener('click', (e) => {
            const btn = e.target.closest('.import-file-remove');
            if (!btn) return;
            state.files.splice(parseInt(btn.dataset.i, 10), 1);
            renderChosenFiles();
            document.getElementById('parseBtn').disabled = state.files.length === 0;
        });
    }

    async function parseFile() {
        if (!state.files.length) return;
        const btn = document.getElementById('parseBtn');
        const txt = document.getElementById('parseBtnText');
        const load = document.getElementById('parseBtnLoading');
        btn.disabled = true; txt.style.display = 'none'; load.style.display = 'inline-block';

        try {
            const token = await getAuthToken();
            if (!token) throw new Error('Non authentifié');

            const fd = new FormData();
            state.files.forEach((f) => fd.append('file', f));
            fd.append('model', document.getElementById('modelSelect').value);

            const resp = await fetch('/api/orders/import/parse', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: fd,
            });
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.error || `Erreur HTTP ${resp.status}`);
            }

            state.rows = (data.orders || []).map(normalizeRow);
            state.declaredTotal = data.declared_total_eur;
            state.metrics = data.metrics;
            state.currencyWarning = data.currency_warning;

            // Erreurs éventuelles par fichier (les autres fichiers ont quand même été traités)
            (data.file_errors || []).forEach((fe) =>
                showMessage(`${fe.file} : ${fe.error}`, 'warning'));

            if (state.rows.length === 0) {
                showMessage('Aucun ordre d\'achat détecté dans le(s) document(s).', 'warning');
                return;
            }
            renderPreview();
            goToStep(2);
        } catch (e) {
            console.error('Parse échoué', e);
            showMessage(e.message, 'error');
        } finally {
            btn.disabled = false; txt.style.display = 'inline'; load.style.display = 'none';
        }
    }

    // ----------------------------------------------------------------------
    // Étape 2 — prévisualisation éditable
    // ----------------------------------------------------------------------
    function normalizeRow(o) {
        return {
            date: o.date || '',
            isin: (o.isin || '').toUpperCase(),
            name: o.name || '',
            quantity: o.quantity != null ? o.quantity : '',
            unit_price_eur: o.unit_price_eur != null ? o.unit_price_eur : '',
            total_eur: o.total_eur != null ? o.total_eur : '',
            side: o.side || '',
            confidence: o.confidence != null ? o.confidence : null,
        };
    }

    function cell(field, value, type) {
        const t = type || 'text';
        const step = t === 'number' ? ' step="any"' : '';
        return `<input class="import-cell" data-field="${field}" type="${t}"${step} value="${value != null ? String(value).replace(/"/g, '&quot;') : ''}">`;
    }

    function renderPreview() {
        const body = document.getElementById('previewBody');
        body.innerHTML = state.rows.map((r, i) => {
            const isinBad = !r.isin || !validateISIN(r.isin);
            const lowConf = r.confidence != null && r.confidence < 0.6;
            const cls = isinBad ? 'row-warn' : (lowConf ? 'row-lowconf' : '');
            return `
                <tr data-index="${i}" class="${cls}">
                    <td>${cell('date', r.date, 'date')}</td>
                    <td>${cell('isin', r.isin)}</td>
                    <td>${cell('name', r.name)}</td>
                    <td>${cell('quantity', r.quantity, 'number')}</td>
                    <td>${cell('unit_price_eur', r.unit_price_eur, 'number')}</td>
                    <td>${cell('total_eur', r.total_eur, 'number')}</td>
                    <td><button class="btn btn-danger import-del" title="Supprimer">✕</button></td>
                </tr>`;
        }).join('');
        renderMetrics();
    }

    function renderMetrics() {
        const m = state.metrics || {};
        const totalSaisi = state.rows.reduce((acc, r) => {
            const t = parseFloat(r.total_eur);
            if (!isNaN(t)) return acc + t;
            const u = parseFloat(r.unit_price_eur), q = parseFloat(r.quantity);
            if (!isNaN(u) && !isNaN(q)) return acc + u * q;
            return acc;
        }, 0);

        const cards = [];
        cards.push(metricCard('Total investi (calculé)', formatCurrency(totalSaisi, { maximumFractionDigits: 2 })));
        if (m.estimated_value_eur != null) {
            cards.push(metricCard('Valeur actuelle estimée', formatCurrency(m.estimated_value_eur, { maximumFractionDigits: 2 }),
                `${m.valued_positions}/${m.positions_count} positions valorisées`));
        }
        cards.push(metricCard('Positions distinctes', String(new Set(state.rows.map(r => (r.isin || '').toUpperCase()).filter(Boolean)).size)));
        if (state.declaredTotal != null) {
            cards.push(metricCard('Total déclaré (document)', formatCurrency(state.declaredTotal, { maximumFractionDigits: 2 }), 'à recouper chez ton courtier'));
        }
        document.getElementById('metricsBar').innerHTML = cards.join('');

        if (state.currencyWarning) {
            document.getElementById('metricsBar').innerHTML +=
                `<div class="import-currency-warn">⚠️ ${state.currencyWarning}</div>`;
        }
    }

    function metricCard(label, value, sub) {
        return `<div class="import-metric">
            <div class="import-metric-label">${label}</div>
            <div class="import-metric-value">${value}</div>
            ${sub ? `<div class="import-metric-sub">${sub}</div>` : ''}
        </div>`;
    }

    function wirePreviewEvents() {
        const body = document.getElementById('previewBody');
        body.addEventListener('input', (e) => {
            const input = e.target.closest('.import-cell');
            if (!input) return;
            const tr = input.closest('tr');
            const idx = parseInt(tr.dataset.index, 10);
            const field = input.dataset.field;
            let val = input.value;
            if (['quantity', 'unit_price_eur', 'total_eur'].includes(field)) {
                val = val === '' ? '' : parseFloat(val);
            }
            if (field === 'isin') val = val.toUpperCase();
            state.rows[idx][field] = val;

            // surlignage ISIN live
            if (field === 'isin') {
                const bad = !val || !validateISIN(val);
                tr.classList.toggle('row-warn', bad);
            }
            renderMetrics();
        });
        body.addEventListener('click', (e) => {
            if (e.target.closest('.import-del')) {
                const tr = e.target.closest('tr');
                const idx = parseInt(tr.dataset.index, 10);
                state.rows.splice(idx, 1);
                renderPreview();
            }
        });
    }

    function addRow() {
        state.rows.push(normalizeRow({ date: getTodayISO() }));
        renderPreview();
    }

    // ----------------------------------------------------------------------
    // Étape 3 — confirmation
    // ----------------------------------------------------------------------
    async function confirmImport() {
        const btn = document.getElementById('confirmBtn');
        const txt = document.getElementById('confirmBtnText');
        const load = document.getElementById('confirmBtnLoading');
        btn.disabled = true; txt.style.display = 'none'; load.style.display = 'inline-block';

        try {
            const orders = state.rows.map((r) => ({
                isin: (r.isin || '').toUpperCase(),
                quantity: r.quantity,
                date: r.date,
                unitPriceEUR: r.unit_price_eur,
                total_eur: r.total_eur,
            }));
            const result = await apiPost('/api/orders/import/confirm', { orders });
            renderDone(result);
            goToStep(3);
        } catch (e) {
            console.error('Confirm échoué', e);
            showMessage(e.message, 'error');
        } finally {
            btn.disabled = false; txt.style.display = 'inline'; load.style.display = 'none';
        }
    }

    function renderDone(result) {
        const el = document.getElementById('doneSummary');
        const parts = [`<div class="import-done-main">✅ ${result.created} ordre(s) importé(s)</div>`];
        if (result.skipped && result.skipped.length) {
            parts.push(`<div class="import-done-block"><strong>${result.skipped.length} ignoré(s)</strong><ul>` +
                result.skipped.map((s) => `<li>Ligne ${s.line} : ${s.reason}</li>`).join('') + '</ul></div>');
        }
        if (result.errors && result.errors.length) {
            parts.push(`<div class="import-done-block import-done-err"><strong>${result.errors.length} erreur(s)</strong><ul>` +
                result.errors.map((s) => `<li>Ligne ${s.line} (${s.isin}) : ${s.reason}</li>`).join('') + '</ul></div>');
        }
        el.innerHTML = parts.join('');
    }

    // ----------------------------------------------------------------------
    // Init
    // ----------------------------------------------------------------------
    async function init() {
        wireDropzone();
        wirePreviewEvents();
        document.getElementById('modelSelect').addEventListener('change', updateModelNote);
        document.getElementById('parseBtn').addEventListener('click', parseFile);
        document.getElementById('addRowBtn').addEventListener('click', addRow);
        document.getElementById('confirmBtn').addEventListener('click', confirmImport);
        document.getElementById('backBtn').addEventListener('click', () => goToStep(1));
        document.getElementById('restartBtn').addEventListener('click', () => {
            state.files = []; state.rows = [];
            document.getElementById('fileInput').value = '';
            renderChosenFiles();
            document.getElementById('parseBtn').disabled = true;
            goToStep(1);
        });
        await loadModels();
        goToStep(1);
    }

    window.ImportPage = { init };
})();
