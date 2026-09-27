import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Function to inject animated-fade class, but skip WelcomeScreen
def process_screen(screen_code):
    if "WelcomeScreen" in screen_code:
        return screen_code
    
    # Add animated-fade to auth-heading-row
    screen_code = screen_code.replace('className="auth-heading-row"', 'className="auth-heading-row animated-fade"')
    
    # Add animated-fade to login-panel
    screen_code = screen_code.replace('className="login-panel"', 'className="login-panel animated-fade"')
    
    return screen_code

# We can split App.jsx by functions and process them
functions = re.split(r'(?=\nfunction [A-Z])', text)
new_text = ""
for func in functions:
    new_text += process_screen(func)

# But wait, LoginScreen is inside `function App()`, not a separate function.
# `function App()` contains the login screen at the end.
# We can just do a global replace and then specifically revert WelcomeScreen.

# Global replace
text = text.replace('className="auth-heading-row"', 'className="auth-heading-row animated-fade"')
text = text.replace('className="login-panel"', 'className="login-panel animated-fade"')

# Revert WelcomeScreen
# Find WelcomeScreen block
ws_start = text.find('function WelcomeScreen')
ws_end = text.find('function App', ws_start)
ws_block = text[ws_start:ws_end]
ws_block = ws_block.replace('className="auth-heading-row animated-fade"', 'className="auth-heading-row"')
ws_block = ws_block.replace('className="login-panel animated-fade"', 'className="login-panel"')
text = text[:ws_start] + ws_block + text[ws_end:]

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

css += """
@keyframes slowFormFade {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.animated-fade {
  animation: slowFormFade 0.8s ease-out forwards;
}
"""

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("Added animated-fade class to forms and CSS.")
