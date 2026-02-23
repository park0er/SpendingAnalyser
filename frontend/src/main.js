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
    if (category) f.category = category;
    if (categoryL2) f.category_l2 = categoryL2;
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
    });

    // L2 depends on L1 selection
    document.getElementById('f-category').addEventListener('change', updateL2Options);
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
    const data = await api.byCategory(getFilters(), 'l1');
    const labels = data.map(d => d.global_category_l1 || '未分类');
    const values = data.map(d => d.total);

    if (pieChart) pieChart.destroy();

    pieChart = new Chart(document.getElementById('category-pie'), {
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
                x: {
                    ticks: { color: '#6b7394', font: { size: 11 } },
                    grid: { display: false },
                },
                y: {
                    ticks: {
                        color: '#6b7394',
                        callback: v => '¥' + (v >= 10000 ? (v / 10000).toFixed(1) + 'W' : v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v),
                    },
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
    const data = await api.topCategories(getFilters(), 'l1', 20);
    const container = document.getElementById('top-categories-list');
    container.innerHTML = '';

    if (!data.length) {
        container.innerHTML = '<div style="color:#6b7394;padding:20px">暂无数据</div>';
        return;
    }

    const maxTotal = data[0]?.total || 1;

    data.forEach((item, i) => {
        const barWidth = Math.max(5, (item.total / maxTotal) * 100);
        const div = document.createElement('div');
        div.className = 'ranking-item';
        div.innerHTML = `
      <span class="rank-num ${i < 3 ? 'top3' : ''}">${i + 1}</span>
      <div class="rank-info">
        <div class="rank-name">${item.category || '未分类'}</div>
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
                    ticks: {
                        color: '#6b7394',
                        callback: v => '¥' + (v >= 10000 ? (v / 10000).toFixed(1) + 'W' : v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v),
                    },
                    grid: { color: '#2a2f4522' },
                },
                y: {
                    ticks: { color: '#9ca3b8', font: { size: 11 } },
                    grid: { display: false },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `${fmt(ctx.parsed.x)} (${data[ctx.dataIndex].count}笔)`,
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
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#6b7394;padding:20px">暂无数据</td></tr>';
    }

    for (const tx of data.records) {
        const tr = document.createElement('tr');
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
      <td>${l1}</td>
      <td>${l2}</td>
      <td>${tx.payment_method || ''}</td>
      <td>${trackTag}</td>
    `;
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
    // Apply filters button
    document.getElementById('btn-apply').addEventListener('click', refreshAll);

    // Reset filters button
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
        renderExcludeTags();
        updateL2Options();
        refreshAll();
    });

    // Search button
    document.getElementById('btn-search').addEventListener('click', () => {
        currentPage = 1;
        loadTransactions();
    });

    // Enter key in search box
    document.getElementById('search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            currentPage = 1;
            loadTransactions();
        }
    });

    // Period toggle
    document.querySelectorAll('.btn-period').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.btn-period').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadTrend(btn.dataset.period);
        });
    });

    // Exclude category add
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
        `<tr><td colspan="10" style="color:#f87171;padding:20px">加载失败: ${err.message}</td></tr>`;
});
