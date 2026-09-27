import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Import the images at the top
import_statement = """import appLogo from './assets/UygulamaLogo.png';
import hl7Img from './assets/hl7.png';
import auditImg from './assets/audit.png';
import etikImg from './assets/etik_kurul.jpg';
"""
text = text.replace("import appLogo from './assets/UygulamaLogo.png';", import_statement)

# New compliance strip content
new_strip = """<div className="compliance-strip" aria-label="GǬvenlik ve standart bilgileri" style={{ gap: '16px', display: 'flex', alignItems: 'center' }}>
          <img src={etikImg} alt="TÜTF-GOBAEK" style={{ height: '36px', objectFit: 'contain', borderRadius: '4px' }} />
          <img src={hl7Img} alt="HL7 FHIR R4" style={{ height: '36px', objectFit: 'contain' }} />
          <img src={auditImg} alt="Audit Ready" style={{ height: '36px', objectFit: 'contain' }} />
        </div>"""

# Replace in MfaScreen
text = re.sub(
    r'<div className="compliance-strip">.*?</div>',
    new_strip,
    text,
    flags=re.DOTALL
)

# Replace in LoginScreen (it has aria-label in the original)
text = re.sub(
    r'<div className="compliance-strip" aria-label="Gvenlik ve standart bilgileri">.*?</div>',
    new_strip,
    text,
    flags=re.DOTALL
)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Compliance strip updated with images.")
