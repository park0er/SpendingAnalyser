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

export const api = {
    summary: () => fetchJSON('/summary'),
    byCategory: (level = 'l1') => fetchJSON('/by-category', { level }),
    byPeriod: (granularity = 'month') => fetchJSON('/by-period', { granularity }),
    topMerchants: (limit = 15) => fetchJSON('/top-merchants', { limit }),
    cashflowSummary: () => fetchJSON('/cashflow-summary'),
    transactions: (params = {}) => fetchJSON('/transactions', params),
};
