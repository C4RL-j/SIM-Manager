"""Small monochrome navigation marks drawn with Qt, without asset dependencies."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def navigation_icon(page: str) -> QIcon:
    icon = QIcon()
    for mode, color in ((QIcon.Mode.Normal, "#97a8ba"), (QIcon.Mode.Selected, "#91efda")):
        for ratio in (1, 2, 3):
            pixmap = QPixmap(20 * ratio, 20 * ratio)
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            if page == "Home":
                path = QPainterPath()
                path.moveTo(2, 9)
                path.lineTo(10, 3)
                path.lineTo(18, 9)
                path.moveTo(4, 8)
                path.lineTo(4, 17)
                path.lineTo(8, 17)
                path.lineTo(8, 12)
                path.lineTo(12, 12)
                path.lineTo(12, 17)
                path.lineTo(16, 17)
                path.lineTo(16, 8)
                painter.drawPath(path)
            elif page == "SIMs":
                path = QPainterPath()
                path.moveTo(6, 3)
                path.lineTo(14, 3)
                path.lineTo(17, 6)
                path.lineTo(17, 17)
                path.lineTo(6, 17)
                path.closeSubpath()
                painter.drawPath(path)
                painter.drawRoundedRect(QRectF(8, 8, 6, 6), 1, 1)
                painter.drawLine(8, 11, 14, 11)
                painter.drawLine(11, 8, 11, 14)
            elif page == "History":
                painter.drawEllipse(QRectF(4, 4, 12, 12))
                painter.drawLine(10, 6, 10, 10)
                painter.drawLine(10, 10, 13, 12)
                painter.drawLine(3, 3, 3, 7)
                painter.drawLine(3, 7, 7, 7)
            elif page == "Overview":
                for x, y in ((3, 3), (12, 3), (3, 12), (12, 12)):
                    painter.drawRoundedRect(QRectF(x, y, 5, 5), 1, 1)
            elif page == "Messages":
                path = QPainterPath()
                path.moveTo(4, 4)
                path.lineTo(16, 4)
                path.quadTo(17, 4, 17, 5)
                path.lineTo(17, 13)
                path.quadTo(17, 14, 16, 14)
                path.lineTo(9, 14)
                path.lineTo(5, 17)
                path.lineTo(5, 14)
                path.lineTo(4, 14)
                path.quadTo(3, 14, 3, 13)
                path.lineTo(3, 5)
                path.quadTo(3, 4, 4, 4)
                painter.drawPath(path)
                painter.drawLine(6, 8, 14, 8)
                painter.drawLine(6, 11, 11, 11)
            elif page == "Settings":
                painter.translate(10, 10)
                painter.drawEllipse(QRectF(-5, -5, 10, 10))
                painter.drawEllipse(QRectF(-1.5, -1.5, 3, 3))
                for _ in range(8):
                    painter.drawLine(0, -5, 0, -8)
                    painter.rotate(45)
            painter.end()
            icon.addPixmap(pixmap, mode)
    return icon
