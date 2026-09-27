import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Insert ThemeToggle into RegisterScreen
# Look for <h1 id="reg-title">Kayıt Ol</h1>
reg_match = re.search(r'(<h1 id="reg-title">Kayıt Ol</h1>\s*</div>)', text)
if reg_match:
    text = text[:reg_match.end()] + '\n          <ThemeToggle theme={theme} setTheme={setTheme} />' + text[reg_match.end():]

# 2. Add status block below action-row in LoginScreen
status_code = """
          {status ? (
            <div className={`form-alert ${status.tone}`} role="status" style={{ fontSize: "0.85rem", padding: "8px 12px", marginTop: "1rem" }}>
              {status.tone === 'success' ? <CheckCircle size={18} /> : <ShieldAlert size={18} />}
              <span>{status.message}</span>
            </div>
          ) : null}
"""

# The login screen is in the App function (which is at the end of the file).
# We can find the last `</form>` which belongs to LoginScreen.
login_form_end = text.rfind('</form>')
# And the action-row before it
action_row_end = text.rfind('</div>', 0, login_form_end)

if login_form_end != -1:
    text = text[:action_row_end+6] + status_code + text[login_form_end:]

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Fixed missing elements.")
