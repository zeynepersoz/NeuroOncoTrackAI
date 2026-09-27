import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Fix WelcomeScreen margins
# Find function WelcomeScreen
ws_start = text.find('function WelcomeScreen')
if ws_start != -1:
    ws_end = text.find('function App', ws_start)
    ws_text = text[ws_start:ws_end]
    ws_text = ws_text.replace("style={{ marginTop: 'auto' }}", "style={{ marginTop: '0' }}")
    ws_text = ws_text.replace("style={{ marginTop: '2rem', marginBottom: 'auto' }}", "style={{ marginTop: '2rem' }}")
    text = text[:ws_start] + ws_text + text[ws_end:]

# 2. Fix LoginScreen fade-out
# The LoginScreen is inside function App, around line 1000
app_start = text.find('function App')
app_text = text[app_start:]
app_text = app_text.replace('className="auth-heading-row"', 'className={`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}')
app_text = app_text.replace('className="login-panel"', 'className={`login-panel ${isExiting ? "fade-out" : "animated-fade"}`}')
# We need to make sure we don't accidentally replace anything in WelcomeScreen again if it's somehow below App (it's not, App is the last function).
text = text[:app_start] + app_text

# 3. Fix the position of compliance-strip in App.jsx
# We will just change its inline style to be fixed at the bottom.
# The user wants them fixed at the bottom like the logo.
# Logo is: position: 'fixed', bottom: '-15px', left: '10px'
# We can put compliance strip at position: 'fixed', bottom: '15px', left: '150px' so it sits next to the logo!
# Let's find the compliance strip in text.
strip_regex = r'<div className="compliance-strip" aria-label="Guvenlik ve standart bilgileri" style={{ gap: \'16px\', display: \'flex\', alignItems: \'center\' }}>'
fixed_strip = '<div className="compliance-strip" aria-label="Guvenlik ve standart bilgileri" style={{ gap: \'16px\', display: \'flex\', alignItems: \'center\', position: \'fixed\', bottom: \'15px\', left: \'150px\', zIndex: 50 }}>'
text = text.replace(strip_regex, fixed_strip)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Fixed WelcomeScreen, LoginScreen animations, and fixed compliance strip.")
