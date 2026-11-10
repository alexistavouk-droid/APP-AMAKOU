"""Thème sombre « diagnostic automobile »."""
BG = "#0f1419"
PANEL = "#171d25"
PANEL2 = "#1e2631"
BORDER = "#2a3441"
TEXT = "#e6edf3"
MUTED = "#8b98a8"
ACCENT = "#00b4d8"
OK = "#2ecc71"
WARN = "#f5a623"
BAD = "#ff4d4f"

SERIES = ["#00b4d8", "#f5a623", "#2ecc71", "#ff6b9d", "#b388ff", "#ffd166"]

STYLE = f"""
* {{ font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget {{ background: {BG}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: {PANEL}; padding: 8px 16px; border: 1px solid {BORDER};
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; color: {MUTED}; }}
QTabBar::tab:selected {{ background: {PANEL2}; color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QFrame#tile, QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QGroupBox {{ margin-top: 14px; padding-top: 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT}; }}
QLabel#tileTitle {{ color: {MUTED}; font-size: 11px; background: transparent; }}
QLabel#tileValue {{ font-size: 24px; font-weight: 700; background: transparent; }}
QLabel#tileUnit {{ color: {MUTED}; background: transparent; }}
QLabel#pill {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 3px 10px; font-weight: 600; }}
QPushButton {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#start {{ background: #1b5e3a; border-color: {OK}; }}
QPushButton#stop {{ background: #6b2226; border-color: {BAD}; }}
QPushButton#primary {{ background: #0b5d73; border-color: {ACCENT}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {PANEL2}; border: 1px solid {BORDER};
    border-radius: 5px; padding: 4px 6px; min-height: 22px; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; selection-background-color: #0b5d73; }}
QTableWidget, QPlainTextEdit, QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    gridline-color: {BORDER}; font-family: 'Consolas', 'DejaVu Sans Mono', monospace; font-size: 12px; }}
QHeaderView::section {{ background: {PANEL2}; border: none; border-bottom: 1px solid {BORDER}; padding: 4px; color: {MUTED}; }}
QSlider::groove:horizontal {{ height: 5px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QProgressBar {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 5px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QCheckBox {{ spacing: 6px; background: transparent; }}
QLabel {{ background: transparent; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {MUTED}; border-radius: 3px; background: {PANEL2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QScrollArea {{ border: none; }}
"""
