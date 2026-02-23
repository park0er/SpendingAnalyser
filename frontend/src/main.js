import { api } from './api.js';

// ── Color palette ────────────────────────────────────────────
const COLORS = [
    '#5b8def', '#4ade80', '#fbbf24', '#f87171', '#a78bfa',
    '#fb923c', '#22d3ee', '#f472b6', '#818cf8', '#34d399',
    '#e879f9', '#facc15', '#38bdf8', '#c084fc', '#a3e635',
    '#fb7185', '#6ee7b7', '#fcd34d', '#93c5fd',
];

function fmt(n) {
    return '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Summary Cards ────────────────────────────────────────────
async function loadSummary() {
    const data = await api.summary();
    document.getElementById('total-spend').textContent = fmt(data.total_spend);
    document.getElementById('total-refund').textContent = fmt(data.total_refund);
    document.getElementById('total-cashflow').textContent = fmt(data.cashflow_total);
    document.getElementById('total-records').textContent = data.total_records.toLocaleString();
}

// ── Category Pie Chart ───────────────────────────────────────
let pieChart = null;

async function loadCategoryPie() {
    const data = await api.byCategory('l1');
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
                        font: { family: 'Inter', size: 12 },
                        padding: 12,
                        usePointStyle: true,
                        pointStyleWidth: 10,
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

    // Populate category filter
    const select = document.getElementById('filter-category');
    labels.forEach(l => {
        if (l && l !== '未分类') {
            const opt = document.createElement('option');
            opt.value = l;
            opt.textContent = l;
            select.appendChild(opt);
        }
    });
}

// ── Trend Line Chart ─────────────────────────────────────────
let trendChart = null;

async function loadTrend(granularity = 'month') {
    const data = await api.byPeriod(granularity);
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
                        callback: v => '¥' + (v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v),
                    },
                    grid: { color: '#2a2f4522' },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => fmt(ctx.parsed.y),
                    },
                },
            },
        },
    });
}

// ── Top Merchants Bar Chart ──────────────────────────────────
let merchantChart = null;

async function loadMerchants() {
    const data = await api.topMerchants(15);
    const labels = data.map(d => d.merchant.length > 12 ? d.merchant.slice(0, 12) + '…' : d.merchant);
    const values = data.map(d => d.total);

    if (merchantChart) merchantChart.destroy();

    merchantChart = new Chart(document.getElementById('merchant-bar'), {
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
                        callback: v => '¥' + (v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v),
                    },
                    grid: { color: '#2a2f4522' },
                },
                y: {
                    ticks: { color: '#9ca3b8', font: { size: 12 } },
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

    // Set canvas height for horizontal bar
    document.getElementById('merchant-bar').parentElement.style.height = '500px';
}

// ── Cashflow Panel ───────────────────────────────────────────
async function loadCashflow() {
    const data = await api.cashflowSummary();
    const container = document.getElementById('cashflow-content');

    let html = `<div class="cashflow-grid">`;
    for (const item of data.categories.slice(0, 8)) {
        html += `
      <div class="cashflow-item">
        <div class="cf-label">${item.category}</div>
        <div class="cf-value">${fmt(item.total)}</div>
        <div class="cf-count">${item.count} 笔</div>
      </div>`;
    }
    html += `</div>`;
    container.innerHTML = html;
}

// ── Transaction Table ────────────────────────────────────────
let currentPage = 1;
const perPage = 50;

async function loadTransactions() {
    const search = document.getElementById('search-input').value;
    const platform = document.getElementById('filter-platform').value;
    const category = document.getElementById('filter-category').value;
    const track = document.getElementById('filter-track').value;

    const data = await api.transactions({
        page: currentPage,
        per_page: perPage,
        search,
        platform,
        category,
        track,
    });

    const tbody = document.getElementById('tx-body');
    tbody.innerHTML = '';

    for (const tx of data.records) {
        const tr = document.createElement('tr');
        const platformBadge = tx.platform === 'alipay'
            ? '<span class="platform-badge platform-alipay">支付宝</span>'
            : '<span class="platform-badge platform-wechat">微信</span>';

        const amountClass = tx.is_refunded ? 'amount refunded' : 'amount';
        const categoryDisplay = tx.category_l1
            ? `<span class="category-tag">${tx.category_l1}</span>`
            : '';

        tr.innerHTML = `
      <td>${tx.timestamp.slice(0, 16)}</td>
      <td>${platformBadge}</td>
      <td title="${tx.counterparty}">${tx.counterparty}</td>
      <td title="${tx.description}">${tx.description}</td>
      <td class="${amountClass}">¥${tx.amount.toFixed(2)}</td>
      <td class="amount">¥${tx.effective_amount.toFixed(2)}</td>
      <td>${categoryDisplay}</td>
      <td>${tx.payment_method || ''}</td>
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
        info.textContent = `第 ${currentPage} / ${totalPages} 页（共 ${data.total} 条）`;
        pagination.appendChild(info);

        if (currentPage < totalPages) {
            const next = document.createElement('button');
            next.textContent = '下一页 →';
            next.addEventListener('click', () => { currentPage++; loadTransactions(); });
            pagination.appendChild(next);
        }
    }
}

// ── Event Listeners ──────────────────────────────────────────
function setupListeners() {
    // Period toggle
    document.querySelectorAll('.btn-period').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.btn-period').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadTrend(btn.dataset.period);
        });
    });

    // Table filters
    let debounceTimer;
    document.getElementById('search-input').addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => { currentPage = 1; loadTransactions(); }, 300);
    });

    ['filter-platform', 'filter-category', 'filter-track'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            currentPage = 1;
            loadTransactions();
        });
    });
}

// ── Init ─────────────────────────────────────────────────────
async function init() {
    setupListeners();
    await Promise.all([
        loadSummary(),
        loadCategoryPie(),
        loadTrend('month'),
        loadMerchants(),
        loadCashflow(),
        loadTransactions(),
    ]);
}

init().catch(err => console.error('Dashboard init error:', err));
