from PIL import Image

# Open the cropped image
img = Image.open('public/favicon.png')

# Find max dimension
max_dim = max(img.size)

# Create a new transparent square image
square_img = Image.new('RGBA', (max_dim, max_dim), (0, 0, 0, 0))

# Paste the cropped image in the center
offset = ((max_dim - img.size[0]) // 2, (max_dim - img.size[1]) // 2)
square_img.paste(img, offset)

# Save
square_img.save('public/favicon.png')
print(f"Squared image to {square_img.size}.")
