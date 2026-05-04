const API_BASE = '/api';

async function parseResponse(res) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `API error: ${res.status}`);
    return data;
}

function uploadPath(relativePath) {
    return String(relativePath).split('/').map(encodeURIComponent).join('/');
}

export async function fetchJSON(endpoint, params = {}) {
    let url = `${API_BASE}${endpoint}`;
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') searchParams.set(k, v);
    });
    const qs = searchParams.toString();
    if (qs) url += '?' + qs;
    const res = await fetch(url, { cache: 'no-store' });
    return parseResponse(res);
}

export async function putJSON(endpoint, body) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    });
    return parseResponse(res);
}

export async function postJSON(endpoint, body = {}, method = 'POST') {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    });
    return parseResponse(res);
}

export async function deleteJSON(endpoint) {
    const res = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE' });
    return parseResponse(res);
}

export async function uploadFiles(platform, user, files) {
    const form = new FormData();
    form.set('platform', platform);
    form.set('user', user);
    Array.from(files).forEach(file => form.append('files', file));
    const res = await fetch(`${API_BASE}/uploads`, {
        method: 'POST',
        body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `API error: ${res.status}`);
    return data;
}

export const api = {
    config: () => fetchJSON('/config'),
    saveConfig: (config) => postJSON('/config', config),
    modelProfiles: () => fetchJSON('/model-profiles'),
    saveModelProfile: (profile) => postJSON('/model-profiles', profile),
    activateModelProfile: (id) => postJSON('/model-profiles/active', { id }),
    processedVersions: () => fetchJSON('/processed-versions'),
    activateProcessedVersion: (id) => postJSON('/processed-versions/active', { id }),
    deleteProcessedVersion: (id) => deleteJSON(`/processed-versions/${encodeURIComponent(id)}`),
    uploads: () => fetchJSON('/uploads'),
    uploadFiles,
    updateUpload: (relativePath, payload) => postJSON(`/uploads/${uploadPath(relativePath)}`, payload, 'PATCH'),
    deleteUpload: (relativePath) => deleteJSON(`/uploads/${uploadPath(relativePath)}`),
    process: () => postJSON('/process'),
    taggingStatus: () => fetchJSON('/tagging/status'),
    runTagging: () => postJSON('/tagging/run'),
    applyTagging: () => postJSON('/tagging/apply'),
    meta: () => fetchJSON('/meta'),
    summary: (f) => fetchJSON('/summary', f),
    byCategory: (f, level = 'l1') => fetchJSON('/by-category', { ...f, level }),
    byPeriod: (f, granularity = 'month') => fetchJSON('/by-period', { ...f, granularity }),
    topMerchants: (f, limit = 15) => fetchJSON('/top-merchants', { ...f, limit }),
    topCategories: (f, level = 'l1', limit = 20) => fetchJSON('/top-categories', { ...f, level, limit }),
    cashflowSummary: (f) => fetchJSON('/cashflow-summary', f),
    transactions: (params) => fetchJSON('/transactions', params),
    updateTransaction: (txId, l1, l2, processedVersionId = '') => putJSON(
        `/transactions/${encodeURIComponent(txId)}`,
        { category_l1: l1, category_l2: l2, processed_version_id: processedVersionId }
    )
};
