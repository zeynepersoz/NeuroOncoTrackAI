import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# I messed up the tags. Let's revert ALL <motion.section> and </motion.section> back to <section>
text = re.sub(r'<motion\.section[^>]*className="auth-side"[^>]*>', '<section className="auth-side"', text)
text = text.replace('</motion.section>', '</section>')

# Now, cleanly apply the motion tag.
motion_open = '<motion.section initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: "easeOut" }} className="auth-side"'

# Find all <section className="auth-side"
# Since they have aria attributes, we regex match the opening tag
# Actually, the reversion just made them exactly '<section className="auth-side"' followed by ' aria-labelledby=...'

# For each match of <section className="auth-side" ..., find the matching </section> 
# Wait, it's easier to just use a regular expression if we assume no nested <section> inside auth-side.
# Are there nested <section> inside auth-side? No, usually just forms and divs.

def repl(match):
    # match.group(0) is the entire auth-side section
    # We replace the opening tag and closing tag
    content = match.group(0)
    content = re.sub(r'^<section className="auth-side"', motion_open, content)
    # The last </section> in content is the closing tag
    content = content[:-10] + '</motion.section>'
    return content

text = re.sub(r'<section className="auth-side".*?</section>', repl, text, flags=re.DOTALL)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)
print("Tags cleanly fixed.")
