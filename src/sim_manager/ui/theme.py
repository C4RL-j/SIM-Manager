"""Compact dark Qt Widgets theme with native window chrome."""

STYLESHEET = """
QWidget { background: #10151c; color: #e8edf3; font-size: 13px; }
QWidget#sidebar { background: #151c25; border-right: 1px solid #27313e; }
QLabel { background: transparent; }
QLabel#brand { font-size: 21px; font-weight: 700; }
QLabel#brandMark { background: transparent; border: none; }
QLabel#eyebrow { color: #7f93a8; font-size: 10px; font-weight: 600; }
QLabel#muted { color: #97a8ba; }
QLabel#pageTitle { font-size: 25px; font-weight: 700; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: #b4c6d8; }
QLabel#identity { font-size: 29px; font-weight: 600; }
QLabel#metric { font-size: 20px; font-weight: 600; }
QLabel#detail { font-size: 14px; font-weight: 600; }
QLabel#demoNotice { color: #e1bd7f; font-size: 11px; }
QLabel#demoBadge { background: #574222; color: #ffda91; border: 1px solid #987239;
                   border-radius: 5px; padding: 6px 12px; font-weight: 700; }
QLabel#liveBadge { background: #234039; color: #91efda; border: 1px solid #39705e;
                   border-radius: 5px; padding: 6px 12px; font-weight: 700; }
QLineEdit { background: #19212c; border: 1px solid #3a4a5c; border-radius: 5px; padding: 9px; }
QLineEdit:focus { border-color: #8ddfcd; }
QLabel#status { background: transparent; color: #97a8ba; border: none; padding: 0; }
QLabel#status[level="ok"] { color: #91d8c8; }
QLabel#status[level="warning"] { color: #edcf8f; }
QLabel#status[level="error"] { color: #efb2be; }
QLabel#messageStatus { color: #97a8ba; }
QLabel#messageStatus[level="warning"] { color: #edcf8f; }
QLabel#messageStatus[level="error"] { color: #efb2be; }
QFrame#statusSurface { background: transparent; border: none; }
QFrame#statusSurface[level="warning"] { background: #342d20; border: 1px solid #625335; border-radius: 5px; }
QFrame#statusSurface[level="error"] { background: #35272c; border: 1px solid #65404a; border-radius: 5px; }
QListWidget { background: transparent; border: none; outline: none; font-size: 14px; }
QListWidget::item { padding: 13px 15px; margin: 3px 0; border-radius: 6px; }
QListWidget::item:selected { background: #234039; color: #91efda; font-weight: 600; }
QListWidget::item:hover:!selected { background: #202b38; }
QListWidget#messageList::item { padding: 9px 10px; margin: 1px 0; font-size: 13px; }
QListWidget#messageList::item:selected { font-weight: 400; }
QPlainTextEdit { background: #141c26; border: 1px solid #2c3745; border-radius: 4px; padding: 7px; }
QFrame#card { background: #19212c; border: 1px solid #2c3745; border-radius: 6px; }
QFrame#card QWidget { background: transparent; }
QPushButton { background: #243140; border: 1px solid #3a4a5c; border-radius: 6px;
              padding: 9px 17px; font-weight: 600; }
QPushButton:hover { background: #304255; }
QPushButton:focus { border: 2px solid #8ddfcd; }
QPushButton#refresh { background: #55dbc3; color: #10251f; border-color: #55dbc3; }
QPushButton#refresh:hover { background: #86ecd8; }
QPushButton:disabled { background: #242e3a; color: #7a899a; border-color: #34404e; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #151c25; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3b4d60; min-height: 30px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# Applied to Home only; the shared shell/sidebar and other pages keep their theme.
HOME_STYLESHEET = """
QWidget#homeDashboard { background: #111820; color: #F1F5F9; }
QWidget { background: transparent; color: #F1F5F9; }
QFrame#homeSimCard, QFrame#homeDataCard, QFrame#homeConnectionCard {
    background: #1A2530; border: 1px solid #2B3B49; border-radius: 10px;
}
QFrame#homeAccountPrompt {
    background: #142923; border: 1px solid #2D564C; border-radius: 10px;
}
QLabel#homeAccountTitle { color: #F1F5F9; font-size: 18px; font-weight: 700; }
QLabel#homeAccountDescription { color: #A2B6CA; font-size: 12px; }
QLabel#homeAccountStatus {
    background: #22372F; color: #A2B6CA; border: 1px solid #3A544A;
    border-radius: 10px; padding: 4px 9px; font-size: 11px;
}
QLabel#homeAccountStatus[level="ok"] { background: #203D39; color: #55D7C4; border-color: #31564F; }
QLabel#homeAccountStatus[level="warning"] { background: #3A3222; color: #E6C17A; border-color: #655438; }
QLabel#homeAccountStatus[level="error"] { background: #3A282D; color: #ED8D9C; border-color: #68424B; }
QPushButton#homeConnectAction {
    background: #55D7C4; color: #10251F; border: 1px solid #55D7C4;
    border-radius: 6px; padding: 9px 16px; font-size: 13px; font-weight: 700;
}
QPushButton#homeConnectAction:hover { background: #7BE2D2; border-color: #7BE2D2; }
QPushButton#homeConnectAction:focus { border: 2px solid #B0F4E9; }
QPushButton#homeConnectAction:disabled { background: #243D35; color: #79998D; border-color: #345348; }
QLabel#homeCaption, QLabel#homeEyebrow, QLabel#homeMuted {
    color: #A2B6CA; font-size: 12px;
}
QLabel#homeSimName { color: #F1F5F9; font-size: 21px; font-weight: 700; }
QLabel#homeDataValue { color: #55D7C4; font-size: 43px; font-weight: 700; }
QLabel#homeDetail, QLabel#homePromoName { color: #F1F5F9; font-size: 13px; font-weight: 600; }
QLabel#homeExpiry { color: #A2B6CA; font-size: 12px; }
QLabel#homeLoadValue { color: #F1F5F9; font-size: 16px; font-weight: 600; }
QLabel#homeConnectionTitle { color: #F1F5F9; font-size: 17px; font-weight: 700; }
QLabel#homeNetworkBadge {
    background: #203D39; color: #55D7C4; border: 1px solid #31564F;
    border-radius: 10px; padding: 4px 10px; font-size: 12px; font-weight: 700;
}
QLabel#homeNetworkBadge[level="warning"] { background: #3A3222; color: #E6C17A; border-color: #655438; }
QLabel#homeNetworkBadge[level="error"] { background: #3A282D; color: #ED8D9C; border-color: #68424B; }
QLabel#homeNetworkBadge[level="info"] { background: #24313D; color: #A2B6CA; border-color: #384957; }
QLabel#homeStatus { color: #A2B6CA; font-size: 12px; }
QLabel#homeStatus[level="ok"] { color: #55D7C4; }
QLabel#homeStatus[level="warning"] { color: #E6C17A; }
QLabel#homeStatus[level="error"] { color: #ED8D9C; }
QLabel#homeStatus[level="info"] { color: #A2B6CA; }
QLabel#homeIcon { background: #203A37; border-radius: 10px; padding: 7px; }
QLabel#homeIcon[level="warning"] { background: #3A3222; }
QLabel#homeIcon[level="error"] { background: #3A282D; }
QLabel#homeIcon[level="info"] { background: #24313D; }
QPushButton#homeRefresh, QPushButton#homeAction {
    background: #21313D; color: #F1F5F9; border: 1px solid #3A5060;
    border-radius: 6px; padding: 6px 11px; font-size: 12px; font-weight: 600;
}
QPushButton#homeRefresh:hover, QPushButton#homeAction:hover { background: #2B4050; border-color: #55D7C4; }
QPushButton#homeRefresh:disabled, QPushButton#homeAction:disabled { background: #24313D; color: #71889B; border-color: #334653; }
QPushButton#homeTextAction, QPushButton#homePhoneToggle {
    background: transparent; color: #A2B6CA; border: none; padding: 4px 6px;
    font-size: 12px;
}
QPushButton#homeTextAction:hover, QPushButton#homePhoneToggle:hover { color: #55D7C4; background: #243A42; }
QPushButton#homeRefresh:focus, QPushButton#homeAction:focus,
QPushButton#homeTextAction:focus, QPushButton#homePhoneToggle:focus { border: 1px solid #55D7C4; }
QFrame#homeDivider { background: #304251; border: none; min-height: 1px; max-height: 1px; }
QProgressBar#homeProgress {
    background: #2B3D48; border: none; border-radius: 3px; min-height: 6px; max-height: 6px;
}
QProgressBar#homeProgress::chunk { background: #55D7C4; border-radius: 3px; }
"""


MESSAGES_STYLESHEET = """
QWidget#messagesPage, QDialog#messageDetailsDialog {
    background: #111820; color: #F1F5F9; font-size: 13px;
}
QFrame#messagesInboxCard, QFrame#messageDetailsCard {
    background: #1A2530; border: 1px solid #304251; border-radius: 8px;
}
QLabel#messagesMuted, QLabel#messagesLastRefresh, QLabel#messageDetailsTimestamp {
    background: transparent; color: #A2B6CA; font-size: 12px;
}
QLabel#messageDetailsSender {
    background: transparent; color: #F1F5F9; font-size: 15px; font-weight: 600;
}
QLabel#messageStatus { background: transparent; color: #A2B6CA; }
QLabel#messageStatus[level="warning"] { color: #E5B86B; }
QLabel#messageStatus[level="error"] { color: #E58C99; }
QListWidget#messagesInboxList {
    background: transparent; color: #F1F5F9; border: none; outline: none;
    selection-background-color: #243A42; selection-color: #F1F5F9;
}
QListWidget#messagesInboxList::item { padding: 0; margin: 0; border: none; }
QPlainTextEdit#messageDetailsContent {
    background: #17222D; color: #F1F5F9; border: 1px solid #304251;
    border-radius: 6px; padding: 10px; selection-background-color: #28574F;
    selection-color: #F1F5F9; font-size: 13px;
}
QPushButton#messagesRefresh, QPushButton#messagesCancel,
QPushButton#messageCopy, QPushButton#messageClose {
    background: #21313D; color: #F1F5F9; border: 1px solid #3A5060;
    border-radius: 6px; padding: 7px 13px; font-size: 12px; font-weight: 600;
}
QPushButton#messagesRefresh, QPushButton#messageClose {
    background: #55D7C4; color: #10241F; border-color: #55D7C4;
}
QPushButton#messagesRefresh:hover, QPushButton#messageClose:hover {
    background: #7DE4D5; border-color: #7DE4D5;
}
QPushButton#messagesCancel:hover, QPushButton#messageCopy:hover {
    background: #2B4050; border-color: #55D7C4;
}
QPushButton#messagesRefresh:focus, QPushButton#messagesCancel:focus,
QPushButton#messageCopy:focus, QPushButton#messageClose:focus {
    border: 2px solid #8DDFCD;
}
QPushButton#messagesRefresh:disabled, QPushButton#messagesCancel:disabled,
QPushButton#messageCopy:disabled, QPushButton#messageClose:disabled {
    background: #24313D; color: #71889B; border-color: #334653;
}
"""


TRAY_STYLESHEET = """
QFrame#trayDashboard { background: #111820; border: 1px solid #304251; border-radius: 10px; }
QWidget { background: transparent; color: #F1F5F9; font-size: 12px; }
QFrame#trayBalanceCard { background: #1A2530; border: none; border-radius: 7px; }
QScrollArea#trayBody { border: none; background: transparent; }
QLabel#trayMuted { color: #A2B6CA; font-size: 11px; }
QLabel#trayName { color: #F1F5F9; font-size: 17px; font-weight: 700; }
QLabel#trayData { color: #55D7C4; font-size: 31px; font-weight: 700; }
QLabel#trayDetail { color: #F1F5F9; font-size: 12px; font-weight: 600; }
QLabel#trayStatus { color: #A2B6CA; font-size: 11px; }
QPushButton#trayRefresh { background: #55D7C4; color: #10251F; border: 1px solid #55D7C4;
    border-radius: 6px; padding: 7px 12px; font-weight: 700; }
QPushButton#trayRefresh:hover { background: #7BE2D2; }
QPushButton#trayRefresh:disabled { background: #24313D; color: #71889B; border-color: #334653; }
QPushButton#trayAction { background: #21313D; color: #F1F5F9; border: 1px solid #3A5060;
    border-radius: 5px; padding: 6px 10px; }
QPushButton#trayAction:hover { background: #2B4050; border-color: #55D7C4; }
QPushButton#trayRefresh:focus, QPushButton#trayAction:focus { border: 2px solid #B0F4E9; }
"""
