/**
 * studyService.js — NeuroOncoTrack-AI Çalışma Servisi
 *
 * Backend endpoint entegrasyonu:
 *   GET  /api/library              — Demo vaka kütüphanesi (legacy)
 *   POST /api/analyze              — Doğrudan analiz (legacy)
 *   POST /api/v1/studies/upload-url — Presigned upload URL
 *   POST /api/v1/studies           — Çalışma kaydı oluştur
 *   POST /api/v1/ai/segment        — Segmentasyon görevi başlat
 *   GET  /api/v1/ai/tasks/{id}     — Görev durumu
 *   GET  /api/v1/ai/predictions/{id} — Tahmin sonucu
 *
 * AI Servis doğrudan entegrasyonu (port 8100):
 *   POST /infer                    — Tam pipeline (aiService.js)
 *   GET  /health                   — AI servisi sağlık
 */

import { API_BASE, API_MODE, MIN_ANALYSIS_LOADER_MS } from '../config/neuroConstants.js';
import { readApiError, repairDeep } from '../utils/neuroUtils.js';
import { apiClient, isEndpointUnavailable } from './apiClient.js';
import { watchTask } from './taskStream.js';
import { isAiServiceAvailable, runAiInfer } from './aiService.js';

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function ensureMinimumDuration(startedAt) {
  const elapsed = Date.now() - startedAt;
  if (elapsed < MIN_ANALYSIS_LOADER_MS) {
    await sleep(MIN_ANALYSIS_LOADER_MS - elapsed);
  }
}

// ─── Demo Vaka Kütüphanesi (Legacy) ────────────────────────────────────────

export async function listCaseLibrary() {
  const data = await apiClient.get('/api/library', { auth: false, base: 'root' });
  return repairDeep(data);
}

// ─── Legacy Analiz (Doğrudan Flask/backend) ──────────────────────────────────

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

// ─── Contract Analiz (Backend API v1) ────────────────────────────────────────

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

  const predictionId =
    finalTask?.predictionId || finalTask?.prediction_id || task?.prediction_id;
  if (!predictionId) return repairDeep(finalTask);

  return repairDeep(await apiClient.get(`/ai/predictions/${predictionId}`));
}

// ─── AI Servis Doğrudan Analiz (port 8100) ───────────────────────────────────

/**
 * AI mikroserfisi üzerinden doğrudan analiz çalıştır.
 * Backend'in `/ai/*` endpoint'leri henüz hazır değilse bu yol kullanılır.
 *
 * @param {object} params
 * @param {string}  [params.patientId]     — Hasta ID'si
 * @param {object}  [params.modalityPaths] — { t1c: "..." } en az t1c zorunlu
 * @param {string}  [params.outputDir]     — Çıktı klasörü
 * @param {string}  [params.mode]          — 'fast' | 'full' | 'classify_only'
 * @param {Function} [params.onTaskUpdate]
 * @param {AbortSignal} [params.signal]
 */
async function runAiServiceAnalysis({ patientId, modalityPaths, outputDir, mode, onTaskUpdate, signal }) {
  onTaskUpdate?.({ status: 'ai_service', progress: 10, stage: 'AI servise bağlanılıyor' });

  const result = await runAiInfer({
    patientId: patientId || `case-${Date.now()}`,
    modalityPaths: modalityPaths || {},
    outputDir: outputDir || `_out/${patientId || 'case'}`,
    mode: mode || 'fast',
    signal,
  });

  onTaskUpdate?.({ status: 'completed', progress: 100, stage: 'Tamamlandı' });

  // AI servisi çıktısını legacy format ile uyumlu hale getir
  const classify = result?.stages?.classify?.payload || {};
  const report = result?.stages?.report?.payload || {};
  const summary = result?.summary || {};

  return repairDeep({
    // Temel tahmin
    prediction: classify.prediction || summary.prediction,
    diagnosis_tr: classify.prediction || summary.prediction,
    confidence: classify.confidence || summary.confidence,
    probs: classify.probabilities || {},
    model_id: classify.model_id,

    // Hacim / radyomik
    volume: summary.tumor_volume_cm3,
    tumor_volume_cm3: summary.tumor_volume_cm3,
    et_wt_ratio: summary.et_wt_ratio,
    who_grade_hint: summary.who_grade_hint,

    // Rapor
    report: report?.sections
      ? Object.values(report.sections).join('\n\n')
      : null,
    is_valid: report?.is_valid,

    // FHIR
    fhir: report?.fhir || {},

    // XAI
    overlay_path: result?.stages?.xai?.payload?.overlay_path || null,

    // Ham pipeline çıktısı (debug/gelişmiş kullanım)
    _pipeline: result,
  });
}

// ─── Ana Giriş Noktası ────────────────────────────────────────────────────────

/**
 * Analiz işini çalıştır.
 *
 * Öncelik sırası:
 *   1. API_MODE === 'contract'  → Backend /api/v1/ai/* endpointleri
 *   2. AI servisi (port 8100) erişilebilirse → Doğrudan runAiInfer
 *   3. Legacy  → /api/analyze (Flask/demo)
 *
 * @param {object} input
 * @param {string}   [input.libraryId]      — Kütüphane vaka ID'si
 * @param {File}     [input.file]           — Yüklenen MRG dosyası
 * @param {string}   [input.patientId]      — Hasta ID (AI servisi için)
 * @param {object}   [input.modalityPaths]  — AI servisi modalite yolları
 * @param {string}   [input.outputDir]      — AI servisi çıktı dizini
 * @param {string}   [input.mode]           — AI pipeline modu
 * @param {object}   options
 * @param {Function} [options.onTaskUpdate]
 * @param {AbortSignal} [options.signal]
 */
export async function runAnalysisJob(input, options = {}) {
  const startedAt = Date.now();
  const { onTaskUpdate, signal } = options;

  // 1. Backend contract modu
  try {
    if (API_MODE === 'contract') {
      const result = await runContractAnalysis({ ...input, signal, onTaskUpdate });
      await ensureMinimumDuration(startedAt);
      return result;
    }
  } catch (error) {
    if (!isEndpointUnavailable(error)) throw error;
    // Endpoint yoksa AI servisine düş
  }

  // 2. AI servisi (port 8100) erişilebilir mi?
  if (input.modalityPaths && Object.keys(input.modalityPaths).length > 0) {
    try {
      const aiAvailable = await isAiServiceAvailable();
      if (aiAvailable) {
        const result = await runAiServiceAnalysis({ ...input, signal, onTaskUpdate });
        await ensureMinimumDuration(startedAt);
        return result;
      }
    } catch (error) {
      // AI servisi hatalıysa legacy'e düş
      console.warn('[studyService] AI servisi çalışmadı, legacy moda geçiliyor:', error.message);
    }
  }

  // 3. Legacy analiz
  const result = await runLegacyAnalysis({ ...input, signal, onTaskUpdate });
  await ensureMinimumDuration(startedAt);
  return result;
}
