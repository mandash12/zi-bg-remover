from PIL import Image
import os

img = Image.open("icon.png")
img.save("icon.ico", format='ICO', sizes=[(256, 256)])
print("Converted icon.png to icon.ico")
