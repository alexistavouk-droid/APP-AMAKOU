"""VESC SIMULATOR PRO — point d'entrée."""
import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from interface import theme
    from interface.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("VESC SIMULATOR PRO")
    app.setStyleSheet(theme.STYLE)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
