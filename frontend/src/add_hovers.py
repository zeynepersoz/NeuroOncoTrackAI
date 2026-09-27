import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Add class to Parolamı unuttum button
# It currently has style={{ background: 'transparent', border: 'none', color: 'var(--primary, #00e5ff)', cursor: 'pointer', fontSize: '0.75rem', padding: 0, fontWeight: 500 }}
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

# Wait, there's another "Parolamı unuttum" in WelcomeScreen? No, only in LoginScreen.

# Add class to the login tabs
text = text.replace(
    'onClick={() => switchLoginTab(tab.id)}',
    'className={`login-tab-btn ${loginTab === tab.id ? "active" : ""}`}\n                onClick={() => switchLoginTab(tab.id)}'
)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)


with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

hover_css = """
/* Hover effects requested by user */
.login-tab-btn {
  transition: all 0.2s ease;
}
.login-tab-btn:not(.active):hover {
  background: rgba(0, 229, 255, 0.1) !important;
  color: var(--primary, #00e5ff) !important;
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.2);
}

.text-link-btn {
  transition: all 0.2s ease;
}
.text-link-btn:hover {
  text-decoration: underline;
  text-shadow: 0 0 8px rgba(0, 229, 255, 0.4);
}
"""

css += "\n" + hover_css

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("Hover effects added.")
