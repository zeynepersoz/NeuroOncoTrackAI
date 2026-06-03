import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Cpu,
  Database,
  Download,
  Eye,
  FileText,
  FlaskConical,
  Image as ImageIcon,
  Moon,
  RefreshCw,
  Settings,
  ShieldAlert,
  Sun,
  Upload,
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';

const CP1254_BYTE_MAP = {
  '€': 0x80,
  '‚': 0x82,
  'ƒ': 0x83,
  '„': 0x84,
  '…': 0x85,
  '†': 0x86,
  '‡': 0x87,
  'ˆ': 0x88,
  '‰': 0x89,
  'Š': 0x8a,
  '‹': 0x8b,
  'Œ': 0x8c,
  'Ž': 0x8e,
  '‘': 0x91,
  '’': 0x92,
  '“': 0x93,
  '”': 0x94,
  '•': 0x95,
  '–': 0x96,
  '—': 0x97,
  '˜': 0x98,
  '™': 0x99,
  'š': 0x9a,
  '›': 0x9b,
  'œ': 0x9c,
  'ž': 0x9e,
  'Ÿ': 0x9f,
  'Ğ': 0xd0,
  'İ': 0xdd,
  'Ş': 0xde,
  'ğ': 0xf0,
  'ı': 0xfd,
  'ş': 0xfe,
};

const LIBRARY_LABELS = {
  'Meningiyom_Referans.jpg': 'Referans meningiyom vakası',
  'Tumor_Vakasi_1.jpg': 'Gliom vakası - agresif örnek',
  'Tumor_Vakasi_2.jpg': 'Meningiyom vakası - benign örnek',
  'Tumor_Vakasi_3.jpg': 'Gliom / hipofiz ayırıcı tanı örneği',
  'Saglikli_Beyin_1.jpg': 'Sağlıklı beyin kesiti 1',
  'Saglikli_Beyin_2.jpg': 'Sağlıklı beyin kesiti 2',
};

const NAV_GROUPS = [
  {
    label: 'Klinik Akış',
    items: [
      { id: 'dashboard', label: 'Klinik görünüm', icon: Activity },
      { id: 'pipeline', label: 'Ön işleme', icon: Settings },
      { id: 'biopsy', label: 'Sanal biyopsi', icon: FlaskConical },
    ],
  },
  {
    label: 'Model İncelemesi',
    items: [{ id: 'xai', label: 'Açıklanabilirlik', icon: Eye }],
  },
  {
    label: 'Dokümantasyon',
    items: [
      { id: 'report', label: 'Klinik rapor', icon: FileText },
      { id: 'fhir', label: 'FHIR çıktısı', icon: Database },
    ],
  },
];

const FHIR_OPTIONS = [
  { id: 'patient', label: 'Patient' },
  { id: 'imaging_study', label: 'ImagingStudy' },
  { id: 'observations', label: 'Observation' },
  { id: 'diagnostic_report', label: 'DiagnosticReport' },
  { id: 'care_plan', label: 'CarePlan' },
];

const VIEW_MODES = [
  { id: 'overlay', label: 'Overlay' },
  { id: 'original', label: 'Orijinal' },
  { id: 'gradcam', label: 'Grad-CAM' },
  { id: 'compare', label: 'Karşılaştır' },
];

const formatter = new Intl.NumberFormat('tr-TR', {
  maximumFractionDigits: 2,
});

function getInitialTheme() {
  if (typeof window === 'undefined') return 'light';
  const storedTheme = window.localStorage.getItem('neuro-theme');
  if (storedTheme === 'dark' || storedTheme === 'light') return storedTheme;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function repairText(value) {
  if (typeof value !== 'string' || !/[ÃÄÅÂğŸ]/.test(value)) {
    return value ?? '';
  }

  const bytes = [];
  for (const character of value) {
    const code = character.charCodeAt(0);
    const byte = CP1254_BYTE_MAP[character] ?? (code <= 0xff ? code : null);
    if (byte === null) {
      return value;
    }
    bytes.push(byte);
  }

  const decoded = new TextDecoder('utf-8').decode(new Uint8Array(bytes));
  return decoded.includes('�') ? value : decoded;
}

function repairDeep(value) {
  if (typeof value === 'string') {
    return repairText(value);
  }
  if (Array.isArray(value)) {
    return value.map(repairDeep);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [repairText(key), repairDeep(item)]),
    );
  }
  return value;
}

function getLibraryName(scan) {
  return LIBRARY_LABELS[scan.id] || repairText(scan.name) || scan.id;
}

function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function formatNumber(value, suffix = '') {
  return `${formatter.format(toNumber(value))}${suffix}`;
}

function formatPercent(value) {
  return `${formatter.format(toNumber(value) * 100)}%`;
}

function imageSource(result, key) {
  const image = result?.images?.[key];
  return image ? `data:image/jpeg;base64,${image}` : '';
}

function diagnosisTone(result) {
  const type = result?.predicted_tumor_type;
  if (type === 'notumor') return 'success';
  if (type === 'glioma') return 'danger';
  if (type === 'meningioma') return 'warning';
  return 'info';
}

function getRiskPlan(result) {
  if (!result) {
    return {
      tone: 'info',
      label: 'Bekliyor',
      followUp: '-',
      note: 'Analiz sonucu alındığında takip önerisi burada görünür.',
    };
  }

  const type = result.predicted_tumor_type;
  const molecular = result.molecular || {};
  const idh = repairText(molecular.idh_status || '').toLocaleUpperCase('tr-TR');
  const mgmt = repairText(molecular.mgmt_status || '').toLocaleUpperCase('tr-TR');

  if (type === 'notumor') {
    return {
      tone: 'success',
      label: 'Patolojik risk izlenmedi',
      followUp: '12 ay',
      note: 'Rutin klinik izlem ve gerekirse karşılaştırmalı MRG önerilir.',
    };
  }

  if (type === 'glioma' && idh.includes('WILD') && mgmt.includes('NON')) {
    return {
      tone: 'danger',
      label: 'Yüksek moleküler risk',
      followUp: '2 hafta',
      note: 'MDT değerlendirmesi ve tedavi planlaması önceliklendirilmelidir.',
    };
  }

  if (type === 'glioma' && idh.includes('MUTANT') && mgmt.includes('MET')) {
    return {
      tone: 'success',
      label: 'Düşük moleküler risk',
      followUp: '3 ay',
      note: 'Tedavi yanıtı ve stabilite için kontrollü takip planı uygundur.',
    };
  }

  return {
    tone: 'warning',
    label: 'Orta klinik risk',
    followUp: '6 hafta',
    note: 'Hacim, morfoloji ve klinik bulgular birlikte izlenmelidir.',
  };
}

function formatFeatureName(name) {
  return repairText(name)
    .replace(/^Original_/i, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toLocaleUpperCase('tr-TR'));
}

function getImageModeSource(result, mode) {
  if (mode === 'original') return imageSource(result, 'original');
  if (mode === 'gradcam') return imageSource(result, 'gradcam');
  if (mode === 'normalized') return imageSource(result, 'normalized');
  return imageSource(result, 'overlay');
}

function getStructuredReportSections(result, patientName, patientAge, patientGender, approval) {
  const risk = getRiskPlan(result);
  const molecular = result.molecular || {};
  const isGlioma = result.predicted_tumor_type === 'glioma';
  const genderLabel = patientGender === 'female' ? 'Kadın' : 'Erkek';
  const approvalLabel =
    approval === 'approved' ? 'FINAL' : approval === 'rejected' ? 'REVİZYON GEREKLİ' : 'TASLAK';

  return [
    {
      title: 'Hasta ve Çalışma',
      rows: [
        ['Protokol', patientName],
        ['Yaş / Cinsiyet', `${patientAge} / ${genderLabel}`],
        ['Çalışma', repairText(result.image_name || 'MRG kesiti')],
        ['Rapor Durumu', approvalLabel],
      ],
    },
    {
      title: 'AI Bulguları',
      rows: [
        ['Ön Tanı', repairText(result.diagnosis_tr)],
        ['Güven', `${formatter.format(toNumber(result.confidence))}%`],
        ['Hacim', formatNumber(result.volume, ' cm³')],
        ['Sferisite', formatter.format(toNumber(result.sphericity))],
      ],
    },
    {
      title: isGlioma ? 'Moleküler Öngörü' : 'Moleküler Durum',
      rows: isGlioma
        ? [
            ['IDH', `${repairText(molecular.idh_status || '-')} (${formatPercent(toNumber(molecular.idh_mutant_prob))})`],
            [
              'MGMT',
              `${repairText(molecular.mgmt_status || '-')} (${formatPercent(toNumber(molecular.mgmt_methylated_prob))})`,
            ],
          ]
        : [['Not', 'IDH/MGMT paneli bu sınıflandırma için endike değil.']],
    },
    {
      title: 'İzlem',
      rows: [
        ['Risk', risk.label],
        ['Kontrol', risk.followUp],
        ['Klinik Not', risk.note],
      ],
    },
  ];
}

function buildReportDraft(result, patientName, patientAge, patientGender, approval) {
  const sections = getStructuredReportSections(result, patientName, patientAge, patientGender, approval);
  return sections
    .map(
      (section) =>
        `${section.title}\n${section.rows.map(([label, value]) => `- ${label}: ${value}`).join('\n')}`,
    )
    .join('\n\n');
}

function getFhirSummary(resource, activeResource) {
  const repaired = repairDeep(resource);
  if (Array.isArray(repaired)) {
    return [
      ['Kaynak', FHIR_OPTIONS.find((option) => option.id === activeResource)?.label || activeResource],
      ['Kayıt Sayısı', repaired.length],
      ['ID Listesi', repaired.map((item) => item.id || item.resourceType || '-').join(', ') || '-'],
    ];
  }

  if (!repaired || typeof repaired !== 'object') {
    return [['Durum', 'Kaynak bulunamadı']];
  }

  const coding =
    repaired.code?.coding?.[0]?.display ||
    repaired.type?.coding?.[0]?.display ||
    repaired.category?.[0]?.coding?.[0]?.display ||
    '-';

  return [
    ['Resource Type', repaired.resourceType || '-'],
    ['ID', repaired.id || '-'],
    ['Status', repaired.status || repaired.clinicalStatus?.text || '-'],
    ['Kod / Tip', coding],
    ['Özet', repaired.conclusion || repaired.description || repaired.name?.[0]?.text || '-'],
  ];
}

function SectionHeader({ eyebrow, title, actions }) {
  return (
    <div className="section-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {actions ? <div className="section-actions">{actions}</div> : null}
    </div>
  );
}

function StatusPill({ tone = 'info', children }) {
  return <span className={`status-pill tone-${tone}`}>{children}</span>;
}

function StatCard({ icon: Icon, label, value, detail, tone = 'neutral' }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <div className="stat-icon">
        <Icon size={18} />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        {detail ? <small>{detail}</small> : null}
      </div>
    </article>
  );
}

function MetricBar({ label, value, tone = 'info' }) {
  const width = Math.max(0, Math.min(100, toNumber(value)));

  return (
    <div className="metric-bar">
      <div className="metric-row">
        <span>{repairText(label)}</span>
        <strong>{formatter.format(width)}%</strong>
      </div>
      <div className="progress-track" aria-hidden="true">
        <span className={`progress-fill tone-${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function ImagePanel({ title, subtitle, src, alt, actions, customFrame = false, children }) {
  return (
    <section className="panel-card image-panel">
      <SectionHeader eyebrow={subtitle} title={title} actions={actions} />
      <div className="scan-frame">
        {customFrame ? (
          children
        ) : src ? (
          <img src={src} alt={alt} />
        ) : (
          <div className="scan-placeholder">
            <ImageIcon size={28} />
            <span>Görüntü bekleniyor</span>
          </div>
        )}
        {customFrame ? null : children}
      </div>
    </section>
  );
}

function EmptyState({ errorMessage, loading, onRetry }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        {loading ? <RefreshCw className="spin" size={30} /> : <Activity size={30} />}
      </div>
      <h2>{loading ? 'Analiz hazırlanıyor' : 'Analiz için vaka seçin'}</h2>
      <p>
        Kütüphaneden bir MRG örneği seçebilir veya bilgisayarınızdan tek kesit görüntü
        yükleyebilirsiniz.
      </p>
      {errorMessage ? <div className="inline-alert">{errorMessage}</div> : null}
      <button className="btn secondary" type="button" onClick={onRetry}>
        <RefreshCw size={16} />
        Yeniden dene
      </button>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="loading-panel">
      <RefreshCw className="spin" size={34} />
      <h2>nnU-Net segmentasyonu çalışıyor</h2>
      <p>Kesit hazırlanıyor, sınıflandırma ve hacim ölçümü tamamlanıyor.</p>
    </div>
  );
}

function DashboardTab({ result }) {
  const [viewMode, setViewMode] = useState('overlay');
  const [overlayOpacity, setOverlayOpacity] = useState(82);
  const tone = diagnosisTone(result);
  const risk = getRiskPlan(result);
  const probabilities = Object.entries(result.probs || {});
  const sphericity = toNumber(result.sphericity);
  const originalSrc = imageSource(result, 'original');
  const overlaySrc = imageSource(result, 'overlay');
  const modeSrc = getImageModeSource(result, viewMode);

  return (
    <div className="dashboard-layout">
      <ImagePanel
        title="Görüntü inceleme"
        subtitle="Clinical review viewport"
        src={viewMode === 'compare' ? '' : modeSrc}
        alt="Segmentasyon bindirmeli beyin MRG kesiti"
        customFrame={viewMode === 'overlay' || viewMode === 'compare'}
        actions={
          <div className="viewport-modes" role="tablist" aria-label="Görüntü modu">
            {VIEW_MODES.map((mode) => (
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
        }
      >
        {viewMode === 'overlay' && originalSrc && overlaySrc ? (
          <div className="overlay-stack">
            <img src={originalSrc} alt="Orijinal beyin MRG kesiti" />
            <img
              className="overlay-layer"
              src={overlaySrc}
              alt="Segmentasyon bindirmesi"
              style={{ opacity: overlayOpacity / 100 }}
            />
          </div>
        ) : null}

        {viewMode === 'compare' ? (
          <div className="compare-grid">
            <figure>
              <img src={originalSrc} alt="Orijinal beyin MRG kesiti" />
              <figcaption>Orijinal</figcaption>
            </figure>
            <figure>
              <img src={overlaySrc} alt="Segmentasyon bindirmeli beyin MRG kesiti" />
              <figcaption>Overlay</figcaption>
            </figure>
          </div>
        ) : null}

        {viewMode === 'overlay' ? (
          <div className="viewport-control">
            <span>Overlay opaklığı</span>
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

        <div className="legend-strip">
          <span>
            <i className="legend-dot wt" /> Whole tumor
          </span>
          <span>
            <i className="legend-dot tc" /> Tumor core
          </span>
          <span>
            <i className="legend-dot et" /> Enhancing tumor
          </span>
        </div>
      </ImagePanel>

      <section className="panel-card decision-panel">
        <SectionHeader
          eyebrow="Karar özeti"
          title="AI ön değerlendirme"
          actions={<StatusPill tone={tone}>{repairText(result.predicted_tumor_type)}</StatusPill>}
        />
        <div className={`diagnosis-box tone-${tone}`}>
          <span>Ön tanı sınıflandırması</span>
          <strong>{repairText(result.diagnosis_tr)}</strong>
          <small>Güven skoru: {formatter.format(toNumber(result.confidence))}%</small>
        </div>

        <div className="stat-grid">
          <StatCard
            icon={FlaskConical}
            label="Tümör hacmi"
            value={formatNumber(result.volume, ' cm³')}
            detail="3D voksel ölçümü"
            tone={tone}
          />
          <StatCard
            icon={Activity}
            label="Sferisite"
            value={formatter.format(sphericity)}
            detail="Geometrik düzenlilik"
            tone="info"
          />
        </div>

        <div className="risk-card">
          <StatusPill tone={risk.tone}>{risk.label}</StatusPill>
          <strong>Sonraki MRG kontrolü: {risk.followUp}</strong>
          <p>{risk.note}</p>
        </div>
      </section>

      <section className="panel-card probability-panel">
        <SectionHeader eyebrow="Diferansiyel tanı" title="Olasılık skorları" />
        <div className="probability-list">
          {probabilities.map(([label, value]) => (
            <MetricBar
              key={label}
              label={label}
              value={value}
              tone={label.toLocaleLowerCase('tr-TR').includes('sağlıklı') ? 'success' : tone}
            />
          ))}
        </div>
      </section>

      <section className="panel-card model-panel">
        <SectionHeader eyebrow="Review workflow" title="İnceleme adımları" />
        <ol className="timeline">
          <li>
            <span>01</span>
            <div>
              <strong>Görüntü kalitesi</strong>
              <p>Skull stripping, bias correction ve yoğunluk normalizasyonu.</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>Segmentasyon</strong>
              <p>Lezyon maskesi ve hacim ölçümü ResUnet tabanlı akıştan alınır.</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>Radyolog onayı</strong>
              <p>AI taslağı rapor ve FHIR çıktısı onay sonrası final statüsüne alınır.</p>
            </div>
          </li>
        </ol>
      </section>
    </div>
  );
}

function PipelineTab({ result }) {
  const stages = [
    {
      key: 'original',
      title: 'Orijinal kesit',
      detail: 'Yüklenen veya kütüphaneden seçilen ham MRG kesiti.',
    },
    {
      key: 'stripped',
      title: 'Skull stripping',
      detail: 'Beyin dışı dokular karar modelinden ayrıştırılır.',
    },
    {
      key: 'corrected',
      title: 'Bias correction',
      detail: 'Yoğunluk dalgalanmaları ve alan sapmaları dengelenir.',
    },
    {
      key: 'normalized',
      title: 'Normalize kesit',
      detail: 'Sınıflandırma öncesi standart yoğunluk aralığına alınır.',
    },
  ];

  return (
    <div className="tab-stack">
      <SectionHeader eyebrow="Ön işleme" title="MRG hazırlık adımları" />
      <div className="visual-grid">
        {stages.map((stage, index) => (
          <article className="visual-item" key={stage.key}>
            <div className="visual-media">
              <img src={imageSource(result, stage.key)} alt={stage.title} />
              <span>{String(index + 1).padStart(2, '0')}</span>
            </div>
            <h3>{stage.title}</h3>
            <p>{stage.detail}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

function BiopsyTab({ result }) {
  const molecular = result.molecular || {};
  const isGlioma = result.predicted_tumor_type === 'glioma';
  const idhProb = toNumber(molecular.idh_mutant_prob);
  const mgmtProb = toNumber(molecular.mgmt_methylated_prob);
  const idhStatus = repairText(molecular.idh_status || (idhProb >= 0.5 ? 'MUTANT' : 'WILD-TYPE'));
  const mgmtStatus = repairText(
    molecular.mgmt_status || (mgmtProb >= 0.5 ? 'METİLE' : 'METİLLENMEMİŞ'),
  );

  return (
    <div className="biopsy-layout">
      <section className="panel-card">
        <SectionHeader eyebrow="Radiogenomik" title="Sanal biyopsi sonucu" />
        {isGlioma ? (
          <div className="marker-grid">
            <article className="marker-card">
              <span>IDH mutasyon olasılığı</span>
              <strong>{formatPercent(idhProb)}</strong>
              <StatusPill tone={idhProb >= 0.5 ? 'success' : 'danger'}>{idhStatus}</StatusPill>
              <MetricBar label="IDH mutant skoru" value={idhProb * 100} tone="info" />
            </article>
            <article className="marker-card">
              <span>MGMT metilasyon olasılığı</span>
              <strong>{formatPercent(mgmtProb)}</strong>
              <StatusPill tone={mgmtProb >= 0.5 ? 'success' : 'warning'}>{mgmtStatus}</StatusPill>
              <MetricBar label="MGMT metile skoru" value={mgmtProb * 100} tone="success" />
            </article>
          </div>
        ) : (
          <div className="clinical-note">
            <ShieldAlert size={22} />
            <div>
              <strong>Moleküler tahmin bu lezyon tipi için endike değil.</strong>
              <p>
                IDH ve MGMT çıktıları diffüz gliom değerlendirmesi için anlamlıdır. Bu
                sınıflandırmada karar, görüntüleme bulguları ve histopatoloji ile
                doğrulanmalıdır.
              </p>
            </div>
          </div>
        )}
      </section>

      <section className="panel-card">
        <SectionHeader eyebrow="Morfometri" title="Hacim ve şekil" />
        <div className="stat-grid two-columns">
          <StatCard
            icon={FlaskConical}
            label="Hacim"
            value={formatNumber(result.volume, ' cm³')}
            detail="Segmentasyon maskesi"
            tone="warning"
          />
          <StatCard
            icon={Activity}
            label="Sferisite"
            value={formatter.format(toNumber(result.sphericity))}
            detail="0-1 arası düzenlilik"
            tone="info"
          />
        </div>
      </section>
    </div>
  );
}

function XaiTab({ result }) {
  const featureRows = Object.entries(result.features || {})
    .filter(([, value]) => Number.isFinite(Number(value)))
    .sort((a, b) => Math.abs(Number(b[1])) - Math.abs(Number(a[1])))
    .slice(0, 7);

  return (
    <div className="xai-layout">
      <ImagePanel
        title="Grad-CAM odak haritası"
        subtitle="Model açıklanabilirliği"
        src={imageSource(result, 'gradcam')}
        alt="Grad-CAM odak haritası"
      />
      <section className="panel-card">
        <SectionHeader eyebrow="Öne çıkan özellikler" title="Model katkıları" />
        <div className="feature-list">
          {featureRows.map(([name, value]) => {
            const numeric = Math.abs(toNumber(value));
            const width = Math.min(100, numeric > 1 ? numeric : numeric * 100);
            return (
              <div className="feature-row" key={name}>
                <div>
                  <strong>{formatFeatureName(name)}</strong>
                  <span>{formatter.format(toNumber(value))}</span>
                </div>
                <div className="progress-track">
                  <span className="progress-fill tone-info" style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function ReportTab({
  result,
  patientName,
  patientAge,
  patientGender,
  generatingReport,
  llmReport,
  onGenerate,
  onDownload,
  radiologistApproval,
  setRadiologistApproval,
}) {
  const reportText = repairText(llmReport || result.report || '');
  const reportSections = useMemo(
    () => getStructuredReportSections(result, patientName, patientAge, patientGender, radiologistApproval),
    [patientAge, patientGender, patientName, radiologistApproval, result],
  );
  const generatedDraft = useMemo(
    () =>
      reportText ||
      buildReportDraft(result, patientName, patientAge, patientGender, radiologistApproval),
    [patientAge, patientGender, patientName, radiologistApproval, reportText, result],
  );
  const draftSourceKey = `${result.image_name || ''}|${reportText}|${radiologistApproval || 'draft'}`;
  const [manualDraft, setManualDraft] = useState('');
  const [manualDraftKey, setManualDraftKey] = useState('');
  const draftReport = manualDraftKey === draftSourceKey ? manualDraft : generatedDraft;

  return (
    <div className="report-layout">
      <section className="panel-card">
        <SectionHeader
          eyebrow="Raporlama"
          title="Klinik rapor taslağı"
          actions={
            <>
              <button
                className="btn primary"
                type="button"
                onClick={onGenerate}
                disabled={generatingReport}
              >
                {generatingReport ? <RefreshCw className="spin" size={16} /> : <FileText size={16} />}
                {generatingReport ? 'Üretiliyor' : 'Rapor üret'}
              </button>
              <button
                className="btn secondary"
                type="button"
                onClick={() => onDownload(draftReport)}
                disabled={!draftReport}
              >
                <Download size={16} />
                İndir
              </button>
            </>
          }
        />

        <div className="approval-row">
          <button
            className={`approval-button ${radiologistApproval === 'approved' ? 'active success' : ''}`}
            type="button"
            onClick={() => setRadiologistApproval('approved')}
          >
            <CheckCircle size={17} />
            Onayla
          </button>
          <button
            className={`approval-button ${radiologistApproval === 'rejected' ? 'active danger' : ''}`}
            type="button"
            onClick={() => setRadiologistApproval('rejected')}
          >
            <AlertTriangle size={17} />
            Revizyon gerekli
          </button>
        </div>

        <div className="structured-report-grid">
          {reportSections.map((section) => (
            <article className="structured-section" key={section.title}>
              <h3>{section.title}</h3>
              <dl>
                {section.rows.map(([label, value]) => (
                  <Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl>
            </article>
          ))}
        </div>

        <label className="report-editor">
          <span>Radyoloji rapor taslağı</span>
          <textarea
            value={draftReport}
            onChange={(event) => {
              setManualDraftKey(draftSourceKey);
              setManualDraft(event.target.value);
            }}
            placeholder="Rapor henüz oluşturulmadı. Hasta bilgileri ve analiz sonucu ile resmi rapor taslağı üretilebilir."
          />
        </label>
      </section>
    </div>
  );
}

function FhirTab({ result, activeResource, setActiveResource, radiologistApproval, llmReport }) {
  const resource = useMemo(() => {
    const fhir = result.fhir || {};
    if (activeResource === 'diagnostic_report') {
      return {
        ...(fhir.diagnostic_report || {}),
        status: radiologistApproval === 'approved' ? 'final' : 'preliminary',
        conclusion:
          repairText(llmReport) ||
          repairText(fhir.diagnostic_report?.conclusion) ||
          `${repairText(result.diagnosis_tr)} için yapay zeka destekli ön değerlendirme.`,
      };
    }
    return fhir[activeResource] || {};
  }, [activeResource, llmReport, radiologistApproval, result.diagnosis_tr, result.fhir]);
  const summaryRows = useMemo(
    () => getFhirSummary(resource, activeResource),
    [activeResource, resource],
  );

  return (
    <section className="panel-card">
      <SectionHeader
        eyebrow="HL7 FHIR R4"
        title="Yapılandırılmış çıktı"
        actions={<StatusPill tone="info">FHIR-ready</StatusPill>}
      />
      <div className="resource-tabs" role="tablist" aria-label="FHIR kaynakları">
        {FHIR_OPTIONS.map((option) => (
          <button
            className={activeResource === option.id ? 'active' : ''}
            key={option.id}
            type="button"
            onClick={() => setActiveResource(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="fhir-summary-grid">
        {summaryRows.map(([label, value]) => (
          <article className="fhir-summary-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>

      <div className="raw-json-heading">
        <span>Raw JSON</span>
        <small>HBYS / PACS entegrasyonu için geliştirici görünümü</small>
      </div>
      <pre className="fhir-code">{JSON.stringify(repairDeep(resource), null, 2)}</pre>
    </section>
  );
}

function IntakeBar({
  libraryScans,
  selectedScanId,
  onLibrarySelect,
  onFileUpload,
  patientName,
  setPatientName,
  patientAge,
  setPatientAge,
  patientGender,
  setPatientGender,
  loading,
}) {
  return (
    <section className="intake-bar">
      <label className="upload-action">
        <Upload size={18} />
        <span>MRG yükle</span>
        <input type="file" accept="image/*" onChange={onFileUpload} disabled={loading} />
      </label>

      <label className="field-group case-selector">
        <span>Vaka kütüphanesi</span>
        <select value={selectedScanId} onChange={onLibrarySelect} disabled={loading}>
          <option value="">Kendi görüntüm</option>
          {libraryScans.map((scan) => (
            <option key={scan.id} value={scan.id}>
              {getLibraryName(scan)}
            </option>
          ))}
        </select>
      </label>

      <label className="field-group patient-name">
        <span>Hasta / protokol</span>
        <input
          type="text"
          value={patientName}
          onChange={(event) => setPatientName(event.target.value)}
          placeholder="Hasta adı veya protokol"
        />
      </label>

      <label className="field-group short">
        <span>Yaş</span>
        <input
          type="number"
          value={patientAge}
          onChange={(event) => setPatientAge(Number.parseInt(event.target.value, 10) || 0)}
          min="0"
        />
      </label>

      <label className="field-group short">
        <span>Cinsiyet</span>
        <select value={patientGender} onChange={(event) => setPatientGender(event.target.value)}>
          <option value="female">Kadın</option>
          <option value="male">Erkek</option>
        </select>
      </label>
    </section>
  );
}

function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [libraryScans, setLibraryScans] = useState([]);
  const [selectedScanId, setSelectedScanId] = useState('');
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [patientName, setPatientName] = useState('Hasta Protokol-9824');
  const [patientAge, setPatientAge] = useState(42);
  const [patientGender, setPatientGender] = useState('female');
  const [generatingReport, setGeneratingReport] = useState(false);
  const [llmReport, setLlmReport] = useState('');
  const [activeFhirResource, setActiveFhirResource] = useState('patient');
  const [radiologistApproval, setRadiologistApproval] = useState(null);
  const initialized = useRef(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('neuro-theme', theme);
  }, [theme]);

  const runAnalysis = useCallback(async (libraryId, file) => {
    setLoading(true);
    setErrorMessage('');
    setLlmReport('');
    setRadiologistApproval(null);

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
        throw new Error('Analiz isteği başarısız oldu.');
      }

      const data = await response.json();
      setAnalysisResult(data);
    } catch (error) {
      console.error(error);
      setErrorMessage(
        "Backend bağlantısı kurulamadı. FastAPI servisinin 127.0.0.1:8000 adresinde çalıştığını kontrol edin.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLibrary = useCallback(async () => {
    setErrorMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/library`);
      if (!response.ok) {
        throw new Error('Vaka kütüphanesi alınamadı.');
      }
      const data = await response.json();
      setLibraryScans(data);
      if (data.length > 0) {
        const firstScanId = data[0].id;
        setSelectedScanId(firstScanId);
        await runAnalysis(firstScanId, null);
      }
    } catch (error) {
      console.error(error);
      setErrorMessage(
        "Vaka kütüphanesi alınamadı. FastAPI backend'in çalıştığından emin olun.",
      );
    }
  }, [runAnalysis]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    loadLibrary();
  }, [loadLibrary]);

  const handleLibrarySelect = (event) => {
    const libraryId = event.target.value;
    setSelectedScanId(libraryId);
    if (libraryId) {
      runAnalysis(libraryId, null);
    }
  };

  const handleLibraryCardSelect = (libraryId) => {
    setSelectedScanId(libraryId);
    setActiveTab('dashboard');
    runAnalysis(libraryId, null);
  };

  const handleFileUpload = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setSelectedScanId('');
    runAnalysis(null, file);
    event.target.value = '';
  };

  const generateGroqReport = async () => {
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

      if (!response.ok) {
        throw new Error('Rapor üretimi başarısız oldu.');
      }

      const data = await response.json();
      setLlmReport(repairText(data.report));
    } catch (error) {
      console.error(error);
      setErrorMessage('Rapor üretilemedi. Backend rapor uç noktasını kontrol edin.');
    } finally {
      setGeneratingReport(false);
    }
  };

  const downloadReport = (overrideText = '') => {
    const reportText = repairText(overrideText || llmReport || analysisResult?.report || '');
    if (!reportText) return;

    const approvalText =
      radiologistApproval === 'approved'
        ? 'Radyolog Onayı: FINAL'
        : radiologistApproval === 'rejected'
          ? 'Radyolog Onayı: REVİZYON GEREKLİ'
          : 'Radyolog Onayı: TASLAK';

    const file = new Blob([`${approvalText}\n\n${reportText}`], { type: 'text/plain' });
    const element = document.createElement('a');
    element.href = URL.createObjectURL(file);
    element.download = `${patientName.replace(/\s+/g, '_')}_Klinik_Rapor.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    URL.revokeObjectURL(element.href);
  };

  const renderTabContent = () => {
    if (loading && !analysisResult) {
      return <LoadingPanel />;
    }

    if (!analysisResult) {
      return <EmptyState errorMessage={errorMessage} loading={loading} onRetry={loadLibrary} />;
    }

    if (loading) {
      return <LoadingPanel />;
    }

    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab result={analysisResult} />;
      case 'pipeline':
        return <PipelineTab result={analysisResult} />;
      case 'biopsy':
        return <BiopsyTab result={analysisResult} />;
      case 'xai':
        return <XaiTab result={analysisResult} />;
      case 'report':
        return (
          <ReportTab
            result={analysisResult}
            patientName={patientName}
            patientAge={patientAge}
            patientGender={patientGender}
            generatingReport={generatingReport}
            llmReport={llmReport}
            onGenerate={generateGroqReport}
            onDownload={downloadReport}
            radiologistApproval={radiologistApproval}
            setRadiologistApproval={setRadiologistApproval}
          />
        );
      case 'fhir':
        return (
          <FhirTab
            result={analysisResult}
            activeResource={activeFhirResource}
            setActiveResource={setActiveFhirResource}
            radiologistApproval={radiologistApproval}
            llmReport={llmReport}
          />
        );
      default:
        return <DashboardTab result={analysisResult} />;
    }
  };

  const risk = getRiskPlan(analysisResult);
  const selectedLibraryScan = libraryScans.find((scan) => scan.id === selectedScanId);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">
            <Activity size={22} />
          </div>
          <div>
            <span className="product-name">NeuroOncoTrack</span>
            <strong>Klinik karar destek paneli</strong>
          </div>
        </div>

        <div className="topbar-status">
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
            aria-label={theme === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç'}
            title={theme === 'dark' ? 'Açık tema' : 'Koyu tema'}
          >
            <span className={theme === 'light' ? 'active' : ''}>
              <Sun size={15} />
            </span>
            <span className={theme === 'dark' ? 'active' : ''}>
              <Moon size={15} />
            </span>
          </button>
          <StatusPill tone={errorMessage ? 'danger' : 'success'}>
            {errorMessage ? 'Backend bekleniyor' : 'Backend aktif'}
          </StatusPill>
          <StatusPill tone={risk.tone}>{risk.label}</StatusPill>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar" aria-label="Ana menü">
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-label">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
                    key={item.id}
                    type="button"
                    onClick={() => setActiveTab(item.id)}
                  >
                    <Icon size={17} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}

          {libraryScans.length > 0 ? (
            <div className="case-worklist">
              <span className="nav-label">Demo Vakalar</span>
              <div className="case-list">
                {libraryScans.map((scan, index) => (
                  <button
                    className={`case-card ${selectedScanId === scan.id ? 'active' : ''}`}
                    key={scan.id}
                    type="button"
                    onClick={() => handleLibraryCardSelect(scan.id)}
                    disabled={loading}
                  >
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <strong>{getLibraryName(scan)}</strong>
                    <small>{scan.id}</small>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="system-card">
            <div>
              <Cpu size={18} />
              <strong>Model durumu</strong>
            </div>
            <dl>
              <dt>Güven</dt>
              <dd>{analysisResult ? `${formatter.format(toNumber(analysisResult.confidence))}%` : '-'}</dd>
              <dt>Aktif vaka</dt>
              <dd>{selectedScanId ? getLibraryName(selectedLibraryScan || { id: selectedScanId }) : 'Yüklenen görüntü'}</dd>
              <dt>API</dt>
              <dd>127.0.0.1:8000</dd>
            </dl>
          </div>
        </aside>

        <main className="content-area">
          <IntakeBar
            libraryScans={libraryScans}
            selectedScanId={selectedScanId}
            onLibrarySelect={handleLibrarySelect}
            onFileUpload={handleFileUpload}
            patientName={patientName}
            setPatientName={setPatientName}
            patientAge={patientAge}
            setPatientAge={setPatientAge}
            patientGender={patientGender}
            setPatientGender={setPatientGender}
            loading={loading}
          />

          {errorMessage && analysisResult ? (
            <div className="inline-alert">
              <AlertTriangle size={17} />
              {errorMessage}
            </div>
          ) : null}

          {renderTabContent()}
        </main>
      </div>
    </div>
  );
}

export default App;
