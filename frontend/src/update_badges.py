import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the style for the compliance-strip
old_style = "style={{ gap: '16px', display: 'flex', alignItems: 'center', position: 'fixed', bottom: '15px', left: '150px', zIndex: 50 }}"
new_style = "style={{ gap: '14px', display: 'flex', alignItems: 'center', position: 'absolute', bottom: '25px', right: '35px', zIndex: 50 }}"
text = text.replace(old_style, new_style)

# Replace the styles for the images
# img 1: etikImg
text = text.replace("style={{ height: '36px', objectFit: 'contain', borderRadius: '4px' }}", "style={{ height: '28px', objectFit: 'contain' }}")
# img 2 & 3: hl7Img, auditImg
text = text.replace("style={{ height: '36px', objectFit: 'contain' }}", "style={{ height: '28px', objectFit: 'contain' }}")

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Add position relative to .auth-side
if 'position: relative;' not in css[:css.find('.auth-side {') + 50]:
    css = css.replace('.auth-side {\n  display: flex;', '.auth-side {\n  position: relative;\n  display: flex;')

with open('index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("Updated badges positions and sizes.")
