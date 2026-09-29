import latex2mathml.converter
import ziamath
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QByteArray, QBuffer, QIODevice

app = QApplication([])
mathml = latex2mathml.converter.convert(r'\sum_{i=1}^n i')
z = ziamath.Math(mathml, size=12)
svg_str = z.svg()

svg_bytes = svg_str.encode('utf-8')
renderer = QSvgRenderer(svg_bytes)
size = renderer.defaultSize()
print("SVG Size:", size.width(), size.height())

image = QImage(size, QImage.Format.Format_ARGB32)
image.fill(0)
painter = QPainter(image)
renderer.render(painter)
painter.end()

byte_array = QByteArray()
buffer = QBuffer(byte_array)
buffer.open(QIODevice.OpenModeFlag.WriteOnly)
image.save(buffer, "PNG")
img_data = byte_array.toBase64().data().decode('utf-8')
print("PNG Base64 length:", len(img_data))
