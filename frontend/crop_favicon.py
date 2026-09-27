from PIL import Image

# Open the image
img = Image.open('public/favicon.png')

# Convert to RGBA if not already
img = img.convert("RGBA")

# Get the bounding box of non-transparent pixels
bbox = img.getbbox()
if bbox:
    # Crop the image to the bounding box
    img_cropped = img.crop(bbox)
    
    # Save the cropped image
    img_cropped.save('public/favicon.png')
    print(f"Cropped image from {img.size} to {img_cropped.size}.")
else:
    print("Image is entirely transparent or empty.")
