import { Activity, Database, Eye, FileText, FlaskConical, Settings } from 'lucide-react';

export const API_BASE = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';
export const API_V1_BASE = `${API_BASE}/api/v1`;
export const AI_SERVICE_BASE = import.meta.env.VITE_AI_SERVICE_URL || 'http://127.0.0.1:8100';
export const API_MODE = import.meta.env.VITE_API_MODE || 'contract';

export const MIN_ANALYSIS_LOADER_MS = 1850;
export const REAL_SESSION_MINUTES = 30;
export const DEMO_SESSION_HOURS = 8;
export const IDLE_WARNING_MINUTES = 2;

export const permissions = {
  patientCreate: 'patient:create',
  patientRead: 'patient:read',
  patientUpdate: 'patient:update',
  studyUpload: 'study:upload',
  studyRead: 'study:read',
  studyDownload: 'study:download',
  aiRunSegmentation: 'ai:run_segmentation',
  aiRunBiopsy: 'ai:run_biopsy',
  aiRunXai: 'ai:run_xai',
  aiViewResult: 'ai:view_result',
  aiOverride: 'ai:override',
  modelListVersions: 'model:list_versions',
  reportGenerate: 'report:generate',
  reportRead: 'report:read',
  reportEditDraft: 'report:edit_draft',
  reportApprove: 'report:approve',
  reportSign: 'report:sign',
  reportExportPdf: 'report:export_pdf',
  fhirRead: 'fhir:read',
  fhirWrite: 'fhir:write',
  fhirSync: 'fhir:sync',
  auditMyActivity: 'audit:read',
};

export const DEFAULT_CLINICAL_PERMISSIONS = [
  permissions.patientCreate,
  permissions.patientRead,
  permissions.patientUpdate,
  permissions.studyUpload,
  permissions.studyRead,
  permissions.studyDownload,
  permissions.aiRunSegmentation,
  permissions.aiRunBiopsy,
  permissions.aiRunXai,
  permissions.aiViewResult,
  permissions.aiOverride,
  permissions.modelListVersions,
  permissions.reportGenerate,
  permissions.reportRead,
  permissions.reportEditDraft,
  permissions.reportApprove,
  permissions.reportSign,
  permissions.reportExportPdf,
  permissions.fhirRead,
  permissions.fhirWrite,
  permissions.fhirSync,
  permissions.auditMyActivity,
];

export const DEFAULT_CLINICAL_USER = {
  id: 'clinical-demo-user',
  name: 'Sistem Yöneticisi',
  title: 'Demo Admin Kullanıcısı',
  role: 'ADMIN',
  email: 'admin@neurooncotrack.ai',
  institutionCode: 'NOT-2026',
  organization: 'NeuroOncoTrack Klinik Çalışma Alanı',
  permissions: ['*'], // Admin tüm izinlere sahip
};

export const capabilities = [
  { icon: Eye, label: 'MRG görüntüleme', value: 'T1 / T1c / T2 / FLAIR' },
  { icon: FlaskConical, label: 'Sanal biyopsi', value: 'IDH ve MGMT öngörüsü' },
  { icon: FileText, label: 'Klinik rapor', value: 'WHO 2021 uyumlu taslak' },
];

export const loginMetrics = [
  { label: 'Macro F1', value: '0.874' },
  { label: 'FHIR', value: 'R4' },
  { label: 'Sekans', value: '4 modalite' },
];

export const workspaceTabs = [
  { id: 'overview', label: 'Klinik görünüm', icon: Activity, permission: permissions.aiViewResult },
  { id: 'pipeline', label: 'Ön işleme', icon: Settings, permission: permissions.studyRead },
  { id: 'biopsy', label: 'Sanal biyopsi', icon: FlaskConical, permission: permissions.aiRunBiopsy },
  { id: 'xai', label: 'Açıklanabilirlik', icon: Eye, permission: permissions.aiRunXai },
  { id: 'report', label: 'Klinik rapor', icon: FileText, permission: permissions.reportRead },
  { id: 'fhir', label: 'FHIR çıktısı', icon: Database, permission: permissions.fhirRead },
];

export const moduleLoaderText = {
  overview: {
    eyebrow: 'Klinik görünüm',
    title: 'Karar ekranı hazırlanıyor',
    detail: 'MRG, ön tanı ve takip özeti klinik görünüme yerleşiyor.',
  },
  pipeline: {
    eyebrow: 'Ön işleme',
    title: 'MRG hattı düzenleniyor',
    detail: 'Skull stripping, bias correction ve normalizasyon adımları hazırlanıyor.',
  },
  biopsy: {
    eyebrow: 'Sanal biyopsi',
    title: 'Moleküler imza taranıyor',
    detail: 'IDH ve MGMT olasılıkları radyomik özelliklerle eşleştiriliyor.',
  },
  xai: {
    eyebrow: 'Açıklanabilirlik',
    title: 'Isı haritası oluşturuluyor',
    detail: 'Modelin karar odağı Grad-CAM ve sınıflandırma skorlarıyla hazırlanıyor.',
  },
  report: {
    eyebrow: 'Klinik rapor',
    title: 'Rapor alanı açılıyor',
    detail: 'Bulgular, moleküler sonuçlar ve takip önerileri rapor şablonuna aktarılıyor.',
  },
  fhir: {
    eyebrow: 'FHIR çıktısı',
    title: 'Kaynaklar yapılandırılıyor',
    detail: 'Patient, Observation ve DiagnosticReport kaynakları senkronize ediliyor.',
  },
};

export const MODULE_TRANSITION_MS = 1350;
export const VIEWER_MIN_ZOOM = 60;
export const VIEWER_MAX_ZOOM = 240;

export const analysisStages = [
  {
    eyebrow: 'Ön işleme',
    title: 'Kesit hazırlanıyor',
    detail: 'Görüntü standardizasyonu ve gürültü azaltma adımları başlatıldı.',
  },
  {
    eyebrow: 'Segmentasyon',
    title: 'Lezyon sınırı çıkarılıyor',
    detail: 'ResUNet hattı olası tümör alanını ve hacim bilgisini hazırlıyor.',
  },
  {
    eyebrow: 'Sanal biyopsi',
    title: 'Moleküler imza okunuyor',
    detail: 'IDH ve MGMT olasılıkları radyomik özelliklerle eşleştiriliyor.',
  },
  {
    eyebrow: 'Klinik rapor',
    title: 'Karar özeti derleniyor',
    detail: 'Diferansiyel tanı, takip önerisi ve FHIR çıktısı eş zamanlı hazırlanıyor.',
  },
];

export const caseFilterDefaults = {
  diagnosis: 'all',
  gender: 'all',
  age: 'all',
};

export const viewModes = [
  { id: 'overlay', label: 'Overlay' },
  { id: 'gradcam', label: 'Grad-CAM' },
  { id: 'compare', label: 'Karşılaştır' },
];

export const fhirOptions = [
  { id: 'patient', label: 'Patient' },
  { id: 'imaging_study', label: 'ImagingStudy' },
  { id: 'observations', label: 'Observation' },
  { id: 'diagnostic_report', label: 'DiagnosticReport' },
  { id: 'care_plan', label: 'CarePlan' },
];

export const demoPatientProfiles = {
  'Meningiyom_Referans.jpg': { protocol: 'NOT-2026-MEN-0142', age: 54, gender: 'female' },
  'Tumor_Vakasi_1.jpg': { protocol: 'NOT-2026-GLI-0881', age: 47, gender: 'male' },
  'Tumor_Vakasi_2.jpg': { protocol: 'NOT-2026-MEN-0317', age: 61, gender: 'female' },
  'Tumor_Vakasi_3.jpg': { protocol: 'NOT-2026-MIX-1190', age: 39, gender: 'male' },
  'Saglikli_Beyin_1.jpg': { protocol: 'NOT-2026-KON-0208', age: 33, gender: 'female' },
  'Saglikli_Beyin_2.jpg': { protocol: 'NOT-2026-KON-0464', age: 29, gender: 'male' },
};

export const formatter = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
