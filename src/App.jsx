import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, CheckCircle, Cpu, Database, RefreshCw, Settings, ShieldAlert } from 'lucide-react';
import heroImage from './assets/login-workstation.png';
import { capabilities, IDLE_WARNING_MINUTES, loginMetrics, REAL_SESSION_MINUTES } from './config/neuroConstants.js';
import ThemeToggle from './components/common/ThemeToggle.jsx';
import ProductWorkspace from './components/workspace/ProductWorkspace.jsx';
import { getInitialTheme } from './utils/neuroUtils.js';
import { login, logout } from './services/authService.js';

const activityEvents = ['pointerdown', 'keydown', 'wheel', 'touchstart'];

function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [institutionCode, setInstitutionCode] = useState('NOT-2026');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberStation, setRememberStation] = useState(true);
  const [status, setStatus] = useState(null);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [idleWarning, setIdleWarning] = useState(false);
  const idleTimersRef = useRef({ warning: null, logout: null });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('neuro-login-theme', theme);
  }, [theme]);

  useEffect(() => {
    document.body.classList.toggle('workspace-mode', Boolean(session));
    return () => document.body.classList.remove('workspace-mode');
  }, [session]);

  const can = useCallback(
    (permission) => {
      if (!permission) return true;
      const userPermissions = session?.user?.permissions || [];
      return userPermissions.includes(permission) || userPermissions.includes('*');
    },
    [session],
  );

  const updateManualField = (setter, value) => {
    setter(value);
    if (isDemoMode) {
      setIsDemoMode(false);
      setStatus(null);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!institutionCode.trim() || !email.trim() || !password.trim()) {
      setStatus({
        tone: 'error',
        message: 'Kurum kodu, e-posta ve şifre alanlarını doldurun.',
      });
      return;
    }

    setAuthLoading(true);
    setStatus(null);

    try {
      const nextSession = await login({
        institutionCode: institutionCode.trim(),
        email: email.trim(),
        password,
        rememberStation,
        demo: isDemoMode,
      });

      if (nextSession.mode === 'mfa') {
        setStatus({
          tone: 'error',
          message: 'İki faktör doğrulama ekranı backend tarafından etkinleştirildiğinde burada açılacak.',
        });
        return;
      }

      if (nextSession.mode === 'password-change') {
        setStatus({
          tone: 'error',
          message: 'Parola değişimi zorunlu. Backend parola ekranı hazır olduğunda bu akışa yönlendirilecek.',
        });
        return;
      }

      setIdleWarning(false);
      setSession(nextSession);
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

  if (session) {
    return (
      <>
        <ProductWorkspace
          isDemoMode={isDemoMode}
          session={session}
          can={can}
          theme={theme}
          setTheme={setTheme}
          onLogout={handleLogout}
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

          <label className="check-row">
            <input
              type="checkbox"
              checked={rememberStation}
              onChange={(event) => setRememberStation(event.target.checked)}
            />
            <span>Bu cihazı güvenli çalışma istasyonu olarak hatırla</span>
          </label>

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
              className={`secondary-action ${isDemoMode ? 'active' : ''}`}
              type="button"
              onClick={toggleDemoAccess}
            >
              <Activity size={18} />
              {isDemoMode ? "Demo'dan çık" : 'Demo erişimi'}
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
