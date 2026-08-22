/**
 * authService.js — NeuroOncoTrack-AI Frontend Auth Servisi
 *
 * Kapsamlı auth endpoint entegrasyonu:
 *   POST   /api/v1/auth/login             — Giriş (JWT + HTTP-only refresh cookie)
 *   POST   /api/v1/auth/refresh           — Token yenileme
 *   POST   /api/v1/auth/logout            — Çıkış (mevcut oturum)
 *   POST   /api/v1/auth/logout-all        — Tüm oturumlardan çıkış
 *   POST   /api/v1/auth/register          — Yeni kullanıcı kaydı
 *   GET    /api/v1/auth/me                — Profil bilgisi
 *   PATCH  /api/v1/auth/me                — Profil güncelleme
 *   POST   /api/v1/auth/change-password   — Parola değiştirme
 *   POST   /api/v1/auth/forgot-password   — Parola sıfırlama isteği
 *   POST   /api/v1/auth/reset-password    — Parola sıfırlama (token ile)
 *   GET    /api/v1/auth/sessions          — Aktif oturumları listele
 *   DELETE /api/v1/auth/sessions/{id}     — Oturum iptal et
 *   POST   /api/v1/auth/mfa/setup         — MFA kurulumu başlat
 *   POST   /api/v1/auth/mfa/enable        — MFA'yı etkinleştir (TOTP kodu ile)
 *   POST   /api/v1/auth/mfa/verify        — MFA giriş doğrulama
 *   POST   /api/v1/auth/mfa/disable       — MFA'yı devre dışı bırak
 */

import {
  DEFAULT_CLINICAL_USER,
  DEMO_SESSION_HOURS,
  REAL_SESSION_MINUTES,
} from '../config/neuroConstants.js';
import {
  apiClient,
  clearAccessToken,
  isEndpointUnavailable,
  isNetworkUnavailable,
  setAccessToken,
} from './apiClient.js';

// ─── Yardımcı: Yerel Oturum Oluşturma ────────────────────────────────────────

function buildLocalSession({ institutionCode, email, mode = 'local' }) {
  const now = Date.now();
  const durationMs =
    mode === 'demo'
      ? DEMO_SESSION_HOURS * 60 * 60 * 1000
      : REAL_SESSION_MINUTES * 60 * 1000;

  return {
    mode,
    accessToken: null,
    expiresAt: now + durationMs,
    user: {
      ...DEFAULT_CLINICAL_USER,
      email: email || DEFAULT_CLINICAL_USER.email,
      institutionCode: institutionCode || DEFAULT_CLINICAL_USER.institutionCode,
    },
  };
}

// ─── Yardımcı: API'den Gelen Oturum Yanıtını Normalize Et ────────────────────

function normalizeSession(payload, fallback) {
  const user = payload?.user || payload?.profile || payload?.me || {};
  const token =
    payload?.access_token || payload?.accessToken || payload?.token || null;

  // Backend expires_at (ISO datetime) veya expires_in (saniye) döndürebilir
  let expiresAt;
  if (payload?.expires_at) {
    expiresAt = new Date(payload.expires_at).getTime();
  } else {
    const expiresIn = Number(
      payload?.expires_in || payload?.expiresIn || REAL_SESSION_MINUTES * 60,
    );
    expiresAt = Date.now() + expiresIn * 1000;
  }

  if (token) setAccessToken(token);

  return {
    mode: 'api',
    accessToken: token,
    expiresAt,
    user: {
      ...DEFAULT_CLINICAL_USER,
      ...user,
      id: user.id || user.sub || DEFAULT_CLINICAL_USER.id,
      email: user.email || fallback.email,
      name:
        user.full_name ||
        [user.first_name, user.last_name].filter(Boolean).join(' ') ||
        fallback.email,
      title: user.title || DEFAULT_CLINICAL_USER.title,
      role: user.role || DEFAULT_CLINICAL_USER.role,
      institutionCode:
        user.institutionCode ||
        user.organization_code ||
        fallback.institutionCode,
      organization: user.organization_name || DEFAULT_CLINICAL_USER.organization,
      permissions:
        user.permissions || user.perms || DEFAULT_CLINICAL_USER.permissions,
      mfaEnabled: user.mfa_enabled ?? false,
      mustChangePassword: user.must_change_password ?? false,
      lastLoginAt: user.last_login_at || null,
    },
  };
}

// ─── Yardımcı: Backend Session Yanıtını Frontend Formatına Normalize Et ───────

function normalizeSessionItem(s) {
  return {
    id: s.id,
    // Backend: ip / ip_address → her ikisini de destekle
    ip_address: s.ip || s.ip_address || null,
    // Backend: device (parsed string) veya user_agent (raw UA string)
    user_agent: s.user_agent || s.device || null,
    device_fingerprint: s.device_fingerprint || null,
    created_at: s.created_at,
    last_used_at: s.last_used_at,
    expires_at: s.expires_at,
    // Backend: current / is_current → her ikisini de destekle
    is_current: s.current ?? s.is_current ?? false,
  };
}

// ─── AUTH: Giriş ──────────────────────────────────────────────────────────────

/**
 * Kullanıcı girişi.
 *
 * Dönüş:
 *   - mode: 'api'            → Başarılı giriş, session nesnesi döner
 *   - mode: 'mfa'            → MFA doğrulaması gerekli (temporaryToken ile)
 *   - mode: 'password-change'→ Parola değişimi zorunlu
 *   - mode: 'demo'           → Demo oturumu (ağ yoksa bile çalışır)
 *   - mode: 'compat'         → Backend erişilemezse uyumluluk oturumu
 */
export async function login({
  institutionCode,
  email,
  password,
  rememberStation,
  demo = false,
}) {
  if (demo) {
    clearAccessToken();
    return buildLocalSession({ institutionCode, email, mode: 'demo' });
  }

  try {
    // Backend LoginRequest: sadece email + password kabul ediyor
    // institution_code ve remember_station backend şemasında YOK
    const payload = await apiClient.post(
      '/auth/login',
      { email, password },
      { auth: false },
    );

    // HTTP 202 — MFA gerekli
    if (payload?.mfa_required || payload?.mfa_temp_token || payload?.temporary_token) {
      return {
        mode: 'mfa',
        temporaryToken:
          payload.mfa_temp_token || payload.temporary_token,
        user: { ...DEFAULT_CLINICAL_USER, email, institutionCode },
      };
    }

    // Parola değişimi zorunlu
    if (payload?.password_change_required || payload?.must_change_password) {
      return {
        mode: 'password-change',
        user: { ...DEFAULT_CLINICAL_USER, email, institutionCode },
      };
    }

    return normalizeSession(payload, { email, institutionCode });
  } catch (error) {
    if (isEndpointUnavailable(error) || isNetworkUnavailable(error)) {
      return {
        ...buildLocalSession({ institutionCode, email, mode: 'compat' }),
        warning:
          'Kimlik servisi hazır olmadığından frontend uyumluluk oturumu açıldı.',
      };
    }
    throw error;
  }
}

// ─── AUTH: Çıkış ─────────────────────────────────────────────────────────────

/** Mevcut oturumdan çıkış — POST /api/v1/auth/logout (204 No Content) */
export async function logout(session) {
  try {
    if (session?.mode === 'api') {
      await apiClient.post('/auth/logout', null, { responseType: 'text' });
    }
  } catch {
    // Sunucu taraflı çıkış başarısız olsa bile istemci temizlenir.
  } finally {
    clearAccessToken();
  }
}

/** Tüm oturumlardan çıkış — POST /api/v1/auth/logout-all (204 No Content) */
export async function logoutAll(session) {
  try {
    if (session?.mode === 'api') {
      await apiClient.post('/auth/logout-all', null, { responseType: 'text' });
    }
  } catch {
    // Hata olsa bile istemci temizlenir.
  } finally {
    clearAccessToken();
  }
}

// ─── AUTH: Kayıt ─────────────────────────────────────────────────────────────

/**
 * Yeni kullanıcı kaydı — POST /api/v1/auth/register
 *
 * @param {object} params
 * @param {string} params.email
 * @param {string} params.password
 * @param {string} params.firstName
 * @param {string} params.lastName
 * @param {string} [params.title]
 * @param {string} params.organizationId  — UUID formatında organizasyon kimliği
 * @param {string} [params.role]          — Örn: 'PHYSICIAN', 'RADIOLOGIST'
 */
export async function register({
  email,
  password,
  firstName,
  lastName,
  title,
  organizationId,
  role = 'PHYSICIAN',
}) {
  return apiClient.post(
    '/auth/register',
    {
      email,
      password,
      first_name: firstName,
      last_name: lastName,
      title,
      organization_id: organizationId,
      role,
    },
    { auth: false },
  );
}

// ─── AUTH: Profil ─────────────────────────────────────────────────────────────

/** Oturum açmış kullanıcının profili — GET /api/v1/auth/me */
export async function getMe() {
  return apiClient.get('/auth/me');
}

/**
 * Profil güncelleme — PATCH /api/v1/auth/me
 *
 * @param {object} updates  — Sadece değiştirilecek alanlar: firstName, lastName, title, email
 */
export async function updateMe({ firstName, lastName, title, email } = {}) {
  const body = {};
  if (firstName !== undefined) body.first_name = firstName;
  if (lastName !== undefined) body.last_name = lastName;
  if (title !== undefined) body.title = title;
  if (email !== undefined) body.email = email;
  return apiClient.patch('/auth/me', body);
}

// ─── AUTH: Parola İşlemleri ───────────────────────────────────────────────────

/**
 * Parola değiştirme — POST /api/v1/auth/change-password
 *
 * @param {string} currentPassword
 * @param {string} newPassword
 */
export async function changePassword(currentPassword, newPassword) {
  return apiClient.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

/**
 * Parola sıfırlama e-postası gönder — POST /api/v1/auth/forgot-password
 *
 * @param {string} email
 */
export async function forgotPassword(email) {
  return apiClient.post('/auth/forgot-password', { email }, { auth: false });
}

/**
 * Parola sıfırla (e-posta ile gelen token) — POST /api/v1/auth/reset-password
 *
 * @param {string} token       — E-posta ile gelen sıfırlama token'ı
 * @param {string} newPassword
 */
export async function resetPassword(token, newPassword) {
  return apiClient.post(
    '/auth/reset-password',
    { token, new_password: newPassword },
    { auth: false },
  );
}

// ─── AUTH: Oturum Yönetimi ────────────────────────────────────────────────────

/** Aktif oturumları listele — GET /api/v1/auth/sessions */
export async function listSessions() {
  const data = await apiClient.get('/auth/sessions');
  // Backend array veya { sessions: [...] } formatında dönebilir
  const raw = Array.isArray(data) ? data : (data?.sessions || data?.items || []);
  return raw.map(normalizeSessionItem);
}

/**
 * Belirli bir oturumu iptal et — DELETE /api/v1/auth/sessions/{id}
 *
 * @param {string} sessionId — UUID formatında oturum kimliği
 */
export async function revokeSession(sessionId) {
  return apiClient.delete(`/auth/sessions/${sessionId}`, {
    responseType: 'text',
  });
}

// ─── AUTH: MFA (İki Faktörlü Doğrulama) ──────────────────────────────────────

/**
 * MFA kurulumunu başlat — POST /api/v1/auth/mfa/setup
 *
 * Dönen bilgiler: secret (TOTP anahtarı), provisioning_uri (QR), backup_codes
 * MFA bu aşamada henüz etkin değil; /mfa/enable ile onaylanmalı.
 */
export async function mfaSetup() {
  return apiClient.post('/auth/mfa/setup', null);
}

/**
 * MFA'yı etkinleştir — POST /api/v1/auth/mfa/enable
 *
 * @param {string} code — Authenticator uygulamasından alınan 6 haneli TOTP kodu
 */
export async function mfaEnable(code) {
  return apiClient.post('/auth/mfa/enable', { code });
}

/**
 * MFA giriş doğrulaması — POST /api/v1/auth/mfa/verify
 *
 * Login sonrası HTTP 202 alındığında (mfa_temp_token mevcutsa) bu endpoint çağrılır.
 * Başarılıysa tam oturum (access_token + refresh cookie) döner.
 *
 * @param {string} mfaTempToken — Login yanıtındaki geçici token
 * @param {string} code         — TOTP kodu (6 hane) veya yedek kod (8 hane)
 * @param {boolean} [isBackupCode] — true ise yedek kod olarak işlenir
 */
export async function mfaVerify(mfaTempToken, code, isBackupCode = false) {
  const payload = await apiClient.post(
    '/auth/mfa/verify',
    {
      mfa_temp_token: mfaTempToken,
      code,
      is_backup_code: isBackupCode,
    },
    { auth: false },
  );
  return normalizeSession(payload, {});
}

/**
 * MFA'yı devre dışı bırak — POST /api/v1/auth/mfa/disable
 *
 * @param {string} currentPassword — Mevcut hesap parolası (doğrulama için)
 */
export async function mfaDisable(currentPassword) {
  return apiClient.post('/auth/mfa/disable', {
    current_password: currentPassword,
  });
}
