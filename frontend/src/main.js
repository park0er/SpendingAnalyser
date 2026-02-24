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

// Multi-select state
let selectedPlatforms = [];
let selectedL1s = [];
let selectedL2s = [];

// Sort state
let currentSort = { column: 'timestamp', order: 'desc' };

function getFilters() {
    const f = {};
    const user = document.getElementById('f-user').value;
    const year = document.getElementById('f-year').value;
    const track = document.getElementById('f-track').value;
    const dateFrom = document.getElementById('f-date-from').value;
    const dateTo = document.getElementById('f-date-to').value;

    if (user) f.user = user;
    if (year) f.year = year;
    if (track) f.track = track;

    // Multi-select platform
    if (selectedPlatforms.length > 0) f.platform = selectedPlatforms.join(',');

    // Multi-select L1 — drill-down overrides if no explicit selection
    if (selectedL1s.length > 0) f.category = selectedL1s.join(',');
    else if (pieDrillDownL1) f.category = pieDrillDownL1;

    // Multi-select L2 — drill-down overrides if no explicit selection
    if (selectedL2s.length > 0) f.category_l2 = selectedL2s.join(',');
    else if (pieDrillDownL2) f.category_l2 = pieDrillDownL2;

    if (dateFrom) f.date_from = dateFrom;
    if (dateTo) f.date_to = dateTo;
    if (excludedCategories.length > 0) f.exclude_categories = excludedCategories.join(',');

    return f;
}

// ── Multi-Select Dropdown Component ──────────────────────────
function createMultiSelect(containerId, options, selectedArr, onChange) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    container.className = 'multi-select';

    // Display area showing selected items
    const display = document.createElement('div');
    display.className = 'ms-display';

    const updateDisplay = () => {
        if (selectedArr.length === 0) {
            display.innerHTML = `<span class="ms-placeholder">${container.dataset.placeholder || '全部'}</span>`;
        } else {
            display.innerHTML = selectedArr.map(v => {
                const opt = options.find(o => o.value === v);
                return `<span class="ms-pill">${opt ? opt.label : v}<span class="ms-pill-x" data-val="${v}">✕</span></span>`;
            }).join('');
        }
    };
    updateDisplay();
    container.appendChild(display);

    // Dropdown panel
    const panel = document.createElement('div');
    panel.className = 'ms-panel';

    options.forEach(opt => {
        const item = document.createElement('label');
        item.className = 'ms-item';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = opt.value;
        cb.checked = selectedArr.includes(opt.value);
        cb.addEventListener('change', () => {
            if (cb.checked) {
                if (!selectedArr.includes(opt.value)) selectedArr.push(opt.value);
            } else {
                const idx = selectedArr.indexOf(opt.value);
                if (idx >= 0) selectedArr.splice(idx, 1);
            }
            updateDisplay();
            if (onChange) onChange();
        });
        item.appendChild(cb);
        item.appendChild(document.createTextNode(opt.label));
        panel.appendChild(item);
    });

    container.appendChild(panel);

    // Toggle dropdown
    display.addEventListener('click', (e) => {
        e.stopPropagation();
        // Close all other dropdowns
        document.querySelectorAll('.multi-select.open').forEach(ms => {
            if (ms !== container) ms.classList.remove('open');
        });
        container.classList.toggle('open');
    });

    // Remove pill
    display.addEventListener('click', (e) => {
        if (e.target.classList.contains('ms-pill-x')) {
            e.stopPropagation();
            const val = e.target.dataset.val;
            const idx = selectedArr.indexOf(val);
            if (idx >= 0) selectedArr.splice(idx, 1);
            // Uncheck the checkbox
            panel.querySelectorAll('input').forEach(cb => {
                if (cb.value === val) cb.checked = false;
            });
            updateDisplay();
            if (onChange) onChange();
        }
    });
}

// Close dropdowns when clicking outside
document.addEventListener('click', () => {
    document.querySelectorAll('.multi-select.open').forEach(ms => ms.classList.remove('open'));
});

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

    // Taxonomy
    taxonomyData = data.taxonomy;

    // Platform multi-select
    createMultiSelect('ms-platform', [
        { value: 'alipay', label: '支付宝' },
        { value: 'wechat', label: '微信' },
        { value: 'jd', label: '京东' },
        { value: 'meituan', label: '美团' },
    ], selectedPlatforms);

    // L1 multi-select
    const l1Options = data.taxonomy.map(t => ({
        value: t.l1,
        label: `${t.l1} (${t.count})`,
    }));
    createMultiSelect('ms-category', l1Options, selectedL1s, updateL2MultiSelect);

    // L2 multi-select
    updateL2MultiSelect();

    // Exclude selector (keep as single select for adding)
    const excludeSel = document.getElementById('f-exclude-add');
    data.taxonomy.forEach(t => {
        const opt2 = document.createElement('option');
        opt2.value = t.l1;
        opt2.textContent = t.l1;
        excludeSel.appendChild(opt2);
        t.l2s.forEach(l2 => {
            const opt3 = document.createElement('option');
            opt3.value = l2;
            opt3.textContent = `  ↳ ${l2}`;
            excludeSel.appendChild(opt3);
        });
    });
}

function updateL2MultiSelect() {
    let l2Options = [];
    if (selectedL1s.length > 0) {
        selectedL1s.forEach(l1 => {
            const entry = taxonomyData.find(t => t.l1 === l1);
            if (entry) {
                entry.l2s.forEach(l2 => l2Options.push({ value: l2, label: l2 }));
            }
        });
    } else {
        taxonomyData.forEach(t => {
            t.l2s.forEach(l2 => l2Options.push({ value: l2, label: `${t.l1} · ${l2}` }));
        });
    }
    // Remove any previously selected L2s that are no longer in the options
    selectedL2s = selectedL2s.filter(v => l2Options.some(o => o.value === v));
    createMultiSelect('ms-category-l2', l2Options, selectedL2s);
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
    let level = 'l1';
    if (filters.category || pieDrillDownL1) level = 'l2';

    const data = await api.byCategory(filters, level);

    const labels = data.map(d => level === 'l1' ? (d.global_category_l1 || '未分类') : (d.global_category_l2 || '未分类'));
    const values = data.map(d => d.total);

    if (pieChart) pieChart.destroy();

    const canvas = document.getElementById('category-pie');
    const header = canvas.parentElement.querySelector('h2');

    const hasGlobalL1 = selectedL1s.length > 0;
    const hasGlobalL2 = selectedL2s.length > 0;

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
            onClick: (e, items) => {
                if (items.length > 0) {
                    const idx = items[0].index;
                    const period = labels[idx];
                    drillDownByPeriod(period, granularity);
                }
            },
            scales: {
                x: { ticks: { color: '#6b7394', font: { size: 11 } }, grid: { display: false } },
                y: {
                    ticks: { color: '#6b7394', callback: v => '¥' + (v >= 10000 ? (v / 10000).toFixed(1) + 'W' : v) },
                    grid: { color: '#2a2f4522' },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `${fmt(ctx.parsed.y)}  (点击筛选此时段)`,
                    },
                },
            },
        },
    });
}

function drillDownByPeriod(period, granularity) {
    let dateFrom, dateTo;
    if (granularity === 'year') {
        dateFrom = `${period}-01-01`;
        dateTo = `${period}-12-31`;
    } else if (granularity === 'month') {
        // period format: "2025-03"
        dateFrom = `${period}-01`;
        const [y, m] = period.split('-').map(Number);
        const lastDay = new Date(y, m, 0).getDate();
        dateTo = `${period}-${String(lastDay).padStart(2, '0')}`;
    } else if (granularity === 'week') {
        // period format: "2025-W12" — approximate: set date_from to Monday of that week
        // For simplicity, just fill the date fields and let the user refine
        const [y, w] = period.replace('W', '').split('-').map(Number);
        const jan1 = new Date(y, 0, 1);
        const mondayOffset = (jan1.getDay() + 6) % 7;
        const weekStart = new Date(y, 0, 1 + (w * 7) - mondayOffset);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        dateFrom = weekStart.toISOString().slice(0, 10);
        dateTo = weekEnd.toISOString().slice(0, 10);
    }

    if (dateFrom && dateTo) {
        document.getElementById('f-date-from').value = dateFrom;
        document.getElementById('f-date-to').value = dateTo;
        refreshAll();
    }
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
        div.className = 'ranking-item clickable';
        div.title = '点击筛选此分类';
        div.innerHTML = `
      <span class="rank-num ${i < 3 ? 'top3' : ''}">${i + 1}</span>
      <div class="rank-info">
        <div class="rank-name">${name || '未分类'}</div>
        <div class="rank-sub">${item.count} 笔 · 均 ${fmt(item.avg)}</div>
        <div class="rank-bar" style="width:${barWidth}%"></div>
      </div>
      <span class="rank-amount">${fmt(item.total)}</span>
    `;
        div.addEventListener('click', () => {
            if (level === 'l1') {
                pieDrillDownL1 = name;
                pieDrillDownL2 = null;
            } else {
                pieDrillDownL2 = name;
            }
            refreshAll();
        });
        container.appendChild(div);
    });
}

// ── Top Merchants Bar Chart ──────────────────────────────────
let merchantChart = null;

async function loadMerchants() {
    const data = await api.topMerchants(getFilters(), 15);
    const labels = data.map(d => d.merchant.length > 14 ? d.merchant.slice(0, 14) + '…' : d.merchant);
    const fullNames = data.map(d => d.merchant);
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
            onClick: (e, items) => {
                if (items.length > 0) {
                    const idx = items[0].index;
                    const merchantName = fullNames[idx];
                    document.getElementById('search-input').value = merchantName;
                    currentPage = 1;
                    loadTransactions();
                    document.getElementById('tx-table').scrollIntoView({ behavior: 'smooth' });
                }
            },
            scales: {
                x: {
                    ticks: { color: '#6b7394', callback: v => '¥' + (v >= 10000 ? (v / 10000).toFixed(1) + 'W' : v) },
                    grid: { color: '#2a2f4522' },
                },
                y: { ticks: { color: '#9ca3b8', font: { size: 11 } }, grid: { display: false } },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `${fmt(ctx.parsed.x)} (${data[ctx.dataIndex].count}笔)  点击查看明细`,
                    },
                },
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

    taxonomyData.forEach(t => {
        const opt = new Option(t.l1, t.l1);
        opt.selected = t.l1 === tx.category_l1;
        l1Sel.add(opt);
    });

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
    updateL2();

    return { l1Sel, l2Sel };
}

async function saveTransactionEdit(tx, l1, l2, tr) {
    try {
        const btn = tr.querySelector('.btn-save');
        if (btn) btn.disabled = true;
        await api.updateTransaction(tx.id, l1, l2);
        loadTransactions();
        loadCategoryPie();
        loadTopCategories();
    } catch (err) {
        alert("保存失败: " + err.message);
        loadTransactions();
    }
}

// ── Transaction Table ────────────────────────────────────────
let currentPage = 1;
const perPage = 50;

// Sort config
const SORT_COLUMNS = [
    { key: 'timestamp', label: '时间' },
    { key: 'platform', label: '平台' },
    { key: 'counterparty', label: '交易对方' },
    { key: 'description', label: '商品描述' },
    { key: 'amount', label: '金额' },
    { key: 'effective_amount', label: '实际支出' },
    { key: 'category_l1', label: 'L1 分类' },
    { key: 'category_l2', label: 'L2 分类' },
    { key: 'payment_method', label: '支付方式' },
    { key: 'track', label: '轨道' },
    { key: null, label: '操作' },
];

function renderTableHeader() {
    const thead = document.querySelector('#tx-table thead tr');
    thead.innerHTML = '';

    SORT_COLUMNS.forEach(col => {
        const th = document.createElement('th');
        if (col.key) {
            th.className = 'sortable';
            th.dataset.col = col.key;
            let arrow = '';
            if (currentSort.column === col.key) {
                arrow = currentSort.order === 'asc' ? ' ▲' : ' ▼';
                th.classList.add('sort-active');
            }
            th.textContent = col.label + arrow;
            th.addEventListener('click', () => {
                if (currentSort.column === col.key) {
                    currentSort.order = currentSort.order === 'asc' ? 'desc' : 'asc';
                } else {
                    currentSort.column = col.key;
                    currentSort.order = col.key === 'timestamp' || col.key === 'amount' || col.key === 'effective_amount' ? 'desc' : 'asc';
                }
                currentPage = 1;
                renderTableHeader();
                loadTransactions();
            });
        } else {
            th.textContent = col.label;
        }
        thead.appendChild(th);
    });
}

async function loadTransactions() {
    const filters = getFilters();
    const search = document.getElementById('search-input').value;

    const data = await api.transactions({
        ...filters,
        page: currentPage,
        per_page: perPage,
        search,
        sort_by: currentSort.column,
        sort_order: currentSort.order,
    });

    const tbody = document.getElementById('tx-body');
    tbody.innerHTML = '';

    if (!data.records.length) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#6b7394;padding:20px">暂无数据</td></tr>';
    }

    for (const tx of data.records) {
        const tr = document.createElement('tr');
        tr.dataset.id = tx.id;

        const platformMap = {
            alipay: '<span class="platform-badge platform-alipay">支付宝</span>',
            wechat: '<span class="platform-badge platform-wechat">微信</span>',
            jd: '<span class="platform-badge platform-jd">京东</span>',
            meituan: '<span class="platform-badge platform-meituan">美团</span>',
        };
        const platformBadge = platformMap[tx.platform] || `<span class="platform-badge">${tx.platform}</span>`;

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
                loadTransactions();
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
        pieDrillDownL1 = null;
        pieDrillDownL2 = null;
        refreshAll();
    });

    document.getElementById('btn-reset').addEventListener('click', () => {
        document.getElementById('f-user').value = '';
        document.getElementById('f-year').value = '';
        document.getElementById('f-track').value = 'consumption';
        document.getElementById('f-date-from').value = '';
        document.getElementById('f-date-to').value = '';
        document.getElementById('search-input').value = '';
        // Reset multi-selects
        selectedPlatforms.length = 0;
        selectedL1s.length = 0;
        selectedL2s.length = 0;
        excludedCategories = [];
        pieDrillDownL1 = null;
        pieDrillDownL2 = null;
        currentSort = { column: 'timestamp', order: 'desc' };
        renderExcludeTags();
        // Re-create multi-selects to reflect cleared state
        createMultiSelect('ms-platform', [
            { value: 'alipay', label: '支付宝' },
            { value: 'wechat', label: '微信' },
            { value: 'jd', label: '京东' },
            { value: 'meituan', label: '美团' },
        ], selectedPlatforms);
        const l1Options = taxonomyData.map(t => ({ value: t.l1, label: `${t.l1} (${t.count})` }));
        createMultiSelect('ms-category', l1Options, selectedL1s, updateL2MultiSelect);
        updateL2MultiSelect();
        renderTableHeader();
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
    renderTableHeader();
    await loadMeta();
    await refreshAll();
}

init().catch(err => {
    console.error('Dashboard init error:', err);
    document.getElementById('tx-body').innerHTML =
        `<tr><td colspan="11" style="color:#f87171;padding:20px">加载失败: ${err.message}</td></tr>`;
});
