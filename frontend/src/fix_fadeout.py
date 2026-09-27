import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Revert all global mistakes
text = text.replace('{`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}', '"auth-heading-row animated-fade"')
text = text.replace('{`login-panel ${isExiting ? "fade-out" : "animated-fade"}`}', '"login-panel animated-fade"')

# We only want to apply it inside function App() (for Login) and function RegisterScreen()

# 1. RegisterScreen
reg_start = text.find('function RegisterScreen')
reg_end = text.find('// ───', reg_start)
reg_text = text[reg_start:reg_end]
reg_text = reg_text.replace('"auth-heading-row animated-fade"', '{`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}')
reg_text = reg_text.replace('"login-panel animated-fade"', '{`login-panel ${isExiting ? "fade-out" : "animated-fade"}`}')
text = text[:reg_start] + reg_text + text[reg_end:]

# 2. LoginScreen (inside App function)
login_start = text.find('// ─── Giriş ekranı ───')
if login_start == -1:
    login_start = text.find('function App') # fallback if comment is different
login_text = text[login_start:]
login_text = login_text.replace('"auth-heading-row animated-fade"', '{`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}')
login_text = login_text.replace('"login-panel animated-fade"', '{`login-panel ${isExiting ? "fade-out" : "animated-fade"}`}')
text = text[:login_start] + login_text

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Fixed fade-out classes.")
