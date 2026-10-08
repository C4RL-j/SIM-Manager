"""Compact dark Qt Widgets theme with native window chrome."""

STYLESHEET = """
QWidget { background: #10151c; color: #e8edf3; font-size: 13px; }
QWidget#sidebar { background: #151c25; border-right: 1px solid #27313e; }
QLabel { background: transparent; }
QLabel#brand { font-size: 21px; font-weight: 700; }
QLabel#brandMark { background: #55dbc3; color: #10241f; border-radius: 9px;
                  font-size: 17px; font-weight: 700; }
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
