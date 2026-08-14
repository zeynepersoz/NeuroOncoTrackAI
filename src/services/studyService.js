import { API_BASE, API_MODE, MIN_ANALYSIS_LOADER_MS } from '../config/neuroConstants.js';
import { readApiError, repairDeep } from '../utils/neuroUtils.js';
import { apiClient, isEndpointUnavailable } from './apiClient.js';
import { watchTask } from './taskStream.js';

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function ensureMinimumDuration(startedAt) {
  const elapsed = Date.now() - startedAt;
  if (elapsed < MIN_ANALYSIS_LOADER_MS) {
    await sleep(MIN_ANALYSIS_LOADER_MS - elapsed);
  }
}

export async function listCaseLibrary() {
  const data = await apiClient.get('/api/library', { auth: false, base: 'root' });
  return repairDeep(data);
}

async function runLegacyAnalysis({ libraryId, file, signal, onTaskUpdate }) {
  const formData = new FormData();
  if (file) {
    formData.append('file', file);
  } else if (libraryId) {
    formData.append('library_id', libraryId);
  }

  onTaskUpdate?.({ status: 'preprocessing', progress: 18, stage: 'Ön işleme' });

  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!response.ok) {
    const apiMessage = await readApiError(response, 'Analiz isteği başarısız oldu.');
    if (response.status === 404 && apiMessage.toLowerCase().includes('library image')) {
      throw new Error(
        'Demo vaka görseli bulunamadı. test_images klasörü eksik olabilir; MRG yükleyin veya demo görsellerini ekleyin.',
      );
    }
    throw new Error(apiMessage);
  }

  onTaskUpdate?.({ status: 'postprocessing', progress: 86, stage: 'Son işleme' });
  return repairDeep(await response.json());
}

async function runContractAnalysis({ libraryId, file, signal, onTaskUpdate }) {
  let studyId = libraryId;

  if (file) {
    const uploadPlan = await apiClient.post('/studies/upload-url', {
      filename: file.name,
      content_type: file.type || 'application/octet-stream',
      size: file.size,
    });

    onTaskUpdate?.({ status: 'uploading', progress: 12, stage: 'Görüntü yükleniyor' });

    if (uploadPlan?.upload_url) {
      await fetch(uploadPlan.upload_url, {
        method: uploadPlan.method || 'PUT',
        body: file,
        headers: uploadPlan.headers || {},
        signal,
      });
    }

    const study = await apiClient.post('/studies', {
      upload_id: uploadPlan.upload_id,
      object_key: uploadPlan.object_key,
      filename: file.name,
      modality: 'MR',
    });
    studyId = study?.id || study?.study_id || uploadPlan?.study_id;
  }

  const task = await apiClient.post('/ai/segment', {
    study_id: studyId,
    library_id: libraryId,
  });

  const taskId = task?.task_id || task?.taskId;
  onTaskUpdate?.({
    taskId,
    status: task?.status || 'queued',
    progress: 20,
    stage: 'Kuyruğa alındı',
  });

  if (!taskId) return repairDeep(task);

  const finalTask = await watchTask({
    taskId,
    pollUrl: task.poll_url,
    wsUrl: task.ws_url,
    onUpdate: onTaskUpdate,
    signal,
  });

  if (finalTask?.error) throw new Error(finalTask.error);
  if (finalTask?.result) return repairDeep(finalTask.result);

  const predictionId = finalTask?.predictionId || finalTask?.prediction_id || task?.prediction_id;
  if (!predictionId) return repairDeep(finalTask);

  return repairDeep(await apiClient.get(`/ai/predictions/${predictionId}`));
}

export async function runAnalysisJob(input, options = {}) {
  const startedAt = Date.now();
  const { onTaskUpdate, signal } = options;

  try {
    if (API_MODE === 'contract') {
      const result = await runContractAnalysis({ ...input, signal, onTaskUpdate });
      await ensureMinimumDuration(startedAt);
      return result;
    }
  } catch (error) {
    if (!isEndpointUnavailable(error)) throw error;
  }

  const result = await runLegacyAnalysis({ ...input, signal, onTaskUpdate });
  await ensureMinimumDuration(startedAt);
  return result;
}
