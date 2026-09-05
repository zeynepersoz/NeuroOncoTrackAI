import { API_BASE, API_V1_BASE } from '../config/neuroConstants.js';
import { repairDeep, repairText } from '../utils/neuroUtils.js';

let accessToken = null;
let refreshPromise = null;

export class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status || 0;
    this.code = options.code || '';
    this.detail = options.detail || '';
    this.requestId = options.requestId || '';
    this.payload = options.payload || null;
  }
}

export function setAccessToken(token) {
  accessToken = token || null;
}

export function getAccessToken() {
  return accessToken;
}

export function clearAccessToken() {
  accessToken = null;
}

export function isEndpointUnavailable() {
  return false;
}

export function isNetworkUnavailable(error) {
  return error instanceof TypeError || (error instanceof ApiError && error.status === 0);
}

function resolveUrl(path, base = 'v1') {
  if (/^https?:\/\//i.test(path)) return path;
  if (base === 'root' || base === 'legacy') return `${API_BASE}${path}`;
  return `${API_V1_BASE}${path}`;
}

async function parseResponse(response, responseType) {
  if (responseType === 'blob') return response.blob();
  if (response.status === 204) return null;

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return repairDeep(await response.json());
  }

  const text = await response.text();
  return responseType === 'text' ? repairText(text) : text;
}

function buildApiError(response, payload, fallbackMessage) {
  const errorEnvelope = payload?.error || {};
  const message = repairText(errorEnvelope.message || payload?.detail || payload?.message || fallbackMessage);

  return new ApiError(message, {
    status: response.status,
    code: errorEnvelope.code || payload?.code || '',
    detail: repairText(errorEnvelope.detail || payload?.detail || ''),
    requestId: errorEnvelope.request_id || response.headers.get('x-request-id') || '',
    payload,
  });
}

async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;

  refreshPromise = fetch(resolveUrl('/auth/refresh', 'v1'), {
    method: 'POST',
    credentials: 'include',
  })
    .then(async (response) => {
      const payload = await parseResponse(response, 'json');
      if (!response.ok) throw buildApiError(response, payload, 'Oturum yenilenemedi.');
      const nextToken = payload?.access_token || payload?.accessToken || payload?.token;
      setAccessToken(nextToken);
      return nextToken;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

export async function apiRequest(path, options = {}) {
  const {
    auth = true,
    base = 'v1',
    body,
    headers = {},
    method = body ? 'POST' : 'GET',
    retryOnUnauthorized = true,
    responseType = 'json',
    signal,
  } = options;

  const requestHeaders = new Headers(headers);
  const isFormData = body instanceof FormData;
  const isBlob = typeof Blob !== 'undefined' && body instanceof Blob;

  if (body && !isFormData && !isBlob && typeof body !== 'string' && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json');
  }

  if (auth && accessToken) {
    requestHeaders.set('Authorization', `Bearer ${accessToken}`);
  }

  const requestBody = body && !isFormData && !isBlob && typeof body !== 'string' ? JSON.stringify(body) : body;

  let response;
  try {
    response = await fetch(resolveUrl(path, base), {
      method,
      headers: requestHeaders,
      body: requestBody,
      credentials: auth ? 'include' : 'same-origin',
      signal,
    });
  } catch (error) {
    throw new ApiError('Backend servisine ulaşılamadı.', {
      status: 0,
      code: 'NETWORK_UNAVAILABLE',
      detail: error.message,
    });
  }

  const payload = await parseResponse(response, responseType);

  if (response.ok) return payload;

  const apiError = buildApiError(response, payload, 'İstek başarısız oldu.');
  if (auth && retryOnUnauthorized && (apiError.status === 401 || apiError.code === 'AUTH_002')) {
    try {
      await refreshAccessToken();
      return apiRequest(path, { ...options, retryOnUnauthorized: false });
    } catch {
      clearAccessToken();
    }
  }

  throw apiError;
}

export const apiClient = {
  get: (path, options) => apiRequest(path, { ...options, method: 'GET' }),
  post: (path, body, options) => apiRequest(path, { ...options, body, method: 'POST' }),
  patch: (path, body, options) => apiRequest(path, { ...options, body, method: 'PATCH' }),
  delete: (path, options) => apiRequest(path, { ...options, method: 'DELETE' }),
};
