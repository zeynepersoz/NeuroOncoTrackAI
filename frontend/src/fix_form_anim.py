import re

with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Remove pageFade
css = re.sub(r'@keyframes pageFade \{.*?\}\s*', '', css, flags=re.DOTALL)
css = re.sub(r'animation: pageFade.*?;', '', css)

# Add formFade and apply it to specific components
form_fade_css = """
@keyframes formFade {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.auth-heading-row, .login-panel {
  animation: formFade 0.4s ease-out forwards;
}
"""

css = css + "\n" + form_fade_css

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("CSS updated with formFade")
