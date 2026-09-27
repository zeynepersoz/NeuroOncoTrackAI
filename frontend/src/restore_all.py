import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Imports
import_statement = """import appLogo from './assets/UygulamaLogo.png';
import hl7Img from './assets/hl7.png';
import auditImg from './assets/audit.png';
import etikImg from './assets/etik_kurul.jpg';
"""
text = text.replace("import heroImage from './assets/login-workstation.png';", import_statement + "import heroImage from './assets/login-workstation.png';")

# 2. Logo replacement
logo_tag = '<img src={appLogo} alt="NeuroOncoTrack-AI Logo" style={{ height: \'120px\', width: \'auto\', position: \'fixed\', bottom: \'-15px\', left: \'10px\', zIndex: 50 }} />'
# Find all <header className="brand-row"> blocks and replace their contents
text = re.sub(
    r'<header className="brand-row">.*?</header>',
    f'<header className="brand-row">\n          {logo_tag}\n        </header>',
    text,
    flags=re.DOTALL
)

# 3. Add `isExiting` to LoginScreen (inside App component) and animated classes
text = text.replace(
    "const [status, setStatus] = useState(null);",
    "const [status, setStatus] = useState(null);\n  const [isExiting, setIsExiting] = useState(false);"
)

# Replace back button in LoginScreen
login_back_func = """onClick={() => {
              setIsExiting(true);
              setTimeout(() => {
                setScreen('welcome');
                setIsExiting(false);
              }, 400);
            }}"""
text = text.replace("onClick={() => setScreen('welcome')}", login_back_func, 1)

# Add animated-fade and isExiting classes
def inject_anim_classes(content):
    c = content.replace('className="auth-heading-row"', 'className={`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}')
    c = c.replace('className="login-panel"', 'className={`login-panel ${isExiting ? "fade-out" : "animated-fade"}`}')
    return c

login_start = text.find('// ─── Giriş ekranı ───')
login_text = text[login_start:]
login_text = inject_anim_classes(login_text)
text = text[:login_start] + login_text

# 4. RegisterScreen modifications (visual side, animations, theme toggle)
reg_start = text.find('function RegisterScreen')
reg_end = text.find('// ───', reg_start)
reg_text = text[reg_start:reg_end]

# Add props
reg_text = reg_text.replace(
    'function RegisterScreen({ onSuccess, onBack }) {',
    'function RegisterScreen({ onSuccess, onBack, theme, setTheme }) {'
)
# Add isExiting and handleBack
reg_state = """function RegisterScreen({ onSuccess, onBack, theme, setTheme }) {
  const [isExiting, setIsExiting] = useState(false);
  const handleBack = () => {
    setIsExiting(true);
    setTimeout(onBack, 400);
  };"""
reg_text = reg_text.replace(
    "function RegisterScreen({ onSuccess, onBack, theme, setTheme }) {",
    reg_state
)
# Replace onBack with handleBack in RegisterScreen ONLY
reg_text = reg_text.replace('onClick={onBack}', 'onClick={handleBack}')

# Add ThemeToggle
reg_text = reg_text.replace(
    '<h1 id="reg-title">Kayıt Ol</h1>\n          </div>\n        </div>',
    '<h1 id="reg-title">Kayıt Ol</h1>\n          </div>\n          <ThemeToggle theme={theme} setTheme={setTheme} />\n        </div>'
)

# Apply classes
reg_text = inject_anim_classes(reg_text)

# Fix missing visual-side in RegisterScreen
# Replace the empty <section className="visual-side" aria-hidden="true" />
visual_side = """<section className="visual-side" aria-label="Sistem yetenekleri ve durum metrikleri">
        <img className="hero-image" src={heroImage} alt="Klinik istasyon görünümü" />
        <div className="visual-scrim" />
        <div className="visual-content">
          <div className="feature-grid">
            {capabilities.map((cap) => (
              <div key={cap.id} className="feature-card">
                <cap.icon className="feature-icon" size={24} />
                <div className="feature-info">
                  <h3>{cap.title}</h3>
                  <p>{cap.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="metrics-row">
            {loginMetrics.map((metric, i) => (
              <div key={i} className="metric-pill">
                <span className="metric-val">{metric.value}</span>
                <span className="metric-label">{metric.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>"""
reg_text = re.sub(r'<section className="visual-side".*?</section>', visual_side, reg_text, flags=re.DOTALL)

text = text[:reg_start] + reg_text + text[reg_end:]

# Update RegisterScreen call in App
text = text.replace(
    '<RegisterScreen onSuccess={() => setScreen(\'login\')} onBack={() => setScreen(\'welcome\')} />',
    '<RegisterScreen onSuccess={() => setScreen(\'login\')} onBack={() => setScreen(\'welcome\')} theme={theme} setTheme={setTheme} />'
)

# 5. Move status block in LoginScreen
status_regex = r'(\s*\{status \? \(\s*<div className=\{`form-alert \$\{status\.tone\}`\} role="status">.*?</div>\s*\) : null\})'
# find first one (which is MfaScreen), ignore it. Find the one inside login_text
# Actually, since it's only in LoginScreen and MfaScreen, let's just find the last one.
status_matches = list(re.finditer(status_regex, text, re.DOTALL))
if len(status_matches) >= 1:
    last_match = status_matches[-1]
    status_block = last_match.group(1)
    modified_status_block = status_block.replace(
        'role="status"', 
        'role="status" style={{ fontSize: "0.85rem", padding: "8px 12px", marginTop: "0.25rem" }}'
    )
    
    # Remove it
    text = text[:last_match.start()] + text[last_match.end():]
    
    # Insert it below action-row in LoginScreen
    login_form_end = text.rfind('</form>')
    action_row_end = text.rfind('</div>', 0, login_form_end)
    text = text[:action_row_end+6] + modified_status_block + "\n        " + text[login_form_end:]

# 6. Adjust button margins and hover classes
text = text.replace(
    "marginBottom: '1rem', marginTop: '0.25rem'",
    "marginBottom: '0.5rem', marginTop: '0.25rem'"
)
text = text.replace(
    """<button
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
            >""",
    """<button
              type="button"
              className="text-link-btn"
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
            >"""
)
text = text.replace(
    'onClick={() => switchLoginTab(tab.id)}',
    'className={`login-tab-btn ${loginTab === tab.id ? "active" : ""}`}\n                onClick={() => switchLoginTab(tab.id)}'
)

# 7. Add images to BOTH compliance strips
new_strip = """<div className="compliance-strip" aria-label="Guvenlik ve standart bilgileri" style={{ gap: '16px', display: 'flex', alignItems: 'center' }}>
          <img src={etikImg} alt="TUTF-GOBAEK" style={{ height: '36px', objectFit: 'contain', borderRadius: '4px' }} />
          <img src={hl7Img} alt="HL7 FHIR R4" style={{ height: '36px', objectFit: 'contain' }} />
          <img src={auditImg} alt="Audit Ready" style={{ height: '36px', objectFit: 'contain' }} />
        </div>"""

text = re.sub(
    r'<div className="compliance-strip".*?</div>',
    new_strip,
    text,
    flags=re.DOTALL
)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Restored ALL changes perfectly.")
