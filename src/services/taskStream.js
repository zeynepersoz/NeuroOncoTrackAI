import { API_BASE } from '../config/neuroConstants.js';
import { apiClient } from './apiClient.js';

function normalizeTaskUpdate(payload = {}) {
  return {
    taskId: payload.task_id || payload.taskId || payload.id || '',
    predictionId: payload.prediction_id || payload.predictionId || payload.result_id || '',
    status: payload.status || 'processing',
    progress: Number(payload.progress ?? payload.percent ?? payload.percentage ?? 0),
    stage: payload.stage || payload.step || payload.message || '',
    result: payload.result || payload.prediction || null,
    error: payload.error || payload.detail || '',
  };
}

function resolveWsUrl(wsUrl) {
  if (!wsUrl) return '';
  if (/^wss?:\/\//i.test(wsUrl)) return wsUrl;
  return `${API_BASE.replace(/^http/i, 'ws')}${wsUrl}`;
}

function isDone(update) {
  return ['completed', 'complete', 'tamamlandı', 'done', 'success'].includes(String(update.status).toLocaleLowerCase('tr-TR'));
}

function isFailed(update) {
  return ['failed', 'error', 'başarısız', 'basarisiz'].includes(String(update.status).toLocaleLowerCase('tr-TR'));
}

async function pollTask(pollUrl, onUpdate, signal) {
  let lastUpdate = null;

  while (!signal?.aborted) {
    const payload = await apiClient.get(pollUrl, { base: 'root', signal });
    lastUpdate = normalizeTaskUpdate(payload);
    onUpdate?.(lastUpdate);

    if (isDone(lastUpdate) || isFailed(lastUpdate)) return lastUpdate;
    await new Promise((resolve) => window.setTimeout(resolve, 3000));
  }

  return lastUpdate;
}

function watchTaskSocket(wsUrl, onUpdate, signal) {
  return new Promise((resolve, reject) => {
    const resolvedUrl = resolveWsUrl(wsUrl);
    if (!resolvedUrl || typeof WebSocket === 'undefined') {
      reject(new Error('WebSocket desteklenmiyor.'));
      return;
    }

    const socket = new WebSocket(resolvedUrl);

    const close = () => {
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
    };

    signal?.addEventListener('abort', close, { once: true });

    socket.onmessage = (event) => {
      try {
        const update = normalizeTaskUpdate(JSON.parse(event.data));
        onUpdate?.(update);
        if (isDone(update) || isFailed(update)) {
          close();
          resolve(update);
        }
      } catch (error) {
        reject(error);
      }
    };

    socket.onerror = () => reject(new Error('Canlı görev bağlantısı kurulamadı.'));
    socket.onclose = () => signal?.removeEventListener('abort', close);
  });
}

export async function watchTask({ taskId, pollUrl, wsUrl, onUpdate, signal }) {
  const normalizedPollUrl = pollUrl || `/api/v1/ai/tasks/${taskId}`;

  if (wsUrl) {
    try {
      return await watchTaskSocket(wsUrl, onUpdate, signal);
    } catch {
      return pollTask(normalizedPollUrl, onUpdate, signal);
    }
  }

  return pollTask(normalizedPollUrl, onUpdate, signal);
}
