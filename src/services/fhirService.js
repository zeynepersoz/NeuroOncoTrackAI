import { API_MODE } from '../config/neuroConstants.js';
import { repairDeep } from '../utils/neuroUtils.js';
import { apiClient, isEndpointUnavailable } from './apiClient.js';

export async function getFhirResource(resourceType, id) {
  if (!id || API_MODE !== 'contract') return null;

  try {
    return repairDeep(await apiClient.get(`/fhir/${resourceType}/${id}`));
  } catch (error) {
    if (isEndpointUnavailable(error)) return null;
    throw error;
  }
}

export async function syncReportToFhir(reportId) {
  if (!reportId || API_MODE !== 'contract') {
    return {
      status: 'local-ready',
      message: 'FHIR senkronizasyonu için rapor kimliği ve /api/v1/fhir servisi bekleniyor.',
    };
  }

  return repairDeep(await apiClient.post(`/fhir/sync/${reportId}`));
}
