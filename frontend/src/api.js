const API_BASE = '/api';

export async function fetchJSON(endpoint, params = {}) {
    let url = `${API_BASE}${endpoint}`;
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') searchParams.set(k, v);
    });
    const qs = searchParams.toString();
    if (qs) url += '?' + qs;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

export async function putJSON(endpoint, body) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

export const api = {
    meta: () => fetchJSON('/meta'),
    summary: (f) => fetchJSON('/summary', f),
    byCategory: (f, level = 'l1') => fetchJSON('/by-category', { ...f, level }),
    byPeriod: (f, granularity = 'month') => fetchJSON('/by-period', { ...f, granularity }),
    topMerchants: (f, limit = 15) => fetchJSON('/top-merchants', { ...f, limit }),
    topCategories: (f, level = 'l1', limit = 20) => fetchJSON('/top-categories', { ...f, level, limit }),
    cashflowSummary: (f) => fetchJSON('/cashflow-summary', f),
    transactions: (params) => fetchJSON('/transactions', params),
    updateTransaction: (txId, l1, l2) => putJSON(`/transactions/${encodeURIComponent(txId)}`, { category_l1: l1, category_l2: l2 })
};
