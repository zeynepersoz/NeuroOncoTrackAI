/**
 * superadminService.js — NeuroOncoTrack-AI Süper Yönetici Servisi
 *
 * SUPERADMIN rolüne sahip kullanıcılar için tüm kurumları kapsayan
 * yönetim endpoint'leri. Backend hazır olduğunda otomatik bağlanır.
 *
 * Beklenen backend endpoint'leri (henüz implement edilmedi):
 *   GET  /api/v1/admin/stats
 *   GET  /api/v1/admin/users
 *   PATCH /api/v1/admin/users/{id}
 *   DELETE /api/v1/admin/users/{id}
 *   GET  /api/v1/admin/organizations
 *   POST /api/v1/admin/organizations
 *   PATCH /api/v1/admin/organizations/{id}
 *   DELETE /api/v1/admin/organizations/{id}
 *   GET  /api/v1/admin/sessions
 *   DELETE /api/v1/admin/sessions/{id}
 *   GET  /api/v1/admin/audit-log
 */

import { apiClient, isEndpointUnavailable } from './apiClient.js';

// Backend superadmin endpoint'leri hazır değilse true yap (manual override)
const MOCK_MODE = false;

// ─── Mock Data (tüm kurumlar) ──────────────────────────────────────────────────

export const MOCK_ALL_ORGANIZATIONS = [
  { id: 'o1', name: 'NeuroOncoTrack Merkezi', code: 'NOT-2026', org_type: 'RESEARCH_CENTER', is_active: true, user_count: 5, admin_email: 'admin@neuroonco.ai', created_at: '2026-01-01T00:00:00Z', description: 'Platform merkez kurumu' },
  { id: 'o2', name: 'Hacettepe Üniversitesi Tıp Fakültesi', code: 'HU-TIP', org_type: 'UNIVERSITY_HOSPITAL', is_active: true, user_count: 7, admin_email: 'admin@hacettepe.edu.tr', created_at: '2026-01-20T00:00:00Z', description: 'Tıp Fakültesi Radyoloji Bölümü' },
  { id: 'o3', name: 'Gazi Üniversitesi Hastanesi', code: 'GAZI-H', org_type: 'UNIVERSITY_HOSPITAL', is_active: true, user_count: 4, admin_email: 'admin@gazi.edu.tr', created_at: '2026-02-05T00:00:00Z', description: 'Nöroloji ve Radyoloji Klinikleri' },
  { id: 'o4', name: 'Teknofest AI Araştırma', code: 'TF-AI', org_type: 'RESEARCH_CENTER', is_active: false, user_count: 2, admin_email: 'admin@teknofest.ai', created_at: '2026-03-10T00:00:00Z', description: 'Pasifleştirildi - bütçe nedeniyle' },
  { id: 'o5', name: 'Ege Üniversitesi Tıp', code: 'EGE-TIP', org_type: 'UNIVERSITY_HOSPITAL', is_active: true, user_count: 3, admin_email: 'admin@ege.edu.tr', created_at: '2026-04-01T00:00:00Z', description: '' },
  { id: 'o6', name: 'İTÜ Biyomedikal Araştırma', code: 'ITU-BIO', org_type: 'RESEARCH_CENTER', is_active: true, user_count: 6, admin_email: 'admin@itu.edu.tr', created_at: '2026-04-15T00:00:00Z', description: 'Biyomedikal görüntüleme AR-GE' },
];

export const MOCK_ALL_USERS = [
  // NeuroOncoTrack Merkezi (o1)
  { id: '1', email: 'superadmin@neuroonco.ai', first_name: 'Süper', last_name: 'Yönetici', role: 'SUPER_ADMIN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o1', organization_name: 'NeuroOncoTrack Merkezi', last_login_at: new Date(Date.now() - 30 * 60000).toISOString(), created_at: '2026-01-01T00:00:00Z', failed_login_attempts: 0 },
  { id: '2', email: 'admin@neuroonco.ai', first_name: 'Sistem', last_name: 'Yöneticisi', role: 'HOSPITAL_ADMIN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o1', organization_name: 'NeuroOncoTrack Merkezi', last_login_at: new Date(Date.now() - 1 * 3600000).toISOString(), created_at: '2026-01-15T10:00:00Z', failed_login_attempts: 0 },
  { id: '3', email: 'researcher1@neuroonco.ai', first_name: 'Kadir', last_name: 'Doğan', title: 'Dr.', role: 'RESEARCHER', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_id: 'o1', organization_name: 'NeuroOncoTrack Merkezi', last_login_at: new Date(Date.now() - 4 * 3600000).toISOString(), created_at: '2026-01-20T09:00:00Z', failed_login_attempts: 0 },
  // Hacettepe (o2)
  { id: '4', email: 'drcelik@hacettepe.edu.tr', first_name: 'Ayşe', last_name: 'Çelik', title: 'Prof. Dr.', role: 'RADIOLOGIST', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o2', organization_name: 'Hacettepe Üniversitesi Tıp Fakültesi', last_login_at: new Date(Date.now() - 2 * 3600000).toISOString(), created_at: '2026-02-10T09:00:00Z', failed_login_attempts: 0 },
  { id: '5', email: 'drkorkmaz@hacettepe.edu.tr', first_name: 'Tarık', last_name: 'Korkmaz', title: 'Doç. Dr.', role: 'PHYSICIAN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o2', organization_name: 'Hacettepe Üniversitesi Tıp Fakültesi', last_login_at: new Date(Date.now() - 6 * 3600000).toISOString(), created_at: '2026-02-15T10:00:00Z', failed_login_attempts: 0 },
  { id: '6', email: 'admin.hacettepe@hacettepe.edu.tr', first_name: 'Hacettepe', last_name: 'Admin', role: 'HOSPITAL_ADMIN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o2', organization_name: 'Hacettepe Üniversitesi Tıp Fakültesi', last_login_at: new Date(Date.now() - 5 * 3600000).toISOString(), created_at: '2026-01-20T00:00:00Z', failed_login_attempts: 0 },
  // Gazi (o3)
  { id: '7', email: 'drdemir@gazi.edu.tr', first_name: 'Mehmet', last_name: 'Demir', title: 'Doç. Dr.', role: 'PHYSICIAN', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_id: 'o3', organization_name: 'Gazi Üniversitesi Hastanesi', last_login_at: new Date(Date.now() - 5 * 3600000).toISOString(), created_at: '2026-02-20T11:00:00Z', failed_login_attempts: 1 },
  { id: '8', email: 'drsahin@gazi.edu.tr', first_name: 'Elif', last_name: 'Şahin', title: 'Uz. Dr.', role: 'RADIOLOGIST', is_active: true, is_locked: false, mfa_enabled: false, must_change_password: false, organization_id: 'o3', organization_name: 'Gazi Üniversitesi Hastanesi', last_login_at: new Date(Date.now() - 24 * 3600000).toISOString(), created_at: '2026-03-01T09:00:00Z', failed_login_attempts: 0 },
  // Ege (o4 - pasif)
  { id: '9', email: 'dryilmaz@ege.edu.tr', first_name: 'Fatma', last_name: 'Yılmaz', title: 'Dr.', role: 'PHYSICIAN', is_active: true, is_locked: true, mfa_enabled: false, must_change_password: false, organization_id: 'o5', organization_name: 'Ege Üniversitesi Tıp', last_login_at: new Date(Date.now() - 48 * 3600000).toISOString(), created_at: '2026-03-01T08:00:00Z', failed_login_attempts: 5 },
  // İTÜ (o6)
  { id: '10', email: 'drarslan@itu.edu.tr', first_name: 'Can', last_name: 'Arslan', title: 'Uz. Dr.', role: 'RESEARCHER', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o6', organization_name: 'İTÜ Biyomedikal Araştırma', last_login_at: new Date(Date.now() - 12 * 3600000).toISOString(), created_at: '2026-03-15T14:00:00Z', failed_login_attempts: 0 },
  { id: '11', email: 'drkaya@itu.edu.tr', first_name: 'Zeynep', last_name: 'Kaya', title: 'Prof. Dr.', role: 'PHYSICIAN', is_active: true, is_locked: false, mfa_enabled: true, must_change_password: false, organization_id: 'o6', organization_name: 'İTÜ Biyomedikal Araştırma', last_login_at: new Date(Date.now() - 30 * 60000).toISOString(), created_at: '2026-03-20T10:00:00Z', failed_login_attempts: 0 },
  { id: '12', email: 'droz@gazi.edu.tr', first_name: 'Murat', last_name: 'Öz', title: 'Dr.', role: 'PHYSICIAN', is_active: false, is_locked: false, mfa_enabled: false, must_change_password: true, organization_id: 'o3', organization_name: 'Gazi Üniversitesi Hastanesi', last_login_at: null, created_at: '2026-04-01T13:00:00Z', failed_login_attempts: 0 },
];

const MOCK_SUPER_STATS = {
  total_users: 12,
  active_users: 10,
  locked_users: 1,
  inactive_users: 1,
  mfa_enabled_count: 7,
  mfa_adoption_rate: 58,
  active_sessions: 12,
  total_organizations: MOCK_ALL_ORGANIZATIONS.length,
  active_organizations: MOCK_ALL_ORGANIZATIONS.filter(o => o.is_active).length,
  new_users_last_30d: 5,
  failed_logins_last_24h: 7,
};

const MOCK_SUPER_SESSIONS = [
  { id: 'ss1', user_email: 'drcelik@hacettepe.edu.tr', user_name: 'Ayşe Çelik', organization_name: 'Hacettepe Üniversitesi', ip_address: '193.140.12.55', user_agent: 'Mozilla/5.0 (Windows NT 10.0) Chrome/126', created_at: new Date(Date.now() - 2 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 5 * 60000).toISOString(), expires_at: new Date(Date.now() + 5 * 3600000).toISOString() },
  { id: 'ss2', user_email: 'superadmin@neuroonco.ai', user_name: 'Süper Yönetici', organization_name: 'NeuroOncoTrack Merkezi', ip_address: '127.0.0.1', user_agent: 'Mozilla/5.0 (Macintosh) Safari/17', created_at: new Date(Date.now() - 30 * 60000).toISOString(), last_used_at: new Date(Date.now() - 1 * 60000).toISOString(), expires_at: new Date(Date.now() + 6 * 3600000).toISOString() },
  { id: 'ss3', user_email: 'drdemir@gazi.edu.tr', user_name: 'Mehmet Demir', organization_name: 'Gazi Üniversitesi', ip_address: '212.175.88.12', user_agent: 'Mozilla/5.0 (X11; Linux) Firefox/127', created_at: new Date(Date.now() - 5 * 3600000).toISOString(), last_used_at: new Date(Date.now() - 20 * 60000).toISOString(), expires_at: new Date(Date.now() + 2 * 3600000).toISOString() },
];

const MOCK_SUPER_AUDIT = [
  { id: 'sa1', timestamp: new Date(Date.now() - 5 * 60000).toISOString(), user_email: 'drkaya@itu.edu.tr', organization_name: 'İTÜ Biyomedikal', action: 'LOGIN_SUCCESS', detail: 'IP: 31.223.66.77', severity: 'info' },
  { id: 'sa2', timestamp: new Date(Date.now() - 12 * 60000).toISOString(), user_email: 'dryilmaz@ege.edu.tr', organization_name: 'Ege Üniversitesi', action: 'LOGIN_FAILED', detail: 'Geçersiz şifre (5. deneme) — Hesap kilitlendi', severity: 'danger' },
  { id: 'sa3', timestamp: new Date(Date.now() - 1 * 3600000).toISOString(), user_email: 'superadmin@neuroonco.ai', organization_name: 'NeuroOncoTrack Merkezi', action: 'ORG_CREATED', detail: 'Yeni kurum eklendi: Ege Üniversitesi Tıp', severity: 'success' },
  { id: 'sa4', timestamp: new Date(Date.now() - 3 * 3600000).toISOString(), user_email: 'superadmin@neuroonco.ai', organization_name: 'NeuroOncoTrack Merkezi', action: 'ORG_DEACTIVATED', detail: 'TF-AI organizasyonu pasifleştirildi', severity: 'warning' },
  { id: 'sa5', timestamp: new Date(Date.now() - 5 * 3600000).toISOString(), user_email: 'admin.hacettepe@hacettepe.edu.tr', organization_name: 'Hacettepe Üniversitesi', action: 'USER_LOCKED', detail: 'drkorkmaz@hacettepe kilitlendi', severity: 'warning' },
];

// ─── Yardımcı ──────────────────────────────────────────────────────────────────

async function callSuperAdmin(path, options = {}) {
  if (MOCK_MODE) return null;
  try {
    if (options.method === 'DELETE') return await apiClient.delete(path);
    if (options.method === 'PATCH') return await apiClient.patch(path, options.body);
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

// ─── İstatistikler (tüm kurumlar) ─────────────────────────────────────────────

export async function getSuperAdminStats() {
  const data = await callSuperAdmin('/admin/security/overview');
  if (data) {
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
  return MOCK_SUPER_STATS;
}

// ─── Kullanıcı Yönetimi (tüm kurumlar) ────────────────────────────────────────

export async function getSuperAdminUsers({
  page = 1,
  search = '',
  role = '',
  status = '',
  organizationId = '',
} = {}) {
  const params = new URLSearchParams({ page, page_size: 50 });
  if (search) params.append('search', search);
  if (role) params.append('role', role);
  if (status) params.append('status', status);
  if (organizationId) params.append('organization_id', organizationId);
  
  const data = await callSuperAdmin(`/admin/users?${params.toString()}`);
  if (data) return data;

  // Mock filtrele
  let users = [...MOCK_ALL_USERS];
  if (organizationId) users = users.filter(u => u.organization_id === organizationId);
  if (search) {
    const q = search.toLowerCase();
    users = users.filter(u =>
      u.email.toLowerCase().includes(q) ||
      `${u.first_name} ${u.last_name}`.toLowerCase().includes(q) ||
      (u.organization_name || '').toLowerCase().includes(q)
    );
  }
  if (role) users = users.filter(u => u.role === role);
  if (status === 'active') users = users.filter(u => u.is_active && !u.is_locked);
  if (status === 'locked') users = users.filter(u => u.is_locked);
  if (status === 'inactive') users = users.filter(u => !u.is_active);
  return { users, total: users.length, page: 1, per_page: 100 };
}

export async function patchSuperAdminUser(userId, updates) {
  if (!MOCK_MODE) {
    try {
      if (updates.first_name || updates.last_name || updates.title) {
         await callSuperAdmin(`/admin/users/${userId}/profile`, { method: 'PATCH', body: {
           first_name: updates.first_name, last_name: updates.last_name, title: updates.title
         }});
      }
      if (updates.role) {
         await callSuperAdmin(`/admin/users/${userId}/role`, { method: 'PUT', body: { role: updates.role }});
      }
      if (updates.is_active !== undefined) {
         if (updates.is_active) await callSuperAdmin(`/admin/users/${userId}/activate`, { method: 'POST' });
         else await callSuperAdmin(`/admin/users/${userId}/deactivate`, { method: 'POST' });
      }
      if (updates.is_locked !== undefined) {
         if (updates.is_locked) await callSuperAdmin(`/admin/users/${userId}/lock`, { method: 'POST' });
         else await callSuperAdmin(`/admin/users/${userId}/unlock`, { method: 'POST' });
      }
      return { success: true };
    } catch(err) {
      console.warn("Granular API updates failed, falling back to mock", err);
    }
  }
  const user = MOCK_ALL_USERS.find(u => u.id === userId);
  if (user) Object.assign(user, updates);
  return { success: true, message: 'Güncelleme uygulandı (mock).' };
}

export async function deleteSuperAdminUser(userId) {
  const data = await callSuperAdmin(`/admin/users/${userId}/deactivate`, { method: 'POST' });
  if (!data && MOCK_MODE) {
    const idx = MOCK_ALL_USERS.findIndex(u => u.id === userId);
    if (idx !== -1) MOCK_ALL_USERS.splice(idx, 1);
    return { success: true, message: 'Kullanıcı silindi (mock).' };
  }
  return data;
}

export async function forceLogoutSuperAdminUser(userId) {
  const data = await callSuperAdmin(`/admin/users/${userId}/force-logout`, { method: 'POST' });
  return data ?? { success: true };
}

// ─── Organizasyon Yönetimi ────────────────────────────────────────────────────

export async function getSuperAdminOrganizations({ search = '' } = {}) {
  const url = search ? `/admin/organizations?search=${encodeURIComponent(search)}` : '/admin/organizations';
  const data = await callSuperAdmin(url);
  if (data) return data;
  let orgs = [...MOCK_ALL_ORGANIZATIONS];
  if (search) {
    const q = search.toLowerCase();
    orgs = orgs.filter(o =>
      o.name.toLowerCase().includes(q) ||
      o.code.toLowerCase().includes(q)
    );
  }
  return { organizations: orgs, total: orgs.length };
}

export async function createSuperAdminOrganization(orgData) {
  const data = await callSuperAdmin('/admin/organizations', { method: 'POST', body: orgData });
  if (!data) {
    const newOrg = {
      id: `o${Date.now()}`,
      ...orgData,
      is_active: true,
      user_count: 0,
      created_at: new Date().toISOString(),
    };
    MOCK_ALL_ORGANIZATIONS.push(newOrg);
    return newOrg;
  }
  return data;
}

export async function patchSuperAdminOrganization(orgId, updates) {
  const data = await callSuperAdmin(`/admin/organizations/${orgId}`, { method: 'PATCH', body: updates });
  if (!data) {
    const org = MOCK_ALL_ORGANIZATIONS.find(o => o.id === orgId);
    if (org) Object.assign(org, updates);
    return { success: true, message: 'Kurum güncellendi (mock).' };
  }
  return data;
}

export async function deactivateSuperAdminOrganization(orgId) {
  const data = await callSuperAdmin(`/admin/organizations/${orgId}/deactivate`, { method: 'POST' });
  return data ?? { success: true };
}

export async function deleteSuperAdminOrganization(orgId) {
  const data = await callSuperAdmin(`/admin/organizations/${orgId}/deactivate`, { method: 'POST' });
  if (!data && MOCK_MODE) {
    const idx = MOCK_ALL_ORGANIZATIONS.findIndex(o => o.id === orgId);
    if (idx !== -1) MOCK_ALL_ORGANIZATIONS.splice(idx, 1);
    return { success: true, message: 'Kurum silindi (mock).' };
  }
  return data;
}

export async function getSuperAdminOrganizationDetail(orgId) {
  const data = await callSuperAdmin(`/admin/organizations/${orgId}`);
  if (data) return data;
  return MOCK_ALL_ORGANIZATIONS.find(o => o.id === orgId) || null;
}

// ─── Oturum Yönetimi ──────────────────────────────────────────────────────────

export async function getSuperAdminSessions({ organizationId = '' } = {}) {
  const data = await callSuperAdmin('/admin/sessions');
  if (data) return data;
  let sessions = [...MOCK_SUPER_SESSIONS];
  if (organizationId) {
    // mock sessions filter
    const orgUsers = MOCK_ALL_USERS.filter(u => u.organization_id === organizationId).map(u => u.email);
    sessions = sessions.filter(s => orgUsers.includes(s.user_email));
  }
  return { sessions, total: sessions.length };
}

export async function revokeSuperAdminSession(userId, sessionId) {
  if (!userId) {
    const data = await callSuperAdmin(`/admin/sessions/${sessionId}`, { method: 'DELETE' });
    return data ?? { success: true };
  }
  const data = await callSuperAdmin(`/admin/users/${userId}/sessions/${sessionId}/terminate`, { method: 'POST' });
  return data ?? { success: true };
}

// ─── Denetim Kayıtları (Audit Log) ────────────────────────────────────────────

export async function getSuperAdminAuditLog({ page = 1, severity = '', organizationId = '' } = {}) {
  const params = new URLSearchParams({ page });
  if (severity) params.append('severity', severity);
  if (organizationId) params.append('organization_id', organizationId);
  const data = await callSuperAdmin(`/admin/audit-logs?${params.toString()}`);
  if (data) return data;
  let logs = [...MOCK_SUPER_AUDIT];
  if (severity) logs = logs.filter(l => l.severity === severity);
  return { logs, total: logs.length };
}

export async function getSuperAdminAuditLogDetail(logId) {
  const data = await callSuperAdmin(`/admin/audit-logs/${logId}`);
  if (data) return data;
  return MOCK_SUPER_AUDIT_LOG.find(l => l.id === logId) || null;
}

export async function getSuperAdminSecurityTrends(interval = 'day') {
  const data = await callSuperAdmin(`/admin/security/trends?interval=${interval}`);
  if (data) return data;
  return { interval, data: [] };
}

export async function getSuperAdminSecurityOrganizations() {
  const data = await callSuperAdmin('/admin/security/organizations');
  if (data) return data;
  return { organizations: [] };
}


