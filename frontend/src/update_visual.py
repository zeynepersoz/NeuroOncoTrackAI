import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Extract the WelcomeScreen visual side
# It starts at: <section className="visual-side visual-abstract" aria-label="Klinik çalışma önizlemesi">
# And ends at the matching </section> before </motion.main>
match = re.search(r'(<section className="visual-side visual-abstract" aria-label="Klinik [^"]*?">.*?</section>)\s*</motion\.main>\s*\);\s*}\s*// ─── Ana Uygulama', text, re.DOTALL)
if match:
    welcome_visual_side = match.group(1)
    
    # Now find the RegisterScreen visual side
    # Starts at: <section className="visual-side visual-abstract" aria-hidden="true">
    # Inside function RegisterScreen
    reg_func_start = text.find('function RegisterScreen')
    if reg_func_start != -1:
        reg_func_end = text.find('// ─── Welcome Ekranı', reg_func_start)
        reg_func_text = text[reg_func_start:reg_func_end]
        
        # Replace the visual-side in RegisterScreen
        # In RegisterScreen, there's a return for the success state, and a return for the form state.
        # The user wants it on the "kayıt ol tarafında", so the form state (or both).
        # We will replace all `<section className="visual-side visual-abstract" aria-hidden="true">...</section>` inside RegisterScreen
        
        new_reg_func_text = re.sub(
            r'<section className="visual-side visual-abstract" aria-hidden="true">\s*<img className="hero-image".*?<div className="visual-scrim".*?</section>',
            welcome_visual_side.replace('\\', '\\\\'),
            reg_func_text,
            flags=re.DOTALL
        )
        
        text = text[:reg_func_start] + new_reg_func_text + text[reg_func_end:]
        
        with open('App.jsx', 'w', encoding='utf-8') as f:
            f.write(text)
        print("Updated RegisterScreen visual side successfully.")
else:
    print("Could not find WelcomeScreen visual side.")

