/**
 * aiService.js — NeuroOncoTrack-AI Servis Entegrasyonu
 *
 * AI mikroservisine (http://localhost:8100) HTTP istekleri gönderir.
 * Backend Gateway, AI servisi HTTP'si üzerinden çalışır; frontend bu servisi
 * doğrudan çağırabilir (demo/geliştirme) ya da backend proxy'si üzerinden kullanır.
 *
 * Endpoint'ler (AI Servisi — serve.py):
 *   GET  /health   → Bileşen sağlık durumu
 *   GET  /info     → Sürüm ve desteklenen modlar
 *   POST /infer    → Tam pipeline çalıştır
 *   POST /report   → Sadece rapor üret (model çıktısı üzerinden)
 */

import { AI_SERVICE_BASE } from '../config/neuroConstants.js';
import { repairDeep } from '../utils/neuroUtils.js';

// ─── Yardımcı ──────────────────────────────────────────────────────────────────

/**
 * AI servisine raw fetch isteği atar.
 * apiClient'ı KULLANMAZ — AI servisi ayrı origin ve auth şemasındadır.
 */
async function aiRequest(path, options = {}) {
  const { method = 'GET', body, signal } = options;

  const requestHeaders = new Headers();
  if (body) requestHeaders.set('Content-Type', 'application/json');

  let response;
  try {
    response = await fetch(`${AI_SERVICE_BASE}${path}`, {
      method,
      headers: requestHeaders,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (error) {
    throw new Error(
      `AI servisine ulaşılamadı (${AI_SERVICE_BASE}): ${error.message}`,
    );
  }

  if (response.status === 204) return null;

  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof data === 'object' ? data?.detail || JSON.stringify(data) : data;
    throw new Error(`AI servisi hatası [${response.status}]: ${detail}`);
  }

  return typeof data === 'object' ? repairDeep(data) : data;
}

// ─── Sağlık Kontrolü ──────────────────────────────────────────────────────────

/**
 * AI servisi bileşen sağlık durumu — GET /health
 *
 * Dönen yapı:
 * {
 *   "zeynep.v3_predictor": true,
 *   "mert.preprocessing": true,
 *   "mert.xai.overlay": true,
 *   "mert.llm.rag_pipeline": true,
 *   "groq_api_key": true
 * }
 */
export async function getAiHealth() {
  return aiRequest('/health');
}

// ─── Sürüm Bilgisi ───────────────────────────────────────────────────────────

/**
 * AI servis versiyon ve yetenek bilgisi — GET /info
 *
 * Dönen yapı:
 * {
 *   "service": "NeuroOncoTrack-AI",
 *   "version": "...",
 *   "supported_modes": ["full", "fast", "classify_only"],
 *   "supported_predictors": ["v3", "v2"],
 *   "supported_devices": ["auto", "cuda", "mps", "cpu"]
 * }
 */
export async function getAiInfo() {
  return aiRequest('/info');
}

// ─── Ana Pipeline ─────────────────────────────────────────────────────────────

/**
 * Tam AI pipeline çalıştır — POST /infer
 *
 * Dönüş şeması (özet):
 * {
 *   patient_id, pipeline_version, mode, device,
 *   stages: {
 *     preprocess: { status, elapsed_ms },
 *     classify:   { status, elapsed_ms, payload: { prediction, confidence, probabilities, model_id } },
 *     xai:        { status, elapsed_ms, payload: { overlay_path } },
 *     report:     { status, elapsed_ms, payload: { is_valid, sections, fhir, validation } }
 *   },
 *   summary: { prediction, confidence, who_grade_hint, tumor_volume_cm3, et_wt_ratio, report_valid },
 *   errors: [],
 *   total_elapsed_ms
 * }
 *
 * @param {object} params
 * @param {string}            params.patientId         — Örn: "BRATS-GLI-00123-000"
 * @param {object}            params.modalityPaths     — { t1, t1c, t2, flair } yolları (en az t1c zorunlu)
 * @param {string}            params.outputDir         — Çıktı klasörü
 * @param {'full'|'fast'|'classify_only'} [params.mode='fast']        — Pipeline modu
 * @param {'auto'|'cuda'|'mps'|'cpu'}     [params.device='auto']
 * @param {'v3'|'v2'}                     [params.predictor='v3']     — Ensemble versiyonu
 * @param {string}            [params.groqApiKey]      — Yoksa env değişkenine düşer
 * @param {string}            [params.guidelinesDir]
 * @param {string}            [params.quarantineRoot]
 * @param {object}            [params.extraFeatures]   — Örn: { tumor_volume_cm3, et_wt_ratio }
 * @param {AbortSignal}       [params.signal]
 */
export async function runAiInfer({
  patientId,
  modalityPaths,
  outputDir,
  mode = 'fast',
  device = 'auto',
  predictor = 'v3',
  groqApiKey,
  guidelinesDir,
  quarantineRoot,
  extraFeatures,
  signal,
} = {}) {
  if (!patientId) throw new Error('patientId zorunludur.');
  if (!modalityPaths?.t1c && !modalityPaths?.T1c && !modalityPaths?.T1C) {
    throw new Error('En az t1c modalitesi zorunludur.');
  }
  if (!outputDir) throw new Error('outputDir zorunludur.');

  return aiRequest('/infer', {
    method: 'POST',
    body: {
      patient_id: patientId,
      modality_paths: modalityPaths,
      output_dir: outputDir,
      mode,
      device,
      predictor,
      groq_api_key: groqApiKey || null,
      guidelines_dir: guidelinesDir || null,
      quarantine_root: quarantineRoot || null,
      extra_features: extraFeatures || null,
    },
    signal,
  });
}

// ─── Sadece Rapor ─────────────────────────────────────────────────────────────

/**
 * Sadece klinik rapor üret (mevcut model çıktısı üzerinden) — POST /report
 *
 * @param {object} modelOutput — Sınıf, hacim ve metrik bilgileri içeren nesne
 * @param {string} [groqApiKey]
 * @param {string} [guidelinesDir]
 */
export async function generateAiReport({
  modelOutput,
  groqApiKey,
  guidelinesDir,
} = {}) {
  if (!modelOutput) throw new Error('modelOutput zorunludur.');

  return aiRequest('/report', {
    method: 'POST',
    body: {
      model_output: modelOutput,
      groq_api_key: groqApiKey || null,
      guidelines_dir: guidelinesDir || null,
    },
  });
}

// ─── Bağlantı Testi ───────────────────────────────────────────────────────────

/**
 * AI servisine bağlantı durumunu test et.
 * Hata yoksa true, erişilemezse false döner.
 */
export async function isAiServiceAvailable() {
  try {
    await getAiHealth();
    return true;
  } catch {
    return false;
  }
}
