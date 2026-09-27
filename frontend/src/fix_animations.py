import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Revert motion.main back to main
text = re.sub(
    r'<motion\.main className="login-shell"[^>]*>',
    '<main className="login-shell">',
    text
)
text = text.replace('</motion.main>', '</main>')

# 2. Add soft fade to auth-side only
# Be careful to only change the opening tag
text = text.replace(
    '<section className="auth-side"',
    '<motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: "easeOut" }} className="auth-side"'
)

# Replace the closing </section> for auth-side.
# The auth-side section always ends right before <section className="visual-side"
text = text.replace(
    '</section>\n      <section className="visual-side',
    '</motion.section>\n      <section className="visual-side'
)
# Wait, some screens might not have visual-side (like Forgot Password). Let's check how they are structured.
# Actually they all have visual-side now? No, MfaScreen doesn't, ForgotPassword doesn't? 
# Wait, MfaScreen: <section className="visual-side visual-abstract" aria-hidden="true">
# ForgotPasswordScreen: <section className="visual-side visual-abstract" aria-hidden="true">
# So they ALL have it. The replacement will work perfectly.

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)
print("Reverted main animation and added soft fade to auth-side.")
