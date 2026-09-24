import { demoPatientProfiles, fhirOptions, formatter } from '../config/neuroConstants.js';

export function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function getViewerPanLimit(zoom) {
  return zoom <= 100 ? 90 : Math.min(520, 90 + (zoom - 100) * 3.2);
}

export function clampViewerPan(pan, zoom) {
  const limit = getViewerPanLimit(zoom);
  return {
    x: clampNumber(pan.x, -limit, limit),
    y: clampNumber(pan.y, -limit, limit),
  };
}

export function getInitialTheme() {
  if (typeof window === 'undefined') return 'light';
  const storedTheme = window.localStorage.getItem('neuro-login-theme');
  if (storedTheme === 'dark' || storedTheme === 'light') return storedTheme;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function repairText(value) {
  if (typeof value !== 'string') return value ?? '';
  try {
    if (!/[ÃƒÃ„Ã…Ã‚ÄÅ]/.test(value)) return value;
    const bytes = Array.from(value, (character) => character.charCodeAt(0) & 0xff);
    const decoded = new TextDecoder('utf-8').decode(new Uint8Array(bytes));
    return decoded.includes('�') ? value : decoded;
  } catch {
    return value;
  }
}

export function repairDeep(value) {
  if (typeof value === 'string') return repairText(value);
  if (Array.isArray(value)) return value.map(repairDeep);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [repairText(key), repairDeep(item)]),
    );
  }
  return value;
}

export function normalizeSearchText(value) {
  return repairText(value)
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

export function getCaseFilterMeta(scan) {
  const id = scan?.id || '';
  const text = normalizeSearchText(`${scan?.name || ''} ${id} ${scan?.description || ''}`);
  const profile = demoPatientProfiles[id] || {};
  const diagnosis = text.includes('saglikli') || text.includes('sağlıklı')
    ? 'healthy'
    : text.includes('gli') || text.includes('glio')
      ? 'glioma'
      : text.includes('men')
        ? 'meningioma'
        : 'tumor';

  return {
    age: profile.age || 0,
    diagnosis,
    gender: profile.gender || 'unknown',
  };
}

export function matchesCaseFilters(scan, filters) {
  const meta = getCaseFilterMeta(scan);
  const ageMatch =
    filters.age === 'all' ||
    (filters.age === 'under40' && meta.age > 0 && meta.age < 40) ||
    (filters.age === '40to59' && meta.age >= 40 && meta.age <= 59) ||
    (filters.age === '60plus' && meta.age >= 60);

  return (
    (filters.diagnosis === 'all' || meta.diagnosis === filters.diagnosis) &&
    (filters.gender === 'all' || meta.gender === filters.gender) &&
    ageMatch
  );
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function getApprovalText(approval) {
  if (approval === 'approved') return 'Radyolog Onayı: FINAL';
  if (approval === 'rejected') return 'Radyolog Onayı: REVİZYON GEREKLİ';
  return 'Radyolog Onayı: TASLAK';
}

export function buildReportHtml(title, approvalText, reportBody) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    body { font-family: Arial, sans-serif; color: #0f172a; line-height: 1.55; padding: 32px; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    .status { margin: 0 0 24px; color: #0f766e; font-weight: 700; }
    pre { white-space: pre-wrap; font-family: Arial, sans-serif; font-size: 13px; }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  <p class="status">${escapeHtml(approvalText)}</p>
  <pre>${escapeHtml(reportBody)}</pre>
</body>
</html>`;
}

export function buildClinicalReportHtml({ title = 'Klinik Rapor', statusLabel = 'TASLAK', sections = [], narrative = '', meta = {} } = {}) {
  const today = meta.date || new Date().toLocaleString('tr-TR');
  const version = meta.version != null ? `Sürüm ${meta.version}` : '';
  const statusColor = statusLabel === 'FINAL' ? '#0f766e' : String(statusLabel).includes('REVİZYON') ? '#b91c1c' : '#b45309';
  const sectionHtml = sections.map((s) => `
    <section class="blk">
      <h2>${escapeHtml(s.title)}</h2>
      <table class="kv"><tbody>
        ${s.rows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(String(v == null ? '—' : v))}</td></tr>`).join('')}
      </tbody></table>
    </section>`).join('');
  const narrativeHtml = narrative ? `<section class="blk"><h2>Rapor metni</h2><pre>${escapeHtml(narrative)}</pre></section>` : '';
  return `<!doctype html><html lang="tr"><head><meta charset="utf-8"/>
  <title>${escapeHtml(title)}</title>
  <style>
    @page { size: A4; margin: 18mm 16mm; }
    * { box-sizing: border-box; }
    body { font-family: 'Segoe UI', Arial, sans-serif; color: #0f172a; line-height: 1.5; font-size: 12.5px; margin: 0; background:#fff; }
    .sheet { max-width: 720px; margin: 0 auto; padding: 24px; }
    .head { display:flex; justify-content:space-between; align-items:flex-start; border-bottom: 3px solid #0f766e; padding-bottom: 12px; }
    .brand { font-size: 20px; font-weight: 800; color:#0f766e; letter-spacing:-0.5px; }
    .brand small { display:block; font-size: 11px; font-weight:600; color:#475569; letter-spacing:0.4px; }
    .meta { text-align:right; font-size: 11px; color:#475569; }
    .status { display:inline-block; margin-top:6px; padding:3px 10px; border-radius: 999px; color:#fff; font-weight:700; font-size:11px; background:${statusColor}; }
    h1 { font-size: 16px; margin: 18px 0 4px; }
    .blk { margin-top: 16px; page-break-inside: avoid; }
    .blk h2 { font-size: 13px; color:#0f766e; margin:0 0 6px; padding-bottom:3px; border-bottom:1px solid #e2e8f0; }
    table.kv { width:100%; border-collapse: collapse; }
    table.kv th { text-align:left; width: 38%; padding:5px 8px; color:#475569; font-weight:600; vertical-align:top; }
    table.kv td { padding:5px 8px; border-bottom:1px solid #f1f5f9; }
    pre { white-space: pre-wrap; font-family: inherit; font-size:12px; background:#f8fafc; padding:12px; border-radius:8px; margin:0; }
    .sign { margin-top: 28px; display:flex; justify-content:space-between; gap:24px; page-break-inside: avoid; }
    .sign div { flex:1; border-top:1px solid #94a3b8; padding-top:6px; font-size:11px; color:#475569; }
    .foot { margin-top: 22px; border-top:1px solid #e2e8f0; padding-top:12px; font-size:10.5px; color:#64748b; }
    .disc { margin-bottom:6px; font-style:italic; }
  </style></head>
  <body><div class="sheet">
    <div class="head">
      <div class="brand">NeuroOncoTrack-AI<small>Klinik Karar Destek · Radyoloji</small></div>
      <div class="meta">${escapeHtml(today)}<br/>${escapeHtml(version)}<br/><span class="status">${escapeHtml(statusLabel)}</span></div>
    </div>
    <h1>${escapeHtml(title)}</h1>
    ${sectionHtml}
    ${narrativeHtml}
    <div class="sign"><div>Hazırlayan (YZ): NeuroOncoTrack-AI</div><div>Onaylayan radyolog: _______________</div></div>
    <div class="foot">
      <div class="disc">Bu rapor yapay zekâ destekli bir ÖN değerlendirmedir; tanısal karar ve sorumluluk uzman radyoloğa aittir. IDH/MGMT gibi moleküler öngörüler kesin tanı yerine geçmez.</div>
      <div>KVKK: Hasta verileri anonim/de-identify işlenmiştir. · WHO 2021 CNS &amp; NCCN kılavuzlarına dayalı. · © 2026 NeuroOncoTrack-AI</div>
    </div>
  </div></body></html>`;
}

export function downloadBlob(content, filename, type) {
  const file = new Blob([content], { type });
  const element = document.createElement('a');
  element.href = URL.createObjectURL(file);
  element.download = filename;
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
  URL.revokeObjectURL(element.href);
}

export function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function formatNumber(value, suffix = '') {
  return `${formatter.format(toNumber(value))}${suffix}`;
}

export function formatPercent(value) {
  return `${formatter.format(toNumber(value) * 100)}%`;
}

export function imageSource(result, key) {
  const image = result?.images?.[key];
  return image ? `data:image/jpeg;base64,${image}` : '';
}

export async function readApiError(response, fallbackMessage) {
  try {
    const payload = await response.json();
    return repairText(payload?.error?.message || payload?.error?.detail || payload?.detail || payload?.message || fallbackMessage);
  } catch {
    return fallbackMessage;
  }
}

export function buildLocalSignatureHash(reportBody, workflowVersion = 1) {
  const source = `${reportBody || ''}|${workflowVersion}|neurooncotrack`;
  let hash = 0;

  for (let index = 0; index < source.length; index += 1) {
    hash = (hash << 5) - hash + source.charCodeAt(index);
    hash |= 0;
  }

  return `NOT-${Math.abs(hash).toString(16).toUpperCase().padStart(8, '0')}`;
}

export function formatDateTime(value) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

export function getDiagnosisTone(result) {
  const type = result?.predicted_tumor_type;
  if (type === 'notumor') return 'success';
  if (type === 'glioma') return 'danger';
  if (type === 'meningioma') return 'warning';
  return 'info';
}

export function getRiskPlan(result) {
  if (!result) {
    return {
      tone: 'info',
      label: 'Analiz bekliyor',
      followUp: '-',
      note: 'MRG yükleyin veya demo vaka seçin; karar özeti burada oluşacak.',
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
      note: 'Rutin klinik izlem ve karşılaştırmalı MRG önerilir.',
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

export function getImageModeSource(result, mode) {
  if (mode === 'original') return imageSource(result, 'original');
  if (mode === 'gradcam') return imageSource(result, 'gradcam');
  if (mode === 'normalized') return imageSource(result, 'normalized');
  return imageSource(result, 'overlay');
}

export function formatFeatureName(name) {
  return repairText(name)
    .replace(/^Original_/i, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toLocaleUpperCase('tr-TR'));
}

export function getStructuredReportSections(result, patientName, patientAge, patientGender, approval) {
  if (!result) return [];
  const risk = getRiskPlan(result);
  const molecular = result.molecular || {};
  const isGlioma = result.predicted_tumor_type === 'glioma';
  const genderLabel = patientGender === 'female' ? 'Kadın' : 'Erkek';
  const approvalLabel =
    approval === 'approved' ? 'FINAL' : approval === 'rejected' ? 'REVİZYON GEREKLİ' : 'TASLAK';

  return [
    {
      title: 'Hasta ve çalışma',
      rows: [
        ['Protokol', patientName],
        ['Yaş / Cinsiyet', `${patientAge} / ${genderLabel}`],
        ['Çalışma', repairText(result.image_name || 'MRG kesiti')],
        ['Rapor durumu', approvalLabel],
      ],
    },
    {
      title: 'AI bulguları',
      rows: [
        ['Ön tanı', repairText(result.diagnosis_tr)],
        ['Güven', `${formatter.format(toNumber(result.confidence))}%`],
        ['Hacim', formatNumber(result.volume, ' cm³')],
        ['Sferisite', (result.sphericity ?? result.morphometry?.sphericity ?? result.features?.['Sferisite']) != null
          ? formatter.format(toNumber(result.sphericity ?? result.morphometry?.sphericity ?? result.features?.['Sferisite']))
          : '—'],
      ],
    },
    {
      title: isGlioma ? 'Moleküler öngörü' : 'Moleküler durum',
      rows: isGlioma
        ? [
            ['IDH', molecular.idh_mutant_prob != null
              ? `${repairText(molecular.idh_status || '-')} (${formatPercent(toNumber(molecular.idh_mutant_prob))})`
              : repairText(molecular.idh_status || '-')],
            ['MGMT', molecular.mgmt_methylated_prob != null
              ? `${repairText(molecular.mgmt_status || '-')} (${formatPercent(toNumber(molecular.mgmt_methylated_prob))})`
              : repairText(molecular.mgmt_status || '-')],
          ]
        : [['Not', 'IDH/MGMT paneli bu sınıflandırma için endike değil.']],
    },
    {
      title: 'İzlem',
      rows: [
        ['Risk', risk.label],
        ['Kontrol', risk.followUp],
        ['Klinik not', risk.note],
      ],
    },
  ];
}

export function buildReportDraft(result, patientName, patientAge, patientGender, approval) {
  return getStructuredReportSections(result, patientName, patientAge, patientGender, approval)
    .map(
      (section) =>
        `${section.title}\n${section.rows.map(([label, value]) => `- ${label}: ${value}`).join('\n')}`,
    )
    .join('\n\n');
}

export function getFhirSummary(resource, activeResource) {
  const repaired = repairDeep(resource);
  if (Array.isArray(repaired)) {
    return [
      ['Kaynak', fhirOptions.find((option) => option.id === activeResource)?.label || activeResource],
      ['Kayıt sayısı', repaired.length],
      ['ID listesi', repaired.map((item) => item.id || item.resourceType || '-').join(', ') || '-'],
    ];
  }

  if (!repaired || typeof repaired !== 'object') return [['Durum', 'Kaynak bulunamadı']];

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
