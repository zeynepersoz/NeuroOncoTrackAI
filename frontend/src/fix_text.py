import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the specific string to add a <br />
# Note: The text in the file is likely "Yapay zeka destekli tıbbi karar destek, segmentasyon ve raporlama platformuna hoş geldiniz. Lütfen devam etmek için bir seçenek belirleyin."
# But powershell output shows strange encoding characters, so let's use a regex that matches regardless of encoding, or just replace 'hoş geldiniz. Lütfen'
text = re.sub(
    r'(platformuna ho.*?geldiniz\.) (L.*?tfen devam etmek i.*?in bir se.*?enek belirleyin\.)',
    r'\1<br />\2',
    text
)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Added line break to WelcomeScreen text.")
