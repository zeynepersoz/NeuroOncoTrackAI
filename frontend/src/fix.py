import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Remove all occurrences of the import
text = re.sub(r"import \{ motion, AnimatePresence \} from 'framer-motion';\n?", "", text)

# Add it exactly once at the top
text = "import { motion, AnimatePresence } from 'framer-motion';\n" + text

# Replace 'main className="login-shell"' with 'motion.main...'
text = text.replace('<main className="login-shell">', '<motion.main className="login-shell" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.4, ease: "easeOut" }}>')
text = text.replace('</main>', '</motion.main>')

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)
