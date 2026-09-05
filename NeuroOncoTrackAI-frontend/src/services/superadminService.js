/**
 * superadminService.js — NeuroOncoTrack-AI Süper Yönetici Servisi
 *
 * SUPERADMIN rolüne sahip kullanıcılar için tüm kurumları kapsayan
 * yönetim endpoint'leri.
 *
 * Gerçek Backend Endpoint'leri:
 *   GET    /api/v1/admin/security/overview
 *   GET    /api/v1/admin/users
 *   PATCH  /api/v1/admin/users/{id}/profile
 *   PUT    /api/v1/admin/users/{id}/role
 *   POST   /api/v1/admin/users/{id}/activate
 *   POST   /api/v1/admin/users/{id}/deactivate
 *   POST   /api/v1/admin/users/{id}/lock
 *   POST   /api/v1/admin/users/{id}/unlock
 *   POST   /api/v1/admin/users/{id}/force-logout
 *   GET    /api/v1/admin/organizations
 *   POST   /api/v1/admin/organizations
 *   PATCH  /api/v1/admin/organizations/{id}
 *   POST   /api/v1/admin/organizations/{id}/deactivate
 *   GET    /api/v1/admin/sessions
 *   DELETE /api/v1/admin/sessions/{id}
 *   POST   /api/v1/admin/users/{userId}/sessions/{sessionId}/terminate
 *   GET    /api/v1/admin/audit-logs
 *   GET    /api/v1/admin/audit-logs/{id}
 *   GET    /api/v1/admin/security/trends
 *   GET    /api/v1/admin/security/organizations
 */

import { apiClient } from './apiClient.js';

// ─── Yardımcı API Çağrıcı ──────────────────────────────────────────────────────

async function callSuperAdmin(path, options = {}) {
  try {
    if (options.method === 'DELETE') return await apiClient.delete(path);
    if (options.method === 'PATCH') return await apiClient.patch(path, options.body);
    if (options.method === 'PUT') return await apiClient.put(path, options.body);
    if (options.method === 'POST') return await apiClient.post(path, options.body);
    return await apiClient.get(path);
  } catch (error) {
    console.error(`SuperAdmin API Error (${path}):`, error);
    throw error;
  }
}

// ─── İstatistikler (tüm kurumlar) ─────────────────────────────────────────────

export async function getSuperAdminStats() {
  const data = await callSuperAdmin('/admin/security/overview');
  if (data) {
    const totalUsers = data.users?.total ?? 0;
    const activeUsers = data.users?.active ?? 0;
    const mfaCount = data.users?.mfa_enabled ?? 0;
    const mfaRate = data.users?.mfa_adoption_rate ?? (totalUsers > 0 ? Math.round((mfaCount / totalUsers) * 100) : 0);

    return {
      total_users: totalUsers,
      active_users: activeUsers,
      locked_users: data.users?.locked ?? 0,
      inactive_users: data.users?.inactive ?? 0,
      mfa_enabled_count: mfaCount,
      mfa_adoption_rate: mfaRate,
      active_sessions: data.sessions?.active ?? 0,
      total_organizations: data.organizations?.total ?? 0,
      active_organizations: data.organizations?.active ?? 0,
      new_users_last_30d: 0,
      failed_logins_last_24h: data.security_events?.failed_logins ?? 0,
    };
  }
  return {
    total_users: 0,
    active_users: 0,
    locked_users: 0,
    inactive_users: 0,
    mfa_enabled_count: 0,
    mfa_adoption_rate: 0,
    active_sessions: 0,
    total_organizations: 0,
    active_organizations: 0,
    new_users_last_30d: 0,
    failed_logins_last_24h: 0,
  };
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
  if (status === 'active') params.append('is_active', 'true');
  if (status === 'inactive') params.append('is_active', 'false');
  if (status === 'locked') params.append('is_locked', 'true');
  if (organizationId) params.append('organization_id', organizationId);

  const data = await callSuperAdmin(`/admin/users?${params.toString()}`);
  return {
    users: data?.items || data?.users || [],
    total: data?.total ?? 0,
    page: data?.page ?? 1,
    per_page: data?.page_size ?? 50,
  };
}

export async function patchSuperAdminUser(userId, updates) {
  if (updates.first_name || updates.last_name || updates.title) {
    await callSuperAdmin(`/admin/users/${userId}/profile`, {
      method: 'PATCH',
      body: {
        first_name: updates.first_name,
        last_name: updates.last_name,
        title: updates.title,
      },
    });
  }
  if (updates.role) {
    await callSuperAdmin(`/admin/users/${userId}/role`, {
      method: 'PUT',
      body: { role: updates.role },
    });
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
}

export async function deleteSuperAdminUser(userId) {
  return await callSuperAdmin(`/admin/users/${userId}/deactivate`, { method: 'POST' });
}

export async function forceLogoutSuperAdminUser(userId) {
  return await callSuperAdmin(`/admin/users/${userId}/force-logout`, { method: 'POST' });
}

// ─── Organizasyon Yönetimi ────────────────────────────────────────────────────

export async function getSuperAdminOrganizations({ search = '' } = {}) {
  const url = search ? `/admin/organizations?search=${encodeURIComponent(search)}` : '/admin/organizations';
  const data = await callSuperAdmin(url);
  return {
    organizations: data?.items || data?.organizations || [],
    total: data?.total ?? 0,
  };
}

export async function createSuperAdminOrganization(orgData) {
  return await callSuperAdmin('/admin/organizations', { method: 'POST', body: orgData });
}

export async function patchSuperAdminOrganization(orgId, updates) {
  return await callSuperAdmin(`/admin/organizations/${orgId}`, { method: 'PATCH', body: updates });
}

export async function deactivateSuperAdminOrganization(orgId) {
  return await callSuperAdmin(`/admin/organizations/${orgId}/deactivate`, { method: 'POST' });
}

export async function deleteSuperAdminOrganization(orgId) {
  return await callSuperAdmin(`/admin/organizations/${orgId}/deactivate`, { method: 'POST' });
}

export async function getSuperAdminOrganizationDetail(orgId) {
  return await callSuperAdmin(`/admin/organizations/${orgId}`);
}

// ─── Oturum Yönetimi ──────────────────────────────────────────────────────────

export async function getSuperAdminSessions({ organizationId = '' } = {}) {
  const url = organizationId
    ? `/admin/sessions?organization_id=${encodeURIComponent(organizationId)}`
    : '/admin/sessions';
  const data = await callSuperAdmin(url);
  return {
    sessions: data?.items || data?.sessions || [],
    total: data?.total ?? 0,
  };
}

export async function revokeSuperAdminSession(userId, sessionId) {
  if (!userId) {
    return await callSuperAdmin(`/admin/sessions/${sessionId}`, { method: 'DELETE' });
  }
  return await callSuperAdmin(`/admin/users/${userId}/sessions/${sessionId}/terminate`, { method: 'POST' });
}

// ─── Denetim Kayıtları (Audit Log) ────────────────────────────────────────────

export async function getSuperAdminAuditLog({ page = 1, severity = '', organizationId = '' } = {}) {
  const params = new URLSearchParams({ page });
  if (severity) params.append('severity', severity);
  if (organizationId) params.append('organization_id', organizationId);
  const data = await callSuperAdmin(`/admin/audit-logs?${params.toString()}`);
  return {
    logs: data?.items || data?.logs || [],
    total: data?.total ?? 0,
  };
}

export async function getSuperAdminAuditLogDetail(logId) {
  return await callSuperAdmin(`/admin/audit-logs/${logId}`);
}

export async function getSuperAdminSecurityTrends(interval = 'day') {
  const data = await callSuperAdmin(`/admin/security/trends?interval=${interval}`);
  return data || { interval, data: [] };
}

export async function getSuperAdminSecurityOrganizations() {
  const data = await callSuperAdmin('/admin/security/organizations');
  return data || { organizations: [] };
}
