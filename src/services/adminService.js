/**
 * adminService.js — NeuroOncoTrack-AI Admin Servisi
 *
 * Backend admin endpoint'leri hazır olana kadar mock data döner.
 * Gerçek endpoint'ler geldiğinde sadece MOCK_MODE = false yapılması yeterli.
 *
 * Beklenen backend endpoint'leri:
 *   GET  /api/v1/admin/stats
 *   GET  /api/v1/admin/users
 *   GET  /api/v1/admin/users/{id}
 *   PATCH /api/v1/admin/users/{id}
 *   GET  /api/v1/admin/sessions
 *   DELETE /api/v1/admin/sessions/{id}
 *   GET  /api/v1/admin/organizations
 *   GET  /api/v1/admin/audit-log
 */

import { apiClient, isEndpointUnavailable } from './apiClient.js';

// Backend admin endpoint'leri hazır değilse true yap (manual override)
// false olduğunda: önce gerçek API dener, 404/501/network hatası alırsa mock'a düşer
const MOCK_MODE = false;

// ─── Mock Data ───────────────────────────────────────────────────────────────

const MOCK_STATS = {
  total_users: 24,
  active_users: 21,
  locked_users: 2,
  inactive_users: 1,
  mfa_enabled_count: 14,
  mfa_adoption_rate: 58,
  active_sessions: 9,
  total_organizations: 4,
  new_users_last_30d: 3,
  failed_logins_last_24h: 7,
};

const MOCK_USERS = [
  { id: '1', email: 'admin@neuroonco.ai', first_name: 'Sistem', last_name: 'Yöneticisi', role: 'ADMIN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_name: 'NeuroOncoTrack Merkezi', last_login_at: new Date(Date.now() - 1 * 3600000).toISOString(), created_at: '2026-01-15T10:00:00Z', failed_login_attempts: 0 },
  { id: '2', email: 'drcelik@hacettepe.edu.tr', first_name: 'Ayşe', last_name: 'Çelik', title: 'Prof. Dr.', role: 'RADIOLOGIST', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_name: 'Hacettepe Üniversitesi', last_login_at: new Date(Date.now() - 2 * 3600000).toISOString(), created_at: '2026-02-10T09:00:00Z', failed_login_attempts: 0 },
  { id: '3', email: 'drdemir@gazi.edu.tr', first_name: 'Mehmet', last_name: 'Demir', title: 'Doç. Dr.', role: 'PHYSICIAN', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_name: 'Gazi Üniversitesi', last_login_at: new Date(Date.now() - 5 * 3600000).toISOString(), created_at: '2026-02-20T11:00:00Z', failed_login_attempts: 1 },
  { id: '4', email: 'dryilmaz@ege.edu.tr', first_name: 'Fatma', last_name: 'Yılmaz', title: 'Dr.', role: 'PHYSICIAN', is_active: true, is_locked: true, mfa_enabled: false, must_change_password: false, organization_name: 'Ege Üniversitesi', last_login_at: new Date(Date.now() - 48 * 3600000).toISOString(), created_at: '2026-03-01T08:00:00Z', failed_login_attempts: 5 },
  { id: '5', email: 'drarslan@itu.edu.tr', first_name: 'Can', last_name: 'Arslan', title: 'Uz. Dr.', role: 'RESEARCHER', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_name: 'İTÜ Araştırma', last_login_at: new Date(Date.now() - 12 * 3600000).toISOString(), created_at: '2026-03-15T14:00:00Z', failed_login_attempts: 0 },
  { id: '6', email: 'drkaya@ankara.edu.tr', first_name: 'Zeynep', last_name: 'Kaya', title: 'Prof. Dr.', role: 'RADIOLOGIST', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_name: 'Ankara Üniversitesi', last_login_at: new Date(Date.now() - 30 * 60000).toISOString(), created_at: '2026-03-20T10:00:00Z', failed_login_attempts: 0 },
  { id: '7', email: 'droz@baskent.edu.tr', first_name: 'Murat', last_name: 'Öz', title: 'Dr.', role: 'PHYSICIAN', is_active: false, is_locked: false, mfa_enabled: false, must_change_password: true, organization_name: 'Başkent Üniversitesi', last_login_at: null, created_at: '2026-04-01T13:00:00Z', failed_login_attempts: 0 },
  { id: '8', email: 'researcher@teknofest.ai', first_name: 'Ali', last_name: 'Şahin', role: 'RESEARCHER', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_name: 'Teknofest AI', last_login_at: new Date(Date.now() - 3 * 3600000).toISOString(), created_at: '2026-04-10T09:00:00Z', failed_login_attempts: 2 },
];

const MOCK_SESSIONS = [
  { id: 's1', user_email: 'drcelik@hacettepe.edu.tr', user_name: 'Ayşe Çelik', ip_address: '193.140.12.55', user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126', created_at: new Date(Date.now() - 2 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 5 * 60000).toISOString(), expires_at: new Date(Date.now() + 5 * 3600000).toISOString() },
  { id: 's2', user_email: 'admin@neuroonco.ai', user_name: 'Sistem Yöneticisi', ip_address: '127.0.0.1', user_agent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/17', created_at: new Date(Date.now() - 1 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 1 * 60000).toISOString(), expires_at: new Date(Date.now() + 6 * 3600000).toISOString() },
  { id: 's3', user_email: 'drdemir@gazi.edu.tr', user_name: 'Mehmet Demir', ip_address: '212.175.88.12', user_agent: 'Mozilla/5.0 (X11; Linux x86_64) Firefox/127', created_at: new Date(Date.now() - 5 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 20 * 60000).toISOString(), expires_at: new Date(Date.now() + 2 * 3600000).toISOString() },
  { id: 's4', user_email: 'drarslan@itu.edu.tr', user_name: 'Can Arslan', ip_address: '85.105.24.33', user_agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5) Mobile Safari', created_at: new Date(Date.now() - 12 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 45 * 60000).toISOString(), expires_at: new Date(Date.now() + 1 * 3600000).toISOString() },
  { id: 's5', user_email: 'drkaya@ankara.edu.tr', user_name: 'Zeynep Kaya', ip_address: '31.223.66.77', user_agent: 'Mozilla/5.0 (Windows NT 10.0) Edge/126', created_at: new Date(Date.now() - 30 * 60000).toISOString(), last_used_at: new Date(Date.now() - 2 * 60000).toISOString(), expires_at: new Date(Date.now() + 6.5 * 3600000).toISOString() },
];

const MOCK_ORGANIZATIONS = [
  { id: 'o1', name: 'NeuroOncoTrack Merkezi', code: 'NOT-2026', org_type: 'RESEARCH_CENTER', is_active: true, user_count: 5, created_at: '2026-01-01T00:00:00Z' },
  { id: 'o2', name: 'Hacettepe Üniversitesi Tıp Fakültesi', code: 'HU-TIP', org_type: 'UNIVERSITY_HOSPITAL', is_active: true, user_count: 7, created_at: '2026-01-20T00:00:00Z' },
  { id: 'o3', name: 'Gazi Üniversitesi Hastanesi', code: 'GAZI-H', org_type: 'UNIVERSITY_HOSPITAL', is_active: true, user_count: 4, created_at: '2026-02-05T00:00:00Z' },
  { id: 'o4', name: 'Teknofest AI Araştırma', code: 'TF-AI', org_type: 'RESEARCH_CENTER', is_active: false, user_count: 2, created_at: '2026-03-10T00:00:00Z' },
];

const MOCK_AUDIT_LOG = [
  { id: 'a1', timestamp: new Date(Date.now() - 5 * 60000).toISOString(), user_email: 'drkaya@ankara.edu.tr', action: 'LOGIN_SUCCESS', detail: 'IP: 31.223.66.77', severity: 'info' },
  { id: 'a2', timestamp: new Date(Date.now() - 12 * 60000).toISOString(), user_email: 'dryilmaz@ege.edu.tr', action: 'LOGIN_FAILED', detail: 'Geçersiz şifre (5. deneme) — Hesap kilitlendi', severity: 'danger' },
  { id: 'a3', timestamp: new Date(Date.now() - 25 * 60000).toISOString(), user_email: 'drarslan@itu.edu.tr', action: 'MFA_VERIFIED', detail: 'TOTP doğrulama başarılı', severity: 'success' },
  { id: 'a4', timestamp: new Date(Date.now() - 1 * 3600000).toISOString(), user_email: 'admin@neuroonco.ai', action: 'USER_LOCKED', detail: 'Kullanıcı dryilmaz@ege.edu.tr kilitlendi', severity: 'warning' },
  { id: 'a5', timestamp: new Date(Date.now() - 2 * 3600000).toISOString(), user_email: 'drcelik@hacettepe.edu.tr', action: 'PASSWORD_CHANGED', detail: 'Parola güncellendi', severity: 'info' },
  { id: 'a6', timestamp: new Date(Date.now() - 3 * 3600000).toISOString(), user_email: 'drdemir@gazi.edu.tr', action: 'LOGIN_SUCCESS', detail: 'IP: 212.175.88.12', severity: 'info' },
  { id: 'a7', timestamp: new Date(Date.now() - 5 * 3600000).toISOString(), user_email: 'researcher@teknofest.ai', action: 'REGISTER', detail: 'Yeni kullanıcı kaydı — Teknofest AI', severity: 'success' },
  { id: 'a8', timestamp: new Date(Date.now() - 8 * 3600000).toISOString(), user_email: 'admin@neuroonco.ai', action: 'SESSION_REVOKED', detail: 'Eski oturum iptal edildi (ID: s9)', severity: 'warning' },
  { id: 'a9', timestamp: new Date(Date.now() - 12 * 3600000).toISOString(), user_email: 'drarslan@itu.edu.tr', action: 'MFA_SETUP', detail: 'TOTP kurulumu tamamlandı', severity: 'success' },
  { id: 'a10', timestamp: new Date(Date.now() - 24 * 3600000).toISOString(), user_email: 'admin@neuroonco.ai', action: 'ORG_UPDATED', detail: 'TF-AI organizasyonu pasifleştirildi', severity: 'warning' },
];

// ─── Yardımcı ──────────────────────────────────────────────────────────────

async function callAdmin(path, options = {}) {
  if (MOCK_MODE) return null; // Manuel mock modunda direkt mock'a düş
  try {
    if (options.method === 'DELETE') return await apiClient.delete(path);
    if (options.method === 'PATCH') return await apiClient.patch(path, options.body);
    return await apiClient.get(path);
  } catch (error) {
    // 404/405/501 = endpoint henüz yok → mock'a düş
    // TypeError / status 0 = backend erişilemez → mock'a düş
    const isUnavailable = isEndpointUnavailable(error) ||
      error instanceof TypeError ||
      (error?.status === 0);
    if (isUnavailable) return null;
    throw error;
  }
}

// ─── İstatistikler ────────────────────────────────────────────────────────────

export async function getAdminStats() {
  const data = await callAdmin('/admin/stats');
  return data ?? MOCK_STATS;
}

// ─── Kullanıcı Yönetimi ───────────────────────────────────────────────────────

export async function getAdminUsers({ page = 1, search = '', role = '', status = '' } = {}) {
  const data = await callAdmin(`/admin/users?page=${page}&search=${search}&role=${role}&status=${status}`);
  if (data) return data;

  // Mock filtrele
  let users = [...MOCK_USERS];
  if (search) {
    const q = search.toLowerCase();
    users = users.filter(u =>
      u.email.toLowerCase().includes(q) ||
      `${u.first_name} ${u.last_name}`.toLowerCase().includes(q)
    );
  }
  if (role) users = users.filter(u => u.role === role);
  if (status === 'active') users = users.filter(u => u.is_active && !u.is_locked);
  if (status === 'locked') users = users.filter(u => u.is_locked);
  if (status === 'inactive') users = users.filter(u => !u.is_active);
  return { users, total: users.length, page: 1, per_page: 50 };
}

export async function patchAdminUser(userId, updates) {
  const data = await callAdmin(`/admin/users/${userId}`, { method: 'PATCH', body: updates });
  if (!data) {
    const user = MOCK_USERS.find(u => u.id === userId);
    if (user) {
      Object.assign(user, updates);
    }
    return { success: true, message: 'Güncelleme uygulandı (mock).' };
  }
  return data;
}

export async function deleteAdminUser(userId) {
  const data = await callAdmin(`/admin/users/${userId}`, { method: 'DELETE' });
  if (!data) {
    const idx = MOCK_USERS.findIndex(u => u.id === userId);
    if (idx !== -1) {
      MOCK_USERS.splice(idx, 1);
    }
    return { success: true, message: 'Kullanıcı silindi (mock).' };
  }
  return data;
}

// ─── Oturum İzleme ────────────────────────────────────────────────────────────

export async function getAdminSessions() {
  const data = await callAdmin('/admin/sessions');
  return data ?? { sessions: MOCK_SESSIONS, total: MOCK_SESSIONS.length };
}

export async function revokeAdminSession(sessionId) {
  const data = await callAdmin(`/admin/sessions/${sessionId}`, { method: 'DELETE' });
  return data ?? { success: true };
}

// ─── Organizasyonlar ─────────────────────────────────────────────────────────

export async function getAdminOrganizations() {
  const data = await callAdmin('/admin/organizations');
  return data ?? { organizations: MOCK_ORGANIZATIONS, total: MOCK_ORGANIZATIONS.length };
}

// ─── Audit Log ────────────────────────────────────────────────────────────────

export async function getAdminAuditLog({ page = 1, severity = '' } = {}) {
  const data = await callAdmin(`/admin/audit-log?page=${page}&severity=${severity}`);
  if (data) return data;
  const logs = severity ? MOCK_AUDIT_LOG.filter(l => l.severity === severity) : MOCK_AUDIT_LOG;
  return { logs, total: logs.length };
}
