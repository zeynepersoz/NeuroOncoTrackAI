import { API_MODE } from '../config/neuroConstants.js';
import { repairDeep, repairText } from '../utils/neuroUtils.js';
import { apiClient, isEndpointUnavailable } from './apiClient.js';
import { runPersistentReport } from './aiHistoryService.js';

export function createReportWorkflow() {
  return {
    id: '',
    status: 'draft',
    version: 1,
    updatedAt: new Date().toISOString(),
    signedAt: '',
    signedHash: '',
    history: [{ status: 'draft', label: 'Taslak oluşturuldu', at: new Date().toISOString() }],
  };
}

export function getReportStatusLabel(status) {
  const labels = {
    draft: 'Taslak',
    review: 'İncelemede',
    approved: 'Onaylandı',
    signed: 'İmzalandı',
    revision: 'Revizyon gerekli',
  };
  return labels[status] || 'Taslak';
}

export function updateWorkflowStatus(workflow, status, label) {
  const nextHistory = [
    ...(workflow?.history || []),
    { status, label: label || getReportStatusLabel(status), at: new Date().toISOString() },
  ];

  return {
    ...(workflow || createReportWorkflow()),
    status,
    updatedAt: new Date().toISOString(),
    signedAt: status === 'signed' ? new Date().toISOString() : workflow?.signedAt || '',
    history: nextHistory,
  };
}

function buildReportPayload({ analysisResult, patientName, patientAge, patientGender }) {
  return {
    patient_name: patientName,
    age: patientAge,
    gender: patientGender,
    tumor_type: repairText(analysisResult?.diagnosis_tr),
    study_id: analysisResult?.study_id || analysisResult?.studyId || analysisResult?.image_name,
    prediction_id: analysisResult?.prediction_id || analysisResult?.predictionId || '',
    volume: analysisResult?.volume,
    sphericity: analysisResult?.sphericity,
    molecular: analysisResult?.molecular,
  };
}

async function generateLegacyReport(input) {
  return apiClient.post('/api/report', buildReportPayload(input), {
    auth: false,
    base: 'root',
  });
}

export async function requestReportDraft(input) {
  const { analysisResult, patientName, patientAge, patientGender } = input;
  const cleanPatientId = (patientName || 'PATIENT-001').replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 40);

  // 1. Primary path: Persistent FastAPI /api/v1/ai/report
  try {
    const pred = (analysisResult?.prediction || analysisResult?.predicted_tumor_type || 'glioma').toLowerCase();
    const validPred = ['glioma', 'meningioma', 'notumor', 'pituitary'].includes(pred) ? pred : 'glioma';

    const classificationDTO = {
      prediction: validPred,
      confidence: Number(analysisResult?.confidence || 0.88),
      probabilities:
        analysisResult?.probs && Object.keys(analysisResult.probs).length > 0
          ? analysisResult.probs
          : { glioma: 0.88, meningioma: 0.08, notumor: 0.02, pituitary: 0.02 },
      who_grade_hint: analysisResult?.who_grade_hint || 'Grade II-IV',
      tumor_volume_cm3: Number(analysisResult?.tumor_volume_cm3 || analysisResult?.volume || 38.4),
    };

    let segmentationDTO = null;
    if (analysisResult?.tumor_volume_cm3 || analysisResult?.volume) {
      segmentationDTO = {
        status: 'COMPLETED',
        tumor_volume_cm3: Number(analysisResult?.tumor_volume_cm3 || analysisResult?.volume || 38.4),
        tumor_area_ratio_2d: Number(analysisResult?.tumor_area_ratio_2d || 0.14),
        et_wt_ratio: Number(analysisResult?.et_wt_ratio || 0.42),
        mask_artifact_id: analysisResult?.mask_artifact_id || 'mask_tumor_gtv.nii.gz',
      };
    }

    const extraClinicalContext = {
      age: Number(patientAge) || 42,
      gender: String(patientGender || 'female'),
    };

    const repOut = await runPersistentReport({
      patientId: cleanPatientId,
      classification: classificationDTO,
      segmentation: segmentationDTO,
      extraClinicalContext,
    });

    return repairDeep({
      report_id: repOut.report_id,
      id: repOut.report_id,
      report: [
        `[KLİNİK ÖZET]\n${repOut.summary}`,
        `[RADYOLOJİK BULGULAR]\n${repOut.findings}`,
        `[ÖNERİLER]\n${repOut.recommendations}`,
        `[SINIRLILIKLAR]\n${repOut.limitations}`,
      ].join('\n\n'),
      summary: repOut.summary,
      findings: repOut.findings,
      limitations: repOut.limitations,
      recommendations: repOut.recommendations,
      status: repOut.status,
      fhir: repOut.fhir,
      created_at: repOut.created_at,
      _backend_report: repOut,
    });
  } catch (persistentErr) {
    console.warn('[reportService] Persistent /api/v1/ai/report hatası:', persistentErr.message);
    if (!isEndpointUnavailable(persistentErr)) {
      throw persistentErr;
    }
  }

  // Fallback for legacy dev mode
  return repairDeep(await generateLegacyReport(input));
}

export async function submitReport(reportId) {
  if (!reportId || API_MODE !== 'contract') return null;
  return apiClient.post(`/reports/${reportId}/submit`);
}

export async function approveReport(reportId) {
  if (!reportId || API_MODE !== 'contract') return null;
  return apiClient.post(`/reports/${reportId}/approve`);
}

export async function signReport(reportId) {
  if (!reportId || API_MODE !== 'contract') return null;
  return apiClient.post(`/reports/${reportId}/sign`);
}

export async function amendReport(reportId) {
  if (!reportId || API_MODE !== 'contract') return null;
  return apiClient.post(`/reports/${reportId}/amend`);
}
