"""Keep native QtQml dependencies without unrelated QML import plugins.

SIM Manager uses Qt Widgets and QtWebEngineWidgets; it loads no QML documents.
The standard QtQml hook additionally collects every installed QML plugin tree,
including optional modules unrelated to this application. Retain PyInstaller's
normal native dependency handling and leave WebEngine's maintained hook intact.
"""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
