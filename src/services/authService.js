import {
  DEFAULT_CLINICAL_USER,
  DEMO_SESSION_HOURS,
  REAL_SESSION_MINUTES,
} from '../config/neuroConstants.js';
import { apiClient, clearAccessToken, isEndpointUnavailable, isNetworkUnavailable, setAccessToken } from './apiClient.js';

function buildLocalSession({ institutionCode, email, mode = 'local' }) {
  const now = Date.now();
  const durationMs = mode === 'demo' ? DEMO_SESSION_HOURS * 60 * 60 * 1000 : REAL_SESSION_MINUTES * 60 * 1000;

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

function normalizeSession(payload, fallback) {
  const user = payload?.user || payload?.profile || payload?.me || {};
  const token = payload?.access_token || payload?.accessToken || payload?.token || null;
  const expiresIn = Number(payload?.expires_in || payload?.expiresIn || REAL_SESSION_MINUTES * 60);

  if (token) setAccessToken(token);

  return {
    mode: 'api',
    accessToken: token,
    expiresAt: Date.now() + expiresIn * 1000,
    user: {
      ...DEFAULT_CLINICAL_USER,
      ...user,
      id: user.id || user.sub || DEFAULT_CLINICAL_USER.id,
      email: user.email || fallback.email,
      institutionCode: user.institutionCode || user.organization_code || fallback.institutionCode,
      permissions: user.permissions || user.perms || DEFAULT_CLINICAL_USER.permissions,
    },
  };
}

export async function login({ institutionCode, email, password, rememberStation, demo = false }) {
  if (demo) {
    clearAccessToken();
    return buildLocalSession({ institutionCode, email, mode: 'demo' });
  }

  try {
    const payload = await apiClient.post(
      '/auth/login',
      {
        institution_code: institutionCode,
        email,
        password,
        remember_station: rememberStation,
      },
      { auth: false },
    );

    if (payload?.mfa_required || payload?.temporary_token) {
      return {
        mode: 'mfa',
        temporaryToken: payload.temporary_token,
        user: { ...DEFAULT_CLINICAL_USER, email, institutionCode },
      };
    }

    if (payload?.password_change_required) {
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
        warning: 'Kimlik servisi hazır olmadığından frontend uyumluluk oturumu açıldı.',
      };
    }
    throw error;
  }
}

export async function logout(session) {
  try {
    if (session?.mode === 'api') {
      await apiClient.post('/auth/logout', null, { responseType: 'text' });
    }
  } catch {
    // Client state is still cleared even if the server-side logout call fails.
  } finally {
    clearAccessToken();
  }
}
