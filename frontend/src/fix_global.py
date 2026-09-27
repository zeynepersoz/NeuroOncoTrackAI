import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

new_strip = """<div className="compliance-strip" aria-label="Guvenlik ve standart bilgileri" style={{ gap: '16px', display: 'flex', alignItems: 'center', position: 'fixed', bottom: '15px', left: '150px', zIndex: 50 }}>
          <img src={etikImg} alt="TUTF-GOBAEK" style={{ height: '36px', objectFit: 'contain', borderRadius: '4px' }} />
          <img src={hl7Img} alt="HL7 FHIR R4" style={{ height: '36px', objectFit: 'contain' }} />
          <img src={auditImg} alt="Audit Ready" style={{ height: '36px', objectFit: 'contain' }} />
        </div>"""

# 1. Remove all existing compliance-strips first to avoid duplicates
text = re.sub(
    r'<div className="compliance-strip".*?</div>',
    '',
    text,
    flags=re.DOTALL
)

# 2. Insert compliance strip before EVERY <section className="visual-side...
text = re.sub(
    r'(\s*)</section>\s*(<section className="visual-side)',
    rf'\1  {new_strip}\n\1</section>\n\1\2',
    text
)

# 3. Copy visual-side from WelcomeScreen to RegisterScreen
ws_start = text.find('function WelcomeScreen')
ws_end = text.find('function App', ws_start)
ws_text = text[ws_start:ws_end]
# Extract the visual side from WelcomeScreen
# It looks like <section className="visual-side visual-abstract" aria-label="Klinik ..."> ... </section>
ws_visual_match = re.search(r'(<section className="visual-side.*?)</main>', ws_text, flags=re.DOTALL)
if ws_visual_match:
    ws_visual = ws_visual_match.group(1).strip()
    
    # Now replace the visual side in RegisterScreen
    reg_start = text.find('function RegisterScreen')
    reg_end = text.find('// ───', reg_start)
    if reg_end == -1: reg_end = ws_start
    reg_text = text[reg_start:reg_end]
    
    # RegisterScreen might have multiple visual sides (one for success, one for form)
    # The success screen visual side
    reg_text = re.sub(r'<section className="visual-side visual-abstract".*?</section>', ws_visual, reg_text, flags=re.DOTALL)
    
    text = text[:reg_start] + reg_text + text[reg_end:]

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Applied compliance strip globally and fixed visual side for RegisterScreen.")
