import { API_MODE } from '../config/neuroConstants.js';
import { repairDeep, repairText } from '../utils/neuroUtils.js';
import { apiClient, isEndpointUnavailable } from './apiClient.js';

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

async function generateContractReport(input) {
  return apiClient.post('/reports/generate', buildReportPayload(input));
}

export async function requestReportDraft(input) {
  try {
    if (API_MODE === 'contract') {
      return repairDeep(await generateContractReport(input));
    }
  } catch (error) {
    if (!isEndpointUnavailable(error)) throw error;
  }

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
