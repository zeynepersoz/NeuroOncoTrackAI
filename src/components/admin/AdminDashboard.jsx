import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Database,
  Download,
  Eye,
  KeyRound,
  Lock,
  LogOut,
  Monitor,
  Pencil,
  RefreshCw,
  Save,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  TrendingUp,
  Unlock,
  User,
  UserCheck,
  UserMinus,
  Users,
  X,
  XCircle,
} from 'lucide-react';
import {
  deleteAdminUser,
  getAdminAuditLog,
  getAdminOrganizations,
  getAdminSessions,
  getAdminStats,
  getAdminUsers,
  patchAdminUser,
  revokeAdminSession,
} from '../../services/adminService.js';

// ─── Yardımcılar ──────────────────────────────────────────────────────────────

function formatRelativeTime(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Az önce';
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} sa önce`;
  const days = Math.floor(hours / 24);
  return `${days} gün önce`;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const ROLE_LABELS = {
  ADMIN: 'Yönetici',
  PHYSICIAN: 'Hekim',
  RADIOLOGIST: 'Radyolog',
  RESEARCHER: 'Araştırmacı',
  VIEWER: 'Gözlemci',
};

const ROLE_COLORS = {
  ADMIN: 'var(--rose)',
  PHYSICIAN: 'var(--teal)',
  RADIOLOGIST: 'var(--cyan)',
  RESEARCHER: 'var(--amber)',
  VIEWER: 'var(--muted)',
};

const AUDIT_SEVERITY_COLORS = {
  info: 'var(--cyan)',
  success: 'var(--teal)',
  warning: 'var(--amber)',
  danger: 'var(--rose)',
};

const AUDIT_ACTION_LABELS = {
  LOGIN_SUCCESS: 'Başarılı giriş',
  LOGIN_FAILED: 'Başarısız giriş',
  MFA_VERIFIED: 'MFA doğrulandı',
  MFA_SETUP: 'MFA kuruldu',
  PASSWORD_CHANGED: 'Parola değiştirildi',
  USER_LOCKED: 'Hesap kilitlendi',
  SESSION_REVOKED: 'Oturum iptal edildi',
  REGISTER: 'Yeni kayıt',
  ORG_UPDATED: 'Kurum güncellendi',
};

// ─── İstatistik Kartı ─────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color = 'var(--teal)', trend }) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--line)',
      borderRadius: 12,
      padding: '1.25rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.5rem',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{
          width: 36, height: 36, borderRadius: 8,
          background: `color-mix(in srgb, ${color} 15%, transparent)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color,
        }}>
          <Icon size={18} />
        </span>
        {trend !== undefined && (
          <span style={{ fontSize: '0.75rem', color: trend >= 0 ? 'var(--teal)' : 'var(--rose)', display: 'flex', alignItems: 'center', gap: 2 }}>
            {trend >= 0 ? <TrendingUp size={12} /> : <ChevronDown size={12} />}
            {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div>
        <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--ink)', lineHeight: 1 }}>
          {value}
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginTop: 4 }}>{label}</div>
        {sub && <div style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}

// ─── Sekme Çubuğu ─────────────────────────────────────────────────────────────

function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{
      display: 'flex',
      gap: '0.25rem',
      borderBottom: '1px solid var(--line)',
      marginBottom: '1.5rem',
    }}>
      {tabs.map(tab => {
        const Icon = tab.icon;
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.625rem 1rem',
              background: 'transparent',
              border: 'none',
              borderBottom: isActive ? '2px solid var(--teal)' : '2px solid transparent',
              cursor: 'pointer',
              color: isActive ? 'var(--teal)' : 'var(--muted)',
              fontSize: '0.875rem',
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.15s',
              marginBottom: -1,
            }}
          >
            <Icon size={16} />
            {tab.label}
            {tab.badge ? (
              <span style={{
                background: 'var(--rose)',
                color: '#fff',
                borderRadius: 99,
                padding: '0 6px',
                fontSize: '0.6875rem',
                fontWeight: 700,
                lineHeight: '1.5',
              }}>{tab.badge}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

// ─── Arama + Filtre Çubuğu ────────────────────────────────────────────────────

function FilterBar({ search, onSearch, filters = [], onRefresh, loading }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <div style={{
        flex: 1, minWidth: 200,
        display: 'flex', alignItems: 'center', gap: '0.5rem',
        background: 'var(--surface-muted)',
        border: '1px solid var(--line)',
        borderRadius: 8,
        padding: '0.4rem 0.75rem',
      }}>
        <Search size={15} style={{ color: 'var(--faint)', flexShrink: 0 }} />
        <input
          type="text"
          value={search}
          onChange={e => onSearch(e.target.value)}
          placeholder="Ara..."
          style={{
            background: 'transparent', border: 'none', outline: 'none',
            color: 'var(--ink)', fontSize: '0.875rem', width: '100%',
          }}
        />
      </div>
      {filters}
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.4rem',
          padding: '0.4rem 0.75rem',
          background: 'var(--surface-muted)',
          border: '1px solid var(--line)',
          borderRadius: 8,
          cursor: 'pointer',
          color: 'var(--muted)',
          fontSize: '0.8125rem',
        }}
      >
        <RefreshCw size={14} className={loading ? 'spin' : ''} />
        Yenile
      </button>
    </div>
  );
}

function SelectFilter({ value, onChange, options, placeholder }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        background: 'var(--surface-muted)',
        border: '1px solid var(--line)',
        borderRadius: 8,
        padding: '0.4rem 0.75rem',
        color: 'var(--ink)',
        fontSize: '0.875rem',
        cursor: 'pointer',
      }}
    >
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

// ─── Kullanıcı Düzenleme Modalı ──────────────────────────────────────────────

function EditUserModal({ user, onClose, onSave, onDelete }) {
  const [formData, setFormData] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    title: user?.title || '',
    email: user?.email || '',
    role: user?.role || 'PHYSICIAN',
    organization_name: user?.organization_name || '',
    is_active: user?.is_active ?? true,
    is_locked: user?.is_locked ?? false,
    must_change_password: user?.must_change_password ?? false,
  });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const isMouseDownOnBackdrop = useRef(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(user.id, formData);
      onClose();
    } catch {
      // Parent toast gösterir
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(user.id);
      onClose();
    } catch {
      // Parent toast gösterir
    } finally {
      setDeleting(false);
    }
  };

  const handleMouseDown = (e) => {
    isMouseDownOnBackdrop.current = (e.target === e.currentTarget);
  };

  const handleMouseUp = (e) => {
    if (isMouseDownOnBackdrop.current && e.target === e.currentTarget) {
      onClose();
    }
    isMouseDownOnBackdrop.current = false;
  };

  const inputStyle = {
    width: '100%',
    boxSizing: 'border-box',
    background: 'var(--surface-muted)',
    border: '1px solid var(--line)',
    borderRadius: 8,
    padding: '0.5rem 0.75rem',
    color: 'var(--ink)',
    fontSize: '0.875rem',
    outline: 'none',
  };

  return (
    <div
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
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
          maxWidth: 540,
          maxHeight: '90vh',
          overflowY: 'auto',
          color: 'var(--ink)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Başlık */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '1.25rem 1.5rem',
          borderBottom: '1px solid var(--line)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{
              width: 36, height: 36, borderRadius: 9,
              background: 'color-mix(in srgb, var(--teal) 12%, transparent)',
              color: 'var(--teal)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <User size={18} />
            </span>
            <div>
              <strong style={{ fontSize: '1rem', display: 'block', color: 'var(--ink)' }}>Kullanıcıyı Düzenle</strong>
              <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{user?.email}</span>
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
            }}
          >
            <X size={15} />
          </button>
        </div>

        {/* Form İçeriği */}
        <form onSubmit={handleSubmit} style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.875rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)', marginBottom: 4 }}>
                Ad *
              </label>
              <input
                required
                style={inputStyle}
                value={formData.first_name}
                onChange={e => setFormData(p => ({ ...p, first_name: e.target.value }))}
                placeholder="Ad"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)', marginBottom: 4 }}>
                Soyad *
              </label>
              <input
                required
                style={inputStyle}
                value={formData.last_name}
                onChange={e => setFormData(p => ({ ...p, last_name: e.target.value }))}
                placeholder="Soyad"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.875rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)', marginBottom: 4 }}>
                Unvan
              </label>
              <input
                style={inputStyle}
                value={formData.title}
                onChange={e => setFormData(p => ({ ...p, title: e.target.value }))}
                placeholder="Dr., Prof. Dr., Uz. Dr."
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)', marginBottom: 4 }}>
                Sistem Rolü *
              </label>
              <select
                style={{ ...inputStyle, cursor: 'pointer' }}
                value={formData.role}
                onChange={e => setFormData(p => ({ ...p, role: e.target.value }))}
              >
                <option value="PHYSICIAN">Hekim (PHYSICIAN)</option>
                <option value="RADIOLOGIST">Radyolog (RADIOLOGIST)</option>
                <option value="RESEARCHER">Araştırmacı (RESEARCHER)</option>
                <option value="ADMIN">Yönetici (ADMIN)</option>
                <option value="VIEWER">Gözlemci (VIEWER)</option>
              </select>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)', marginBottom: 4 }}>
              E-posta Adresi *
            </label>
            <input
              required
              type="email"
              style={inputStyle}
              value={formData.email}
              onChange={e => setFormData(p => ({ ...p, email: e.target.value }))}
              placeholder="ornek@hastane.edu.tr"
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted)', marginBottom: 4 }}>
              Kurum / Organizasyon
            </label>
            <input
              style={inputStyle}
              value={formData.organization_name}
              onChange={e => setFormData(p => ({ ...p, organization_name: e.target.value }))}
              placeholder="Kurum adı"
            />
          </div>

          {/* Durum & Güvenlik Ayarları */}
          <div style={{
            background: 'var(--surface-muted)',
            border: '1px solid var(--line)',
            borderRadius: 10,
            padding: '1rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Hesap Durumu & Güvenlik
            </span>

            {/* 3 Durum Seçici (Aktif / Kilitli / Pasif) */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setFormData(p => ({ ...p, is_active: true, is_locked: false }))}
                style={{
                  padding: '0.55rem 0.5rem',
                  borderRadius: 8,
                  border: `1px solid ${formData.is_active && !formData.is_locked ? 'var(--teal)' : 'var(--line)'}`,
                  background: formData.is_active && !formData.is_locked ? 'color-mix(in srgb, var(--teal) 14%, transparent)' : 'var(--surface)',
                  color: formData.is_active && !formData.is_locked ? 'var(--teal)' : 'var(--muted)',
                  cursor: 'pointer',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 5,
                  transition: 'all 0.15s',
                }}
              >
                <CheckCircle size={14} /> Aktif
              </button>
              <button
                type="button"
                onClick={() => setFormData(p => ({ ...p, is_locked: true }))}
                style={{
                  padding: '0.55rem 0.5rem',
                  borderRadius: 8,
                  border: `1px solid ${formData.is_locked ? 'var(--rose)' : 'var(--line)'}`,
                  background: formData.is_locked ? 'color-mix(in srgb, var(--rose) 14%, transparent)' : 'var(--surface)',
                  color: formData.is_locked ? 'var(--rose)' : 'var(--muted)',
                  cursor: 'pointer',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 5,
                  transition: 'all 0.15s',
                }}
              >
                <Lock size={14} /> Kilitli
              </button>
              <button
                type="button"
                onClick={() => setFormData(p => ({ ...p, is_active: false, is_locked: false }))}
                style={{
                  padding: '0.55rem 0.5rem',
                  borderRadius: 8,
                  border: `1px solid ${!formData.is_active && !formData.is_locked ? 'var(--amber)' : 'var(--line)'}`,
                  background: !formData.is_active && !formData.is_locked ? 'color-mix(in srgb, var(--amber) 14%, transparent)' : 'var(--surface)',
                  color: !formData.is_active && !formData.is_locked ? 'var(--amber)' : 'var(--muted)',
                  cursor: 'pointer',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 5,
                  transition: 'all 0.15s',
                }}
              >
                <UserMinus size={14} /> Pasif
              </button>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', cursor: 'pointer', fontSize: '0.8125rem', marginTop: '0.25rem' }}>
              <input
                type="checkbox"
                checked={formData.must_change_password}
                onChange={e => setFormData(p => ({ ...p, must_change_password: e.target.checked }))}
                style={{ accentColor: 'var(--amber)', width: 16, height: 16 }}
              />
              <span>İlk girişte parola değişimini zorunlu kıl</span>
            </label>
          </div>

          {/* Aksiyon Butonları & Silme Alanı */}
          <div style={{
            borderTop: '1px solid var(--line)',
            paddingTop: '1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.5rem',
            flexWrap: 'wrap',
          }}>
            {!confirmDelete ? (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.45rem 0.875rem',
                  background: 'var(--danger-bg)',
                  border: '1px solid var(--rose)',
                  borderRadius: 8,
                  cursor: 'pointer',
                  color: 'var(--rose)',
                  fontSize: '0.8125rem',
                  fontWeight: 500,
                }}
              >
                <Trash2 size={14} />
                Kullanıcıyı Sil
              </button>
            ) : (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                background: 'var(--danger-bg)',
                padding: '0.35rem 0.75rem',
                borderRadius: 8,
                border: '1px solid var(--rose)',
              }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--rose)', fontWeight: 500 }}>
                  Silinsin mi?
                </span>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  style={{
                    padding: '0.25rem 0.6rem',
                    background: 'var(--rose)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                  }}
                >
                  {deleting ? 'Siliniyor...' : 'Evet, Sil'}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  style={{
                    padding: '0.25rem 0.5rem',
                    background: 'transparent',
                    color: 'var(--muted)',
                    border: '1px solid var(--line)',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: '0.75rem',
                  }}
                >
                  Vazgeç
                </button>
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.625rem' }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'var(--surface-muted)',
                  border: '1px solid var(--line)',
                  borderRadius: 8,
                  cursor: 'pointer',
                  color: 'var(--muted)',
                  fontSize: '0.875rem',
                }}
              >
                İptal
              </button>
              <button
                type="submit"
                disabled={saving}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.5rem 1.25rem',
                  background: 'var(--teal)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: 500,
                  opacity: saving ? 0.7 : 1,
                }}
              >
                {saving ? <RefreshCw size={14} className="spin" /> : <Save size={14} />}
                {saving ? 'Kaydediliyor...' : 'Kaydet'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Kullanıcı Tablosu ────────────────────────────────────────────────────────

function UsersTab({ lockedCount }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [editingUser, setEditingUser] = useState(null);
  const [toast, setToast] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminUsers({ search, role: roleFilter, status: statusFilter });
      setUsers(data.users || []);
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleSaveUser = async (userId, formData) => {
    try {
      await patchAdminUser(userId, formData);
      showToast('Kullanıcı bilgileri başarıyla güncellendi.');
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, ...formData } : u));
    } catch {
      showToast('Kullanıcı güncellenemedi.', 'danger');
      throw new Error();
    }
  };

  const handleDeleteUser = async (userId) => {
    try {
      await deleteAdminUser(userId);
      showToast('Kullanıcı sistemden silindi.');
      setUsers(prev => prev.filter(u => u.id !== userId));
    } catch {
      showToast('Kullanıcı silinemedi.', 'danger');
      throw new Error();
    }
  };

  const statusBadge = (user) => {
    if (user.is_locked) return { label: 'Kilitli', color: 'var(--rose)' };
    if (!user.is_active) return { label: 'Pasif', color: 'var(--muted)' };
    return { label: 'Aktif', color: 'var(--teal)' };
  };

  return (
    <div>
      {toast && (
        <div style={{
          position: 'fixed', top: 80, right: 24, zIndex: 9999,
          background: toast.type === 'danger' ? 'var(--danger-bg)' : 'var(--success-bg)',
          border: `1px solid ${toast.type === 'danger' ? 'var(--rose)' : 'var(--teal)'}`,
          color: toast.type === 'danger' ? 'var(--rose)' : 'var(--teal)',
          borderRadius: 10, padding: '0.75rem 1.25rem',
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          boxShadow: 'var(--shadow)', fontSize: '0.875rem',
        }}>
          {toast.type === 'danger' ? <XCircle size={16} /> : <CheckCircle size={16} />}
          {toast.msg}
        </div>
      )}

      {editingUser && (
        <EditUserModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSave={handleSaveUser}
          onDelete={handleDeleteUser}
        />
      )}

      <FilterBar
        search={search}
        onSearch={setSearch}
        loading={loading}
        onRefresh={load}
        filters={[
          <SelectFilter
            key="role"
            value={roleFilter}
            onChange={setRoleFilter}
            placeholder="Tüm roller"
            options={[
              { value: 'ADMIN', label: 'Yönetici' },
              { value: 'PHYSICIAN', label: 'Hekim' },
              { value: 'RADIOLOGIST', label: 'Radyolog' },
              { value: 'RESEARCHER', label: 'Araştırmacı' },
              { value: 'VIEWER', label: 'Gözlemci' },
            ]}
          />,
          <SelectFilter
            key="status"
            value={statusFilter}
            onChange={setStatusFilter}
            placeholder="Tüm durumlar"
            options={[
              { value: 'active', label: 'Aktif' },
              { value: 'locked', label: 'Kilitli' },
              { value: 'inactive', label: 'Pasif' },
            ]}
          />,
        ]}
      />

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--line)' }}>
              {['Kullanıcı', 'Rol', 'Kurum', 'Durum', 'MFA', 'Son Giriş', 'İşlemler'].map(h => (
                <th key={h} style={{
                  padding: '0.625rem 0.75rem', textAlign: 'left',
                  color: 'var(--muted)', fontWeight: 600, fontSize: '0.75rem',
                  whiteSpace: 'nowrap',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
                <RefreshCw size={18} className="spin" style={{ marginRight: 8 }} />
                Yükleniyor...
              </td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
                Kullanıcı bulunamadı.
              </td></tr>
            ) : users.map(user => {
              const badge = statusBadge(user);
              return (
                <tr key={user.id} style={{ borderBottom: '1px solid var(--line)', transition: 'background 0.1s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-muted)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  {/* Kullanıcı */}
                  <td style={{ padding: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                      <span style={{
                        width: 30, height: 30, borderRadius: '50%',
                        background: ROLE_COLORS[user.role] || 'var(--muted)',
                        color: '#fff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontWeight: 700, fontSize: '0.8125rem', flexShrink: 0,
                      }}>
                        {(user.first_name || user.email || '?')[0].toUpperCase()}
                      </span>
                      <div>
                        <div style={{ fontWeight: 500, color: 'var(--ink)' }}>
                          {user.title ? `${user.title} ` : ''}{user.first_name} {user.last_name}
                        </div>
                        <div style={{ color: 'var(--faint)', fontSize: '0.75rem' }}>{user.email}</div>
                      </div>
                    </div>
                  </td>
                  {/* Rol */}
                  <td style={{ padding: '0.75rem' }}>
                    <span style={{
                      background: `color-mix(in srgb, ${ROLE_COLORS[user.role] || 'var(--muted)'} 12%, transparent)`,
                      color: ROLE_COLORS[user.role] || 'var(--muted)',
                      border: `1px solid ${ROLE_COLORS[user.role] || 'var(--muted)'}`,
                      borderRadius: 6, padding: '2px 8px', fontSize: '0.75rem', fontWeight: 600,
                    }}>
                      {ROLE_LABELS[user.role] || user.role}
                    </span>
                  </td>
                  {/* Kurum */}
                  <td style={{ padding: '0.75rem', color: 'var(--muted)', maxWidth: 180 }}>
                    <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {user.organization_name || '—'}
                    </span>
                  </td>
                  {/* Durum */}
                  <td style={{ padding: '0.75rem' }}>
                    <span style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      color: badge.color, fontSize: '0.8125rem', fontWeight: 500,
                    }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: badge.color, flexShrink: 0 }} />
                      {badge.label}
                    </span>
                    {user.failed_login_attempts > 0 && (
                      <span style={{ fontSize: '0.6875rem', color: 'var(--amber)' }}>
                        {user.failed_login_attempts} başarısız deneme
                      </span>
                    )}
                  </td>
                  {/* MFA */}
                  <td style={{ padding: '0.75rem' }}>
                    {user.mfa_enabled
                      ? <ShieldCheck size={16} style={{ color: 'var(--teal)' }} />
                      : <ShieldAlert size={16} style={{ color: 'var(--faint)' }} />
                    }
                  </td>
                  {/* Son Giriş */}
                  <td style={{ padding: '0.75rem', color: 'var(--muted)', whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                    {formatRelativeTime(user.last_login_at)}
                  </td>
                  {/* İşlemler */}
                  <td style={{ padding: '0.75rem' }}>
                    <button
                      type="button"
                      title="Kullanıcıyı Düzenle"
                      onClick={() => setEditingUser(user)}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.375rem',
                        padding: '0.35rem 0.75rem',
                        background: 'color-mix(in srgb, var(--teal) 10%, transparent)',
                        border: '1px solid color-mix(in srgb, var(--teal) 30%, transparent)',
                        borderRadius: 7,
                        cursor: 'pointer',
                        color: 'var(--teal)',
                        fontSize: '0.75rem',
                        fontWeight: 500,
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'color-mix(in srgb, var(--teal) 20%, transparent)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'color-mix(in srgb, var(--teal) 10%, transparent)'}
                    >
                      <Pencil size={12} />
                      <span>Düzenle</span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Oturumlar Sekmesi ────────────────────────────────────────────────────────

function SessionsTab() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [revoking, setRevoking] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminSessions();
      setSessions(data.sessions || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRevoke = async (sessionId) => {
    setRevoking(sessionId);
    try {
      await revokeAdminSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
    } finally {
      setRevoking('');
    }
  };

  const filtered = sessions.filter(s => {
    const q = search.toLowerCase();
    return !q || s.user_email?.toLowerCase().includes(q) || s.ip_address?.includes(q);
  });

  const parseDevice = (ua = '') => {
    if (!ua) return '—';
    if (ua.includes('iPhone') || ua.includes('Mobile')) return '📱 Mobil';
    if (ua.includes('Macintosh')) return '🍎 macOS';
    if (ua.includes('Windows')) return '🪟 Windows';
    if (ua.includes('Linux') || ua.includes('X11')) return '🐧 Linux';
    return '🖥 Masaüstü';
  };

  const parseBrowser = (ua = '') => {
    if (ua.includes('Chrome')) return 'Chrome';
    if (ua.includes('Firefox')) return 'Firefox';
    if (ua.includes('Safari')) return 'Safari';
    if (ua.includes('Edge')) return 'Edge';
    return 'Bilinmiyor';
  };

  return (
    <div>
      <FilterBar search={search} onSearch={setSearch} loading={loading} onRefresh={load} />
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--line)' }}>
              {['Kullanıcı', 'IP Adresi', 'Cihaz / Tarayıcı', 'Başlangıç', 'Son Aktivite', 'Bitiş', 'İşlem'].map(h => (
                <th key={h} style={{ padding: '0.625rem 0.75rem', textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
                <RefreshCw size={18} className="spin" style={{ marginRight: 8 }} />Yükleniyor...
              </td></tr>
            ) : filtered.map(sess => (
              <tr key={sess.id} style={{ borderBottom: '1px solid var(--line)' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-muted)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ padding: '0.75rem' }}>
                  <div style={{ fontWeight: 500, color: 'var(--ink)' }}>{sess.user_name || '—'}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>{sess.user_email}</div>
                </td>
                <td style={{ padding: '0.75rem', color: 'var(--muted)', fontFamily: 'monospace', fontSize: '0.8125rem' }}>
                  {sess.ip_address || '—'}
                </td>
                <td style={{ padding: '0.75rem', color: 'var(--muted)' }}>
                  <div>{parseDevice(sess.user_agent)}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>{parseBrowser(sess.user_agent)}</div>
                </td>
                <td style={{ padding: '0.75rem', color: 'var(--muted)', whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                  {formatDate(sess.created_at)}
                </td>
                <td style={{ padding: '0.75rem', color: 'var(--muted)', whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                  {formatRelativeTime(sess.last_used_at)}
                </td>
                <td style={{ padding: '0.75rem', color: 'var(--muted)', whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                  {formatDate(sess.expires_at)}
                </td>
                <td style={{ padding: '0.75rem' }}>
                  <button
                    type="button"
                    onClick={() => handleRevoke(sess.id)}
                    disabled={revoking === sess.id}
                    title="Oturumu sonlandır"
                    style={actionBtn('var(--rose)')}
                  >
                    {revoking === sess.id ? <RefreshCw size={13} className="spin" /> : <Trash2 size={13} />}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Organizasyonlar Sekmesi ──────────────────────────────────────────────────

function OrganizationsTab() {
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminOrganizations();
      setOrgs(data.organizations || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const ORG_TYPE_LABELS = {
    UNIVERSITY_HOSPITAL: 'Üniversite Hastanesi',
    RESEARCH_CENTER: 'Araştırma Merkezi',
    PRIVATE_CLINIC: 'Özel Klinik',
    PUBLIC_HOSPITAL: 'Kamu Hastanesi',
  };

  const filtered = orgs.filter(o => {
    const q = search.toLowerCase();
    return !q || o.name?.toLowerCase().includes(q) || o.code?.toLowerCase().includes(q);
  });

  return (
    <div>
      <FilterBar search={search} onSearch={setSearch} loading={loading} onRefresh={load} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
        {loading ? (
          <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: '2rem', color: 'var(--muted)' }}>
            <RefreshCw size={18} className="spin" />
          </div>
        ) : filtered.map(org => (
          <div key={org.id} style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 12,
            padding: '1.25rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: 'color-mix(in srgb, var(--cyan) 12%, transparent)',
                  color: 'var(--cyan)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Building2 size={20} />
                </span>
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--ink)', fontSize: '0.875rem' }}>{org.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--faint)', fontFamily: 'monospace' }}>{org.code}</div>
                </div>
              </div>
              <span style={{
                borderRadius: 6, padding: '2px 8px',
                fontSize: '0.6875rem', fontWeight: 600,
                background: org.is_active ? 'color-mix(in srgb, var(--teal) 12%, transparent)' : 'var(--surface-muted)',
                color: org.is_active ? 'var(--teal)' : 'var(--muted)',
                border: `1px solid ${org.is_active ? 'var(--teal)' : 'var(--line)'}`,
                whiteSpace: 'nowrap',
              }}>
                {org.is_active ? 'Aktif' : 'Pasif'}
              </span>
            </div>
            <div style={{ marginTop: '1rem', display: 'flex', gap: '1.5rem', fontSize: '0.8125rem', color: 'var(--muted)' }}>
              <span><Users size={13} style={{ marginRight: 4, verticalAlign: 'middle' }} />{org.user_count || 0} kullanıcı</span>
              <span>{ORG_TYPE_LABELS[org.org_type] || org.org_type || '—'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Audit Log Sekmesi ────────────────────────────────────────────────────────

function AuditLogTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminAuditLog({ severity });
      setLogs(data.logs || []);
    } finally {
      setLoading(false);
    }
  }, [severity]);

  useEffect(() => { load(); }, [load]);

  const filtered = logs.filter(l => {
    const q = search.toLowerCase();
    return !q || l.user_email?.toLowerCase().includes(q) || l.action?.toLowerCase().includes(q) || l.detail?.toLowerCase().includes(q);
  });

  const SEVERITY_ICONS = {
    info: <Activity size={14} />,
    success: <CheckCircle size={14} />,
    warning: <AlertTriangle size={14} />,
    danger: <XCircle size={14} />,
  };

  return (
    <div>
      <FilterBar
        search={search}
        onSearch={setSearch}
        loading={loading}
        onRefresh={load}
        filters={[
          <SelectFilter
            key="sev"
            value={severity}
            onChange={setSeverity}
            placeholder="Tüm seviyeler"
            options={[
              { value: 'info', label: 'Bilgi' },
              { value: 'success', label: 'Başarılı' },
              { value: 'warning', label: 'Uyarı' },
              { value: 'danger', label: 'Hata / Risk' },
            ]}
          />,
        ]}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--muted)' }}>
            <RefreshCw size={18} className="spin" />
          </div>
        ) : filtered.map(log => {
          const color = AUDIT_SEVERITY_COLORS[log.severity] || 'var(--muted)';
          return (
            <div key={log.id} style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              padding: '0.75rem 1rem',
              background: 'var(--surface)',
              border: '1px solid var(--line)',
              borderLeft: `3px solid ${color}`,
              borderRadius: '0 10px 10px 0',
            }}>
              <span style={{ color, marginTop: 2 }}>{SEVERITY_ICONS[log.severity]}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 600, color: 'var(--ink)', fontSize: '0.8125rem' }}>
                      {AUDIT_ACTION_LABELS[log.action] || log.action}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>{log.user_email}</span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--faint)', whiteSpace: 'nowrap' }}>
                    {formatDate(log.timestamp)}
                  </span>
                </div>
                {log.detail && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>{log.detail}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Ana Admin Dashboard ──────────────────────────────────────────────────────

export default function AdminDashboard({ session, onBack }) {
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('users');

  useEffect(() => {
    setStatsLoading(true);
    getAdminStats().then(setStats).finally(() => setStatsLoading(false));
  }, []);

  const tabs = [
    { id: 'users', label: 'Kullanıcılar', icon: Users, badge: stats?.locked_users || null },
    { id: 'sessions', label: 'Oturumlar', icon: Monitor },
    { id: 'organizations', label: 'Kurumlar', icon: Building2 },
    { id: 'audit', label: 'Audit Log', icon: Shield },
  ];

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--canvas)',
      color: 'var(--ink)',
      fontFamily: 'inherit',
    }}>
      {/* Üst Bar */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'var(--panel-bg)',
        borderBottom: '1px solid var(--line)',
        backdropFilter: 'blur(12px)',
        padding: '0 1.5rem',
        height: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.4rem',
              background: 'var(--surface-muted)',
              border: '1px solid var(--line)',
              borderRadius: 8,
              padding: '0.35rem 0.75rem',
              cursor: 'pointer',
              color: 'var(--muted)',
              fontSize: '0.8125rem',
            }}
          >
            <ArrowLeft size={15} />
            Geri
          </button>

          <div style={{ width: 1, height: 20, background: 'var(--line)' }} />

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{
              width: 28, height: 28, borderRadius: 8,
              background: 'color-mix(in srgb, var(--rose) 15%, transparent)',
              color: 'var(--rose)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Shield size={15} />
            </span>
            <div>
              <strong style={{ fontSize: '0.9375rem', color: 'var(--ink)' }}>Admin Paneli</strong>
              <div style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>NeuroOncoTrack-AI Yönetim</div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{
            background: 'color-mix(in srgb, var(--amber) 12%, transparent)',
            color: 'var(--amber)',
            border: '1px solid color-mix(in srgb, var(--amber) 30%, transparent)',
            borderRadius: 6, padding: '2px 10px', fontSize: '0.75rem', fontWeight: 600,
          }}>
            ADMIN
          </span>
          <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
            {session?.user?.name || session?.user?.email || 'Yönetici'}
          </span>
        </div>
      </header>

      <main style={{ maxWidth: 1280, margin: '0 auto', padding: '1.5rem' }}>

        {/* İstatistik Kartları */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}>
          <StatCard
            icon={Users}
            label="Toplam Kullanıcı"
            value={statsLoading ? '—' : stats?.total_users ?? '—'}
            sub={`${stats?.active_users ?? '—'} aktif`}
            color="var(--teal)"
            trend={stats?.new_users_last_30d}
          />
          <StatCard
            icon={Lock}
            label="Kilitli Hesap"
            value={statsLoading ? '—' : stats?.locked_users ?? '—'}
            sub="İnceleme gerekebilir"
            color={stats?.locked_users > 0 ? 'var(--rose)' : 'var(--muted)'}
          />
          <StatCard
            icon={ShieldCheck}
            label="MFA Aktif"
            value={statsLoading ? '—' : `${stats?.mfa_adoption_rate ?? '—'}%`}
            sub={`${stats?.mfa_enabled_count ?? '—'} kullanıcı`}
            color="var(--cyan)"
          />
          <StatCard
            icon={Monitor}
            label="Aktif Oturum"
            value={statsLoading ? '—' : stats?.active_sessions ?? '—'}
            sub="Şu an bağlı"
            color="var(--amber)"
          />
          <StatCard
            icon={Building2}
            label="Organizasyon"
            value={statsLoading ? '—' : stats?.total_organizations ?? '—'}
            color="var(--cyan)"
          />
          <StatCard
            icon={AlertTriangle}
            label="Başarısız Giriş"
            value={statsLoading ? '—' : stats?.failed_logins_last_24h ?? '—'}
            sub="Son 24 saat"
            color={stats?.failed_logins_last_24h > 5 ? 'var(--rose)' : 'var(--amber)'}
          />
        </div>

        {/* Sekme İçerikleri */}
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 16,
          padding: '1.5rem',
        }}>
          <TabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

          {activeTab === 'users' && <UsersTab lockedCount={stats?.locked_users} />}
          {activeTab === 'sessions' && <SessionsTab />}
          {activeTab === 'organizations' && <OrganizationsTab />}
          {activeTab === 'audit' && <AuditLogTab />}
        </div>

        {/* Alt Not */}
        <div style={{
          marginTop: '1.5rem',
          padding: '0.875rem 1rem',
          background: 'color-mix(in srgb, var(--amber) 8%, transparent)',
          border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
          borderRadius: 10,
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          fontSize: '0.8125rem',
          color: 'var(--amber)',
        }}>
          <AlertTriangle size={16} style={{ flexShrink: 0 }} />
          <span>
            Gösterilen veriler şu an <strong>demo/mock</strong> modunda çalışmaktadır.
            Backend admin endpoint'leri hazır olduğunda <code style={{ fontSize: '0.75rem' }}>adminService.js</code> dosyasında
            {' '}<code style={{ fontSize: '0.75rem' }}>MOCK_MODE = false</code> yapılması yeterlidir.
          </span>
        </div>
      </main>
    </div>
  );
}
