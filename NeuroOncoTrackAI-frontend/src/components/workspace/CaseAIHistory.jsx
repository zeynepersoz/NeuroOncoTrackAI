import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Brain,
  Clock,
  ExternalLink,
  Eye,
  FileText,
  Layers,
  RefreshCw,
  X,
} from 'lucide-react';
import StatusPill from '../common/StatusPill.jsx';
import {
  getAIHistory,
  getAIAnalysisDetail,
  getClinicalReports,
  getClinicalReportDetail,
  formatSafeErrorMessage,
} from '../../services/aiHistoryService.js';
import { formatDateTime, repairText } from '../../utils/neuroUtils.js';

export default function CaseAIHistory({ patientId, activeCaseId, onSelectAnalysis }) {
  const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'classification' | 'segmentation' | 'report'
  const [historyItems, setHistoryItems] = useState([]);
  const [reportItems, setReportItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  
  // Modals state
  const [selectedAnalysisId, setSelectedAnalysisId] = useState(null);
  const [analysisDetail, setAnalysisDetail] = useState(null);
  const [loadingAnalysisDetail, setLoadingAnalysisDetail] = useState(false);
  const [analysisDetailError, setAnalysisDetailError] = useState('');

  const [selectedReportId, setSelectedReportId] = useState(null);
  const [reportDetail, setReportDetail] = useState(null);
  const [loadingReportDetail, setLoadingReportDetail] = useState(false);
  const [reportDetailError, setReportDetailError] = useState('');

  // Fetch all persisted history for current patient
  const fetchHistory = useCallback(async () => {
    if (!patientId) {
      setHistoryItems([]);
      setReportItems([]);
      return;
    }

    setLoading(true);
    setErrorMessage('');

    try {
      // Parallel fetch of analyses and clinical reports
      const [analysesRes, reportsRes] = await Promise.all([
        getAIHistory({ patientId: patientId.trim(), limit: 100 }),
        getClinicalReports({ patientId: patientId.trim(), limit: 100 }),
      ]);

      setHistoryItems(analysesRes?.items || []);
      setReportItems(reportsRes?.items || []);
    } catch (err) {
      console.error('History fetch error:', err);
      setErrorMessage(formatSafeErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      if (!patientId) {
        setHistoryItems([]);
        setReportItems([]);
        return;
      }
      setLoading(true);
      setErrorMessage('');
      try {
        const [analysesRes, reportsRes] = await Promise.all([
          getAIHistory({ patientId: patientId.trim(), limit: 100 }),
          getClinicalReports({ patientId: patientId.trim(), limit: 100 }),
        ]);
        if (!ignore) {
          setHistoryItems(analysesRes?.items || []);
          setReportItems(reportsRes?.items || []);
        }
      } catch (err) {
        if (!ignore) {
          console.error('History fetch error:', err);
          setErrorMessage(formatSafeErrorMessage(err));
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [patientId]);

  // Load Analysis Detail
  const openAnalysisDetail = async (id) => {
    setSelectedAnalysisId(id);
    setLoadingAnalysisDetail(true);
    setAnalysisDetailError('');
    setAnalysisDetail(null);

    try {
      const data = await getAIAnalysisDetail(id);
      setAnalysisDetail(data);
    } catch (err) {
      console.error('Detail fetch error:', err);
      setAnalysisDetailError(formatSafeErrorMessage(err));
    } finally {
      setLoadingAnalysisDetail(false);
    }
  };

  // Load Report Detail
  const openReportDetail = async (repId) => {
    setSelectedReportId(repId);
    setLoadingReportDetail(true);
    setReportDetailError('');
    setReportDetail(null);

    try {
      const data = await getClinicalReportDetail(repId);
      setReportDetail(data);
    } catch (err) {
      console.error('Report detail fetch error:', err);
      setReportDetailError(formatSafeErrorMessage(err));
    } finally {
      setLoadingReportDetail(false);
    }
  };

  // Combine and sort all historical records chronologically (newest first)
  const unifiedList = React.useMemo(() => {
    const list = [];

    historyItems.forEach((item) => {
      list.push({
        type: 'analysis',
        id: item.id,
        operation: item.operation,
        status: item.status,
        model: item.model,
        prediction: item.prediction,
        confidence: item.confidence,
        tumor_volume_cm3: item.tumor_volume_cm3,
        created_at: item.created_at,
        completed_at: item.completed_at,
        raw: item,
      });
    });

    reportItems.forEach((rep) => {
      list.push({
        type: 'report',
        id: rep.id,
        report_id: rep.report_id,
        operation: 'report',
        status: rep.status,
        model: 'clinical-rag-llm',
        summary: rep.summary,
        created_at: rep.created_at,
        raw: rep,
      });
    });

    list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    if (activeFilter === 'all') return list;
    if (activeFilter === 'report') return list.filter((x) => x.type === 'report');
    return list.filter((x) => x.operation === activeFilter);
  }, [historyItems, reportItems, activeFilter]);

  const getStatusTone = (status) => {
    const s = String(status).toUpperCase();
    if (s === 'COMPLETED') return 'success';
    if (s === 'FAILED') return 'danger';
    if (s === 'PROCESSING' || s === 'PENDING') return 'info';
    return 'warning';
  };

  const getOperationLabel = (op) => {
    if (op === 'classification') return 'Sınıflandırma (2D/3D)';
    if (op === 'segmentation') return 'Segmentasyon (BraTS)';
    if (op === 'report') return 'Klinik Rapor (Yapılandırılmış)';
    return op;
  };

  const getOperationIcon = (op) => {
    if (op === 'classification') return <Brain size={16} className="text-teal" />;
    if (op === 'segmentation') return <Layers size={16} className="text-amber" />;
    return <FileText size={16} className="text-blue" />;
  };

  return (
    <div className="case-ai-history-panel">
      {/* Header & Filter Toolbar */}
      <div className="history-toolbar">
        <div className="toolbar-left">
          <div className="history-title-row">
            <Activity size={18} />
            <h3>AI Analiz ve Rapor Geçmişi</h3>
            <span className="history-count-badge">{unifiedList.length} kayıt</span>
            {activeCaseId && (
              <span className="case-id-badge" style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: '6px', background: 'var(--chip-bg, rgba(255,255,255,0.08))', color: 'var(--muted)' }}>
                Vaka: {activeCaseId}
              </span>
            )}
          </div>
          <p className="history-subtitle">
            Bu vakaya ({patientId || 'Belirtilmedi'}) ait PostgreSQL üzerinde kalıcı olarak saklanan tüm AI analizleri.
          </p>
        </div>

        <div className="toolbar-right">
          <div className="filter-pill-group">
            <button
              type="button"
              className={`filter-btn ${activeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setActiveFilter('all')}
            >
              Tümü ({historyItems.length + reportItems.length})
            </button>
            <button
              type="button"
              className={`filter-btn ${activeFilter === 'classification' ? 'active' : ''}`}
              onClick={() => setActiveFilter('classification')}
            >
              Sınıflandırma ({historyItems.filter((x) => x.operation === 'classification').length})
            </button>
            <button
              type="button"
              className={`filter-btn ${activeFilter === 'segmentation' ? 'active' : ''}`}
              onClick={() => setActiveFilter('segmentation')}
            >
              Segmentasyon ({historyItems.filter((x) => x.operation === 'segmentation').length})
            </button>
            <button
              type="button"
              className={`filter-btn ${activeFilter === 'report' ? 'active' : ''}`}
              onClick={() => setActiveFilter('report')}
            >
              Rapor ({reportItems.length})
            </button>
          </div>

          <button
            type="button"
            className="history-refresh-btn"
            onClick={fetchHistory}
            disabled={loading}
            title="Geçmişi PostgreSQL'den yenile"
          >
            <RefreshCw size={15} className={loading ? 'spin' : ''} />
            <span>Yenile</span>
          </button>
        </div>
      </div>

      {/* Error Alert with Retry */}
      {errorMessage && (
        <div className="history-error-banner" role="alert">
          <div className="banner-content">
            <AlertCircle size={18} />
            <span>{errorMessage}</span>
          </div>
          <button type="button" onClick={fetchHistory} className="retry-action-btn">
            Tekrar Dene
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !unifiedList.length && (
        <div className="history-loading-container">
          <RefreshCw size={28} className="spin text-teal" />
          <p>Kalıcı AI analiz geçmişi PostgreSQL veritabanından yükleniyor...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && !errorMessage && unifiedList.length === 0 && (
        <div className="history-empty-state">
          <div className="empty-icon-circle">
            <Clock size={32} />
          </div>
          <h4>Bu vaka için henüz bir AI analizi yapılmadı</h4>
          <p>
            Yeni bir analiz çalıştırmak için sol panelden MRG görseli yükleyin veya kütüphaneden vaka seçip
            çalıştırın. Tamamlanan tüm çıkarımlar veritabanında kalıcı olarak saklanacaktır.
          </p>
        </div>
      )}

      {/* Records Table / List */}
      {!loading && unifiedList.length > 0 && (
        <div className="history-table-container">
          <table className="history-table">
            <thead>
              <tr>
                <th>Operasyon</th>
                <th>Durum</th>
                <th>Model / Sürüm</th>
                <th>Özet Bulgular</th>
                <th>Tarih / Saat</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {unifiedList.map((item, idx) => {
                const isReport = item.type === 'report';
                return (
                  <tr
                    key={item.id || item.report_id || idx}
                    className="history-row"
                    onClick={() => {
                      if (isReport) {
                        openReportDetail(item.report_id);
                      } else {
                        openAnalysisDetail(item.id);
                      }
                    }}
                  >
                    <td>
                      <div className="operation-cell">
                        {getOperationIcon(item.operation)}
                        <div>
                          <strong>{getOperationLabel(item.operation)}</strong>
                          <span className="sub-id">
                            {isReport ? `ID: ${item.report_id.slice(0, 12)}...` : `Req: ${item.raw.request_id?.slice(0, 8) || item.id.slice(0, 8)}`}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <StatusPill tone={getStatusTone(item.status)}>
                        {item.status}
                      </StatusPill>
                    </td>
                    <td>
                      <span className="model-tag">{item.model || 'neuroonco-v3'}</span>
                    </td>
                    <td>
                      <div className="metrics-cell">
                        {item.operation === 'classification' && (
                          <>
                            <span className="highlight-metric">
                              Tanı: <strong>{repairText(item.prediction || 'N/A')}</strong>
                            </span>
                            {item.confidence !== undefined && (
                              <span className="metric-badge">
                                Güven: %{Math.round(item.confidence * 100)}
                              </span>
                            )}
                          </>
                        )}
                        {item.operation === 'segmentation' && (
                          <>
                            <span className="highlight-metric">
                              Hacim:{' '}
                              <strong>
                                {item.tumor_volume_cm3 !== null && item.tumor_volume_cm3 !== undefined
                                  ? `${Number(item.tumor_volume_cm3).toFixed(2)} cm³`
                                  : 'Ölçüldü'}
                              </strong>
                            </span>
                          </>
                        )}
                        {isReport && (
                          <span className="report-summary-snippet" title={item.summary}>
                            {item.summary ? item.summary.slice(0, 75) + '...' : 'Klinik değerlendirme raporu'}
                          </span>
                        )}
                        {item.status === 'FAILED' && (
                          <span className="failed-notice">İşlem hatası kaydedildi</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className="timestamp-text">
                        {formatDateTime(item.created_at)}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="detail-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isReport) {
                            openReportDetail(item.report_id);
                          } else {
                            openAnalysisDetail(item.id);
                          }
                        }}
                      >
                        <Eye size={14} />
                        <span>İncele</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── ANALYSIS DETAIL MODAL ────────────────────────────────────── */}
      {selectedAnalysisId && (
        <div className="history-modal-backdrop" onClick={() => setSelectedAnalysisId(null)}>
          <div className="history-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="history-modal-header">
              <div className="modal-title-left">
                <Brain size={20} className="text-teal" />
                <div>
                  <h4>AI Analiz Detayı (Kalıcı Kayıt)</h4>
                  <span className="modal-sub">ID: {selectedAnalysisId}</span>
                </div>
              </div>
              <button
                type="button"
                className="close-modal-btn"
                onClick={() => setSelectedAnalysisId(null)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="history-modal-body">
              {loadingAnalysisDetail && (
                <div className="modal-loading-pane">
                  <RefreshCw size={24} className="spin text-teal" />
                  <p>Analiz detayı veritabanından getiriliyor...</p>
                </div>
              )}

              {analysisDetailError && (
                <div className="history-error-banner">
                  <AlertCircle size={18} />
                  <span>{analysisDetailError}</span>
                </div>
              )}

              {analysisDetail && !loadingAnalysisDetail && (
                <div className="detail-content-grid">
                  {/* Status Banner */}
                  <div className={`detail-status-banner tone-${getStatusTone(analysisDetail.status)}`}>
                    <div className="status-label-group">
                      <span>Operasyon:</span>
                      <strong>{getOperationLabel(analysisDetail.operation)}</strong>
                    </div>
                    <div className="status-label-group">
                      <span>Durum:</span>
                      <StatusPill tone={getStatusTone(analysisDetail.status)}>
                        {analysisDetail.status}
                      </StatusPill>
                    </div>
                    <div className="status-label-group">
                      <span>Model:</span>
                      <strong>{analysisDetail.model}</strong>
                    </div>
                  </div>

                  {/* If Failed */}
                  {analysisDetail.status === 'FAILED' && (
                    <div className="failed-alert-card">
                      <AlertTriangle size={20} className="text-rose" />
                      <div>
                        <strong>Analiz Başarısız Oldu</strong>
                        <p>{formatSafeErrorMessage({ message: analysisDetail.error })}</p>
                      </div>
                    </div>
                  )}

                  {/* Timestamps and IDs */}
                  <div className="detail-meta-grid">
                    <div className="meta-item">
                      <label>Hasta Protokol / Kodu:</label>
                      <span>{analysisDetail.patient_id}</span>
                    </div>
                    <div className="meta-item">
                      <label>Oluşturulma Zamanı:</label>
                      <span>{formatDateTime(analysisDetail.created_at)}</span>
                    </div>
                    {analysisDetail.completed_at && (
                      <div className="meta-item">
                        <label>Tamamlanma Zamanı:</label>
                        <span>{formatDateTime(analysisDetail.completed_at)}</span>
                      </div>
                    )}
                    <div className="meta-item">
                      <label>İstek (Correlation) ID:</label>
                      <span className="mono-text">{analysisDetail.request_id}</span>
                    </div>
                  </div>

                  {/* Operation Specific Metrics */}
                  {analysisDetail.operation === 'classification' && (
                    <div className="detail-section-card">
                      <h5>Sınıflandırma ve Diferansiyel Tanı Sonuçları</h5>
                      <div className="classification-metrics-row">
                        <div className="metric-box">
                          <span className="box-label">Tahmin Edilen Tanı</span>
                          <strong className="box-val text-teal">
                            {repairText(analysisDetail.prediction || 'Belirsiz')}
                          </strong>
                        </div>
                        <div className="metric-box">
                          <span className="box-label">Model Güven Skoru</span>
                          <strong className="box-val">
                            {analysisDetail.confidence !== null && analysisDetail.confidence !== undefined
                              ? `%${Math.round(analysisDetail.confidence * 100)}`
                              : 'N/A'}
                          </strong>
                        </div>
                        {analysisDetail.who_grade_hint && (
                          <div className="metric-box">
                            <span className="box-label">WHO Derece İpucu</span>
                            <strong className="box-val">{analysisDetail.who_grade_hint}</strong>
                          </div>
                        )}
                      </div>

                      {/* Probabilities distribution */}
                      {analysisDetail.probabilities && Object.keys(analysisDetail.probabilities).length > 0 && (
                        <div className="probabilities-sublist">
                          <label>Sınıf Olasılık Dağılımı:</label>
                          <div className="prob-bars">
                            {Object.entries(analysisDetail.probabilities).map(([lbl, pVal]) => (
                              <div key={lbl} className="prob-bar-row">
                                <div className="bar-labels">
                                  <span>{repairText(lbl)}</span>
                                  <strong>%{Math.round(Number(pVal) * 100)}</strong>
                                </div>
                                <div className="bar-track">
                                  <div
                                    className="bar-fill"
                                    style={{ width: `${Math.round(Number(pVal) * 100)}%` }}
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {analysisDetail.operation === 'segmentation' && (
                    <div className="detail-section-card">
                      <h5>Segmentasyon ve Volumetrik Ölçümler</h5>
                      <div className="segmentation-metrics-row">
                        <div className="metric-box">
                          <span className="box-label">Tümör Hacmi (3D)</span>
                          <strong className="box-val text-amber">
                            {analysisDetail.tumor_volume_cm3 !== null && analysisDetail.tumor_volume_cm3 !== undefined
                              ? `${Number(analysisDetail.tumor_volume_cm3).toFixed(2)} cm³`
                              : 'N/A'}
                          </strong>
                        </div>
                        {analysisDetail.tumor_area_ratio_2d !== null && (
                          <div className="metric-box">
                            <span className="box-label">2D Alan Oranı</span>
                            <strong className="box-val">
                              %{Math.round(Number(analysisDetail.tumor_area_ratio_2d) * 100)}
                            </strong>
                          </div>
                        )}
                        {analysisDetail.et_wt_ratio !== null && (
                          <div className="metric-box">
                            <span className="box-label">ET / WT Oranı</span>
                            <strong className="box-val">
                              {Number(analysisDetail.et_wt_ratio).toFixed(3)}
                            </strong>
                          </div>
                        )}
                      </div>

                      {analysisDetail.mask_artifact_id && (
                        <div className="artifact-ref-box">
                          <Layers size={16} />
                          <div>
                            <span>Maske Çıktısı (Artifact Reference):</span>
                            <strong>{analysisDetail.mask_artifact_id}</strong>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Input parameters */}
                  {analysisDetail.inputs && (
                    <div className="detail-section-card">
                      <h5>Girdi Parametreleri</h5>
                      <pre className="code-block-preview">
                        {JSON.stringify(analysisDetail.inputs, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="history-modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                {onSelectAnalysis && analysisDetail && analysisDetail.status === 'COMPLETED' && (
                  <button
                    type="button"
                    className="workspace-primary"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '0.45rem 0.9rem', fontSize: '0.8125rem' }}
                    onClick={() => {
                      onSelectAnalysis(analysisDetail);
                      setSelectedAnalysisId(null);
                    }}
                  >
                    <ExternalLink size={14} />
                    <span>Çalışma Alanında Görüntüle</span>
                  </button>
                )}
              </div>
              <button
                type="button"
                className="workspace-secondary"
                onClick={() => setSelectedAnalysisId(null)}
              >
                Kapat
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── CLINICAL REPORT DETAIL MODAL ────────────────────────────── */}
      {selectedReportId && (
        <div className="history-modal-backdrop" onClick={() => setSelectedReportId(null)}>
          <div className="history-modal-card wide" onClick={(e) => e.stopPropagation()}>
            <div className="history-modal-header">
              <div className="modal-title-left">
                <FileText size={20} className="text-blue" />
                <div>
                  <h4>Kalıcı Klinik AI Raporu (Snapshot)</h4>
                  <span className="modal-sub">Rapor ID: {selectedReportId}</span>
                </div>
              </div>
              <button
                type="button"
                className="close-modal-btn"
                onClick={() => setSelectedReportId(null)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="history-modal-body">
              {loadingReportDetail && (
                <div className="modal-loading-pane">
                  <RefreshCw size={24} className="spin text-teal" />
                  <p>Klinik rapor snapshot veritabanından yükleniyor...</p>
                </div>
              )}

              {reportDetailError && (
                <div className="history-error-banner">
                  <AlertCircle size={18} />
                  <span>{reportDetailError}</span>
                </div>
              )}

              {reportDetail && !loadingReportDetail && (
                <div className="report-detail-layout">
                  {/* Header Banner */}
                  <div className="report-header-banner">
                    <div>
                      <span className="report-tag">IMMUTABLE CLINICAL DOCUMENT</span>
                      <h3>Beyin MRG Yapay Zeka Ön Değerlendirme Raporu</h3>
                    </div>
                    <StatusPill tone={getStatusTone(reportDetail.status)}>
                      {reportDetail.status}
                    </StatusPill>
                  </div>

                  <div className="report-meta-strip">
                    <span><strong>Hasta:</strong> {reportDetail.patient_id}</span>
                    <span><strong>Tarih:</strong> {formatDateTime(reportDetail.created_at)}</span>
                    <span><strong>Model:</strong> {reportDetail.model}</span>
                  </div>

                  {/* Summary */}
                  <div className="report-section-pane">
                    <h5>1. Klinik Özet</h5>
                    <p className="report-body-text">{reportDetail.summary}</p>
                  </div>

                  {/* Snapshots */}
                  <div className="report-snapshot-row">
                    {reportDetail.classification_snapshot && (
                      <div className="snapshot-card">
                        <h6>Sınıflandırma Snapshot</h6>
                        <dl className="snapshot-dl">
                          <dt>Ön Tanı:</dt>
                          <dd><strong>{reportDetail.classification_snapshot.prediction}</strong></dd>
                          <dt>Güven:</dt>
                          <dd>%{Math.round((reportDetail.classification_snapshot.confidence || 0) * 100)}</dd>
                          {reportDetail.classification_snapshot.who_grade_hint && (
                            <>
                              <dt>WHO Notu:</dt>
                              <dd>{reportDetail.classification_snapshot.who_grade_hint}</dd>
                            </>
                          )}
                        </dl>
                      </div>
                    )}

                    {reportDetail.segmentation_snapshot && (
                      <div className="snapshot-card">
                        <h6>Segmentasyon Snapshot</h6>
                        <dl className="snapshot-dl">
                          <dt>Tümör Hacmi:</dt>
                          <dd>
                            <strong>
                              {reportDetail.segmentation_snapshot.tumor_volume_cm3 !== undefined
                                ? `${Number(reportDetail.segmentation_snapshot.tumor_volume_cm3).toFixed(2)} cm³`
                                : 'N/A'}
                            </strong>
                          </dd>
                          {reportDetail.segmentation_snapshot.mask_artifact_id && (
                            <>
                              <dt>Maske ID:</dt>
                              <dd className="mono-text">{reportDetail.segmentation_snapshot.mask_artifact_id}</dd>
                            </>
                          )}
                        </dl>
                      </div>
                    )}
                  </div>

                  {/* Findings */}
                  <div className="report-section-pane">
                    <h5>2. Radyolojik Bulgular</h5>
                    <p className="report-body-text">{reportDetail.findings}</p>
                  </div>

                  {/* Recommendations */}
                  <div className="report-section-pane">
                    <h5>3. Öneriler & Klinik Takip</h5>
                    <p className="report-body-text">{reportDetail.recommendations}</p>
                  </div>

                  {/* Limitations */}
                  <div className="report-section-pane limitations-box">
                    <h5>4. Sınırlılıklar & Tıbbi Yasal Uyarı</h5>
                    <p className="report-body-text">{reportDetail.limitations}</p>
                  </div>

                  {/* FHIR Preview if present */}
                  {reportDetail.fhir_resource && (
                    <div className="report-section-pane">
                      <h5>FHIR R4 DiagnosticReport Kaynağı</h5>
                      <pre className="code-block-preview">
                        {JSON.stringify(reportDetail.fhir_resource, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="history-modal-footer">
              <button
                type="button"
                className="workspace-secondary"
                onClick={() => setSelectedReportId(null)}
              >
                Kapat
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
