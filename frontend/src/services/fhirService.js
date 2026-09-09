/**
 * fhirService.js — NeuroOncoTrack-AI FHIR R4 Entegrasyonu
 *
 * Backend endpoint'leri (contract modda):
 *   GET  /api/v1/fhir/{resourceType}/{id} — FHIR kaynağı getir
 *   POST /api/v1/fhir/sync/{reportId}     — Raporu FHIR'a senkronize et
 *
 * Desteklenen kaynak tipleri (HL7 FHIR R4):
 *   Patient, ImagingStudy, Observation, DiagnosticReport, CarePlan
 */

import { API_MODE } from '../config/neuroConstants.js';
import { repairDeep } from '../utils/neuroUtils.js';
import { apiClient, isEndpointUnavailable } from './apiClient.js';

// FHIR kaynak tipi → backend path eşlemesi
const FHIR_RESOURCE_PATHS = {
  patient: 'Patient',
  imaging_study: 'ImagingStudy',
  observations: 'Observation',
  diagnostic_report: 'DiagnosticReport',
  care_plan: 'CarePlan',
};

/**
 * FHIR kaynağını backend'den getir — GET /api/v1/fhir/{resourceType}/{id}
 *
 * @param {string} resourceType — 'patient' | 'imaging_study' | 'observations' | 'diagnostic_report' | 'care_plan'
 * @param {string} id           — Kaynak kimliği
 * @returns {Promise<object|null>}
 */
export async function getFhirResource(resourceType, id) {
  if (!id || API_MODE !== 'contract') return null;

  const pathSegment = FHIR_RESOURCE_PATHS[resourceType] || resourceType;

  try {
    return repairDeep(await apiClient.get(`/fhir/${pathSegment}/${id}`));
  } catch (error) {
    if (isEndpointUnavailable(error)) return null;
    throw error;
  }
}

/**
 * Raporu HL7 FHIR R4 formatında senkronize et — POST /api/v1/fhir/sync/{reportId}
 *
 * DiagnosticReport kaynağı oluşturur/günceller; hekim onayı varsa
 * status 'preliminary' → 'final' olarak işaretlenir.
 *
 * @param {string} reportId — Rapor kimliği
 * @returns {Promise<{status: string, message: string, fhir?: object}|null>}
 */
export async function syncReportToFhir(reportId) {
  if (!reportId || API_MODE !== 'contract') {
    return {
      status: 'local-ready',
      message:
        'FHIR senkronizasyonu için rapor kimliği ve /api/v1/fhir servisi bekleniyor.',
    };
  }

  return repairDeep(await apiClient.post(`/fhir/sync/${reportId}`));
}

/**
 * Analiz sonucundan yerel FHIR kaynakları oluştur (backend gerekmez).
 * AI pipeline'ından gelen fhir nesnesini normalize eder.
 *
 * @param {object} analysisResult — runAnalysisJob dönüş değeri
 * @param {object} [patientInfo]  — { name, age, gender }
 * @returns {object} — { patient, imaging_study, observations, diagnostic_report, care_plan }
 */
export function buildLocalFhirBundle(analysisResult, patientInfo = {}) {
  const fhir = analysisResult?.fhir || {};
  const pipeline = analysisResult?._pipeline;

  // AI servisi FHIR çıktısı doğrudan kullanılabilir
  if (pipeline?.stages?.report?.payload?.fhir) {
    return repairDeep(pipeline.stages.report.payload.fhir);
  }

  // Legacy/compat: mevcut fhir alanı
  return repairDeep(fhir);
}
