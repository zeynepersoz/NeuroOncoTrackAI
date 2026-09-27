import re

with open('App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Move closer to the right line (change right: '35px' to right: '10px')
text = text.replace("right: '35px'", "right: '10px'")

# 2. Add border-radius to the images to make them rounded (not sharp)
# I will apply borderRadius: '8px' to all of them so they look perfectly consistent.
# The previous style was style={{ height: '28px', objectFit: 'contain' }}
# I will replace it with style={{ height: '28px', objectFit: 'contain', borderRadius: '6px' }}
text = text.replace("style={{ height: '28px', objectFit: 'contain' }}", "style={{ height: '28px', objectFit: 'contain', borderRadius: '6px' }}")

with open('App.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated badges positions and rounded corners.")
