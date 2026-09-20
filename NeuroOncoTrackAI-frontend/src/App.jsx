import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  CheckCircle,
  Cpu,
  Database,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  Mail,
  RefreshCw,
  Settings,
  ShieldAlert,
  ShieldCheck,
  User,
} from 'lucide-react';
import heroImage from './assets/login-workstation.png';
import {
  capabilities,
  IDLE_WARNING_MINUTES,
  loginMetrics,
  REAL_SESSION_MINUTES,
} from './config/neuroConstants.js';
import ThemeToggle from './components/common/ThemeToggle.jsx';
import ProductWorkspace from './components/workspace/ProductWorkspace.jsx';
import AdminDashboard from './components/admin/AdminDashboard.jsx';
import { getInitialTheme } from './utils/neuroUtils.js';
import {
  changePassword,
  forgotPassword,
  login,
  logout,
  mfaVerify,
  resetPassword,
  register,
} from './services/authService.js';
import { setAccessToken } from './services/apiClient.js';

const activityEvents = ['pointerdown', 'keydown', 'wheel', 'touchstart'];

// ─── MFA Doğrulama Ekranı ────────────────────────────────────────────────────

function MfaScreen({ mfaState, onSuccess, onBack }) {
  const [code, setCode] = useState('');
  const [isBackupCode, setIsBackupCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setError('');
    try {
      const session = await mfaVerify(mfaState.temporaryToken, code.trim(), isBackupCode);
      onSuccess(session);
    } catch (err) {
      setError(err.message || 'MFA doğrulama başarısız.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="mfa-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>İki faktörlü doğrulama</span>
          </div>
        </header>

        <div className="auth-heading-row">
          <div className="auth-copy">
            <span className="eyebrow">Güvenli doğrulama</span>
            <h1 id="mfa-title">Kimlik doğrulama</h1>
          </div>
        </div>

        <form className="login-panel" onSubmit={handleSubmit}>
          <p style={{ marginBottom: '1rem', opacity: 0.75, fontSize: '0.875rem' }}>
            Authenticator uygulamanızdaki 6 haneli kodu girin.
            Erişiminiz yoksa yedek kodunuzu kullanabilirsiniz.
          </p>

          <label className="field-group">
            <span>{isBackupCode ? 'Yedek kod (8 hane)' : 'TOTP kodu (6 hane)'}</span>
            <div className="input-shell">
              <ShieldCheck size={18} />
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="one-time-code"
                placeholder={isBackupCode ? 'XXXXXXXX' : '000000'}
                maxLength={isBackupCode ? 8 : 6}
                inputMode="numeric"
                autoFocus
              />
            </div>
          </label>

          <label className="check-row">
            <input
              type="checkbox"
              checked={isBackupCode}
              onChange={(e) => {
                setIsBackupCode(e.target.checked);
                setCode('');
              }}
            />
            <span>Yedek kod kullan</span>
          </label>

          {error && (
            <div className="form-alert error" role="alert">
              <ShieldAlert size={18} />
              <span>{error}</span>
            </div>
          )}

          <div className="action-row">
            <button className="primary-action" type="submit" disabled={loading || !code.trim()}>
              {loading ? <RefreshCw className="spin" size={18} /> : <CheckCircle size={18} />}
              {loading ? 'Doğrulanıyor' : 'Doğrula'}
            </button>
            <button className="secondary-action" type="button" onClick={onBack}>
              <Activity size={18} />
              Geri dön
            </button>
          </div>
        </form>

        <div className="compliance-strip">
          <span><ShieldAlert size={16} /> TOTP (RFC 6238)</span>
          <span><Database size={16} /> RS256 JWT</span>
          <span><Settings size={16} /> Audit-ready</span>
        </div>
      </section>

      <section className="visual-side visual-abstract" aria-hidden="true">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />
      </section>
    </main>
  );
}

// ─── Parola Değiştirme Ekranı ─────────────────────────────────────────────────

function ChangePasswordScreen({ onSuccess, onBack }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!current || !next || !confirm) {
      setError('Tüm alanları doldurun.');
      return;
    }
    if (next !== confirm) {
      setError('Yeni parolalar eşleşmiyor.');
      return;
    }
    if (next.length < 12) {
      setError('Yeni parola en az 12 karakter olmalıdır.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await changePassword(current, next);
      setSuccess('Parola başarıyla değiştirildi. Yeni parolanızla giriş yapabilirsiniz.');
    } catch (err) {
      setError(err.message || 'Parola değiştirme başarısız.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <main className="login-shell">
        <section className="auth-side" aria-labelledby="cp-title">
          <header className="brand-row">
            <div>
              <strong>NeuroOncoTrack-AI</strong>
              <span>Parola değiştirildi</span>
            </div>
          </header>
          <div className="auth-heading-row">
            <div className="auth-copy">
              <span className="eyebrow">Başarılı</span>
              <h1 id="cp-title">Parola güncellendi</h1>
            </div>
          </div>
          <div className="login-panel">
            <div className="form-alert success" role="status">
              <CheckCircle size={18} />
              <span>{success}</span>
            </div>
            <div className="action-row" style={{ marginTop: '1.5rem' }}>
              <button className="primary-action" type="button" onClick={onBack}>
                <CheckCircle size={18} />
                Giriş ekranına dön
              </button>
            </div>
          </div>
        </section>
        <section className="visual-side visual-abstract" aria-hidden="true">
          <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
          <div className="visual-scrim" aria-hidden="true" />
        </section>
      </main>
    );
  }

  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="cp-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>Parola değiştirme zorunlu</span>
          </div>
        </header>
        <div className="auth-heading-row">
          <div className="auth-copy">
            <span className="eyebrow">Hesap güvenliği</span>
            <h1 id="cp-title">Parola değiştir</h1>
          </div>
        </div>
        <form className="login-panel" onSubmit={handleSubmit}>
          <label className="field-group">
            <span>Mevcut parola</span>
            <div className="input-shell">
              <Lock size={18} />
              <input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </div>
          </label>
          <label className="field-group">
            <span>Yeni parola (en az 12 karakter)</span>
            <div className="input-shell">
              <KeyRound size={18} />
              <input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                autoComplete="new-password"
                placeholder="••••••••••••"
              />
            </div>
          </label>
          <label className="field-group">
            <span>Yeni parolayı tekrar girin</span>
            <div className="input-shell">
              <KeyRound size={18} />
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                placeholder="••••••••••••"
              />
            </div>
          </label>
          {error && (
            <div className="form-alert error" role="alert">
              <ShieldAlert size={18} />
              <span>{error}</span>
            </div>
          )}
          <div className="action-row">
            <button className="primary-action" type="submit" disabled={loading}>
              {loading ? <RefreshCw className="spin" size={18} /> : <CheckCircle size={18} />}
              {loading ? 'Değiştiriliyor' : 'Parolayı değiştir'}
            </button>
            <button className="secondary-action" type="button" onClick={onBack}>
              <Activity size={18} />
              Geri dön
            </button>
          </div>
        </form>
      </section>
      <section className="visual-side visual-abstract" aria-hidden="true">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />
      </section>
    </main>
  );
}

// ─── Parola Sıfırlama Ekranı ──────────────────────────────────────────────────

function ForgotPasswordScreen({ onBack, onGoToSetPassword }) {
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [step, setStep] = useState('request'); // 'request' | 'reset'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleRequest = async (event) => {
    event.preventDefault();
    if (!email.trim()) { setError('E-posta adresinizi girin.'); return; }
    setLoading(true); setError('');
    try {
      await forgotPassword(email.trim());
      setSuccess('Sıfırlama bağlantısı e-posta adresinize gönderildi (mevcut hesapsa).');
      setStep('reset');
    } catch (err) {
      setError(err.message || 'İstek gönderilemedi.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (event) => {
    event.preventDefault();
    if (!token.trim() || !newPassword) { setError('Tüm alanları doldurun.'); return; }
    if (newPassword.length < 12) { setError('Parola en az 12 karakter olmalıdır.'); return; }
    setLoading(true); setError('');
    try {
      await resetPassword(token.trim(), newPassword);
      setSuccess('Parola başarıyla sıfırlandı. Yeni parolanızla giriş yapabilirsiniz.');
    } catch (err) {
      setError(err.message || 'Parola sıfırlanamadı.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="fp-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>Parola sıfırlama</span>
          </div>
        </header>
        <div className="auth-heading-row">
          <div className="auth-copy">
            <span className="eyebrow">{step === 'request' ? 'Hesap erişimi' : 'Yeni parola'}</span>
            <h1 id="fp-title">{step === 'request' ? 'Parolayı sıfırla' : 'Parola yenile'}</h1>
          </div>
        </div>

        {success && step === 'reset' && !error ? (
          <div className="login-panel">
            <div className="form-alert success" role="status">
              <CheckCircle size={18} />
              <span>{success}</span>
            </div>
            <div className="action-row" style={{ marginTop: '1.5rem' }}>
              <button className="primary-action" type="button" onClick={onBack}>
                <CheckCircle size={18} />
                Giriş ekranına dön
              </button>
            </div>
          </div>
        ) : step === 'request' ? (
          <form className="login-panel" onSubmit={handleRequest}>
            <p style={{ marginBottom: '0.75rem', opacity: 0.75, fontSize: '0.875rem' }}>
              Kayıtlı e-posta adresinizi girin; sıfırlama bağlantısı göndereceğiz.
            </p>
            {onGoToSetPassword && (
              <div style={{ marginBottom: '1.25rem', fontSize: '0.8rem', color: 'var(--text-2, #94a3b8)' }}>
                Yöneticinizden ilk kurulum kodu mu aldınız?{' '}
                <button
                  type="button"
                  onClick={onGoToSetPassword}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary, #00e5ff)',
                    cursor: 'pointer',
                    padding: 0,
                    textDecoration: 'underline',
                    fontSize: 'inherit',
                    fontWeight: 600,
                  }}
                >
                  Şifrenizi buradan belirleyin
                </button>
              </div>
            )}
            {success && (
              <div className="form-alert success" role="status">
                <CheckCircle size={18} />
                <span>{success}</span>
              </div>
            )}
            <label className="field-group">
              <span>E-posta adresi</span>
              <div className="input-shell">
                <Mail size={18} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="ad.soyad@kurum.org"
                />
              </div>
            </label>
            {error && (
              <div className="form-alert error" role="alert">
                <ShieldAlert size={18} />
                <span>{error}</span>
              </div>
            )}
            <div className="action-row">
              <button className="primary-action" type="submit" disabled={loading}>
                {loading ? <RefreshCw className="spin" size={18} /> : <Mail size={18} />}
                {loading ? 'Gönderiliyor' : 'Sıfırlama bağlantısı gönder'}
              </button>
              <button className="secondary-action" type="button" onClick={onBack}>
                <Activity size={18} />
                Geri dön
              </button>
            </div>
          </form>
        ) : (
          <form className="login-panel" onSubmit={handleReset}>
            <p style={{ marginBottom: '1rem', opacity: 0.75, fontSize: '0.875rem' }}>
              E-postanızdaki sıfırlama token'ını ve yeni parolanızı girin.
            </p>
            <label className="field-group">
              <span>Sıfırlama token'ı</span>
              <div className="input-shell">
                <KeyRound size={18} />
                <input
                  type="text"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="E-postanızdaki token"
                  autoFocus
                />
              </div>
            </label>
            <label className="field-group">
              <span>Yeni parola (en az 12 karakter)</span>
              <div className="input-shell">
                <Lock size={18} />
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  placeholder="••••••••••••"
                />
              </div>
            </label>
            {error && (
              <div className="form-alert error" role="alert">
                <ShieldAlert size={18} />
                <span>{error}</span>
              </div>
            )}
            <div className="action-row">
              <button className="primary-action" type="submit" disabled={loading}>
                {loading ? <RefreshCw className="spin" size={18} /> : <CheckCircle size={18} />}
                {loading ? 'Sıfırlanıyor' : 'Parolayı sıfırla'}
              </button>
              <button className="secondary-action" type="button" onClick={onBack}>
                <Activity size={18} />
                Geri dön
              </button>
            </div>
          </form>
        )}
      </section>
      <section className="visual-side visual-abstract" aria-hidden="true">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />
      </section>
    </main>
  );
}

// ─── İlk Parola Belirleme Ekranı (Zero-Knowledge Setup Token) ─────────────────

function SetPasswordScreen({ onBack, onSuccess, defaultToken = '' }) {
  const [token, setToken] = useState(defaultToken);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  // Parola güvenlik kriterleri
  const hasMinLength = newPassword.length >= 12;
  const hasUpper = /[A-Z]/.test(newPassword);
  const hasLower = /[a-z]/.test(newPassword);
  const hasNumber = /[0-9]/.test(newPassword);
  const hasSpecial = /[^A-Za-z0-9]/.test(newPassword);
  const isStrong = hasMinLength && hasUpper && hasLower && hasNumber && hasSpecial;
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!token.trim()) {
      setError('Lütfen kurum yöneticinizden aldığınız kurulum kodunu (setup token) girin.');
      return;
    }
    if (!hasMinLength) {
      setError('Parola en az 12 karakter uzunluğunda olmalıdır.');
      return;
    }
    if (!isStrong) {
      setError('Parola en az 1 büyük harf, 1 küçük harf, 1 rakam ve 1 özel karakter içermelidir.');
      return;
    }
    if (!passwordsMatch) {
      setError('Girdiğiniz parolalar birbiriyle uyuşmuyor.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await resetPassword(token.trim(), newPassword);
      setSuccess(true);
    } catch (err) {
      setError(
        err?.detail ||
          err?.message ||
          'Parola belirlenemedi. Kurulum kodu geçersiz veya 24 saatlik süresi dolmuş olabilir.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="sp-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>Güvenli İlk Parola Kurulumu</span>
          </div>
        </header>

        <div className="auth-heading-row">
          <div className="auth-copy">
            <span className="eyebrow">Hesap Kurulumu</span>
            <h1 id="sp-title">Şifremi Belirle</h1>
          </div>
        </div>

        {success ? (
          <div className="login-panel">
            <div className="form-alert success" role="status">
              <CheckCircle size={18} />
              <span>
                Parolanız başarıyla oluşturuldu ve hesabınız aktifleştirildi! Artık yeni parolanızla güvenli giriş yapabilirsiniz.
              </span>
            </div>
            <div className="action-row" style={{ marginTop: '1.5rem' }}>
              <button
                className="primary-action"
                type="button"
                onClick={() => (onSuccess ? onSuccess() : onBack())}
              >
                <CheckCircle size={18} />
                Giriş Ekranına Git
              </button>
            </div>
          </div>
        ) : (
          <form className="login-panel" onSubmit={handleSubmit}>
            <p style={{ marginBottom: '1rem', color: 'var(--text-2, #a0aec0)', fontSize: '0.85rem', lineHeight: 1.5 }}>
              Kurum yöneticinizin size sağladığı <strong>tek kullanımlık kurulum kodunu (setup_token)</strong> ve kullanmak istediğiniz güçlü parolayı girin.
            </p>

            <label className="field-group">
              <span>Kurulum Kodu (Setup Token) *</span>
              <div className="input-shell">
                <KeyRound size={18} />
                <input
                  type="text"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Yöneticinizin verdiği tek kullanımlık kod"
                  required
                  autoFocus
                  style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                />
              </div>
            </label>

            <label className="field-group">
              <span>Yeni Parola *</span>
              <div className="input-shell" style={{ gridTemplateColumns: '22px 1fr 24px', alignItems: 'center' }}>
                <Lock size={18} />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="En az 12 karakter"
                  autoComplete="new-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--muted, #94a3b8)',
                    cursor: 'pointer',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  title={showPassword ? 'Gizle' : 'Göster'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>

            <label className="field-group">
              <span>Yeni Parola (Tekrar) *</span>
              <div className="input-shell" style={{ gridTemplateColumns: '22px 1fr 24px', alignItems: 'center' }}>
                <Lock size={18} />
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Parolayı tekrar girin"
                  autoComplete="new-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--muted, #94a3b8)',
                    cursor: 'pointer',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  title={showConfirmPassword ? 'Gizle' : 'Göster'}
                >
                  {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>

            {/* Şifre Güvenlik Kriterleri İpuçları */}
            <div style={{
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid var(--line, rgba(255,255,255,0.08))',
              borderRadius: '8px',
              padding: '0.75rem',
              fontSize: '0.75rem',
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '0.35rem',
              color: 'var(--text-2, #a0aec0)',
              marginBottom: '0.5rem',
            }}>
              <span style={{ color: hasMinLength ? '#10b981' : 'inherit' }}>
                {hasMinLength ? '✓' : '○'} En az 12 karakter
              </span>
              <span style={{ color: hasUpper ? '#10b981' : 'inherit' }}>
                {hasUpper ? '✓' : '○'} Büyük harf (A-Z)
              </span>
              <span style={{ color: hasLower ? '#10b981' : 'inherit' }}>
                {hasLower ? '✓' : '○'} Küçük harf (a-z)
              </span>
              <span style={{ color: hasNumber ? '#10b981' : 'inherit' }}>
                {hasNumber ? '✓' : '○'} Rakam (0-9)
              </span>
              <span style={{ color: hasSpecial ? '#10b981' : 'inherit' }}>
                {hasSpecial ? '✓' : '○'} Özel karakter (!@#$%...)
              </span>
              <span style={{ color: passwordsMatch ? '#10b981' : (confirmPassword ? '#ef4444' : 'inherit') }}>
                {passwordsMatch ? '✓ Parolalar eşleşti' : (confirmPassword ? '✕ Eşleşmiyor' : '○ Parola onayı')}
              </span>
            </div>

            {error && (
              <div className="form-alert error" role="alert">
                <ShieldAlert size={18} />
                <span>{error}</span>
              </div>
            )}

            <div className="action-row">
              <button className="primary-action" type="submit" disabled={loading || !isStrong || !passwordsMatch}>
                {loading ? <RefreshCw className="spin" size={18} /> : <CheckCircle size={18} />}
                {loading ? 'Kaydediliyor...' : 'Parolayı Belirle & Aktifleştir'}
              </button>
              <button className="secondary-action" type="button" onClick={onBack}>
                <ArrowLeft size={18} />
                Giriş Ekranına Dön
              </button>
            </div>
          </form>
        )}

        <div className="compliance-strip" aria-label="Güvenlik bilgisi">
          <span>
            <ShieldCheck size={16} />
            Argon2id Kriptografik Özet
          </span>
          <span>
            <KeyRound size={16} />
            Tek Kullanımlık Token
          </span>
        </div>
      </section>

      <section className="visual-side visual-abstract" aria-hidden="true">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />
      </section>
    </main>
  );
}

// ─── Kayıt Ekranı ─────────────────────────────────────────────────────────────

function RegisterScreen({ onSuccess, onBack }) {
  const [form, setForm] = useState({
    firstName: '', lastName: '', title: '', email: '', password: '', organizationId: '', role: 'PHYSICIAN',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.firstName || !form.lastName || !form.email || !form.password) {
      setError('Zorunlu alanları doldurun (Ad, Soyad, E-posta, Parola).');
      return;
    }
    if (form.password.length < 12) {
      setError('Parola en az 12 karakter olmalıdır.');
      return;
    }
    setLoading(true); setError('');
    try {
      await register({
        firstName: form.firstName.trim(),
        lastName: form.lastName.trim(),
        email: form.email.trim(),
        password: form.password,
        title: form.title.trim(),
        organizationId: form.organizationId.trim() || null,
        role: form.role,
      });
      setSuccess('Hesabınız başarıyla oluşturuldu. Giriş yapabilirsiniz.');
    } catch (err) {
      setError(err.message || 'Kayıt başarısız oldu.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <main className="login-shell">
        <section className="auth-side" aria-labelledby="reg-title">
          <header className="brand-row">
            <div>
              <strong>NeuroOncoTrack-AI</strong>
              <span>Kayıt başarılı</span>
            </div>
          </header>
          <div className="auth-heading-row">
            <div className="auth-copy">
              <span className="eyebrow">Hoş geldiniz</span>
              <h1 id="reg-title">Hesap oluşturuldu</h1>
            </div>
          </div>
          <div className="login-panel">
            <div className="form-alert success" role="status">
              <CheckCircle size={18} />
              <span>{success}</span>
            </div>
            <div className="action-row" style={{ marginTop: '1.5rem' }}>
              <button className="primary-action" type="button" onClick={onBack}>
                <CheckCircle size={18} />
                Giriş ekranına dön
              </button>
            </div>
          </div>
        </section>
        <section className="visual-side visual-abstract" aria-hidden="true">
          <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
          <div className="visual-scrim" aria-hidden="true" />
        </section>
      </main>
    );
  }

  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="reg-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>Yeni hesap oluştur</span>
          </div>
        </header>
        <div className="auth-heading-row">
          <div className="auth-copy">
            <span className="eyebrow">Ağımıza katılın</span>
            <h1 id="reg-title">Kayıt Ol</h1>
          </div>
        </div>
        <form className="login-panel" onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <label className="field-group">
              <span>Ad</span>
              <div className="input-shell">
                <User size={18} />
                <input type="text" value={form.firstName} onChange={e => setForm({ ...form, firstName: e.target.value })} placeholder="Adınız" />
              </div>
            </label>
            <label className="field-group">
              <span>Soyad</span>
              <div className="input-shell">
                <User size={18} />
                <input type="text" value={form.lastName} onChange={e => setForm({ ...form, lastName: e.target.value })} placeholder="Soyadınız" />
              </div>
            </label>
          </div>
          <label className="field-group">
            <span>E-posta</span>
            <div className="input-shell">
              <Mail size={18} />
              <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="ad.soyad@kurum.edu.tr" />
            </div>
          </label>
          <label className="field-group">
            <span>Parola (en az 12 karakter)</span>
            <div className="input-shell">
              <KeyRound size={18} />
              <input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder="••••••••••••" />
            </div>
          </label>
          <label className="field-group">
            <span>Kurum Kodu (UUID) (İsteğe bağlı)</span>
            <div className="input-shell">
              <Database size={18} />
              <input type="text" value={form.organizationId} onChange={e => setForm({ ...form, organizationId: e.target.value })} placeholder="Kurumunuzun UUID kodu" />
            </div>
          </label>
          {error && (
            <div className="form-alert error" role="alert">
              <ShieldAlert size={18} />
              <span>{error}</span>
            </div>
          )}
          <div className="action-row">
            <button className="primary-action" type="submit" disabled={loading}>
              {loading ? <RefreshCw className="spin" size={18} /> : <CheckCircle size={18} />}
              {loading ? 'Kaydediliyor' : 'Hesap Oluştur'}
            </button>
            <button className="secondary-action" type="button" onClick={onBack}>
              <Activity size={18} />
              Vazgeç
            </button>
          </div>
        </form>
      </section>
      <section className="visual-side visual-abstract" aria-hidden="true">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />
      </section>
    </main>
  );
}

// ─── Welcome Ekranı (İlk Açılış) ──────────────────────────────────────────────

function WelcomeScreen({ onLogin, onRegister }) {
  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="welcome-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>Klinik karar destek platformu</span>
          </div>
        </header>

        <div className="auth-heading-row" style={{ marginTop: 'auto' }}>
          <div className="auth-copy">
            <span className="eyebrow">Hoş Geldiniz</span>
            <h1 id="welcome-title">NeuroOncoTrack-AI</h1>
            <p style={{ marginTop: '1rem', color: 'var(--muted)', lineHeight: 1.5 }}>
              Yapay zeka destekli tıbbi karar destek, segmentasyon ve raporlama platformuna hoş geldiniz. Lütfen devam etmek için bir seçenek belirleyin.
            </p>
          </div>
        </div>

        <div className="login-panel" style={{ marginTop: '2rem', marginBottom: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <button
              className="primary-action"
              type="button"
              onClick={onLogin}
              style={{ width: '100%', justifyContent: 'center', padding: '0.875rem' }}
            >
              <Lock size={18} />
              Giriş Yap
            </button>
            <button
              className="secondary-action"
              type="button"
              onClick={onRegister}
              style={{ width: '100%', justifyContent: 'center', padding: '0.875rem' }}
            >
              <Activity size={18} />
              Kayıt Ol
            </button>
          </div>
        </div>
      </section>

      <section className="visual-side visual-abstract" aria-label="Klinik çalışma önizlemesi">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />

        <div className="system-panel">
          <div className="panel-heading">
            <span>Canlı analiz akışı</span>
            <strong>MRG &gt; Segmentasyon &gt; Rapor</strong>
          </div>
          <div className="capability-list">
            {capabilities.map((item) => {
              const Icon = item.icon;
              return (
                <article className="capability-item" key={item.label}>
                  <span className="capability-icon" aria-hidden="true">
                    <Icon size={18} />
                  </span>
                  <div>
                    <strong>{item.label}</strong>
                    <small>{item.value}</small>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="metric-rail" aria-label="Model ve entegrasyon göstergeleri">
          {loginMetrics.map((metric) => (
            <div className="metric-item" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

// ─── Ana Uygulama ─────────────────────────────────────────────────────────────

function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [institutionCode, setInstitutionCode] = useState('NOT-2026');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberStation, setRememberStation] = useState(true);
  const [status, setStatus] = useState(null);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [session, setSession] = useState(() => {
    try {
      const saved = window.localStorage.getItem('neuro_session');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && parsed.expiresAt > Date.now()) {
          if (parsed.accessToken) {
            setAccessToken(parsed.accessToken);
          }
          return parsed;
        }
      }
    } catch (e) {
      console.error(e);
    }
    return null;
  });
  const [authLoading, setAuthLoading] = useState(false);
  const [idleWarning, setIdleWarning] = useState(false);
  const idleTimersRef = useRef({ warning: null, logout: null });

  // Ekran durumu: 'welcome' | 'login' | 'mfa' | 'change-password' | 'forgot-password' | 'set-password' | 'register'
  const [screen, setScreen] = useState(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('setup_token') || params.get('token')) {
        return 'set-password';
      }
      const savedSession = window.localStorage.getItem('neuro_session');
      if (savedSession) {
        const parsed = JSON.parse(savedSession);
        if (parsed && parsed.expiresAt > Date.now()) {
          const savedScreen = window.localStorage.getItem('neuro_screen');
          return savedScreen || 'workspace';
        }
      }
    } catch (e) {
      console.error(e);
    }
    return 'welcome';
  });
  const [initialSetupToken, setInitialSetupToken] = useState(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get('setup_token') || params.get('token') || '';
    } catch {
      return '';
    }
  });
  const [mfaState, setMfaState] = useState(null);

  // Giriş sekmesi: 'kurum' | 'bireysel'
  const [loginTab, setLoginTab] = useState('kurum');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('neuro-login-theme', theme);
  }, [theme]);

  useEffect(() => {
    if (session) {
      window.localStorage.setItem('neuro_session', JSON.stringify(session));
    } else {
      window.localStorage.removeItem('neuro_session');
      window.localStorage.removeItem('neuro_screen');
    }
  }, [session]);

  useEffect(() => {
    if (session) {
      window.localStorage.setItem('neuro_screen', screen);
    }
  }, [screen, session]);

  useEffect(() => {
    // Admin ekranında workspace overflow:hidden kaldırılır, scroll çalışsın
    const isWorkspace = Boolean(session) && screen !== 'admin';
    document.body.classList.toggle('workspace-mode', isWorkspace);
    return () => document.body.classList.remove('workspace-mode');
  }, [session, screen]);

  const can = useCallback(
    (permission) => {
      if (!permission) return true;
      const userPermissions = session?.user?.permissions || [];
      return userPermissions.includes(permission) || userPermissions.includes('*');
    },
    [session],
  );

  // Sekme değiştirince alanları sıfırla
  const switchLoginTab = (tab) => {
    setLoginTab(tab);
    setStatus(null);
    setIsDemoMode(false);
    setEmail('');
    setPassword('');
    setInstitutionCode(tab === 'kurum' ? 'NOT-2026' : '');
  };

  const updateManualField = (setter, value) => {
    setter(value);
    if (isDemoMode) {
      setIsDemoMode(false);
      setStatus(null);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (loginTab === 'kurum' && !institutionCode.trim()) {
      setStatus({ tone: 'error', message: 'Kurum / proje kodunu girin.' });
      return;
    }
    if (!email.trim() || !password.trim()) {
      setStatus({ tone: 'error', message: 'E-posta ve şifre alanlarını doldurun.' });
      return;
    }

    setAuthLoading(true);
    setStatus(null);

    try {
      const nextSession = await login({
        institutionCode: loginTab === 'kurum' ? institutionCode.trim() : '',
        email: email.trim(),
        password,
        rememberStation,
        demo: isDemoMode,
      });

      if (nextSession.mode === 'mfa') {
        setMfaState(nextSession);
        setScreen('mfa');
        return;
      }

      if (nextSession.mode === 'password-change') {
        setScreen('change-password');
        return;
      }

      setIdleWarning(false);
      setSession(nextSession);
      const userRole = nextSession?.user?.role;
      const isAdminRole = ['ADMIN', 'SUPERADMIN', 'HOSPITAL_ADMIN', 'SUPER_ADMIN'].includes(userRole);
      setScreen(isAdminRole ? 'admin' : 'workspace');
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error.message || 'Giriş başarısız oldu.',
      });
    } finally {
      setAuthLoading(false);
    }
  };


  const clearIdleTimers = useCallback(() => {
    if (idleTimersRef.current.warning) window.clearTimeout(idleTimersRef.current.warning);
    if (idleTimersRef.current.logout) window.clearTimeout(idleTimersRef.current.logout);
    idleTimersRef.current = { warning: null, logout: null };
  }, []);

  const handleLogout = useCallback(async () => {
    clearIdleTimers();
    await logout(session);
    setSession(null);
    setStatus(null);
    setIdleWarning(false);
    setScreen('welcome');
  }, [clearIdleTimers, session]);

  const scheduleIdleClock = useCallback(() => {
    clearIdleTimers();
    if (!session) return;

    idleTimersRef.current.warning = window.setTimeout(
      () => setIdleWarning(true),
      Math.max(1, REAL_SESSION_MINUTES - IDLE_WARNING_MINUTES) * 60 * 1000,
    );
    idleTimersRef.current.logout = window.setTimeout(handleLogout, REAL_SESSION_MINUTES * 60 * 1000);
  }, [clearIdleTimers, handleLogout, session]);

  const handleUserActivity = useCallback(() => {
    if (!session) return;
    setIdleWarning(false);
    scheduleIdleClock();
  }, [scheduleIdleClock, session]);

  useEffect(() => {
    if (!session) return undefined;

    scheduleIdleClock();
    activityEvents.forEach((eventName) => {
      window.addEventListener(eventName, handleUserActivity, { passive: true });
    });

    return () => {
      activityEvents.forEach((eventName) => {
        window.removeEventListener(eventName, handleUserActivity);
      });
      clearIdleTimers();
    };
  }, [clearIdleTimers, handleUserActivity, scheduleIdleClock, session]);

  const toggleDemoAccess = () => {
    if (isDemoMode) {
      setInstitutionCode('NOT-2026');
      setEmail('');
      setPassword('');
      setIsDemoMode(false);
      setStatus(null);
      return;
    }

    // Demo her zaman kurum sekmesinde açılır
    setLoginTab('kurum');
    setInstitutionCode('NOT-DEMO');
    setEmail('demo@neurooncotrack.ai');
    setPassword('tekno2026');
    setRememberStation(true);
    setIsDemoMode(true);
    setStatus({
      tone: 'success',
      message: 'Demo bilgileri yüklendi. Güvenli giriş ile akışı deneyebilirsiniz.',
    });
  };

  // ── Ekran yönlendirme ────────────────────────────────────────────────────

  if (session) {
    if (screen === 'admin') {
      return (
        <AdminDashboard
          session={session}
          onBack={() => setScreen('workspace')}
          theme={theme}
          setTheme={setTheme}
        />
      );
    }

    return (
      <>
        <ProductWorkspace
          isDemoMode={isDemoMode}
          session={session}
          can={can}
          theme={theme}
          setTheme={setTheme}
          onLogout={handleLogout}
          onOpenAdmin={['ADMIN', 'SUPERADMIN', 'HOSPITAL_ADMIN', 'SUPER_ADMIN'].includes(session?.user?.role) ? () => setScreen('admin') : undefined}
        />
        {idleWarning ? (
          <div className="session-warning" role="status">
            <ShieldAlert size={17} />
            <span>Oturum hareketsizlik nedeniyle yakında kapanacak.</span>
            <button type="button" onClick={handleUserActivity}>
              Devam et
            </button>
          </div>
        ) : null}
      </>
    );
  }

  if (screen === 'mfa') {
    return (
      <MfaScreen
        mfaState={mfaState}
        onSuccess={(sess) => {
          setSession(sess);
          const userRole = sess?.user?.role;
          const isAdminRole = ['ADMIN', 'SUPERADMIN', 'HOSPITAL_ADMIN', 'SUPER_ADMIN'].includes(userRole);
          setScreen(isAdminRole ? 'admin' : 'workspace');
          setMfaState(null);
        }}
        onBack={() => {
          setScreen('welcome');
          setMfaState(null);
        }}
      />
    );
  }

  if (screen === 'change-password') {
    return (
      <ChangePasswordScreen
        onSuccess={() => setScreen('welcome')}
        onBack={() => setScreen('welcome')}
      />
    );
  }

  if (screen === 'forgot-password') {
    return (
      <ForgotPasswordScreen
        onBack={() => setScreen('login')}
        onGoToSetPassword={() => setScreen('set-password')}
      />
    );
  }

  if (screen === 'set-password') {
    return (
      <SetPasswordScreen
        defaultToken={initialSetupToken}
        onBack={() => setScreen('login')}
        onSuccess={() => {
          setScreen('login');
          setStatus({
            tone: 'success',
            message: 'Parolanız başarıyla belirlendi! Yeni parolanızla giriş yapabilirsiniz.',
          });
        }}
      />
    );
  }

  if (screen === 'register') {
    return <RegisterScreen onSuccess={() => setScreen('login')} onBack={() => setScreen('welcome')} />;
  }

  if (screen === 'welcome') {
    return <WelcomeScreen onLogin={() => setScreen('login')} onRegister={() => setScreen('register')} />;
  }

  // ── Giriş ekranı ─────────────────────────────────────────────────────────

  return (
    <main className="login-shell">
      <section className="auth-side" aria-labelledby="login-title">
        <header className="brand-row">
          <div>
            <strong>NeuroOncoTrack-AI</strong>
            <span>Klinik karar destek platformu</span>
          </div>
        </header>

        <div className="auth-heading-row">
          <div className="auth-copy">
            <span className="eyebrow">Yetkili erişim</span>
            <h1 id="login-title">Klinik giriş</h1>
          </div>
          <ThemeToggle theme={theme} setTheme={setTheme} />
        </div>

        <form className="login-panel" onSubmit={handleSubmit}>
          {/* Geri Dön Butonu */}
          <button
            type="button"
            onClick={() => setScreen('welcome')}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-2)',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              padding: '0.25rem',
              marginBottom: '1rem',
              marginLeft: '-0.25rem',
              borderRadius: '6px',
            }}
            title="Geri dön"
          >
            <ArrowLeft size={20} />
          </button>

          {/* ── Sekme Değiştirici ── */}
          <div style={{
            display: 'flex',
            gap: '0.5rem',
            marginBottom: '1.25rem',
            background: 'var(--surface-2, rgba(255,255,255,0.06))',
            borderRadius: '10px',
            padding: '4px',
          }}>
            {[
              { id: 'kurum', label: 'Kurum girişi' },
              { id: 'bireysel', label: 'Bireysel giriş' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => switchLoginTab(tab.id)}
                style={{
                  flex: 1,
                  padding: '0.5rem 0.75rem',
                  borderRadius: '7px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: loginTab === tab.id ? 600 : 400,
                  background: loginTab === tab.id
                    ? 'var(--primary, #00e5ff)'
                    : 'transparent',
                  color: loginTab === tab.id
                    ? 'var(--on-primary, #000)'
                    : 'var(--text-2, inherit)',
                  transition: 'all 0.2s ease',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Kurum kodu — sadece kurum girişinde görünür */}
          {loginTab === 'kurum' && (
            <label className="field-group">
              <span>Kurum / proje kodu</span>
              <div className="input-shell">
                <Database size={18} />
                <input
                  type="text"
                  value={institutionCode}
                  onChange={(event) => updateManualField(setInstitutionCode, event.target.value)}
                  autoComplete="organization"
                  placeholder="NOT-2026"
                />
              </div>
            </label>
          )}

          <label className="field-group">
            <span>E-posta</span>
            <div className="input-shell">
              <Cpu size={18} />
              <input
                type="email"
                value={email}
                onChange={(event) => updateManualField(setEmail, event.target.value)}
                autoComplete="email"
                placeholder="ad.soyad@kurum.org"
              />
            </div>
          </label>

          <label className="field-group">
            <span>Şifre</span>
            <div className="input-shell">
              <ShieldAlert size={18} />
              <input
                type="password"
                value={password}
                onChange={(event) => updateManualField(setPassword, event.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </div>
          </label>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', marginBottom: '1rem', marginTop: '0.25rem' }}>
            <label className="check-row" style={{ margin: 0 }}>
              <input
                type="checkbox"
                checked={rememberStation}
                onChange={(event) => setRememberStation(event.target.checked)}
              />
              <span>Beni hatırla</span>
            </label>
            <button
              type="button"
              onClick={() => setScreen('forgot-password')}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--primary, #00e5ff)',
                cursor: 'pointer',
                fontSize: '0.75rem',
                padding: 0,
                fontWeight: 500,
              }}
            >
              Parolamı unuttum
            </button>
          </div>

          {status ? (
            <div className={`form-alert ${status.tone}`} role="status">
              {status.tone === 'success' ? <CheckCircle size={18} /> : <ShieldAlert size={18} />}
              <span>{status.message}</span>
            </div>
          ) : null}

          <div className="action-row">
            <button className="primary-action" type="submit" disabled={authLoading}>
              {authLoading ? <RefreshCw className="spin" size={18} /> : <CheckCircle size={18} />}
              {authLoading ? 'Oturum açılıyor' : 'Güvenli giriş'}
            </button>
            <button
              className="secondary-action"
              type="button"
              onClick={() => setScreen('set-password')}
              title="Kurum yöneticinizden aldığınız kurulum kodu ile ilk parolanızı belirleyin"
            >
              <KeyRound size={18} />
              Şifremi Belirle
            </button>
          </div>
        </form>

        <div className="compliance-strip" aria-label="Güvenlik ve standart bilgileri">
          <span>
            <ShieldAlert size={16} />
            Etik kurul: TÜTF-GOBAEK 2026/205
          </span>
          <span>
            <Database size={16} />
            HL7 FHIR R4
          </span>
          <span>
            <Settings size={16} />
            Audit-ready
          </span>
        </div>
      </section>

      <section className="visual-side visual-abstract" aria-label="Klinik çalışma önizlemesi">
        <img className="hero-image" src={heroImage} alt="" aria-hidden="true" />
        <div className="visual-scrim" aria-hidden="true" />

        <div className="system-panel">
          <div className="panel-heading">
            <span>Canlı analiz akışı</span>
            <strong>MRG &gt; Segmentasyon &gt; Rapor</strong>
          </div>
          <div className="capability-list">
            {capabilities.map((item) => {
              const Icon = item.icon;
              return (
                <article className="capability-item" key={item.label}>
                  <span className="capability-icon" aria-hidden="true">
                    <Icon size={18} />
                  </span>
                  <div>
                    <strong>{item.label}</strong>
                    <small>{item.value}</small>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="metric-rail" aria-label="Model ve entegrasyon göstergeleri">
          {loginMetrics.map((metric) => (
            <div className="metric-item" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

export default App;
