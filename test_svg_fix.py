import latex2mathml.converter, ziamath
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter
import sys

app = QApplication([])
m = latex2mathml.converter.convert(r'x')
z = ziamath.Math(m)
svg_str = z.svg()
svg_str = svg_str.replace('<svg ', '<svg xmlns:xlink="http://www.w3.org/1999/xlink" ')
svg_str = svg_str.replace('<use href="', '<use xlink:href="')

print("SVG:", svg_str)

renderer = QSvgRenderer(svg_str.encode('utf-8'))
print("Is valid:", renderer.isValid())

image = QImage(renderer.defaultSize(), QImage.Format.Format_ARGB32)
image.fill(0)
p = QPainter(image)
renderer.render(p)
p.end()

print("Non-transparent pixels:", sum(1 for i in range(image.width()) for j in range(image.height()) if image.pixelColor(i, j).alpha() > 0))
