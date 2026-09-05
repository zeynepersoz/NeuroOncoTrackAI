/**
 * UserModals.jsx — Kullanıcı Profil Modalları
 *
 * 1. ProfileModal    → Profil görüntüle + düzenle (PATCH /api/v1/auth/me)
 * 2. ChangePasswordModal → Parola değiştir (POST /api/v1/auth/change-password)
 * 3. SessionsModal   → Aktif oturumları yönet (GET/DELETE /api/v1/auth/sessions)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Eye,
  EyeOff,
  Globe,
  KeyRound,
  Loader2,
  LogOut,
  Monitor,
  Save,
  Settings,
  Shield,
  ShieldCheck,
  Smartphone,
  Trash2,
  User,
  X,
} from 'lucide-react';
import {
  changePassword,
  getMe,
  listSessions,
  revokeSession,
  updateMe,
  logoutAll,
  mfaSetup,
  mfaEnable,
  mfaDisable,
} from '../../services/authService.js';

// ─── Genel Modal Çerçevesi ────────────────────────────────────────────────────

function ModalBackdrop({ onClose, children }) {
  const isMouseDownOnBackdrop = useRef(false);

  // Escape tuşu ile kapat
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleMouseDown = (e) => {
    isMouseDownOnBackdrop.current = (e.target === e.currentTarget);
  };

  const handleMouseUp = (e) => {
    if (isMouseDownOnBackdrop.current && e.target === e.currentTarget) {
      onClose();
    }
    isMouseDownOnBackdrop.current = false;
  };

  return (
    <div
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.45)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '1rem',
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 16,
          boxShadow: 'var(--shadow)',
          width: '100%',
          maxWidth: 520,
          maxHeight: '90vh',
          overflowY: 'auto',
          color: 'var(--ink)',
        }}
      >
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ icon: Icon, title, subtitle, onClose }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      gap: '1rem',
      padding: '1.25rem 1.5rem',
      borderBottom: '1px solid var(--line)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <span style={{
          width: 36, height: 36, borderRadius: 9,
          background: 'color-mix(in srgb, var(--teal) 12%, transparent)',
          color: 'var(--teal)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <Icon size={18} />
        </span>
        <div>
          <strong style={{ fontSize: '1rem', display: 'block', color: 'var(--ink)' }}>{title}</strong>
          {subtitle && <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{subtitle}</span>}
        </div>
      </div>
      <button
        type="button"
        onClick={onClose}
        style={{
          width: 30, height: 30, borderRadius: 8,
          background: 'transparent',
          border: '1px solid var(--line)',
          cursor: 'pointer', color: 'var(--muted)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <X size={15} />
      </button>
    </div>
  );
}

function Toast({ msg, type }) {
  if (!msg) return null;
  const isError = type === 'error';
  return (
    <div style={{
      margin: '0 1.5rem',
      padding: '0.625rem 1rem',
      borderRadius: 8,
      background: isError ? 'var(--danger-bg)' : 'var(--success-bg)',
      border: `1px solid ${isError ? 'var(--rose)' : 'var(--teal)'}`,
      color: isError ? 'var(--rose)' : 'var(--teal)',
      fontSize: '0.8125rem',
      display: 'flex', alignItems: 'center', gap: '0.5rem',
      marginTop: '1rem',
    }}>
      {isError ? <AlertTriangle size={14} /> : <CheckCircle size={14} />}
      {msg}
    </div>
  );
}

function FormField({ label, children, required }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
      <label style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)' }}>
        {label}{required && <span style={{ color: 'var(--rose)', marginLeft: 2 }}>*</span>}
      </label>
      {children}
    </div>
  );
}

const inputStyle = {
  background: 'var(--surface-muted)',
  border: '1px solid var(--line)',
  borderRadius: 8,
  padding: '0.5rem 0.75rem',
  color: 'var(--ink)',
  fontSize: '0.875rem',
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
};

const readonlyStyle = {
  ...inputStyle,
  opacity: 0.65,
  cursor: 'default',
};

// ─── 1. Profil Bilgileri Modalı ───────────────────────────────────────────────

export function ProfileModal({ session, onClose, onProfileUpdate }) {
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    title: '',
    email: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [profile, setProfile] = useState(null);

  // Profil yükle
  useEffect(() => {
    setLoading(true);
    getMe()
      .then((data) => {
        setProfile(data);
        setForm({
          first_name: data.first_name || '',
          last_name: data.last_name || '',
          title: data.title || '',
          email: data.email || '',
        });
      })
      .catch(() => {
        // Backend yoksa session'dan doldur
        const u = session?.user || {};
        const nameParts = (u.name || '').split(' ');
        setForm({
          first_name: nameParts[0] || '',
          last_name: nameParts.slice(1).join(' ') || '',
          title: u.title || '',
          email: u.email || '',
        });
        setProfile(u);
      })
      .finally(() => setLoading(false));
  }, [session]);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleSave = async () => {
    if (!form.first_name.trim() || !form.last_name.trim()) {
      showToast('Ad ve soyad zorunludur.', 'error');
      return;
    }
    setSaving(true);
    try {
      const updated = await updateMe({
        firstName: form.first_name.trim(),
        lastName: form.last_name.trim(),
        title: form.title.trim() || null,
        email: form.email.trim() !== (profile?.email || '') ? form.email.trim() : undefined,
      });
      showToast('Profil başarıyla güncellendi.');
      if (onProfileUpdate) onProfileUpdate(updated);
    } catch (err) {
      showToast(err?.detail || err?.message || 'Güncelleme başarısız oldu.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const u = profile || session?.user || {};
  const ROLE_LABELS = {
    SUPERADMIN: 'Süper Yönetici', SUPER_ADMIN: 'Süper Yönetici',
    ADMIN: 'Yönetici', HOSPITAL_ADMIN: 'Yönetici',
    PHYSICIAN: 'Hekim', RADIOLOGIST: 'Radyolog',
    RESEARCHER: 'Araştırmacı', VIEWER: 'Gözlemci',
  };

  return (
    <ModalBackdrop onClose={onClose}>
      <ModalHeader icon={User} title="Profil Bilgileri" subtitle="Hesap bilgilerini görüntüle ve düzenle" onClose={onClose} />

      <div style={{ padding: '1.5rem' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--muted)' }}>
            <Loader2 size={24} className="spin" />
          </div>
        ) : (
          <>
            {/* Avatar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <span style={{
                width: 56, height: 56, borderRadius: '50%',
                background: 'var(--teal)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, fontSize: '1.375rem', flexShrink: 0,
              }}>
                {(form.first_name || u.email || '?')[0].toUpperCase()}
              </span>
              <div>
                <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--ink)' }}>
                  {form.title ? `${form.title} ` : ''}{form.first_name} {form.last_name}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
                  {ROLE_LABELS[u.role] || u.role || '—'} · {u.organization || u.organization_name || '—'}
                </div>
              </div>
            </div>

            {/* Form Alanları */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <FormField label="Ad" required>
                <input
                  style={inputStyle}
                  value={form.first_name}
                  onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))}
                  placeholder="Adınız"
                />
              </FormField>
              <FormField label="Soyad" required>
                <input
                  style={inputStyle}
                  value={form.last_name}
                  onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))}
                  placeholder="Soyadınız"
                />
              </FormField>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <FormField label="Unvan">
                <input
                  style={inputStyle}
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="Dr., Prof. Dr., Uz. Dr. ..."
                />
              </FormField>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <FormField label="E-posta" required>
                <input
                  type="email"
                  style={inputStyle}
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  placeholder="ornek@kurum.edu.tr"
                />
              </FormField>
            </div>

            {/* Salt Okunur Bilgiler */}
            <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <FormField label="Rol">
                <input style={readonlyStyle} readOnly value={ROLE_LABELS[u.role] || u.role || '—'} />
              </FormField>
              <FormField label="MFA Durumu">
                <div style={{
                  ...inputStyle,
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  cursor: 'default', opacity: 1,
                  color: u.mfa_enabled || u.mfaEnabled ? 'var(--teal)' : 'var(--muted)',
                }}>
                  {(u.mfa_enabled || u.mfaEnabled)
                    ? <><ShieldCheck size={14} /> Aktif</>
                    : <><Shield size={14} /> Pasif</>
                  }
                </div>
              </FormField>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <FormField label="Kurum">
                <input style={readonlyStyle} readOnly value={u.organization || u.organization_name || '—'} />
              </FormField>
            </div>

            {toast && <Toast msg={toast.msg} type={toast.type} />}
          </>
        )}
      </div>

      {!loading && (
        <div style={{
          padding: '1rem 1.5rem',
          borderTop: '1px solid var(--line)',
          display: 'flex', gap: '0.75rem', justifyContent: 'flex-end',
        }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.5rem 1.25rem',
              background: 'var(--surface-muted)',
              border: '1px solid var(--line)',
              borderRadius: 8, cursor: 'pointer',
              color: 'var(--muted)', fontSize: '0.875rem',
            }}
          >
            Kapat
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.4rem',
              padding: '0.5rem 1.25rem',
              background: 'var(--teal)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: 'pointer',
              fontSize: '0.875rem', fontWeight: 500,
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
            {saving ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
        </div>
      )}
    </ModalBackdrop>
  );
}

// ─── 2. Parola Değiştir Modalı ────────────────────────────────────────────────

function PasswordStrength({ password }) {
  if (!password) return null;
  const checks = [
    { label: 'En az 12 karakter', ok: password.length >= 12 },
    { label: 'Büyük harf', ok: /[A-Z]/.test(password) },
    { label: 'Küçük harf', ok: /[a-z]/.test(password) },
    { label: 'Rakam', ok: /[0-9]/.test(password) },
    { label: 'Özel karakter', ok: /[^A-Za-z0-9]/.test(password) },
  ];
  const score = checks.filter(c => c.ok).length;
  const colors = ['var(--rose)', 'var(--rose)', 'var(--amber)', 'var(--amber)', 'var(--teal)'];
  const labels = ['', 'Çok zayıf', 'Zayıf', 'Orta', 'Güçlü', 'Çok güçlü'];
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '0.375rem' }}>
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} style={{
            flex: 1, height: 4, borderRadius: 99,
            background: i <= score ? (colors[score - 1] || 'var(--line)') : 'var(--line)',
            transition: 'background 0.2s',
          }} />
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.6875rem', color: colors[score - 1] || 'var(--faint)', fontWeight: 500 }}>
          {labels[score]}
        </span>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {checks.map(c => (
            <span key={c.label} style={{ fontSize: '0.625rem', color: c.ok ? 'var(--teal)' : 'var(--faint)' }}>
              {c.ok ? '✓' : '○'} {c.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ChangePasswordModal({ onClose }) {
  const [form, setForm] = useState({ current: '', newPass: '', confirm: '' });
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [done, setDone] = useState(false);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const handleSave = async () => {
    if (!form.current) { showToast('Mevcut parolayı girin.', 'error'); return; }
    if (form.newPass.length < 12) { showToast('Yeni parola en az 12 karakter olmalıdır.', 'error'); return; }
    if (form.newPass !== form.confirm) { showToast('Yeni parola ve tekrarı eşleşmiyor.', 'error'); return; }
    if (form.current === form.newPass) { showToast('Yeni parola mevcut parolayla aynı olamaz.', 'error'); return; }

    setSaving(true);
    try {
      await changePassword(form.current, form.newPass);
      setDone(true);
    } catch (err) {
      const msg = err?.detail || err?.message || 'Parola değiştirilemedi.';
      showToast(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  const pwdInput = (value, onChange, show, onToggle, placeholder) => (
    <div style={{ position: 'relative' }}>
      <input
        type={show ? 'text' : 'password'}
        style={{ ...inputStyle, paddingRight: '2.5rem' }}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
      <button
        type="button"
        onClick={onToggle}
        style={{
          position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--muted)', padding: 2,
        }}
      >
        {show ? <EyeOff size={15} /> : <Eye size={15} />}
      </button>
    </div>
  );

  if (done) {
    return (
      <ModalBackdrop onClose={onClose}>
        <ModalHeader icon={KeyRound} title="Parola Değiştir" onClose={onClose} />
        <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center' }}>
          <ShieldCheck size={48} style={{ color: 'var(--teal)', marginBottom: '1rem' }} />
          <div style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--ink)', marginBottom: '0.5rem' }}>
            Parola başarıyla değiştirildi
          </div>
          <div style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: '2rem' }}>
            Güvenliğiniz için tüm diğer oturumlarınız sonlandırıldı.
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.625rem 2rem',
              background: 'var(--teal)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: 'pointer',
              fontSize: '0.875rem', fontWeight: 500,
            }}
          >
            Tamam
          </button>
        </div>
      </ModalBackdrop>
    );
  }

  return (
    <ModalBackdrop onClose={onClose}>
      <ModalHeader icon={KeyRound} title="Parola Değiştir" subtitle="Güçlü bir parola seçin" onClose={onClose} />

      <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <FormField label="Mevcut Parola" required>
          {pwdInput(form.current, (v) => setForm(f => ({ ...f, current: v })), showCurrent, () => setShowCurrent(s => !s), '••••••••••••')}
        </FormField>

        <div style={{ height: 1, background: 'var(--line)' }} />

        <FormField label="Yeni Parola" required>
          {pwdInput(form.newPass, (v) => setForm(f => ({ ...f, newPass: v })), showNew, () => setShowNew(s => !s), 'En az 12 karakter')}
          <PasswordStrength password={form.newPass} />
        </FormField>

        <FormField label="Yeni Parola Tekrar" required>
          <input
            type="password"
            style={{
              ...inputStyle,
              borderColor: form.confirm && form.confirm !== form.newPass ? 'var(--rose)' : undefined,
            }}
            value={form.confirm}
            onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
            placeholder="Yeni parolayı tekrar girin"
          />
          {form.confirm && form.confirm !== form.newPass && (
            <span style={{ fontSize: '0.75rem', color: 'var(--rose)' }}>Parolalar eşleşmiyor</span>
          )}
        </FormField>

        {toast && <Toast msg={toast.msg} type={toast.type} />}
      </div>

      <div style={{
        padding: '1rem 1.5rem',
        borderTop: '1px solid var(--line)',
        display: 'flex', gap: '0.75rem', justifyContent: 'flex-end',
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.5rem 1.25rem',
            background: 'var(--surface-muted)',
            border: '1px solid var(--line)',
            borderRadius: 8, cursor: 'pointer',
            color: 'var(--muted)', fontSize: '0.875rem',
          }}
        >
          İptal
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.5rem 1.25rem',
            background: 'var(--teal)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 500,
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? <Loader2 size={14} className="spin" /> : <KeyRound size={14} />}
          {saving ? 'Değiştiriliyor...' : 'Parolayı Değiştir'}
        </button>
      </div>
    </ModalBackdrop>
  );
}

// ─── 3. Oturum Yönetimi Modalı ────────────────────────────────────────────────

function parseDevice(ua = '') {
  if (!ua) return { icon: Monitor, label: 'Bilinmiyor' };
  if (/iphone|ipad|android/i.test(ua)) return { icon: Smartphone, label: 'Mobil' };
  return { icon: Monitor, label: 'Masaüstü' };
}

function parseBrowser(ua = '') {
  if (!ua) return '—';
  if (ua.includes('Chrome') && !ua.includes('Edg')) return 'Chrome';
  if (ua.includes('Firefox')) return 'Firefox';
  if (ua.includes('Safari') && !ua.includes('Chrome')) return 'Safari';
  if (ua.includes('Edg')) return 'Edge';
  return 'Tarayıcı';
}

function parseOS(ua = '') {
  if (!ua) return '';
  if (ua.includes('Windows')) return 'Windows';
  if (ua.includes('Mac')) return 'macOS';
  if (ua.includes('Linux')) return 'Linux';
  if (ua.includes('iPhone') || ua.includes('iPad')) return 'iOS';
  if (ua.includes('Android')) return 'Android';
  return '';
}

function formatRelativeTime(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Az önce';
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} sa önce`;
  return `${Math.floor(hours / 24)} gün önce`;
}

export function SessionsModal({ onClose }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [revoking, setRevoking] = useState('');
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSessions();
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      setSessions([]);
      showToast('Oturumlar yüklenemedi — backend bağlantısı yok.', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRevoke = async (sessionId) => {
    setRevoking(sessionId);
    try {
      await revokeSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      showToast('Oturum sonlandırıldı.');
    } catch (err) {
      showToast(err?.detail || 'Oturum sonlandırılamadı.', 'error');
    } finally {
      setRevoking('');
    }
  };

  const currentSession = sessions.find(s => s.is_current);
  const otherSessions = sessions.filter(s => !s.is_current);

  return (
    <ModalBackdrop onClose={onClose}>
      <ModalHeader
        icon={Globe}
        title="Oturum Yönetimi"
        subtitle={`${sessions.length} aktif oturum`}
        onClose={onClose}
      />

      <div style={{ padding: '1.25rem 1.5rem' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--muted)' }}>
            <Loader2 size={24} className="spin" />
            <div style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>Oturumlar yükleniyor...</div>
          </div>
        ) : sessions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--muted)' }}>
            Aktif oturum bulunamadı.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {/* Mevcut Oturum */}
            {currentSession && (
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Bu Cihaz
                </div>
                <SessionCard session={currentSession} isCurrent onRevoke={handleRevoke} revoking={revoking} />
              </div>
            )}

            {/* Diğer Oturumlar */}
            {otherSessions.length > 0 && (
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Diğer Oturumlar ({otherSessions.length})
                </div>
                {otherSessions.map(s => (
                  <SessionCard key={s.id} session={s} isCurrent={false} onRevoke={handleRevoke} revoking={revoking} />
                ))}
              </div>
            )}
          </div>
        )}

        {toast && <Toast msg={toast.msg} type={toast.type} />}
      </div>

      <div style={{
        padding: '1rem 1.5rem',
        borderTop: '1px solid var(--line)',
        display: 'flex', gap: '0.75rem', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          style={{
            padding: '0.5rem 1rem',
            background: 'var(--surface-muted)',
            border: '1px solid var(--line)',
            borderRadius: 8, cursor: 'pointer',
            color: 'var(--muted)', fontSize: '0.8125rem',
            display: 'flex', alignItems: 'center', gap: '0.4rem',
          }}
        >
          {loading ? <Loader2 size={13} className="spin" /> : null}
          Yenile
        </button>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.5rem 1.25rem',
            background: 'var(--teal)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 500,
          }}
        >
          Kapat
        </button>
      </div>
    </ModalBackdrop>
  );
}

function SessionCard({ session, isCurrent, onRevoke, revoking }) {
  const { icon: DeviceIcon, label: deviceLabel } = parseDevice(session.user_agent);
  const browser = parseBrowser(session.user_agent);
  const os = parseOS(session.user_agent);

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '0.875rem',
      padding: '0.875rem',
      background: isCurrent ? 'color-mix(in srgb, var(--teal) 6%, transparent)' : 'var(--surface-muted)',
      border: `1px solid ${isCurrent ? 'color-mix(in srgb, var(--teal) 25%, transparent)' : 'var(--line)'}`,
      borderRadius: 10,
      marginBottom: '0.5rem',
    }}>
      <span style={{
        width: 38, height: 38, borderRadius: 9,
        background: isCurrent ? 'color-mix(in srgb, var(--teal) 15%, transparent)' : 'var(--surface)',
        color: isCurrent ? 'var(--teal)' : 'var(--muted)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, border: '1px solid var(--line)',
      }}>
        <DeviceIcon size={18} />
      </span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 500, fontSize: '0.875rem', color: 'var(--ink)' }}>
            {browser} {os ? `· ${os}` : ''}
          </span>
          {isCurrent && (
            <span style={{
              background: 'color-mix(in srgb, var(--teal) 15%, transparent)',
              color: 'var(--teal)',
              border: '1px solid color-mix(in srgb, var(--teal) 30%, transparent)',
              borderRadius: 99, padding: '1px 8px',
              fontSize: '0.6875rem', fontWeight: 600,
            }}>
              Bu cihaz
            </span>
          )}
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2, display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {session.ip_address && <span>IP: {session.ip_address}</span>}
          <span>Son aktivite: {formatRelativeTime(session.last_used_at)}</span>
        </div>
      </div>

      {!isCurrent && (
        <button
          type="button"
          onClick={() => onRevoke(session.id)}
          disabled={revoking === session.id}
          title="Oturumu sonlandır"
          style={{
            width: 32, height: 32,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--danger-bg)',
            border: '1px solid var(--danger-border)',
            borderRadius: 8, cursor: 'pointer',
            color: 'var(--rose)',
            flexShrink: 0,
          }}
        >
          {revoking === session.id ? <Loader2 size={14} className="spin" /> : <LogOut size={14} />}
        </button>
      )}
    </div>
  );
}

// ─── 4. Birleşik Hesap & Kullanıcı Ayarları Modalı ─────────────────────────────

export function SettingsModal({ session, onClose, onProfileUpdate, initialTab = 'profile' }) {
  const [activeTab, setActiveTab] = useState(initialTab);

  const tabs = [
    { id: 'profile', label: 'Profil Bilgileri', icon: User },
    { id: 'password', label: 'Parola Değiştir', icon: KeyRound },
    { id: 'sessions', label: 'Aktif Oturumlar', icon: Globe },
    { id: 'mfa', label: 'İki Faktörlü Doğrulama', icon: ShieldCheck },
  ];

  return (
    <ModalBackdrop onClose={onClose}>
      <ModalHeader
        icon={Settings}
        title="Hesap Ayarları"
        subtitle={session?.user?.email || 'Profil, güvenlik ve oturum tercihleri'}
        onClose={onClose}
      />

      {/* Sekme Çubuğu */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--line)',
        background: 'var(--surface-muted)',
        padding: '0 1rem',
        gap: '0.25rem',
        overflowX: 'auto',
      }}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.625rem 0.875rem',
                background: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid var(--teal)' : '2px solid transparent',
                color: isActive ? 'var(--teal)' : 'var(--muted)',
                fontWeight: isActive ? 600 : 400,
                fontSize: '0.8125rem',
                cursor: 'pointer',
                marginBottom: -1,
                transition: 'all 0.15s',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Seçili Sekme Görünümü */}
      <div>
        {activeTab === 'profile' && (
          <ProfileTabContent session={session} onClose={onClose} onProfileUpdate={onProfileUpdate} />
        )}
        {activeTab === 'password' && (
          <PasswordTabContent onClose={onClose} />
        )}
        {activeTab === 'sessions' && (
          <SessionsTabContent onClose={onClose} />
        )}
        {activeTab === 'mfa' && (
          <MfaTabContent session={session} onClose={onClose} onProfileUpdate={onProfileUpdate} />
        )}
      </div>
    </ModalBackdrop>
  );
}

// ─── Sekme İçerikleri (SettingsModal için) ────────────────────────────────────

function ProfileTabContent({ session, onClose, onProfileUpdate }) {
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    title: '',
    email: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    setLoading(true);
    getMe()
      .then((data) => {
        setProfile(data);
        setForm({
          first_name: data.first_name || '',
          last_name: data.last_name || '',
          title: data.title || '',
          email: data.email || '',
        });
      })
      .catch(() => {
        const u = session?.user || {};
        const nameParts = (u.name || '').split(' ');
        setForm({
          first_name: nameParts[0] || '',
          last_name: nameParts.slice(1).join(' ') || '',
          title: u.title || '',
          email: u.email || '',
        });
        setProfile(u);
      })
      .finally(() => setLoading(false));
  }, [session]);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleSave = async () => {
    if (!form.first_name.trim() || !form.last_name.trim()) {
      showToast('Ad ve soyad zorunludur.', 'error');
      return;
    }
    setSaving(true);
    try {
      const updated = await updateMe({
        firstName: form.first_name.trim(),
        lastName: form.last_name.trim(),
        title: form.title.trim() || null,
        email: form.email.trim() !== (profile?.email || '') ? form.email.trim() : undefined,
      });
      showToast('Profil başarıyla güncellendi.');
      if (onProfileUpdate) onProfileUpdate(updated);
    } catch (err) {
      showToast(err?.detail || err?.message || 'Güncelleme başarısız oldu.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const u = profile || session?.user || {};
  const ROLE_LABELS = {
    SUPERADMIN: 'Süper Yönetici', SUPER_ADMIN: 'Süper Yönetici',
    ADMIN: 'Yönetici', HOSPITAL_ADMIN: 'Yönetici',
    PHYSICIAN: 'Hekim', RADIOLOGIST: 'Radyolog',
    RESEARCHER: 'Araştırmacı', VIEWER: 'Gözlemci',
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem 2rem', color: 'var(--muted)' }}>
        <Loader2 size={24} className="spin" />
        <div style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>Profil yükleniyor...</div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
          <span style={{
            width: 52, height: 52, borderRadius: '50%',
            background: 'var(--teal)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 700, fontSize: '1.25rem', flexShrink: 0,
          }}>
            {(form.first_name || u.email || '?')[0].toUpperCase()}
          </span>
          <div>
            <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--ink)' }}>
              {form.title ? `${form.title} ` : ''}{form.first_name} {form.last_name}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
              {ROLE_LABELS[u.role] || u.role || '—'} · {u.organization || u.organization_name || '—'}
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <FormField label="Ad" required>
            <input
              style={inputStyle}
              value={form.first_name}
              onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))}
              placeholder="Adınız"
            />
          </FormField>
          <FormField label="Soyad" required>
            <input
              style={inputStyle}
              value={form.last_name}
              onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))}
              placeholder="Soyadınız"
            />
          </FormField>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <FormField label="Unvan">
            <input
              style={inputStyle}
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="Dr., Prof. Dr., Uz. Dr. ..."
            />
          </FormField>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <FormField label="E-posta" required>
            <input
              type="email"
              style={inputStyle}
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              placeholder="ornek@kurum.edu.tr"
            />
          </FormField>
        </div>

        <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <FormField label="Rol">
            <input style={readonlyStyle} readOnly value={ROLE_LABELS[u.role] || u.role || '—'} />
          </FormField>
          <FormField label="MFA Durumu">
            <div style={{
              ...inputStyle,
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              cursor: 'default', opacity: 1,
              color: u.mfa_enabled || u.mfaEnabled ? 'var(--teal)' : 'var(--muted)',
            }}>
              {(u.mfa_enabled || u.mfaEnabled)
                ? <><ShieldCheck size={14} /> Aktif</>
                : <><Shield size={14} /> Pasif</>
              }
            </div>
          </FormField>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <FormField label="Kurum">
            <input style={readonlyStyle} readOnly value={u.organization || u.organization_name || '—'} />
          </FormField>
        </div>

        {toast && <Toast msg={toast.msg} type={toast.type} />}
      </div>

      <div style={{
        padding: '1rem 1.5rem',
        borderTop: '1px solid var(--line)',
        display: 'flex', gap: '0.75rem', justifyContent: 'flex-end',
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.5rem 1.25rem',
            background: 'var(--surface-muted)',
            border: '1px solid var(--line)',
            borderRadius: 8, cursor: 'pointer',
            color: 'var(--muted)', fontSize: '0.875rem',
          }}
        >
          Kapat
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.5rem 1.25rem',
            background: 'var(--teal)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 500,
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
          {saving ? 'Kaydediliyor...' : 'Değişiklikleri Kaydet'}
        </button>
      </div>
    </div>
  );
}

function PasswordTabContent({ onClose }) {
  const [form, setForm] = useState({ current: '', newPass: '', confirm: '' });
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [done, setDone] = useState(false);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const handleSave = async () => {
    if (!form.current) { showToast('Mevcut parolayı girin.', 'error'); return; }
    if (form.newPass.length < 12) { showToast('Yeni parola en az 12 karakter olmalıdır.', 'error'); return; }
    if (form.newPass !== form.confirm) { showToast('Yeni parola ve tekrarı eşleşmiyor.', 'error'); return; }
    if (form.current === form.newPass) { showToast('Yeni parola mevcut parolayla aynı olamaz.', 'error'); return; }

    setSaving(true);
    try {
      await changePassword(form.current, form.newPass);
      setDone(true);
    } catch (err) {
      const msg = err?.detail || err?.message || 'Parola değiştirilemedi.';
      showToast(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  const pwdInput = (value, onChange, show, onToggle, placeholder) => (
    <div style={{ position: 'relative' }}>
      <input
        type={show ? 'text' : 'password'}
        style={{ ...inputStyle, paddingRight: '2.5rem' }}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
      <button
        type="button"
        onClick={onToggle}
        style={{
          position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--muted)', padding: 2,
        }}
      >
        {show ? <EyeOff size={15} /> : <Eye size={15} />}
      </button>
    </div>
  );

  if (done) {
    return (
      <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center' }}>
        <ShieldCheck size={48} style={{ color: 'var(--teal)', marginBottom: '1rem' }} />
        <div style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--ink)', marginBottom: '0.5rem' }}>
          Parola başarıyla değiştirildi
        </div>
        <div style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: '2rem' }}>
          Güvenliğiniz için diğer tüm oturumlarınız sonlandırıldı.
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.625rem 2rem',
            background: 'var(--teal)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 500,
          }}
        >
          Tamam
        </button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <FormField label="Mevcut Parola" required>
          {pwdInput(form.current, (v) => setForm(f => ({ ...f, current: v })), showCurrent, () => setShowCurrent(s => !s), '••••••••••••')}
        </FormField>

        <div style={{ height: 1, background: 'var(--line)' }} />

        <FormField label="Yeni Parola" required>
          {pwdInput(form.newPass, (v) => setForm(f => ({ ...f, newPass: v })), showNew, () => setShowNew(s => !s), 'En az 12 karakter')}
          <PasswordStrength password={form.newPass} />
        </FormField>

        <FormField label="Yeni Parola Tekrar" required>
          <input
            type="password"
            style={{
              ...inputStyle,
              borderColor: form.confirm && form.confirm !== form.newPass ? 'var(--rose)' : undefined,
            }}
            value={form.confirm}
            onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
            placeholder="Yeni parolayı tekrar girin"
          />
          {form.confirm && form.confirm !== form.newPass && (
            <span style={{ fontSize: '0.75rem', color: 'var(--rose)' }}>Parolalar eşleşmiyor</span>
          )}
        </FormField>

        {toast && <Toast msg={toast.msg} type={toast.type} />}
      </div>

      <div style={{
        padding: '1rem 1.5rem',
        borderTop: '1px solid var(--line)',
        display: 'flex', gap: '0.75rem', justifyContent: 'flex-end',
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.5rem 1.25rem',
            background: 'var(--surface-muted)',
            border: '1px solid var(--line)',
            borderRadius: 8, cursor: 'pointer',
            color: 'var(--muted)', fontSize: '0.875rem',
          }}
        >
          İptal
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.5rem 1.25rem',
            background: 'var(--teal)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 500,
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? <Loader2 size={14} className="spin" /> : <KeyRound size={14} />}
          {saving ? 'Değiştiriliyor...' : 'Parolayı Güncelle'}
        </button>
      </div>
    </div>
  );
}

export function SessionsTabContent({ onClose }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [revoking, setRevoking] = useState('');
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSessions();
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      setSessions([]);
      showToast('Oturumlar yüklenemedi — backend bağlantısı yok.', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRevoke = async (sessionId) => {
    setRevoking(sessionId);
    try {
      await revokeSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      showToast('Oturum sonlandırıldı.');
    } catch (err) {
      showToast(err?.detail || 'Oturum sonlandırılamadı.', 'error');
    } finally {
      setRevoking('');
    }
  };

  const currentSession = sessions.find(s => s.is_current);
  const otherSessions = sessions.filter(s => !s.is_current);

  return (
    <div>
      <div style={{ padding: '1.25rem 1.5rem' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '2.5rem 2rem', color: 'var(--muted)' }}>
            <Loader2 size={24} className="spin" />
            <div style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>Oturumlar yükleniyor...</div>
          </div>
        ) : sessions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2.5rem 2rem', color: 'var(--muted)' }}>
            Aktif oturum bulunamadı.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {currentSession && (
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Bu Cihaz
                </div>
                <SessionCard session={currentSession} isCurrent onRevoke={handleRevoke} revoking={revoking} />
              </div>
            )}

            {otherSessions.length > 0 && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Diğer Oturumlar ({otherSessions.length})
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await logoutAll({ mode: 'api' });
                        showToast('Tüm diğer oturumlar sonlandırıldı.');
                        load();
                      } catch {
                        showToast('Oturumlar sonlandırılamadı.', 'error');
                      }
                    }}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: 'var(--rose)', fontSize: '0.75rem', fontWeight: 500,
                      display: 'flex', alignItems: 'center', gap: '0.25rem',
                    }}
                  >
                    <Trash2 size={13} />
                    Tümünü Kapat
                  </button>
                </div>
                {otherSessions.map(s => (
                  <SessionCard key={s.id} session={s} isCurrent={false} onRevoke={handleRevoke} revoking={revoking} />
                ))}
              </div>
            )}
          </div>
        )}

        {toast && <Toast msg={toast.msg} type={toast.type} />}
      </div>

      <div style={{
        padding: '1rem 1.5rem',
        borderTop: '1px solid var(--line)',
        display: 'flex', gap: '0.75rem', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          style={{
            padding: '0.5rem 1rem',
            background: 'var(--surface-muted)',
            border: '1px solid var(--line)',
            borderRadius: 8, cursor: 'pointer',
            color: 'var(--muted)', fontSize: '0.8125rem',
            display: 'flex', alignItems: 'center', gap: '0.4rem',
          }}
        >
          {loading ? <Loader2 size={13} className="spin" /> : null}
          Yenile
        </button>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.5rem 1.25rem',
            background: 'var(--teal)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 500,
          }}
        >
          </button>
      </div>
    </div>
  );
}

export function MfaTabContent({ session, onClose, onProfileUpdate }) {
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [step, setStep] = useState('initial'); // 'initial', 'setup', 'disable'
  const [setupData, setSetupData] = useState(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');

  const mfaEnabled = session?.user?.mfa_enabled || session?.user?.mfaEnabled;

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleStartSetup = async () => {
    setLoading(true);
    try {
      const data = await mfaSetup();
      setSetupData(data);
      setStep('setup');
    } catch (err) {
      showToast(err.message || 'MFA kurulumu başlatılamadı.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleEnableMfa = async () => {
    if (!code) { showToast('Doğrulama kodunu girin.', 'error'); return; }
    setLoading(true);
    try {
      await mfaEnable(code);
      showToast('MFA başarıyla aktifleştirildi.');
      if (onProfileUpdate) onProfileUpdate({ mfa_enabled: true });
      setStep('initial');
    } catch (err) {
      showToast(err.message || 'MFA aktifleştirilemedi.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDisableMfa = async () => {
    if (!password) { showToast('Mevcut parolanızı girin.', 'error'); return; }
    setLoading(true);
    try {
      await mfaDisable(password);
      showToast('MFA devre dışı bırakıldı.');
      if (onProfileUpdate) onProfileUpdate({ mfa_enabled: false });
      setStep('initial');
      setPassword('');
    } catch (err) {
      showToast(err.message || 'MFA devre dışı bırakılamadı.', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {step === 'initial' && (
          <div style={{ textAlign: 'center', padding: '1rem' }}>
            {mfaEnabled ? (
              <>
                <ShieldCheck size={48} style={{ color: 'var(--teal)', margin: '0 auto 1rem' }} />
                <h3 style={{ marginBottom: '0.5rem', fontSize: '1.125rem' }}>İki Faktörlü Doğrulama Aktif</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
                  Hesabınız şu anda ekstra bir güvenlik katmanıyla korunuyor.
                </p>
                <button
                  type="button"
                  onClick={() => setStep('disable')}
                  style={{
                    padding: '0.625rem 1.25rem',
                    background: 'var(--danger-bg)', color: 'var(--rose)',
                    border: '1px solid var(--rose)', borderRadius: 8, cursor: 'pointer',
                    fontSize: '0.875rem', fontWeight: 500,
                  }}
                >
                  MFA'yı Devre Dışı Bırak
                </button>
              </>
            ) : (
              <>
                <Shield size={48} style={{ color: 'var(--muted)', margin: '0 auto 1rem' }} />
                <h3 style={{ marginBottom: '0.5rem', fontSize: '1.125rem' }}>İki Faktörlü Doğrulama Pasif</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
                  Hesabınızın güvenliğini artırmak için iki faktörlü doğrulamayı aktifleştirin.
                </p>
                <button
                  type="button"
                  onClick={handleStartSetup}
                  disabled={loading}
                  style={{
                    padding: '0.625rem 1.25rem',
                    background: 'var(--teal)', color: '#fff',
                    border: 'none', borderRadius: 8, cursor: 'pointer',
                    fontSize: '0.875rem', fontWeight: 500,
                  }}
                >
                  {loading ? 'Başlatılıyor...' : 'Kurulumu Başlat'}
                </button>
              </>
            )}
          </div>
        )}

        {step === 'setup' && setupData && (
          <div>
            <div style={{ marginBottom: '1.5rem' }}>
              <strong style={{ display: 'block', marginBottom: '0.5rem' }}>1. Authenticator uygulamanıza ekleyin</strong>
              <p style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: '1rem' }}>
                Aşağıdaki kodu Google Authenticator veya benzeri bir uygulamaya manuel olarak ekleyin:
              </p>
              <div style={{
                background: 'var(--surface-muted)', padding: '0.75rem', borderRadius: 8,
                fontFamily: 'monospace', fontSize: '1.125rem', textAlign: 'center', letterSpacing: '0.1em'
              }}>
                {setupData.secret}
              </div>
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <strong style={{ display: 'block', marginBottom: '0.5rem' }}>2. Doğrulama kodunu girin</strong>
              <FormField label="Uygulamadaki 6 haneli kod">
                <input
                  type="text"
                  style={inputStyle}
                  value={code}
                  onChange={e => setCode(e.target.value)}
                  placeholder="000000"
                  maxLength={6}
                />
              </FormField>
            </div>
            
            {setupData.backup_codes && (
              <div style={{ marginBottom: '1.5rem' }}>
                <strong style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--rose)' }}>Önemli: Yedek Kodlar</strong>
                <p style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>Bu kodları güvenli bir yere kaydedin. Cihazınıza erişiminizi kaybederseniz bu kodlarla giriş yapabilirsiniz:</p>
                <div style={{
                  background: 'var(--surface-muted)', padding: '0.75rem', borderRadius: 8,
                  fontFamily: 'monospace', fontSize: '0.875rem', marginTop: '0.5rem',
                  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem'
                }}>
                  {setupData.backup_codes.map((bc, i) => <div key={i}>{bc}</div>)}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => setStep('initial')}
                style={{
                  padding: '0.5rem 1.25rem', background: 'var(--surface-muted)', border: '1px solid var(--line)',
                  borderRadius: 8, cursor: 'pointer', color: 'var(--muted)', fontSize: '0.875rem',
                }}
              >
                İptal
              </button>
              <button
                type="button"
                onClick={handleEnableMfa}
                disabled={loading}
                style={{
                  padding: '0.5rem 1.25rem', background: 'var(--teal)', color: '#fff',
                  border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
                }}
              >
                {loading ? 'Doğrulanıyor...' : 'Aktifleştir'}
              </button>
            </div>
          </div>
        )}

        {step === 'disable' && (
          <div>
            <p style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: '1rem' }}>
              İki faktörlü doğrulamayı devre dışı bırakmak için mevcut parolanızı girin.
            </p>
            <FormField label="Mevcut Parolanız">
              <input
                type="password"
                style={inputStyle}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </FormField>
            
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
              <button
                type="button"
                onClick={() => setStep('initial')}
                style={{
                  padding: '0.5rem 1.25rem', background: 'var(--surface-muted)', border: '1px solid var(--line)',
                  borderRadius: 8, cursor: 'pointer', color: 'var(--muted)', fontSize: '0.875rem',
                }}
              >
                İptal
              </button>
              <button
                type="button"
                onClick={handleDisableMfa}
                disabled={loading}
                style={{
                  padding: '0.5rem 1.25rem', background: 'var(--danger-bg)', color: 'var(--rose)',
                  border: '1px solid var(--rose)', borderRadius: 8, cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
                }}
              >
                {loading ? 'Devre Dışı Bırakılıyor...' : 'Devre Dışı Bırak'}
              </button>
            </div>
          </div>
        )}

        {toast && <Toast msg={toast.msg} type={toast.type} />}
      </div>
      
      {step === 'initial' && (
        <div style={{
          padding: '1rem 1.5rem',
          borderTop: '1px solid var(--line)',
          display: 'flex', justifyContent: 'flex-end',
        }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.5rem 1.25rem',
              background: 'var(--teal)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: 'pointer',
              fontSize: '0.875rem', fontWeight: 500,
            }}
          >
            Kapat
          </button>
        </div>
      )}
    </div>
  );
}

