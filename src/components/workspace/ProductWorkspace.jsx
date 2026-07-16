import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Calendar,
  CheckCircle,
  Download,
  Eye,
  FileText,
  Image as ImageIcon,
  Layers,
  LogOut,
  Maximize2,
  Minimize2,
  MoveDown,
  MoveLeft,
  MoveRight,
  MoveUp,
  Printer,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Upload,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import {
  API_BASE,
  MODULE_TRANSITION_MS,
  VIEWER_MAX_ZOOM,
  VIEWER_MIN_ZOOM,
  analysisStages,
  caseFilterDefaults,
  demoPatientProfiles,
  fhirOptions,
  formatter,
  viewModes,
  workspaceTabs,
} from '../../config/neuroConstants.js';
import ThemeToggle from '../common/ThemeToggle.jsx';
import StatusPill from '../common/StatusPill.jsx';
import MetricCard from './MetricCard.jsx';
import ModuleLoader from './ModuleLoader.jsx';
import {
  buildReportDraft,
  buildReportHtml,
  clampNumber,
  clampViewerPan,
  downloadBlob,
  formatFeatureName,
  formatNumber,
  formatPercent,
  getApprovalText,
  getDiagnosisTone,
  getFhirSummary,
  getImageModeSource,
  getRiskPlan,
  getStructuredReportSections,
  imageSource,
  matchesCaseFilters,
  normalizeSearchText,
  readApiError,
  repairDeep,
  repairText,
  toNumber,
} from '../../utils/neuroUtils.js';

export default function ProductWorkspace({ isDemoMode, theme, setTheme, onLogout }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [tabLoading, setTabLoading] = useState(null);
  const [libraryScans, setLibraryScans] = useState([]);
  const [selectedScanId, setSelectedScanId] = useState('');
  const viewerShellRef = useRef(null);
  const viewerDragRef = useRef({ active: false, pointerId: null, startX: 0, startY: 0, originX: 0, originY: 0 });
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [patientName, setPatientName] = useState('Hasta Protokol-9824');
  const [patientAge, setPatientAge] = useState(42);
  const [patientGender, setPatientGender] = useState('female');
  const [viewMode, setViewMode] = useState('overlay');
  const [overlayOpacity, setOverlayOpacity] = useState(82);
  const [showSegmentationOverlay, setShowSegmentationOverlay] = useState(true);
  const [viewerZoom, setViewerZoom] = useState(100);
  const [viewerPan, setViewerPan] = useState({ x: 0, y: 0 });
  const [isViewerDragging, setIsViewerDragging] = useState(false);
  const [isViewerFullscreen, setIsViewerFullscreen] = useState(false);
  const [xaiHeatOpacity, setXaiHeatOpacity] = useState(82);
  const [showXaiHeatmap, setShowXaiHeatmap] = useState(true);
  const [analysisStepIndex, setAnalysisStepIndex] = useState(0);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [llmReport, setLlmReport] = useState('');
  const [radiologistApproval, setRadiologistApproval] = useState(null);
  const [manualDraft, setManualDraft] = useState('');
  const [manualDraftKey, setManualDraftKey] = useState('');
  const [activeFhirResource, setActiveFhirResource] = useState('patient');
  const [searchQuery, setSearchQuery] = useState('');
  const [caseFilters, setCaseFilters] = useState(caseFilterDefaults);
  const [isCaseFilterOpen, setIsCaseFilterOpen] = useState(false);

  const risk = getRiskPlan(analysisResult);
  const diagnosisTone = getDiagnosisTone(analysisResult);
  const probabilities = Object.entries(analysisResult?.probs || {});
  const features = Object.entries(analysisResult?.features || {}).slice(0, 8);
  const selectedScan = libraryScans.find((scan) => scan.id === selectedScanId);
  const filteredLibraryScans = useMemo(
    () => libraryScans.filter((scan) => matchesCaseFilters(scan, caseFilters)),
    [caseFilters, libraryScans],
  );
  const libraryOptions =
    selectedScan && !filteredLibraryScans.some((scan) => scan.id === selectedScan.id)
      ? [selectedScan, ...filteredLibraryScans]
      : filteredLibraryScans;
  const activeAnalysisStage = analysisStages[Math.min(analysisStepIndex, analysisStages.length - 1)];
  const viewerTransform = {
    transform: `translate(${viewerPan.x}px, ${viewerPan.y}px) scale(${viewerZoom / 100})`,
  };
  const reportSections = useMemo(
    () =>
      getStructuredReportSections(
        analysisResult,
        patientName,
        patientAge,
        patientGender,
        radiologistApproval,
      ),
    [analysisResult, patientAge, patientGender, patientName, radiologistApproval],
  );
  const reportText = repairText(llmReport || analysisResult?.report || '');
  const generatedDraft = useMemo(
    () =>
      reportText ||
      (analysisResult
        ? buildReportDraft(analysisResult, patientName, patientAge, patientGender, radiologistApproval)
        : ''),
    [analysisResult, patientAge, patientGender, patientName, radiologistApproval, reportText],
  );
  const draftSourceKey = `${analysisResult?.image_name || ''}|${reportText}|${radiologistApproval || 'draft'}`;
  const draftReport = manualDraftKey === draftSourceKey ? manualDraft : generatedDraft;
  const fhirResource = useMemo(() => {
    const fhir = analysisResult?.fhir || {};
    if (activeFhirResource === 'diagnostic_report') {
      return {
        ...(fhir.diagnostic_report || {}),
        status: radiologistApproval === 'approved' ? 'final' : 'preliminary',
        conclusion:
          repairText(llmReport) ||
          repairText(fhir.diagnostic_report?.conclusion) ||
          (analysisResult ? `${repairText(analysisResult.diagnosis_tr)} için yapay zeka destekli ön değerlendirme.` : ''),
      };
    }
    return fhir[activeFhirResource] || {};
  }, [activeFhirResource, analysisResult, llmReport, radiologistApproval]);

  const switchTab = useCallback(
    (tabId) => {
      if (!tabId || tabId === activeTab) return;
      setActiveTab(tabId);
      setTabLoading(tabId);
      window.setTimeout(() => {
        setTabLoading((current) => (current === tabId ? null : current));
      }, MODULE_TRANSITION_MS);
    },
    [activeTab],
  );

  const applyCaseProfile = useCallback((libraryId) => {
    const profile = demoPatientProfiles[libraryId];
    if (!profile) return;
    setPatientName(profile.protocol);
    setPatientAge(profile.age);
    setPatientGender(profile.gender);
  }, []);

  useEffect(() => {
    if (!loading) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setAnalysisStepIndex((current) => Math.min(current + 1, analysisStages.length - 1));
    }, 620);

    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    const syncFullscreenState = () => {
      setIsViewerFullscreen(document.fullscreenElement === viewerShellRef.current);
    };

    document.addEventListener('fullscreenchange', syncFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState);
  }, []);

  useEffect(() => {
    const closeFallbackFullscreen = (event) => {
      if (event.key === 'Escape' && isViewerFullscreen && !document.fullscreenElement) {
        setIsViewerFullscreen(false);
      }
    };

    window.addEventListener('keydown', closeFallbackFullscreen);
    return () => window.removeEventListener('keydown', closeFallbackFullscreen);
  }, [isViewerFullscreen]);

  const updateCaseFilter = (key, value) => {
    setCaseFilters((current) => ({ ...current, [key]: value }));
  };

  const resetCaseFilters = () => {
    setCaseFilters(caseFilterDefaults);
  };

  const updateViewerZoom = (nextZoom) => {
    const clampedZoom = Math.round(clampNumber(nextZoom, VIEWER_MIN_ZOOM, VIEWER_MAX_ZOOM));
    setViewerZoom(clampedZoom);
    setViewerPan((current) => clampViewerPan(current, clampedZoom));
  };

  const adjustViewerZoom = (delta) => {
    setViewerZoom((current) => {
      const nextZoom = Math.round(clampNumber(current + delta, VIEWER_MIN_ZOOM, VIEWER_MAX_ZOOM));
      setViewerPan((pan) => clampViewerPan(pan, nextZoom));
      return nextZoom;
    });
  };

  const nudgeViewer = (axis, delta) => {
    setViewerPan((current) => clampViewerPan({ ...current, [axis]: current[axis] + delta }, viewerZoom));
  };

  const handleViewerWheel = (event) => {
    if (!analysisResult) return;
    event.preventDefault();
    adjustViewerZoom(event.deltaY > 0 ? -10 : 10);
  };

  const handleViewerPointerDown = (event) => {
    if (!analysisResult || event.button !== 0 || event.target.closest('.overlay-control-modern')) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    viewerDragRef.current = {
      active: true,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: viewerPan.x,
      originY: viewerPan.y,
    };
    setIsViewerDragging(true);
  };

  const handleViewerPointerMove = (event) => {
    const drag = viewerDragRef.current;
    if (!drag.active) return;
    event.preventDefault();
    setViewerPan(
      clampViewerPan(
        {
          x: drag.originX + event.clientX - drag.startX,
          y: drag.originY + event.clientY - drag.startY,
        },
        viewerZoom,
      ),
    );
  };

  const stopViewerDrag = (event) => {
    const drag = viewerDragRef.current;
    if (!drag.active) return;
    event.currentTarget.releasePointerCapture?.(drag.pointerId);
    viewerDragRef.current = { active: false, pointerId: null, startX: 0, startY: 0, originX: 0, originY: 0 };
    setIsViewerDragging(false);
  };

  const toggleViewerFullscreen = async () => {
    const element = viewerShellRef.current;
    if (!element) return;

    try {
      if (isViewerFullscreen) {
        if (!document.fullscreenElement) {
          setIsViewerFullscreen(false);
          return;
        }
        await document.exitFullscreen?.();
        return;
      }
      if (element.requestFullscreen) {
        await element.requestFullscreen();
        window.setTimeout(() => {
          if (!document.fullscreenElement) setIsViewerFullscreen(true);
        }, 120);
        return;
      }
      setIsViewerFullscreen(true);
    } catch {
      setIsViewerFullscreen(true);
    }
  };

  const resetViewer = () => {
    setViewerZoom(100);
    setViewerPan({ x: 0, y: 0 });
    setOverlayOpacity(82);
    setShowSegmentationOverlay(true);
  };

  const runAnalysis = useCallback(async (libraryId, file) => {
    setAnalysisStepIndex(0);
    setLoading(true);
    setErrorMessage('');
    setLlmReport('');
    setRadiologistApproval(null);
    setManualDraft('');
    setManualDraftKey('');

    try {
      const formData = new FormData();
      if (file) {
        formData.append('file', file);
      } else if (libraryId) {
        formData.append('library_id', libraryId);
      }

      const response = await fetch(`${API_BASE}/api/analyze`, {
        method: 'POST',
        body: formData,
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
      const data = await response.json();
      setAnalysisResult(repairDeep(data));
      setActiveTab('overview');
      setTabLoading(null);
    } catch (error) {
      console.error(error);
      setErrorMessage(
        error instanceof TypeError
          ? "Backend bağlantısı kurulamadı. FastAPI servisinin 127.0.0.1:8000 adresinde çalıştığını kontrol edin."
          : repairText(error.message),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLibrary = useCallback(async () => {
    setErrorMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/library`);
      if (!response.ok) throw new Error('Vaka kütüphanesi alınamadı.');
      const data = repairDeep(await response.json());
      setLibraryScans(data);
      if (data.length > 0 && isDemoMode) {
        setSelectedScanId(data[0].id);
        applyCaseProfile(data[0].id);
        await runAnalysis(data[0].id, null);
      }
    } catch (error) {
      console.error(error);
      setErrorMessage("Vaka kütüphanesi alınamadı. FastAPI backend'in çalıştığından emin olun.");
    }
  }, [applyCaseProfile, isDemoMode, runAnalysis]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadLibrary();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadLibrary]);

  const handleLibrarySelect = (event) => {
    const libraryId = event.target.value;
    setSelectedScanId(libraryId);
    if (libraryId) {
      applyCaseProfile(libraryId);
      runAnalysis(libraryId, null);
    }
  };

  const handleFileUpload = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setSelectedScanId('');
    runAnalysis(null, file);
    event.target.value = '';
  };

  const searchResults = useMemo(() => {
    const query = normalizeSearchText(searchQuery.trim());
    if (!query) return [];

    const caseResults = libraryScans
      .filter((scan) =>
        normalizeSearchText(`${scan.name || ''} ${scan.id || ''} ${scan.description || ''}`).includes(query),
      )
      .slice(0, 5)
      .map((scan) => ({
        type: 'case',
        id: scan.id,
        title: repairText(scan.name) || scan.id,
        detail: repairText(scan.description) || 'Demo vaka',
      }));

    const tabResults = workspaceTabs
      .filter((tab) => normalizeSearchText(tab.label).includes(query))
      .map((tab) => ({
        type: 'tab',
        id: tab.id,
        title: tab.label,
        detail: 'Modül sekmesine git',
      }));

    const reportResults = analysisResult
      ? [
          {
            type: 'tab',
            id: 'report',
            title: 'Klinik rapor',
            detail: `${patientName} rapor taslağı`,
          },
          {
            type: 'tab',
            id: 'fhir',
            title: 'FHIR çıktısı',
            detail: 'Patient, Observation ve DiagnosticReport',
          },
        ].filter((item) => normalizeSearchText(`${item.title} ${item.detail}`).includes(query))
      : [];

    return [...caseResults, ...tabResults, ...reportResults].slice(0, 7);
  }, [analysisResult, libraryScans, patientName, searchQuery]);

  const executeSearchResult = (result) => {
    if (!result) return;
    setSearchQuery('');
    if (result.type === 'case') {
      setSelectedScanId(result.id);
      applyCaseProfile(result.id);
      runAnalysis(result.id, null);
      return;
    }
    switchTab(result.id);
  };

  const handleSearchSubmit = (event) => {
    event.preventDefault();
    executeSearchResult(searchResults[0]);
  };

  const generateReport = async () => {
    if (!analysisResult) return;
    setGeneratingReport(true);
    setErrorMessage('');

    try {
      const response = await fetch(`${API_BASE}/api/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_name: patientName,
          age: patientAge,
          gender: patientGender,
          tumor_type: repairText(analysisResult.diagnosis_tr),
          volume: analysisResult.volume,
          sphericity: analysisResult.sphericity,
          molecular: analysisResult.molecular,
        }),
      });

      if (!response.ok) throw new Error('Rapor üretimi başarısız oldu.');
      const data = repairDeep(await response.json());
      setLlmReport(repairText(data.report));
    } catch (error) {
      console.error(error);
      setErrorMessage('Rapor üretilemedi. Backend rapor uç noktasını kontrol edin.');
    } finally {
      setGeneratingReport(false);
    }
  };

  const downloadReport = (format = 'txt') => {
    if (!draftReport) return;
    if (format === 'doc') {
      const safeName = patientName.replace(/\s+/g, '_');
      const html = buildReportHtml(`${patientName} Klinik Rapor`, getApprovalText(radiologistApproval), draftReport);
      downloadBlob(html, `${safeName}_Klinik_Rapor.doc`, 'application/msword;charset=utf-8');
      return;
    }
    const approvalText =
      radiologistApproval === 'approved'
        ? 'Radyolog Onayı: FINAL'
        : radiologistApproval === 'rejected'
          ? 'Radyolog Onayı: REVİZYON GEREKLİ'
          : 'Radyolog Onayı: TASLAK';
    const file = new Blob([`${approvalText}\n\n${draftReport}`], { type: 'text/plain' });
    const element = document.createElement('a');
    element.href = URL.createObjectURL(file);
    element.download = `${patientName.replace(/\s+/g, '_')}_Klinik_Rapor.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    URL.revokeObjectURL(element.href);
  };

  const printReportAsPdf = () => {
    if (!draftReport) return;
    const printWindow = window.open('', '_blank', 'width=900,height=720');
    if (!printWindow) return;
    printWindow.document.write(buildReportHtml(`${patientName} Klinik Rapor`, getApprovalText(radiologistApproval), draftReport));
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  };

  const renderScanFrame = () => {
    const originalSrc = imageSource(analysisResult, 'original');
    const overlaySrc = imageSource(analysisResult, 'overlay');
    const modeSrc = getImageModeSource(analysisResult, viewMode);

    if (!analysisResult || (!modeSrc && viewMode !== 'compare')) {
      return (
        <div className="scan-empty-art">
          <ImageIcon size={30} />
          <strong>MRG görüntüsü bekleniyor</strong>
          <span>Demo vaka seçin veya MRG yükleyin.</span>
        </div>
      );
    }

    if (viewMode === 'compare') {
      return (
        <div className="scan-compare">
          <figure>
            {originalSrc ? <img src={originalSrc} alt="Orijinal beyin MRG kesiti" style={viewerTransform} /> : null}
            <figcaption>Orijinal</figcaption>
          </figure>
          <figure>
            {overlaySrc ? <img src={overlaySrc} alt="Segmentasyon bindirmeli beyin MRG kesiti" style={viewerTransform} /> : null}
            <figcaption>Overlay</figcaption>
          </figure>
        </div>
      );
    }

    if (viewMode === 'overlay' && originalSrc && overlaySrc) {
      return (
        <div className="scan-stack scan-transform-layer" style={viewerTransform}>
          <img src={originalSrc} alt="Orijinal beyin MRG kesiti" />
          {showSegmentationOverlay ? (
            <img
              className="scan-overlay-layer"
              src={overlaySrc}
              alt="Segmentasyon bindirmesi"
              style={{ opacity: overlayOpacity / 100 }}
            />
          ) : null}
        </div>
      );
    }

    if (modeSrc) {
      return (
        <div className="scan-transform-layer" style={viewerTransform}>
          <img className="scan-single" src={modeSrc} alt="Beyin MRG analiz görünümü" />
        </div>
      );
    }

    return <img className="scan-single" src={modeSrc} alt="Beyin MRG analiz görünümü" />;
  };

  const renderMainTab = () => {
    if (loading) {
      return (
        <section className="product-card loading-card clinical-loader" aria-live="polite">
          <div className="loader-brain" aria-hidden="true">
            <svg viewBox="0 0 260 190" role="img">
              <path
                className="brain-fill"
                d="M87 151c-27-1-48-20-48-47 0-19 11-35 28-42 5-23 25-40 49-40 15 0 29 6 39 17 8-5 17-8 27-8 26 0 47 21 47 47 0 10-3 20-9 28 2 5 3 10 3 16 0 23-19 42-43 42-10 0-20-4-27-10-12 10-27 15-43 15-8 0-16-1-23-4Z"
              />
              <path
                className="brain-outline"
                d="M87 151c-27-1-48-20-48-47 0-19 11-35 28-42 5-23 25-40 49-40 15 0 29 6 39 17 8-5 17-8 27-8 26 0 47 21 47 47 0 10-3 20-9 28 2 5 3 10 3 16 0 23-19 42-43 42-10 0-20-4-27-10-12 10-27 15-43 15-8 0-16-1-23-4Z"
              />
              <path className="brain-fold fold-a" d="M88 59c20 6 31 19 31 39 0 16-8 28-24 36" />
              <path className="brain-fold fold-b" d="M143 44c-14 14-18 29-12 45 5 14 16 23 34 26" />
              <path className="brain-fold fold-c" d="M177 66c-17 9-25 22-23 38 2 15 12 27 29 35" />
              <path className="brain-fold fold-d" d="M69 92c15-2 27 3 35 14 8 12 9 25 2 39" />
              <path className="brain-lesion" d="M157 89c15-8 31 1 34 17 4 19-8 33-26 34-15 0-27-12-27-27 0-10 7-19 19-24Z" />
            </svg>
            <span className="brain-scan-beam" />
          </div>
          <div className="loader-copy">
            <span>Yapay zeka hattı hazırlanıyor</span>
            <strong>MRG analizi sürüyor</strong>
            <small>Ön işleme, segmentasyon ve klinik rapor verileri eş zamanlı işleniyor.</small>
          </div>
          <div className="loader-steps" aria-label="Analiz aşamaları">
            <i />
            <i />
            <i />
            <i />
          </div>
          <div className="analysis-current-stage">
            <span>{activeAnalysisStage.eyebrow}</span>
            <strong>{activeAnalysisStage.title}</strong>
            <small>{activeAnalysisStage.detail}</small>
          </div>
          <div className="analysis-stage-list" aria-label="Analiz aşamaları">
            {analysisStages.map((stage, index) => (
              <article
                className={index < analysisStepIndex ? 'done' : index === analysisStepIndex ? 'active' : ''}
                key={stage.eyebrow}
              >
                <span>{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <strong>{stage.eyebrow}</strong>
                  <small>{stage.title}</small>
                </div>
              </article>
            ))}
          </div>
        </section>
      );
    }

    if (tabLoading) {
      return <ModuleLoader tabId={tabLoading} />;
    }

    if (activeTab === 'pipeline') {
      const stages = [
        ['original', 'Orijinal kesit', 'Yüklenen veya seçilen ham MRG kesiti.'],
        ['stripped', 'Skull stripping', 'Beyin dışı dokular ayrıştırılır.'],
        ['corrected', 'Bias correction', 'Yoğunluk sapmaları dengelenir.'],
        ['normalized', 'Normalize kesit', 'Model girdisi standart aralığa alınır.'],
      ];

      return (
        <section className="product-card">
          <div className="product-section-title">
            <span>Ön işleme</span>
            <h2>MRG hazırlık adımları</h2>
          </div>
          <div className="stage-grid">
            {stages.map(([key, title, detail], index) => (
              <article className="stage-card" key={key}>
                <div className="stage-media">
                  {imageSource(analysisResult, key) ? (
                    <img src={imageSource(analysisResult, key)} alt={title} />
                  ) : (
                    <ImageIcon size={24} />
                  )}
                  <span>{String(index + 1).padStart(2, '0')}</span>
                </div>
                <strong>{title}</strong>
                <small>{detail}</small>
              </article>
            ))}
          </div>
        </section>
      );
    }

    if (activeTab === 'biopsy') {
      const molecular = analysisResult?.molecular || {};
      return (
        <div className="product-two-column">
          <section className="product-card">
            <div className="product-section-title">
              <span>Sanal biyopsi</span>
              <h2>Moleküler öngörü</h2>
            </div>
            <div className="marker-list">
              <div className="marker-row">
                <div>
                  <strong>IDH durumu</strong>
                  <small>{repairText(molecular.idh_status || 'Analiz bekleniyor')}</small>
                </div>
                <span>{formatPercent(toNumber(molecular.idh_mutant_prob))}</span>
                <i style={{ width: `${Math.min(100, toNumber(molecular.idh_mutant_prob) * 100)}%` }} />
              </div>
              <div className="marker-row">
                <div>
                  <strong>MGMT metilasyon</strong>
                  <small>{repairText(molecular.mgmt_status || 'Analiz bekleniyor')}</small>
                </div>
                <span>{formatPercent(toNumber(molecular.mgmt_methylated_prob))}</span>
                <i style={{ width: `${Math.min(100, toNumber(molecular.mgmt_methylated_prob) * 100)}%` }} />
              </div>
              </div>
          </section>
          <section className="product-card">
            <div className="product-section-title">
              <span>Radyomik</span>
              <h2>Öne çıkan özellikler</h2>
            </div>
            <div className="feature-list-modern">
              {features.length ? (
                features.map(([name, value]) => (
                  <div className="feature-chip" key={name}>
                    <strong>{formatFeatureName(name)}</strong>
                    <span>{formatter.format(toNumber(value))}</span>
                  </div>
                ))
              ) : (
                <p className="muted-copy">Analiz sonucu bekleniyor.</p>
              )}
            </div>
            {activeTab === 'xai' ? (
              <div className="xai-control-panel">
              <button
                className={showXaiHeatmap ? 'active' : ''}
                type="button"
                onClick={() => setShowXaiHeatmap((current) => !current)}
              >
                <Eye size={15} />
                <span>Heatmap</span>
              </button>
              <label>
                <SlidersHorizontal size={15} />
                <span>Yoğunluk</span>
                <input
                  type="range"
                  min="20"
                  max="100"
                  value={xaiHeatOpacity}
                  onChange={(event) => setXaiHeatOpacity(Number(event.target.value))}
                  aria-label="Grad-CAM yoğunluğu"
                />
                <strong>{xaiHeatOpacity}%</strong>
              </label>
              </div>
            ) : null}
          </section>
        </div>
      );
    }

    if (activeTab === 'xai') {
      const gradcamSrc = imageSource(analysisResult, 'gradcam');
      return (
        <div className="product-two-column">
          <section className="product-card">
            <div className="product-section-title">
              <span>Açıklanabilirlik</span>
              <h2>Grad-CAM odağı</h2>
            </div>
            <div className={`xai-frame ${showXaiHeatmap ? '' : 'heat-hidden'}`} style={{ '--xai-opacity': xaiHeatOpacity / 100 }}>
              {gradcamSrc ? (
                <img src={imageSource(analysisResult, 'gradcam')} alt="Grad-CAM ısı haritası" />
              ) : (
                <div className="scan-empty-art compact">
                  <Eye size={26} />
                  <strong>Isı haritası bekleniyor</strong>
                </div>
              )}
            </div>
            <div className="xai-control-panel">
              <button
                className={showXaiHeatmap ? 'active' : ''}
                type="button"
                onClick={() => setShowXaiHeatmap((current) => !current)}
              >
                <Eye size={15} />
                <span>Heatmap</span>
              </button>
              <label>
                <SlidersHorizontal size={15} />
                <span>Yoğunluk</span>
                <input
                  type="range"
                  min="20"
                  max="100"
                  value={xaiHeatOpacity}
                  onChange={(event) => setXaiHeatOpacity(Number(event.target.value))}
                  aria-label="Grad-CAM yoğunluğu"
                />
                <strong>{xaiHeatOpacity}%</strong>
              </label>
            </div>
          </section>
          <section className="product-card">
            <div className="product-section-title">
              <span>Model yorumu</span>
              <h2>Kararı etkileyen sinyaller</h2>
            </div>
            <div className="probability-list-modern">
              {probabilities.length ? (
                probabilities.map(([label, value]) => (
                  <div className="probability-row" key={label}>
                    <div>
                      <span>{repairText(label)}</span>
                      <strong>{formatter.format(toNumber(value))}%</strong>
                    </div>
                    <i style={{ width: `${Math.min(100, toNumber(value))}%` }} />
                  </div>
                ))
              ) : (
                <p className="muted-copy">Sınıflandırma skorları analizden sonra görünür.</p>
              )}
            </div>
          </section>
        </div>
      );
    }

    if (activeTab === 'report') {
      return (
        <section className="product-card">
          <div className="product-section-title action-title">
            <div>
              <span>Raporlama</span>
              <h2>Klinik rapor taslağı</h2>
            </div>
            <div className="workspace-button-row">
              <button className="workspace-primary" type="button" onClick={generateReport} disabled={!analysisResult || generatingReport}>
                {generatingReport ? <RefreshCw className="spin" size={16} /> : <FileText size={16} />}
                {generatingReport ? 'Üretiliyor' : 'Rapor üret'}
              </button>
              <button className="workspace-secondary" type="button" onClick={downloadReport} disabled={!draftReport}>
                <Download size={16} />
                İndir
              </button>
              <button className="workspace-secondary" type="button" onClick={() => downloadReport('doc')} disabled={!draftReport}>
                <FileText size={16} />
                Word
              </button>
              <button className="workspace-secondary" type="button" onClick={printReportAsPdf} disabled={!draftReport}>
                <Printer size={16} />
                PDF
              </button>
            </div>
          </div>

          <div className="approval-row-modern">
            <button
              className={radiologistApproval === 'approved' ? 'active success' : ''}
              type="button"
              onClick={() => setRadiologistApproval('approved')}
            >
              <CheckCircle size={17} />
              Onayla
            </button>
            <button
              className={radiologistApproval === 'rejected' ? 'active danger' : ''}
              type="button"
              onClick={() => setRadiologistApproval('rejected')}
            >
              <AlertTriangle size={17} />
              Revizyon gerekli
            </button>
          </div>

          <div className="report-summary-grid">
            {reportSections.map((section) => (
              <article key={section.title}>
                <h3>{section.title}</h3>
                <dl>
                  {section.rows.map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>

          <textarea
            className="report-textarea"
            value={draftReport}
            onChange={(event) => {
              setManualDraftKey(draftSourceKey);
              setManualDraft(event.target.value);
            }}
            placeholder="Analiz sonucu geldiğinde rapor taslağı burada oluşur."
          />
        </section>
      );
    }

    if (activeTab === 'fhir') {
      const summaryRows = getFhirSummary(fhirResource, activeFhirResource);
      return (
        <section className="product-card">
          <div className="product-section-title">
            <span>HL7 FHIR R4</span>
            <h2>Yapılandırılmış çıktı</h2>
          </div>
          <div className="resource-tabs-modern" role="tablist" aria-label="FHIR kaynakları">
            {fhirOptions.map((option) => (
              <button
                className={activeFhirResource === option.id ? 'active' : ''}
                key={option.id}
                type="button"
                onClick={() => setActiveFhirResource(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="fhir-summary-modern">
            {summaryRows.map(([label, value]) => (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </div>
          <pre className="fhir-code-modern">{JSON.stringify(repairDeep(fhirResource), null, 2)}</pre>
        </section>
      );
    }

    return (
      <>
        <div className="overview-row">
          <MetricCard
            icon={Activity}
            label="Ön tanı"
            value={analysisResult ? repairText(analysisResult.diagnosis_tr) : 'Analiz bekliyor'}
            detail={analysisResult ? `${formatter.format(toNumber(analysisResult.confidence))}% güven` : 'MRG seçin veya yükleyin'}
            tone={diagnosisTone}
          />
          <MetricCard
            icon={Layers}
            label="Hacim"
            value={analysisResult ? formatNumber(analysisResult.volume, ' cm³') : '-'}
            detail="ResUNet segmentasyonu"
            tone="info"
          />
          <MetricCard
            icon={Calendar}
            label="Takip"
            value={risk.followUp}
            detail={risk.label}
            tone={risk.tone}
          />
        </div>

        <section className="scan-decision-grid">
          <div className={`product-card scan-card ${isViewerFullscreen ? 'viewer-fullscreen-card' : ''}`} ref={viewerShellRef}>
            <div className="product-section-title action-title">
              <div>
                <span>MRG inceleme</span>
                <h2>Görüntü çalışma alanı</h2>
              </div>
              <div className="view-mode-tabs" role="tablist" aria-label="Görüntü modu">
                {viewModes.map((mode) => (
                  <button
                    className={viewMode === mode.id ? 'active' : ''}
                    key={mode.id}
                    type="button"
                    onClick={() => setViewMode(mode.id)}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="viewer-control-bar" aria-label="MRG görüntü kontrolleri">
              <button
                className={showSegmentationOverlay ? 'active' : ''}
                type="button"
                onClick={() => setShowSegmentationOverlay((current) => !current)}
                title="Overlay aç/kapat"
              >
                <Layers size={15} />
                <span>Overlay</span>
              </button>
              <button type="button" onClick={() => adjustViewerZoom(-10)} title="Uzaklaştır">
                <ZoomOut size={15} />
              </button>
              <input
                type="range"
                min={VIEWER_MIN_ZOOM}
                max={VIEWER_MAX_ZOOM}
                value={viewerZoom}
                onChange={(event) => updateViewerZoom(Number(event.target.value))}
                aria-label="Görüntü yakınlaştırma"
              />
              <strong>{viewerZoom}%</strong>
              <button type="button" onClick={() => adjustViewerZoom(10)} title="Yakınlaştır">
                <ZoomIn size={15} />
              </button>
              <div className="viewer-pan-cluster" aria-label="Görüntü kaydırma">
                <button type="button" onClick={() => nudgeViewer('y', 18)} title="Yukarı kaydır">
                  <MoveUp size={14} />
                </button>
                <button type="button" onClick={() => nudgeViewer('x', 18)} title="Sola kaydır">
                  <MoveLeft size={14} />
                </button>
                <button type="button" onClick={() => nudgeViewer('x', -18)} title="Sağa kaydır">
                  <MoveRight size={14} />
                </button>
                <button type="button" onClick={() => nudgeViewer('y', -18)} title="Aşağı kaydır">
                  <MoveDown size={14} />
                </button>
              </div>
              <button type="button" onClick={resetViewer} title="Görüntüyü sıfırla">
                <RotateCcw size={15} />
              </button>
              <button type="button" onClick={toggleViewerFullscreen} title={isViewerFullscreen ? 'Tam ekrandan çık' : 'Tam ekran'}>
                {isViewerFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
            </div>
            <div
              className={`scan-modern-frame ${isViewerDragging ? 'is-dragging' : ''}`}
              onPointerDown={handleViewerPointerDown}
              onPointerMove={handleViewerPointerMove}
              onPointerUp={stopViewerDrag}
              onPointerCancel={stopViewerDrag}
              onWheel={handleViewerWheel}
            >
              {renderScanFrame()}
              {analysisResult && viewMode === 'overlay' && showSegmentationOverlay ? (
                <div className="overlay-control-modern">
                  <span>Overlay</span>
                  <input
                    type="range"
                    min="35"
                    max="100"
                    value={overlayOpacity}
                    onChange={(event) => setOverlayOpacity(Number(event.target.value))}
                    aria-label="Overlay opaklığı"
                  />
                  <strong>{overlayOpacity}%</strong>
                </div>
              ) : null}
            </div>
          </div>

          <section className="product-card decision-modern">
            <div className="product-section-title">
              <span>Karar özeti</span>
              <h2>{analysisResult ? repairText(analysisResult.predicted_tumor_type) : 'Vaka seçilmedi'}</h2>
            </div>
            <StatusPill tone={risk.tone}>{risk.label}</StatusPill>
            <p>{risk.note}</p>
            <div className="probability-list-modern">
              {probabilities.length ? (
                probabilities.map(([label, value]) => (
                  <div className="probability-row" key={label}>
                    <div>
                      <span>{repairText(label)}</span>
                      <strong>{formatter.format(toNumber(value))}%</strong>
                    </div>
                    <i style={{ width: `${Math.min(100, toNumber(value))}%` }} />
                  </div>
                ))
              ) : (
                <p className="muted-copy">Diferansiyel tanı skorları analiz sonrası burada görünür.</p>
              )}
            </div>
          </section>
        </section>
      </>
    );
  };

  return (
    <main className="product-shell">
      <header className="product-topbar">
        <div className="workspace-brand">
          <strong>NeuroOncoTrack-AI</strong>
          <span>Klinik çalışma alanı</span>
        </div>
        <form className="workspace-search" onSubmit={handleSearchSubmit}>
          <Search size={17} />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                executeSearchResult(searchResults[0]);
              }
            }}
            placeholder="Vaka, protokol veya rapor ara"
            aria-label="Vaka, protokol veya rapor ara"
          />
          {searchQuery ? (
            <div className="search-results-panel">
              {searchResults.length ? (
                searchResults.map((result) => (
                  <button
                    key={`${result.type}-${result.id}`}
                    type="button"
                    onClick={() => executeSearchResult(result)}
                  >
                    <span>{result.title}</span>
                    <small>{result.detail}</small>
                  </button>
                ))
              ) : (
                <p>Sonuç bulunamadı</p>
              )}
            </div>
          ) : null}
        </form>
        <div className="workspace-actions">
          <ThemeToggle theme={theme} setTheme={setTheme} />
          <div className="user-chip">
            <span>K</span>
            <div>
              <strong>Klinik kullanıcı</strong>
              <small>{isDemoMode ? 'Demo oturumu' : 'Kurum oturumu'}</small>
            </div>
          </div>
          <button className="logout-action" type="button" onClick={onLogout}>
            <LogOut size={17} />
            Çıkış
          </button>
        </div>
      </header>

      <div className="product-grid">
        <aside className="product-sidebar" aria-label="Klinik navigasyon">
          <label className="upload-tile">
            <Upload size={18} />
            <span>MRG yükle</span>
            <input type="file" accept="image/*" onChange={handleFileUpload} disabled={loading} />
          </label>

          <section className={`case-filter-panel ${isCaseFilterOpen ? 'open' : ''}`} aria-label="Vaka filtresi">
            <button
              className="case-filter-toggle"
              type="button"
              onClick={() => setIsCaseFilterOpen((current) => !current)}
              aria-expanded={isCaseFilterOpen}
            >
              <SlidersHorizontal size={15} />
              <span>Filtreler</span>
              <small>{filteredLibraryScans.length} vaka</small>
            </button>
            <div>
              <span>Vaka filtresi</span>
              <button type="button" onClick={resetCaseFilters}>
                Sıfırla
              </button>
            </div>
            <select value={caseFilters.diagnosis} onChange={(event) => updateCaseFilter('diagnosis', event.target.value)}>
              <option value="all">Tüm tanılar</option>
              <option value="meningioma">Meningiyom</option>
              <option value="glioma">Gliom</option>
              <option value="tumor">Diğer tümör</option>
              <option value="healthy">Sağlıklı</option>
            </select>
            <select value={caseFilters.gender} onChange={(event) => updateCaseFilter('gender', event.target.value)}>
              <option value="all">Tüm cinsiyetler</option>
              <option value="female">Kadın</option>
              <option value="male">Erkek</option>
            </select>
            <select value={caseFilters.age} onChange={(event) => updateCaseFilter('age', event.target.value)}>
              <option value="all">Tüm yaşlar</option>
              <option value="under40">40 altı</option>
              <option value="40to59">40-59</option>
              <option value="60plus">60 ve üzeri</option>
            </select>
            <small>{filteredLibraryScans.length} vaka listeleniyor</small>
          </section>

          <label className="workspace-field">
            <span>Vaka kütüphanesi</span>
            <select value={selectedScanId} onChange={handleLibrarySelect} disabled={loading}>
              <option value="">Kendi görüntüm</option>
              {libraryOptions.map((scan) => (
                <option key={scan.id} value={scan.id}>
                  {repairText(scan.name) || scan.id}
                </option>
              ))}
              {!libraryOptions.length ? <option disabled>Filtreye uygun vaka yok</option> : null}
            </select>
          </label>

          <div className="workspace-patient-grid">
            <label className="workspace-field">
              <span>Protokol</span>
              <input value={patientName} onChange={(event) => setPatientName(event.target.value)} />
            </label>
            <label className="workspace-field">
              <span>Yaş</span>
              <input
                type="number"
                min="0"
                value={patientAge}
                onChange={(event) => setPatientAge(Number.parseInt(event.target.value, 10) || 0)}
              />
            </label>
            <label className="workspace-field">
              <span>Cinsiyet</span>
              <select value={patientGender} onChange={(event) => setPatientGender(event.target.value)}>
                <option value="female">Kadın</option>
                <option value="male">Erkek</option>
              </select>
            </label>
          </div>

          <nav className="workspace-tab-list" aria-label="Ürün modülleri">
            {workspaceTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  className={activeTab === tab.id ? 'active' : ''}
                  key={tab.id}
                  type="button"
                  onClick={() => switchTab(tab.id)}
                >
                  <Icon size={17} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>

          <section className="sidebar-panel">
            <span>Sistem</span>
            <dl>
              <dt>Backend</dt>
              <dd>{errorMessage ? 'Bekleniyor' : 'Aktif'}</dd>
              <dt>Aktif vaka</dt>
              <dd>{selectedScan ? repairText(selectedScan.name) : selectedScanId || 'Yüklenen görüntü'}</dd>
              <dt>Veri modu</dt>
              <dd>{isDemoMode ? 'Demo' : selectedScanId ? 'Kütüphane' : 'Yükleme'}</dd>
              <dt>API</dt>
              <dd>127.0.0.1:8000</dd>
            </dl>
          </section>
        </aside>

        <section className="product-main">
          {errorMessage ? (
            <div className="workspace-alert">
              <AlertTriangle size={17} />
              <span>{errorMessage}</span>
              <button type="button" onClick={loadLibrary}>
                Yeniden dene
              </button>
            </div>
          ) : null}
          {renderMainTab()}
        </section>
      </div>
    </main>
  );
}
