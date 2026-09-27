import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Adjust buttons margin and Demo text margin
text = text.replace(
    "marginBottom: '1rem', marginTop: '0.25rem'",
    "marginBottom: '0.5rem', marginTop: '0.25rem'"
)
text = text.replace(
    "padding: \"8px 12px\", marginTop: \"1rem\"",
    "padding: \"8px 12px\", marginTop: \"0.25rem\""
)

# 2. Add isExiting state to App component (for LoginScreen)
text = text.replace(
    "const [status, setStatus] = useState(null);",
    "const [status, setStatus] = useState(null);\n  const [isExiting, setIsExiting] = useState(false);"
)

# Replace the onClick={() => setScreen('welcome')} for Login back button
login_back_func = """onClick={() => {
              setIsExiting(true);
              setTimeout(() => {
                setScreen('welcome');
                setIsExiting(false);
              }, 400);
            }}"""
text = text.replace("onClick={() => setScreen('welcome')}", login_back_func, 1)

# Apply isExiting to LoginScreen's animated-fade classes
text = text.replace(
    '<div className="auth-heading-row animated-fade">',
    '<div className={`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}>',
    1
)
text = text.replace(
    '<form className="login-panel animated-fade" onSubmit={handleSubmit}>',
    '<form className={`login-panel ${isExiting ? "fade-out" : "animated-fade"}`} onSubmit={handleSubmit}>',
    1
)

# 3. Add isExiting state to RegisterScreen
reg_state = """function RegisterScreen({ onSuccess, onBack, theme, setTheme }) {
  const [isExiting, setIsExiting] = useState(false);
  const handleBack = () => {
    setIsExiting(true);
    setTimeout(onBack, 400);
  };"""
text = text.replace(
    "function RegisterScreen({ onSuccess, onBack, theme, setTheme }) {",
    reg_state
)
# Update RegisterScreen back button
text = text.replace(
    'onClick={onBack}',
    'onClick={handleBack}',
    1 # First one is Vazgeç button
)
# Apply isExiting to RegisterScreen's animated-fade classes
text = text.replace(
    '<div className="auth-heading-row animated-fade">',
    '<div className={`auth-heading-row ${isExiting ? "fade-out" : "animated-fade"}`}>',
    1
)
text = text.replace(
    '<div className="login-panel animated-fade">',
    '<div className={`login-panel ${isExiting ? "fade-out" : "animated-fade"}`}>',
    1
)
# Wait, RegisterScreen has a success state and a form state.
# Form state:
text = text.replace(
    '<form className="login-panel animated-fade" onSubmit={handleRegister}>',
    '<form className={`login-panel ${isExiting ? "fade-out" : "animated-fade"}`} onSubmit={handleRegister}>',
    1
)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)


with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

css += """
@keyframes slowFormFadeOut {
  from { opacity: 1; transform: translateY(0); }
  to { opacity: 0; transform: translateY(-4px); }
}

.fade-out {
  animation: slowFormFadeOut 0.4s ease-in forwards !important;
}
"""

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("Exit animations and spacing updated.")
