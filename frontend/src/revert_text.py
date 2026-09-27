import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('<br />L', ' L')
text = text.replace('<br /> L', ' L')

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Removed line break.")
