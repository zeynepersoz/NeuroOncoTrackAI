/**
 * aiHistoryService.js — NeuroOncoTrack-AI Persistent AI & History Service
 *
 * Connects frontend clinical workspace to persistent FastAPI backend endpoints (/api/v1/ai/*)
 * backed by PostgreSQL. Enforces authentication token propagation, multi-tenant isolation,
 * and safe error handling without leaking stack traces or internal secrets.
 *
 * Endpoints:
 *   GET  /api/v1/ai/history            — Paginated tenant-scoped analysis history
 *   GET  /api/v1/ai/analyses/{id}      — Full analysis execution detail
 *   GET  /api/v1/ai/reports            — Paginated clinical reports list
 *   GET  /api/v1/ai/reports/{report_id}— Immutable clinical report detail
 *   POST /api/v1/ai/classify           — Persistent tumor classification
 *   POST /api/v1/ai/segment            — Persistent tumor segmentation
 *   POST /api/v1/ai/report             — Persistent structured clinical report
 */

import { apiClient } from './apiClient.js';
import { repairDeep, repairText } from '../utils/neuroUtils.js';

/**
 * Build URL query string from parameters, filtering out undefined/null/empty.
 * @param {Record<string, any>} params
 * @returns {string}
 */
function buildQueryString(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, String(value));
    }
  }
  const str = query.toString();
  return str ? `?${str}` : '';
}

/**
 * Format a human-readable safe error message from ApiError or network failure.
 * @param {any} error
 * @returns {string}
 */
export function formatSafeErrorMessage(error) {
  if (!error) return 'Beklenmeyen bir hata oluştu.';
  if (error.status === 401) return 'Oturum süreniz doldu veya yetkiniz yok. Lütfen tekrar giriş yapın.';
  if (error.status === 403) return 'Bu işlem için yetkiniz bulunmamaktadır (Yetki hatası).';
  if (error.status === 404) return 'İstenen analiz veya rapor kaydı bulunamadı.';
  if (error.status === 429) return 'AI işlem istek limiti aşıldı. Lütfen bir süre sonra tekrar deneyin.';
  if (error.status >= 500) return 'Sunucu tarafında geçici bir sorun oluştu. Sistem yöneticisine bildirin.';

  const rawMsg = String(error.message || error.detail || '');
  if (
    /traceback|exception|file\s+".*?",\s+line|\/home\/|\/var\/|\/tmp\/|[a-zA-Z]:\\|secret|token|password|groq|bearer|http:\/\/localhost|http:\/\/127\.0\.0\.1/i.test(
      rawMsg,
    )
  ) {
    return 'Sunucu işlemi sırasında bir hata meydana geldi.';
  }
  return repairText(rawMsg) || 'İşlem gerçekleştirilemedi.';
}

/**
 * Retrieve paginated AI analysis history for current tenant.
 *
 * @param {object} options
 * @param {string} [options.patientId]      - Optional patient ID filter
 * @param {string} [options.operation]      - 'classification' | 'segmentation' | 'report_generation'
 * @param {string} [options.statusFilter]   - 'COMPLETED' | 'FAILED' | 'PROCESSING'
 * @param {number} [options.limit=50]
 * @param {number} [options.offset=0]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{ items: Array<object>, total: number }>}
 */
export async function getAIHistory({
  patientId,
  operation,
  statusFilter,
  limit = 50,
  offset = 0,
  signal,
} = {}) {
  const qs = buildQueryString({
    patient_id: patientId,
    operation,
    status_filter: statusFilter,
    limit,
    offset,
  });

  const response = await apiClient.get(`/ai/history${qs}`, { signal });
  return repairDeep(response || { items: [], total: 0 });
}

/**
 * Retrieve full execution detail of a specific AI analysis.
 *
 * @param {string} analysisId - UUID of the AI analysis record
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object>}
 */
export async function getAIAnalysisDetail(analysisId, { signal } = {}) {
  if (!analysisId) throw new Error('analysisId parametresi zorunludur.');
  const response = await apiClient.get(`/ai/analyses/${analysisId}`, { signal });
  return repairDeep(response);
}

/**
 * Retrieve paginated clinical reports list for current tenant.
 *
 * @param {object} options
 * @param {string} [options.patientId]
 * @param {number} [options.limit=50]
 * @param {number} [options.offset=0]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{ items: Array<object>, total: number }>}
 */
export async function getClinicalReports({
  patientId,
  limit = 50,
  offset = 0,
  signal,
} = {}) {
  const qs = buildQueryString({
    patient_id: patientId,
    limit,
    offset,
  });

  const response = await apiClient.get(`/ai/reports${qs}`, { signal });
  return repairDeep(response || { items: [], total: 0 });
}

/**
 * Retrieve full immutable clinical report by report_id.
 *
 * @param {string} reportId - Unique report identifier string
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object>}
 */
export async function getClinicalReportDetail(reportId, { signal } = {}) {
  if (!reportId) throw new Error('reportId parametresi zorunludur.');
  const response = await apiClient.get(`/ai/reports/${reportId}`, { signal });
  return repairDeep(response);
}

/**
 * Execute persistent tumor classification via FastAPI backend.
 *
 * @param {object} params
 * @param {string} params.patientId
 * @param {Record<string, string>} params.modalityPaths
 * @param {'fast'|'full'|'classify_only'} [params.mode='fast']
 * @param {'auto'|'cuda'|'mps'|'cpu'} [params.device='auto']
 * @param {'v3'|'v2'} [params.predictor='v3']
 * @param {Record<string, number>} [params.extraFeatures]
 * @param {AbortSignal} [params.signal]
 * @returns {Promise<object>}
 */
export async function runPersistentClassification({
  patientId,
  modalityPaths,
  mode = 'fast',
  device = 'auto',
  predictor = 'v3',
  extraFeatures,
  signal,
} = {}) {
  if (!patientId) throw new Error('patientId zorunludur.');
  if (!modalityPaths?.t1c) throw new Error('En az t1c modalitesi zorunludur.');

  const payload = {
    patient_id: patientId,
    modality_paths: modalityPaths,
    mode,
    device,
    predictor,
  };
  if (extraFeatures && Object.keys(extraFeatures).length > 0) {
    payload.extra_features = extraFeatures;
  }

  const response = await apiClient.post('/ai/classify', payload, { signal });
  return repairDeep(response);
}

/**
 * Execute persistent tumor segmentation via FastAPI backend.
 *
 * @param {object} params
 * @param {string} params.patientId
 * @param {Record<string, string>} params.modalityPaths
 * @param {'fast'|'full'} [params.mode='fast']
 * @param {'auto'|'cuda'|'mps'|'cpu'} [params.device='auto']
 * @param {'v3'|'v2'} [params.predictor='v3']
 * @param {Record<string, number>} [params.extraFeatures]
 * @param {AbortSignal} [params.signal]
 * @returns {Promise<object>}
 */
export async function runPersistentSegmentation({
  patientId,
  modalityPaths,
  mode = 'fast',
  device = 'auto',
  predictor = 'v3',
  extraFeatures,
  signal,
} = {}) {
  if (!patientId) throw new Error('patientId zorunludur.');
  if (!modalityPaths?.t1c) throw new Error('En az t1c modalitesi zorunludur.');

  const payload = {
    patient_id: patientId,
    modality_paths: modalityPaths,
    mode,
    device,
    predictor,
  };
  if (extraFeatures && Object.keys(extraFeatures).length > 0) {
    payload.extra_features = extraFeatures;
  }

  const response = await apiClient.post('/ai/segment', payload, { signal });
  return repairDeep(response);
}

/**
 * Generate and persist a structured AI clinical report via FastAPI backend.
 *
 * @param {object} params
 * @param {string} params.patientId
 * @param {object} [params.classification]
 * @param {object} [params.segmentation]
 * @param {object} [params.extraClinicalContext]
 * @param {AbortSignal} [params.signal]
 * @returns {Promise<object>}
 */
export async function runPersistentReport({
  patientId,
  classification,
  segmentation,
  extraClinicalContext,
  signal,
} = {}) {
  if (!patientId) throw new Error('patientId zorunludur.');
  if (!classification && !segmentation) {
    throw new Error('Rapor üretimi için en az bir analiz sonucu (sınıflandırma veya segmentasyon) gereklidir.');
  }

  const payload = {
    patient_id: patientId,
  };
  if (classification) payload.classification = classification;
  if (segmentation) payload.segmentation = segmentation;
  if (extraClinicalContext) payload.extra_clinical_context = extraClinicalContext;

  const response = await apiClient.post('/ai/report', payload, { signal });
  return repairDeep(response);
}
