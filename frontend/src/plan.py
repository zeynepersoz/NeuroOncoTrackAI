import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Move buttons up and Demo text closer
text = text.replace(
    "marginBottom: '1rem', marginTop: '0.25rem'",
    "marginBottom: '0.5rem', marginTop: '0.25rem'"
)
text = text.replace(
    "padding: \"8px 12px\", marginTop: \"1rem\"",
    "padding: \"8px 12px\", marginTop: \"0.25rem\""
)

# Also there's an action-row in RegisterScreen, but the user specifically mentioned "güvenli giriş ve demo butonu" which is LoginScreen.

# Now for the exit animations, since refactoring the entire layout is huge and risky, let's try a CSS trick for exit animations, or just use framer-motion inside the components.
# If I wrap the Login form in a motion.div, and Register form in a motion.div... it won't animate on exit unless AnimatePresence wraps the CONDITIONAL RENDER.
# What if we just manually trigger a CSS class before changing screen? That's too complex.

# Let's extract the layout.
# We will create an AuthLayout component that takes `children` and `screen`.
# Actually, if we just wrap the dynamic parts inside App.jsx...
