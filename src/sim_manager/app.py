"""Desktop composition root; importing backend modules never imports Qt."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from sim_manager.services.device import SnapshotProvider
    from sim_manager.services.messages import MessageProvider
    from sim_manager.services.accounts import AccountService
    from sim_manager.services.sim_profiles import SimProfileService
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
    *, demo: bool = False, provider: SnapshotProvider | None = None,
    message_provider: MessageProvider | None = None,
    account_service: AccountService | None = None,
    sim_profiles: SimProfileService | None = None,
) -> MainWindow:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from sim_manager.services.device import DemoDeviceService, LiveDeviceService
    from sim_manager.services.messages import DemoMessageService, LiveMessageService
    from sim_manager.services.accounts import DemoAccountService, DitoAccountService
    from sim_manager.services.router_login import D2LoginService
    from sim_manager.services.sim_profiles import SimProfileService
    from sim_manager.ui.main_window import MainWindow

    selected = provider if provider is not None else (DemoDeviceService() if demo else LiveDeviceService())
    router_login = None
    if provider is None and not demo:
        from sim_manager.storage.windows_credentials import WindowsD2CredentialStore
        router_login = D2LoginService(selected, WindowsD2CredentialStore(selected.router_address))
        selected = router_login
    # Injected snapshot providers are used by offline consumers/tests. They
    # never implicitly enable a separate live SMS connection on navigation.
    messages = message_provider
    if messages is None and provider is None:
        messages = DemoMessageService() if demo else LiveMessageService()
    account = account_service
    if account is None and provider is None:
        if demo:
            account = DemoAccountService()
        else:
            def create_carrier_browser():
                # Optional WebEngine imports and all network activity begin
                # only after the user's explicit Connect action.
                from sim_manager.carriers.dito.browser import DitoBrowserSurface
                return DitoBrowserSurface()
            account = DitoAccountService(browser_factory=create_carrier_browser)
    profiles = sim_profiles
    if profiles is None:
        if provider is None and not demo:
            from sim_manager.storage.sim_profiles import WindowsSimProfileStore
            profiles = SimProfileService(store=WindowsSimProfileStore())
        else:
            profiles = SimProfileService(demo=demo)
    window = MainWindow(selected, demo=demo, message_provider=messages, account_service=account,
                        router_login_service=router_login, sim_profiles=profiles)
    application = QApplication.instance()
    if application is not None:
        application.aboutToQuit.connect(window.shutdown)
    # Rendering/refresh occurs only after Qt starts processing events.
    QTimer.singleShot(0, window.start_initial_load)
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
