import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Nothing to change in App.jsx

with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Clean up all leftover subtleFade keyframes
css = re.sub(r'@keyframes subtleFade \{.*?\}\s*', '', css, flags=re.DOTALL)
css = re.sub(r'animation: subtleFade.*?;', '', css)

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("CSS cleaned up.")
