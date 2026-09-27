import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Move status block below action-row in App component (LoginScreen)
# Look for:
#           {status ? (
#             <div className={`form-alert ${status.tone}`} role="status">
#               ...
#           ) : null}
#           <div className="action-row">
#             ...
#           </div>
#         </form>

# First, extract the status block
status_regex = r'(\s*\{status \? \(\s*<div className=\{`form-alert \$\{status\.tone\}`\} role="status">.*?</div>\s*\) : null\})'
match = re.search(status_regex, text, re.DOTALL)
if match:
    status_block = match.group(1)
    
    # We want to add inline styles to shrink it
    modified_status_block = status_block.replace(
        'role="status"', 
        'role="status" style={{ fontSize: "0.85rem", padding: "8px 12px", marginTop: "1rem" }}'
    )
    
    # Remove original status block
    text = text[:match.start()] + text[match.end():]
    
    # Find the end of action-row
    # It ends right before </form>
    # Wait, action-row ends with </div>, then </form>
    insert_pos = text.find('</form>')
    text = text[:insert_pos] + modified_status_block + "\n        " + text[insert_pos:]

# 2. Add ThemeToggle to RegisterScreen
# Update RegisterScreen signature
text = text.replace(
    'function RegisterScreen({ onSuccess, onBack }) {',
    'function RegisterScreen({ onSuccess, onBack, theme, setTheme }) {'
)
# Add ThemeToggle inside auth-heading-row
text = text.replace(
    '<h1 id="reg-title">Klinik platforma katılın</h1>\n          </div>\n        </div>',
    '<h1 id="reg-title">Klinik platforma katılın</h1>\n          </div>\n          <ThemeToggle theme={theme} setTheme={setTheme} />\n        </div>'
)

# 3. Pass theme props to RegisterScreen in App
text = text.replace(
    '<RegisterScreen onSuccess={() => setScreen(\'login\')} onBack={() => setScreen(\'welcome\')} />',
    '<RegisterScreen onSuccess={() => setScreen(\'login\')} onBack={() => setScreen(\'welcome\')} theme={theme} setTheme={setTheme} />'
)

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated status block and added ThemeToggle to RegisterScreen")
