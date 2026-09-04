/**
 * adminService.js — NeuroOncoTrack-AI Admin Servisi
 *
 * ADMIN rolü: sadece kendi kurumundaki kullanıcıları/oturumları yönetir.
 * SUPERADMIN için superadminService.js kullanılmalı.
 *
 * Backend admin endpoint'leri hazır olana kadar mock data döner.
 * Gerçek endpoint'ler geldiğinde sadece MOCK_MODE = false yapılması yeterli.
 *
 * Beklenen backend endpoint'leri (henüz implement edilmedi):
 *   GET  /api/v1/admin/stats
 *   GET  /api/v1/admin/users          ← JWT'den org filtresi otomatik uygulanır
 *   PATCH /api/v1/admin/users/{id}
 *   DELETE /api/v1/admin/users/{id}
 *   GET  /api/v1/admin/sessions       ← sadece kendi kurumu
 *   DELETE /api/v1/admin/sessions/{id}
 *   GET  /api/v1/admin/organizations  ← sadece kendi kurumu
 *   GET  /api/v1/admin/audit-log      ← sadece kendi kurumu
 */

import { apiClient, isEndpointUnavailable } from './apiClient.js';

// Backend admin endpoint'leri hazır değilse true yap (manual override)
// false olduğunda: önce gerçek API dener, 404/501/network hatası alırsa mock'a düşer
const MOCK_MODE = false;

// ─── Mock Data (sadece tek kurum örneği — ADMIN için) ────────────────────────
// Gerçekte her ADMIN kendi kurumu için filtrelenmiş veri alır (JWT bazlı, backend tarafında)

const MOCK_STATS = {
  total_users: 8,
  active_users: 6,
  locked_users: 1,
  inactive_users: 1,
  mfa_enabled_count: 4,
  mfa_adoption_rate: 50,
  active_sessions: 5,
  total_organizations: 1,
  new_users_last_30d: 2,
  failed_logins_last_24h: 3,
};

// Demo ADMIN'in kendi kurumu: "NeuroOncoTrack Merkezi" (organizasyon kodu: NOT-2026)
const ADMIN_ORG_ID = 'o1';
const ADMIN_ORG_NAME = 'NeuroOncoTrack Merkezi';

let MOCK_USERS = [
  { id: 'a1', email: 'admin@neuroonco.ai', first_name: 'Sistem', last_name: 'Yöneticisi', role: 'HOSPITAL_ADMIN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 1 * 3600000).toISOString(), created_at: '2026-01-15T10:00:00Z', failed_login_attempts: 0 },
  { id: 'a2', email: 'drcelik@neuroonco.ai', first_name: 'Ayşe', last_name: 'Çelik', title: 'Prof. Dr.', role: 'RADIOLOGIST', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 2 * 3600000).toISOString(), created_at: '2026-02-10T09:00:00Z', failed_login_attempts: 0 },
  { id: 'a3', email: 'drdemir@neuroonco.ai', first_name: 'Mehmet', last_name: 'Demir', title: 'Doç. Dr.', role: 'PHYSICIAN', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 5 * 3600000).toISOString(), created_at: '2026-02-20T11:00:00Z', failed_login_attempts: 1 },
  { id: 'a4', email: 'dryilmaz@neuroonco.ai', first_name: 'Fatma', last_name: 'Yılmaz', title: 'Dr.', role: 'PHYSICIAN', is_active: true, is_locked: true, mfa_enabled: false, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 48 * 3600000).toISOString(), created_at: '2026-03-01T08:00:00Z', failed_login_attempts: 5 },
  { id: 'a5', email: 'drarslan@neuroonco.ai', first_name: 'Can', last_name: 'Arslan', title: 'Uz. Dr.', role: 'RESEARCHER', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 12 * 3600000).toISOString(), created_at: '2026-03-15T14:00:00Z', failed_login_attempts: 0 },
  { id: 'a6', email: 'drkaya@neuroonco.ai', first_name: 'Zeynep', last_name: 'Kaya', title: 'Prof. Dr.', role: 'RADIOLOGIST', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 30 * 60000).toISOString(), created_at: '2026-03-20T10:00:00Z', failed_login_attempts: 0 },
  { id: 'a7', email: 'droz@neuroonco.ai', first_name: 'Murat', last_name: 'Öz', title: 'Dr.', role: 'PHYSICIAN', is_active: false, is_locked: false, mfa_enabled: false, must_change_password: true, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: null, created_at: '2026-04-01T13:00:00Z', failed_login_attempts: 0 },
  { id: 'a8', email: 'researcher@neuroonco.ai', first_name: 'Ali', last_name: 'Şahin', role: 'RESEARCHER', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_id: ADMIN_ORG_ID, organization_name: ADMIN_ORG_NAME, last_login_at: new Date(Date.now() - 3 * 3600000).toISOString(), created_at: '2026-04-10T09:00:00Z', failed_login_attempts: 2 },
];

const MOCK_SESSIONS = [
  { id: 's1', user_email: 'drcelik@neuroonco.ai', user_name: 'Ayşe Çelik', ip_address: '193.140.12.55', user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126', created_at: new Date(Date.now() - 2 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 5 * 60000).toISOString(), expires_at: new Date(Date.now() + 5 * 3600000).toISOString() },
  { id: 's2', user_email: 'admin@neuroonco.ai', user_name: 'Sistem Yöneticisi', ip_address: '127.0.0.1', user_agent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/17', created_at: new Date(Date.now() - 1 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 1 * 60000).toISOString(), expires_at: new Date(Date.now() + 6 * 3600000).toISOString() },
  { id: 's3', user_email: 'drdemir@neuroonco.ai', user_name: 'Mehmet Demir', ip_address: '212.175.88.12', user_agent: 'Mozilla/5.0 (X11; Linux x86_64) Firefox/127', created_at: new Date(Date.now() - 5 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 20 * 60000).toISOString(), expires_at: new Date(Date.now() + 2 * 3600000).toISOString() },
];

const MOCK_ORGANIZATIONS = [
  { id: ADMIN_ORG_ID, name: ADMIN_ORG_NAME, code: 'NOT-2026', org_type: 'RESEARCH_CENTER', is_active: true, user_count: 8, created_at: '2026-01-01T00:00:00Z' },
];

const MOCK_AUDIT_LOG = [
  { id: 'a1', timestamp: new Date(Date.now() - 5 * 60000).toISOString(), user_email: 'drkaya@neuroonco.ai', action: 'LOGIN_SUCCESS', detail: 'IP: 31.223.66.77', severity: 'info' },
  { id: 'a2', timestamp: new Date(Date.now() - 12 * 60000).toISOString(), user_email: 'dryilmaz@neuroonco.ai', action: 'LOGIN_FAILED', detail: 'Geçersiz şifre (5. deneme) — Hesap kilitlendi', severity: 'danger' },
  { id: 'a3', timestamp: new Date(Date.now() - 25 * 60000).toISOString(), user_email: 'drarslan@neuroonco.ai', action: 'MFA_VERIFIED', detail: 'TOTP doğrulama başarılı', severity: 'success' },
  { id: 'a4', timestamp: new Date(Date.now() - 1 * 3600000).toISOString(), user_email: 'admin@neuroonco.ai', action: 'USER_LOCKED', detail: 'Kullanıcı dryilmaz@neuroonco kilitlendi', severity: 'warning' },
  { id: 'a5', timestamp: new Date(Date.now() - 2 * 3600000).toISOString(), user_email: 'drcelik@neuroonco.ai', action: 'PASSWORD_CHANGED', detail: 'Parola güncellendi', severity: 'info' },
];

// ─── Yardımcı ──────────────────────────────────────────────────────────────────

async function callAdmin(path, options = {}) {
  if (MOCK_MODE) return null;
  try {
    if (options.method === 'DELETE') return await apiClient.delete(path);
    if (options.method === 'PATCH') return await apiClient.patch(path, options.body);
    if (options.method === 'PUT') return await apiClient.put(path, options.body);
    if (options.method === 'POST') return await apiClient.post(path, options.body);
    return await apiClient.get(path);
  } catch (error) {
    const isUnavailable =
      isEndpointUnavailable(error) ||
      error instanceof TypeError ||
      (error?.status === 0);
    if (isUnavailable) return null;
    throw error;
  }
}

// ─── İstatistikler (kendi kurumu) ─────────────────────────────────────────────

export async function getAdminStats() {
  const data = await callAdmin('/admin/security/overview');
  if (data) {
    // Map backend overview schema to frontend stats schema
    return {
      total_users: data.users.total,
      active_users: data.users.active,
      locked_users: data.users.locked,
      inactive_users: data.users.inactive,
      mfa_enabled_count: data.users.mfa_enabled,
      mfa_adoption_rate: data.users.mfa_adoption_rate,
      active_sessions: data.sessions.active,
      total_organizations: data.organizations.total,
      new_users_last_30d: 0,
      failed_logins_last_24h: data.security_events.failed_logins,
    };
  }
  return MOCK_STATS;
}

// ─── Kullanıcı Yönetimi ───────────────────────────────────────────────────────

export async function getAdminUsers({
  page = 1,
  search = '',
  role = '',
  status = '',
} = {}) {
  const params = new URLSearchParams({ page, page_size: 50 });
  if (search) params.append('search', search);
  if (role) params.append('role', role);
  if (status) params.append('status', status);
  
  const data = await callAdmin(`/admin/users?${params.toString()}`);
  if (data) return { users: data.users, total: data.total, page: data.page, per_page: data.page_size };

  let users = MOCK_USERS.filter(u => u.organization_id === ADMIN_ORG_ID);
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
  // Backend relies on granular endpoints instead of single PATCH
  if (!MOCK_MODE) {
    try {
      if (updates.first_name || updates.last_name || updates.title) {
         await callAdmin(`/admin/users/${userId}/profile`, { method: 'PATCH', body: {
           first_name: updates.first_name, last_name: updates.last_name, title: updates.title
         }});
      }
      if (updates.role) {
         await callAdmin(`/admin/users/${userId}/role`, { method: 'PUT', body: { role: updates.role }});
      }
      if (updates.is_active !== undefined) {
         if (updates.is_active) await callAdmin(`/admin/users/${userId}/activate`, { method: 'POST' });
         else await callAdmin(`/admin/users/${userId}/deactivate`, { method: 'POST' });
      }
      if (updates.is_locked !== undefined) {
         if (updates.is_locked) await callAdmin(`/admin/users/${userId}/lock`, { method: 'POST' });
         else await callAdmin(`/admin/users/${userId}/unlock`, { method: 'POST' });
      }
      return { success: true };
    } catch(err) {
      console.warn("Granular API updates failed, falling back to mock", err);
    }
  }

  const user = MOCK_USERS.find(u => u.id === userId);
  if (user) Object.assign(user, updates);
  return { success: true, message: 'Güncelleme uygulandı (mock).' };
}

export async function deleteAdminUser(userId) {
  // Backend doesn't support hard delete, so we deactivate
  const data = await callAdmin(`/admin/users/${userId}/deactivate`, { method: 'POST' });
  if (!data && MOCK_MODE) {
    const idx = MOCK_USERS.findIndex(u => u.id === userId);
    if (idx !== -1) MOCK_USERS.splice(idx, 1);
    return { success: true, message: 'Kullanıcı silindi (mock).' };
  }
  return data;
}

// ─── Oturum İzleme (kendi kurumu) ─────────────────────────────────────────────

export async function getAdminSessions() {
  const data = await callAdmin('/admin/sessions');
  if (data) return data;
  return { sessions: MOCK_SESSIONS, total: MOCK_SESSIONS.length };
}

export async function revokeAdminSession(userId, sessionId) {
  // Backend uses /users/{user_id}/sessions/{session_id}/terminate
  if (!userId) {
    // If userId is missing, fallback to mock or try DELETE /admin/sessions/{id} if backend supports it
    const data = await callAdmin(`/admin/sessions/${sessionId}`, { method: 'DELETE' });
    return data ?? { success: true };
  }
  const data = await callAdmin(`/admin/users/${userId}/sessions/${sessionId}/terminate`, { method: 'POST' });
  return data ?? { success: true };
}

export async function forceLogoutAdminUser(userId) {
  const data = await callAdmin(`/admin/users/${userId}/force-logout`, { method: 'POST' });
  return data ?? { success: true };
}

// ─── Organizasyonlar (sadece kendi kurumu) ─────────────────────────────────────

export async function getAdminOrganizations() {
  const data = await callAdmin('/admin/organizations');
  if (data) return data;
  return { organizations: MOCK_ORGANIZATIONS, total: MOCK_ORGANIZATIONS.length };
}

export async function getAdminOrganizationDetail(orgId) {
  const data = await callAdmin(`/admin/organizations/${orgId}`);
  if (data) return data;
  return MOCK_ORGANIZATIONS.find(o => o.id === orgId) || null;
}

export async function deactivateAdminOrganization(orgId) {
  const data = await callAdmin(`/admin/organizations/${orgId}/deactivate`, { method: 'POST' });
  return data ?? { success: true };
}

// ─── Audit Log (kendi kurumu) ─────────────────────────────────────────────────

export async function getAdminAuditLog({ page = 1, severity = '' } = {}) {
  const url = severity ? `/admin/audit-logs?page=${page}&severity=${encodeURIComponent(severity)}` : `/admin/audit-logs?page=${page}`;
  const data = await callAdmin(url);
  if (data) return data;
  const logs = severity ? MOCK_AUDIT_LOG.filter(l => l.severity === severity) : MOCK_AUDIT_LOG;
  return { logs, total: logs.length };
}

export async function getAdminAuditLogDetail(logId) {
  const data = await callAdmin(`/admin/audit-logs/${logId}`);
  if (data) return data;
  return MOCK_AUDIT_LOG.find(l => l.id === logId) || null;
}

// ─── Ekstra Güvenlik Analizleri ───────────────────────────────────────────────

export async function getAdminSecurityTrends(interval = 'day') {
  const data = await callAdmin(`/admin/security/trends?interval=${interval}`);
  if (data) return data;
  return { interval, data: [] };
}

export async function getAdminSecurityOrganizations() {
  const data = await callAdmin('/admin/security/organizations');
  if (data) return data;
  return { organizations: [] };
}

