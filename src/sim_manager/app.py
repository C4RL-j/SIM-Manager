"""Desktop composition root; importing backend modules never imports Qt."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from sim_manager import __version__

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
    from sim_manager.ui.icons import application_icon

    application = QApplication.instance()
    if application is None:
        if sys.platform == "win32":
            try:
                import ctypes
                set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
                set_id.argtypes = [ctypes.c_wchar_p]
                set_id.restype = ctypes.c_long
                set_id("SIMManager.Desktop")
            except (AttributeError, OSError):
                pass
        application = QApplication(argv or [])
    application.setApplicationName("SIM Manager")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("SIM Manager")
    application.setWindowIcon(application_icon())
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 10))
    application.setStyleSheet(STYLESHEET)
    return application


def create_window(
    *, demo: bool = False, provider: SnapshotProvider | None = None,
    message_provider: MessageProvider | None = None,
    account_service: AccountService | None = None,
    sim_profiles: SimProfileService | None = None,
    preferences_store=None,
    enable_tray: bool | None = None,
    startup_service=None,
) -> MainWindow:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from sim_manager.services.device import DemoDeviceService, LiveDeviceService
    from sim_manager.services.messages import DemoMessageService, LiveMessageService
    from sim_manager.services.accounts import DemoAccountService, DitoAccountService
    from sim_manager.services.router_login import D2LoginService
    from sim_manager.services.sim_profiles import SimProfileService
    from sim_manager.ui.main_window import MainWindow
    from sim_manager.ui.preferences import AppPreferences, MemoryPreferencesStore, QtPreferencesStore

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
                from sim_manager.ui.sign_in_helpers import SignInHelpers
                helpers = SignInHelpers(profiles, window.messages_controller,
                                        window.start_messages_refresh)
                context = (profiles.context_token,
                           profiles.active_profile.profile_id if profiles.active_profile else None)

                def current_account_number():
                    from sim_manager.sim_models import SimCarrier
                    active = profiles.active_profile
                    if (not profiles.current_sim or active is None
                            or active.carrier is not SimCarrier.DITO
                            or context != (profiles.context_token, active.profile_id)):
                        return None
                    return profiles.current_phone_number or active.phone_number

                return DitoBrowserSurface(helper_panel=helpers,
                                          account_number=current_account_number)
            account = DitoAccountService(browser_factory=create_carrier_browser)
    profiles = sim_profiles
    if profiles is None:
        if provider is None and not demo:
            from sim_manager.storage.sim_profiles import WindowsSimProfileStore
            profiles = SimProfileService(store=WindowsSimProfileStore())
        else:
            profiles = SimProfileService(demo=demo)
    preferences = preferences_store
    if preferences is None:
        preferences = (QtPreferencesStore() if provider is None and not demo
                       else MemoryPreferencesStore(AppPreferences(auto_refresh=False)))
    startup = startup_service
    if startup is None and provider is None and not demo:
        from sim_manager.services.windows_startup import WindowsStartupService
        startup = WindowsStartupService()
    window = MainWindow(selected, demo=demo, message_provider=messages, account_service=account,
                        router_login_service=router_login, sim_profiles=profiles,
                        preferences_store=preferences,
                        startup_service=startup,
                        enable_tray=provider is None if enable_tray is None else enable_tray)
    application = QApplication.instance()
    if application is not None:
        application.aboutToQuit.connect(window.shutdown)
    # Rendering/refresh occurs only after Qt starts processing events.
    QTimer.singleShot(0, window.start_initial_load)
    return window


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SIM Manager desktop application.")
    parser.add_argument("--demo", action="store_true", help="Show clearly marked offline sample data.")
    parser.add_argument("--release-smoke", metavar="REPORT", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.release_smoke:
        from sim_manager.ui.release_smoke import run_release_smoke
        return run_release_smoke(args.release_smoke)
    instance = None
    try:
        application = create_application([])
        from sim_manager.ui.single_instance import SingleInstanceGuard
        instance = SingleInstanceGuard(application)
        if not instance.acquire_or_notify():
            if instance.notified_existing:
                return 0
            print("SIM Manager could not open its desktop session.", file=sys.stderr)
            return 1
        window = create_window(demo=args.demo)
    except ImportError:
        print('Desktop dependencies are unavailable. Install with: python -m pip install -e ".[desktop]"', file=sys.stderr)
        if instance is not None:
            instance.shutdown()
        return 1
    instance.activation_requested.connect(window.show_main_window)
    application.aboutToQuit.connect(instance.shutdown)
    window.show()
    try:
        return application.exec()
    finally:
        instance.shutdown()
