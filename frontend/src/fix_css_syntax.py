import re

with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Remove the broken parts of the regex
css = css.replace("to { opacity: 1; filter: blur(0); }\n}", "")
# there might also be:
css = css.replace("to { opacity: 1; filter: blur(0); }\n}\n", "")

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("Fixed CSS syntax error")
