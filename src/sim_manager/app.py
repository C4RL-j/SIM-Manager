"""Desktop composition root; importing backend modules never imports Qt."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from sim_manager.services.device import SnapshotProvider
    from sim_manager.ui.main_window import MainWindow


def create_application(argv: list[str] | None = None) -> QApplication:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from sim_manager.ui.theme import STYLESHEET

    application = QApplication.instance() or QApplication(argv or [])
    application.setApplicationName("SIM Manager")
    application.setApplicationVersion("0.1.0")
    application.setOrganizationName("SIM Manager")
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 10))
    application.setStyleSheet(STYLESHEET)
    return application


def create_window(
    *, demo: bool = False, provider: SnapshotProvider | None = None
) -> MainWindow:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from sim_manager.services.device import DemoDeviceService, LiveDeviceService
    from sim_manager.ui.main_window import MainWindow

    selected = provider if provider is not None else (DemoDeviceService() if demo else LiveDeviceService())
    window = MainWindow(selected, demo=demo)
    application = QApplication.instance()
    if application is not None:
        application.aboutToQuit.connect(window.refresh_controller.shutdown)
    # Rendering/refresh occurs only after Qt starts processing events.
    QTimer.singleShot(0, window.start_refresh)
    return window


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SIM Manager desktop application.")
    parser.add_argument("--demo", action="store_true", help="Show clearly marked offline sample data.")
    args = parser.parse_args(argv)
    try:
        application = create_application([])
        window = create_window(demo=args.demo)
    except ImportError:
        print('Desktop dependencies are unavailable. Install with: python -m pip install -e ".[desktop]"', file=sys.stderr)
        return 1
    window.show()
    return application.exec()
