import { useEffect, useState } from 'react';
import { Activity, CheckCircle, Cpu, Database, Settings, ShieldAlert } from 'lucide-react';
import heroImage from './assets/login-workstation.png';
import { capabilities, loginMetrics } from './config/neuroConstants.js';
import ThemeToggle from './components/common/ThemeToggle.jsx';
import ProductWorkspace from './components/workspace/ProductWorkspace.jsx';
import { getInitialTheme } from './utils/neuroUtils.js';

function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [institutionCode, setInstitutionCode] = useState('NOT-2026');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberStation, setRememberStation] = useState(true);
  const [status, setStatus] = useState(null);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('neuro-login-theme', theme);
  }, [theme]);

  useEffect(() => {
    document.body.classList.toggle('workspace-mode', isAuthenticated);
    return () => document.body.classList.remove('workspace-mode');
  }, [isAuthenticated]);

  const updateManualField = (setter, value) => {
    setter(value);
    if (isDemoMode) {
      setIsDemoMode(false);
      setStatus(null);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    if (!institutionCode.trim() || !email.trim() || !password.trim()) {
      setStatus({
        tone: 'error',
        message: 'Kurum kodu, e-posta ve şifre alanlarını doldurun.',
      });
      return;
    }

    setStatus(null);
    setIsAuthenticated(true);
  };

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

  if (isAuthenticated) {
    return (
      <ProductWorkspace
        isDemoMode={isDemoMode}
        theme={theme}
        setTheme={setTheme}
        onLogout={() => {
          setIsAuthenticated(false);
          setStatus(null);
        }}
      />
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
          <ThemeToggle theme={theme} setTheme={setTheme} />
        </header>

        <div className="auth-copy">
          <span className="eyebrow">Yetkili erişim</span>
          <h1 id="login-title">Klinik giriş</h1>
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
            <button className="primary-action" type="submit">
              <CheckCircle size={18} />
              Güvenli giriş
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
