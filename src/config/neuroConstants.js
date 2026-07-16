import { Activity, Database, Eye, FileText, FlaskConical, Settings } from 'lucide-react';

export const API_BASE = 'http://127.0.0.1:8000';

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
  { id: 'overview', label: 'Klinik görünüm', icon: Activity },
  { id: 'pipeline', label: 'Ön işleme', icon: Settings },
  { id: 'biopsy', label: 'Sanal biyopsi', icon: FlaskConical },
  { id: 'xai', label: 'Açıklanabilirlik', icon: Eye },
  { id: 'report', label: 'Klinik rapor', icon: FileText },
  { id: 'fhir', label: 'FHIR çıktısı', icon: Database },
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
