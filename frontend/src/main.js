import { api } from './api.js';

// ── Color palette ────────────────────────────────────────────
const COLORS = [
    '#5b8def', '#4ade80', '#fbbf24', '#f87171', '#a78bfa',
    '#fb923c', '#22d3ee', '#f472b6', '#818cf8', '#34d399',
    '#e879f9', '#facc15', '#38bdf8', '#c084fc', '#a3e635',
    '#fb7185', '#6ee7b7', '#fcd34d', '#93c5fd',
];

function fmt(n) {
    return '¥' + Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Global Filter State ──────────────────────────────────────
let taxonomyData = [];
let excludedCategories = [];

// Track if pie chart is drilling down
let pieDrillDownL1 = null;
let pieDrillDownL2 = null;

function getFilters() {
    const f = {};
    const user = document.getElementById('f-user').value;
    const year = document.getElementById('f-year').value;
    const platform = document.getElementById('f-platform').value;
    const track = document.getElementById('f-track').value;
    const category = document.getElementById('f-category').value;
    const categoryL2 = document.getElementById('f-category-l2').value;
    const dateFrom = document.getElementById('f-date-from').value;
    const dateTo = document.getElementById('f-date-to').value;

    if (user) f.user = user;
    if (year) f.year = year;
    if (platform) f.platform = platform;
    if (track) f.track = track;

    // Drill-down overrides L1 if not explicitly set
    if (category) f.category = category;
    else if (pieDrillDownL1) f.category = pieDrillDownL1;

    // Drill-down overrides L2 if not explicitly set
    if (categoryL2) f.category_l2 = categoryL2;
    else if (pieDrillDownL2) f.category_l2 = pieDrillDownL2;

    if (dateFrom) f.date_from = dateFrom;
    if (dateTo) f.date_to = dateTo;
    if (excludedCategories.length > 0) f.exclude_categories = excludedCategories.join(',');

    return f;
}

// ── Meta: Populate Filter Dropdowns ──────────────────────────
async function loadMeta() {
    const data = await api.meta();

    // Users
    const userSel = document.getElementById('f-user');
    data.users.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.id;
        opt.textContent = u.label;
        userSel.appendChild(opt);
    });

    // Years
    const yearSel = document.getElementById('f-year');
    data.years.forEach(y => {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y + ' 年';
        yearSel.appendChild(opt);
    });

    // Taxonomy (L1 + L2)
    taxonomyData = data.taxonomy;
    const catSel = document.getElementById('f-category');
    const excludeSel = document.getElementById('f-exclude-add');

    data.taxonomy.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.l1;
        opt.textContent = `${t.l1} (${t.count})`;
        catSel.appendChild(opt);

        const opt2 = document.createElement('option');
        opt2.value = t.l1;
        opt2.textContent = t.l1;
        excludeSel.appendChild(opt2);

        // Also allow excluding specific L2s
        t.l2s.forEach(l2 => {
            const opt3 = document.createElement('option');
            opt3.value = l2;
            opt3.textContent = `  ↳ ${l2}`;
            excludeSel.appendChild(opt3);
        });
    });

    document.getElementById('f-category').addEventListener('change', updateL2Options);
    updateL2Options(); // Populate L2 initially
}

function updateL2Options() {
    const l1 = document.getElementById('f-category').value;
    const l2Sel = document.getElementById('f-category-l2');
    l2Sel.innerHTML = '<option value="">全部二级</option>';

    if (l1) {
        const entry = taxonomyData.find(t => t.l1 === l1);
        if (entry) {
            entry.l2s.forEach(l2 => {
                const opt = document.createElement('option');
                opt.value = l2;
                opt.textContent = l2;
                l2Sel.appendChild(opt);
            });
        }
    } else {
        // If no L1 is selected, group all L2s by L1
        taxonomyData.forEach(t => {
            const group = document.createElement('optgroup');
            group.label = t.l1;
            t.l2s.forEach(l2 => {
                const opt = document.createElement('option');
                opt.value = l2;
                opt.textContent = l2;
                group.appendChild(opt);
            });
            l2Sel.appendChild(group);
        });
    }
}

// ── Exclude Tags ─────────────────────────────────────────────
function renderExcludeTags() {
    const container = document.getElementById('exclude-tags');
    container.innerHTML = '';
    excludedCategories.forEach(cat => {
        const tag = document.createElement('span');
        tag.className = 'exclude-tag';
        tag.innerHTML = `${cat} <span class="remove-tag" data-cat="${cat}">✕</span>`;
        container.appendChild(tag);
    });

    container.querySelectorAll('.remove-tag').forEach(btn => {
        btn.addEventListener('click', () => {
            excludedCategories = excludedCategories.filter(c => c !== btn.dataset.cat);
            renderExcludeTags();
        });
    });
}

// ── Summary Cards ────────────────────────────────────────────
async function loadSummary() {
    const data = await api.summary(getFilters());
    document.getElementById('total-spend').textContent = fmt(data.total_spend);
    document.getElementById('total-refund').textContent = fmt(data.total_refund);
    document.getElementById('total-cashflow').textContent = fmt(data.cashflow_total);
    document.getElementById('total-records').textContent = data.total_records.toLocaleString();
}

// ── Category Pie Chart ───────────────────────────────────────
let pieChart = null;

async function loadCategoryPie() {
    const filters = getFilters();

    // If we are drilling down or filtering by L1, show L2 distribution
    // If we are drilling down into L2, pie chart won't drill further, it just shows that single L2 slice (or L3 if we had it, but we don't)
    // To keep it useful, if pieDrillDownL2 is active, the pie still shows the L2 slice, but it's 100% of itself.
    let level = 'l1';
    if (filters.category || pieDrillDownL1) level = 'l2';

    const data = await api.byCategory(filters, level);

    const labels = data.map(d => level === 'l1' ? (d.global_category_l1 || '未分类') : (d.global_category_l2 || '未分类'));
    const values = data.map(d => d.total);

    if (pieChart) pieChart.destroy();

    const canvas = document.getElementById('category-pie');

    // Update header to indicate drill-down
    const header = canvas.parentElement.querySelector('h2');

    // Check if global filters are actively driving this vs pie clicks
    const hasGlobalL1 = !!document.getElementById('f-category').value;
    const hasGlobalL2 = !!document.getElementById('f-category-l2').value;

    if (pieDrillDownL2 && !hasGlobalL2) {
        header.innerHTML = `分类支出 <span style="font-size:12px;color:#5b8def;cursor:pointer" id="reset-drill-l2">(退出: ${pieDrillDownL2}) ✕</span>`;
        document.getElementById('reset-drill-l2').addEventListener('click', () => {
            pieDrillDownL2 = null;
            refreshAll();
        });
    } else if (pieDrillDownL1 && !hasGlobalL1) {
        header.innerHTML = `分类支出 <span style="font-size:12px;color:#5b8def;cursor:pointer" id="reset-drill-l1">(退出: ${pieDrillDownL1}) ✕</span>`;
        document.getElementById('reset-drill-l1').addEventListener('click', () => {
            pieDrillDownL1 = null;
            pieDrillDownL2 = null;
            refreshAll();
        });
    } else if (level === 'l2') {
        header.innerHTML = `二级分类分布`;
    } else {
        header.innerHTML = `一级分类分布 <span style="font-size:11px;color:#6b7394">(点击钻取)</span>`;
    }

    pieChart = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: COLORS.slice(0, labels.length),
                borderWidth: 0,
                hoverOffset: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            onClick: (e, items) => {
                if (items.length > 0) {
                    const idx = items[0].index;
                    if (level === 'l1' && !pieDrillDownL1) {
                        pieDrillDownL1 = labels[idx];
                        refreshAll();
                    } else if (level === 'l2' && !pieDrillDownL2) {
                        const selectedL2 = labels[idx] === '未分类' ? '' : labels[idx];
                        pieDrillDownL2 = selectedL2;
                        refreshAll();
                        // Scroll down to the table so the user can see the filtered result
                        document.getElementById('tx-table').scrollIntoView({ behavior: 'smooth' });
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#9ca3b8',
                        font: { family: 'Inter', size: 11 },
                        padding: 10,
                        usePointStyle: true,
                        pointStyleWidth: 8,
                    },
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = ((ctx.parsed / total) * 100).toFixed(1);
                            return `${ctx.label}: ${fmt(ctx.parsed)} (${pct}%)`;
                        },
                    },
                },
            },
        },
    });
}

// ── Trend Chart ──────────────────────────────────────────────
let trendChart = null;

async function loadTrend(granularity = 'month') {
    const data = await api.byPeriod(getFilters(), granularity);
    const labels = data.map(d => d.period);
    const values = data.map(d => d.total);

    if (trendChart) trendChart.destroy();

    trendChart = new Chart(document.getElementById('trend-line'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: '消费支出',
                data: values,
                backgroundColor: '#5b8def44',
                borderColor: '#5b8def',
                borderWidth: 2,
                borderRadius: 6,
                hoverBackgroundColor: '#5b8def88',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                x: { ticks: { color: '#6b7394', font: { size: 11 } }, grid: { display: false } },
                y: {
                    ticks: { color: '#6b7394', callback: v => '¥' + (v >= 10000 ? (v / 10000).toFixed(1) + 'W' : v) },
                    grid: { color: '#2a2f4522' },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => fmt(ctx.parsed.y) } },
            },
        },
    });
}

// ── Top Categories Ranking ───────────────────────────────────
async function loadTopCategories() {
    const level = (getFilters().category || pieDrillDownL1) ? 'l2' : 'l1';
    const data = await api.topCategories(getFilters(), level, 20);
    const container = document.getElementById('top-categories-list');
    container.innerHTML = '';

    if (!data.length) {
        container.innerHTML = '<div style="color:#6b7394;padding:20px">暂无数据</div>';
        return;
    }

    const maxTotal = data[0]?.total || 1;

    data.forEach((item, i) => {
        const barWidth = Math.max(5, (item.total / maxTotal) * 100);
        const name = level === 'l1' ? item.category : item.category_l2;
        const div = document.createElement('div');
        div.className = 'ranking-item';
        div.innerHTML = `
      <span class="rank-num ${i < 3 ? 'top3' : ''}">${i + 1}</span>
      <div class="rank-info">
        <div class="rank-name">${name || '未分类'}</div>
        <div class="rank-sub">${item.count} 笔 · 均 ${fmt(item.avg)}</div>
        <div class="rank-bar" style="width:${barWidth}%"></div>
      </div>
      <span class="rank-amount">${fmt(item.total)}</span>
    `;
        container.appendChild(div);
    });
}

// ── Top Merchants Bar Chart ──────────────────────────────────
let merchantChart = null;

async function loadMerchants() {
    const data = await api.topMerchants(getFilters(), 15);
    const labels = data.map(d => d.merchant.length > 14 ? d.merchant.slice(0, 14) + '…' : d.merchant);
    const values = data.map(d => d.total);

    if (merchantChart) merchantChart.destroy();

    const canvas = document.getElementById('merchant-bar');
    canvas.parentElement.style.height = Math.max(400, data.length * 32) + 'px';

    merchantChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: COLORS.slice(0, labels.length).map(c => c + '88'),
                borderColor: COLORS.slice(0, labels.length),
                borderWidth: 1,
                borderRadius: 4,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: { color: '#6b7394', callback: v => '¥' + (v >= 10000 ? (v / 10000).toFixed(1) + 'W' : v) },
                    grid: { color: '#2a2f4522' },
                },
                y: { ticks: { color: '#9ca3b8', font: { size: 11 } }, grid: { display: false } },
            },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => `${fmt(ctx.parsed.x)} (${data[ctx.dataIndex].count}笔)` } },
            },
        },
    });
}

// ── Cashflow Panel ───────────────────────────────────────────
async function loadCashflow() {
    const data = await api.cashflowSummary(getFilters());
    const container = document.getElementById('cashflow-content');

    if (!data.categories.length) {
        container.innerHTML = '<div style="color:#6b7394;padding:20px">暂无数据</div>';
        return;
    }

    let html = '<div class="cashflow-grid">';
    for (const item of data.categories.slice(0, 10)) {
        html += `
      <div class="cashflow-item">
        <div class="cf-label">${item.category}</div>
        <div class="cf-value">${fmt(item.total)}</div>
        <div class="cf-count">${item.count} 笔</div>
      </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
}

// ── Transaction Table Inline Editing ─────────────────────────
function createL1L2Selects(tx) {
    const l1Sel = document.createElement('select');
    l1Sel.className = 'edit-select';

    const l2Sel = document.createElement('select');
    l2Sel.className = 'edit-select';

    // Populate L1
    taxonomyData.forEach(t => {
        const opt = new Option(t.l1, t.l1);
        opt.selected = t.l1 === tx.category_l1;
        l1Sel.add(opt);
    });

    // Function to populate L2 based on L1
    const updateL2 = () => {
        const l1 = l1Sel.value;
        l2Sel.innerHTML = '';
        const entry = taxonomyData.find(t => t.l1 === l1);
        if (entry) {
            entry.l2s.forEach(l2 => {
                const opt = new Option(l2, l2);
                opt.selected = l2 === tx.category_l2;
                l2Sel.add(opt);
            });
        }
    };

    l1Sel.addEventListener('change', updateL2);
    updateL2(); // initial populate

    return { l1Sel, l2Sel };
}

async function saveTransactionEdit(tx, l1, l2, tr) {
    try {
        const btn = tr.querySelector('.btn-save');
        if (btn) btn.disabled = true;

        await api.updateTransaction(tx.id, l1, l2);

        // Refresh table to reflect changes cleanly without full reload
        loadTransactions();
        // And refresh summary pie if necessary
        loadCategoryPie();
        loadTopCategories();
    } catch (err) {
        alert("保存失败: " + err.message);
        loadTransactions(); // Revert
    }
}

// ── Transaction Table ────────────────────────────────────────
let currentPage = 1;
const perPage = 50;

async function loadTransactions() {
    const filters = getFilters();
    const search = document.getElementById('search-input').value;

    const data = await api.transactions({
        ...filters,
        page: currentPage,
        per_page: perPage,
        search,
    });

    const tbody = document.getElementById('tx-body');
    tbody.innerHTML = '';

    if (!data.records.length) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#6b7394;padding:20px">暂无数据</td></tr>';
    }

    for (const tx of data.records) {
        const tr = document.createElement('tr');
        tr.dataset.id = tx.id;

        const platformBadge = tx.platform === 'alipay'
            ? '<span class="platform-badge platform-alipay">支付宝</span>'
            : '<span class="platform-badge platform-wechat">微信</span>';

        const amountClass = tx.is_refunded ? 'amount refunded' : 'amount';
        const l1 = tx.category_l1 ? `<span class="category-tag">${tx.category_l1}</span>` : '-';
        const l2 = tx.category_l2 ? `<span class="l2-tag">${tx.category_l2}</span>` : '<span class="l2-tag" style="opacity:0.3">待打标</span>';

        let trackTag = '';
        if (tx.track === 'consumption') trackTag = '<span class="track-tag track-consumption">消费</span>';
        else if (tx.track === 'cashflow') trackTag = '<span class="track-tag track-cashflow">资金</span>';
        else trackTag = '<span class="track-tag track-refund">退款</span>';

        tr.innerHTML = `
      <td>${tx.timestamp.slice(0, 16)}</td>
      <td>${platformBadge}</td>
      <td title="${tx.counterparty}">${tx.counterparty}</td>
      <td title="${tx.description}">${tx.description}</td>
      <td class="${amountClass}">¥${tx.amount.toFixed(2)}</td>
      <td class="amount">¥${tx.effective_amount.toFixed(2)}</td>
      <td class="l1-cell">${l1}</td>
      <td class="l2-cell">${l2}</td>
      <td>${tx.payment_method || ''}</td>
      <td>${trackTag}</td>
      <td class="td-actions"><button class="btn-mini btn-edit">编辑</button></td>
    `;

        // Setup Edit Button
        const btnEdit = tr.querySelector('.btn-edit');
        btnEdit.addEventListener('click', () => {
            const { l1Sel, l2Sel } = createL1L2Selects(tx);

            tr.querySelector('.l1-cell').innerHTML = '';
            tr.querySelector('.l1-cell').appendChild(l1Sel);

            tr.querySelector('.l2-cell').innerHTML = '';
            tr.querySelector('.l2-cell').appendChild(l2Sel);

            const actions = tr.querySelector('.td-actions');
            actions.innerHTML = `
        <button class="btn-mini save btn-save">保存</button>
        <button class="btn-mini cancel">取消</button>
      `;

            actions.querySelector('.btn-save').addEventListener('click', () => {
                saveTransactionEdit(tx, l1Sel.value, l2Sel.value, tr);
            });

            actions.querySelector('.cancel').addEventListener('click', () => {
                loadTransactions(); // Just reload to cancel
            });
        });

        tbody.appendChild(tr);
    }

    // Pagination
    const totalPages = Math.ceil(data.total / perPage);
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';

    if (totalPages > 1) {
        if (currentPage > 1) {
            const prev = document.createElement('button');
            prev.textContent = '← 上一页';
            prev.addEventListener('click', () => { currentPage--; loadTransactions(); });
            pagination.appendChild(prev);
        }

        const info = document.createElement('span');
        info.className = 'page-info';
        info.textContent = ` 第 ${currentPage}/${totalPages} 页（共 ${data.total} 条）`;
        pagination.appendChild(info);

        if (currentPage < totalPages) {
            const next = document.createElement('button');
            next.textContent = '下一页 →';
            next.addEventListener('click', () => { currentPage++; loadTransactions(); });
            pagination.appendChild(next);
        }
    }
}

// ── Refresh All ──────────────────────────────────────────────
async function refreshAll() {
    currentPage = 1;
    await Promise.all([
        loadSummary(),
        loadCategoryPie(),
        loadTrend(document.querySelector('.btn-period.active')?.dataset.period || 'month'),
        loadTopCategories(),
        loadMerchants(),
        loadCashflow(),
        loadTransactions(),
    ]);
}

// ── Event Listeners ──────────────────────────────────────────
function setupListeners() {
    document.getElementById('btn-apply').addEventListener('click', () => {
        pieDrillDownL1 = null; // reset drill-down on new explicit filter
        pieDrillDownL2 = null;
        refreshAll();
    });

    document.getElementById('btn-reset').addEventListener('click', () => {
        document.getElementById('f-user').value = '';
        document.getElementById('f-year').value = '';
        document.getElementById('f-platform').value = '';
        document.getElementById('f-track').value = 'consumption';
        document.getElementById('f-category').value = '';
        document.getElementById('f-category-l2').value = '';
        document.getElementById('f-date-from').value = '';
        document.getElementById('f-date-to').value = '';
        document.getElementById('search-input').value = '';
        excludedCategories = [];
        pieDrillDownL1 = null;
        pieDrillDownL2 = null;
        renderExcludeTags();
        updateL2Options();
        refreshAll();
    });

    document.getElementById('btn-search').addEventListener('click', () => {
        currentPage = 1;
        loadTransactions();
    });

    document.getElementById('search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            currentPage = 1;
            loadTransactions();
        }
    });

    document.querySelectorAll('.btn-period').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.btn-period').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadTrend(btn.dataset.period);
        });
    });

    document.getElementById('f-exclude-add').addEventListener('change', (e) => {
        const val = e.target.value;
        if (val && !excludedCategories.includes(val)) {
            excludedCategories.push(val);
            renderExcludeTags();
        }
        e.target.value = '';
    });
}

// ── Init ─────────────────────────────────────────────────────
async function init() {
    setupListeners();
    await loadMeta();
    await refreshAll();
}

init().catch(err => {
    console.error('Dashboard init error:', err);
    document.getElementById('tx-body').innerHTML =
        `<tr><td colspan="11" style="color:#f87171;padding:20px">加载失败: ${err.message}</td></tr>`;
});
