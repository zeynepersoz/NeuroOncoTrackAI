import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace any variant of GOBAEK with the exact correct one
text = re.sub(r'Etik kurul: .*?GOBAEK.*?</span', 'Etik kurul: TÜTF-GOBAEK 2026/205\n          </span', text)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated ethics code.")
