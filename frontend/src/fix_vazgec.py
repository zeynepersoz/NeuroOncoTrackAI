import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace all onClick={onBack} with onClick={handleBack} inside RegisterScreen
reg_start = text.find('function RegisterScreen')
# Find the end of RegisterScreen, which is right before function WelcomeScreen
reg_end = text.find('function WelcomeScreen', reg_start)

if reg_start != -1 and reg_end != -1:
    reg_text = text[reg_start:reg_end]
    reg_text = reg_text.replace('onClick={onBack}', 'onClick={handleBack}')
    text = text[:reg_start] + reg_text + text[reg_end:]
    
    with open('App.jsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Fixed Vazgeç animation.")
else:
    print("Could not find RegisterScreen bounds")
