"""Graphique temps réel léger (QPainter) : aucune dépendance, ne bloque pas l'interface."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from interface import theme


class LineChart(QWidget):
    def __init__(self, title: str, unit: str, series: list[str], window_s: float = 60.0, parent=None):
        super().__init__(parent)
        self.title, self.unit, self.names, self.window = title, unit, series, window_s
        self.data = [deque() for _ in series]       # (t, valeur)
        self.setMinimumSize(220, 130)

    def add(self, t: float, *values: float) -> None:
        for dq, v in zip(self.data, values):
            dq.append((t, v))
            while dq and dq[0][0] < t - self.window:
                dq.popleft()

    def clear(self) -> None:
        for dq in self.data:
            dq.clear()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        f = QFont(self.font()); f.setPointSize(9); p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        p.drawText(10, 16, f"{self.title} ({self.unit})")
        left, top, right, bottom = 44, 24, w - 10, h - 18
        allv = [v for dq in self.data for _, v in dq]
        ts = [t for dq in self.data for t, _ in dq]
        if not allv:
            return
        lo, hi = min(allv), max(allv)
        if hi - lo < 1e-6:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad
        tmax = max(ts)
        tmin = tmax - self.window
        grid = QPen(QColor(theme.BORDER), 1, Qt.DotLine)
        for i in range(5):
            y = top + (bottom - top) * i / 4
            p.setPen(grid)
            p.drawLine(left, int(y), right, int(y))
            p.setPen(QColor(theme.MUTED))
            dec = 0 if hi - lo >= 20 else 1 if hi - lo >= 2 else 2
            p.drawText(2, int(y) + 4, 40, 12, Qt.AlignRight, f"{hi - (hi - lo) * i / 4:.{dec}f}")
        p.setPen(QColor(theme.MUTED))
        p.drawText(left, h - 4, f"-{self.window:.0f} s")
        p.drawText(right - 20, h - 4, "0")
        for i, dq in enumerate(self.data):
            if len(dq) < 2:
                continue
            path = QPainterPath()
            for j, (t, v) in enumerate(dq):
                x = left + (right - left) * (t - tmin) / self.window
                y = bottom - (bottom - top) * (v - lo) / (hi - lo)
                path.moveTo(x, y) if j == 0 else path.lineTo(x, y)
            col = QColor(theme.SERIES[i % len(theme.SERIES)])
            p.setPen(QPen(col, 1.8))
            p.drawPath(path)
            if len(self.names) > 1:
                p.drawText(right - 70, top + 12 + 12 * i, f"● {self.names[i]}")
