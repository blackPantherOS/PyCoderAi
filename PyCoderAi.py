#!/usr/bin/python3
#*********************************************************************************************************
#*   __     __               __     ______                __   __                      _______ _______   *
#*  |  |--.|  |.---.-..----.|  |--.|   __ \.---.-..-----.|  |_|  |--..-----..----.    |       |     __|  *
#*  |  _  ||  ||  _  ||  __||    < |    __/|  _  ||     ||   _|     ||  -__||   _|    |   -   |__     |  *
#*  |_____||__||___._||____||__|__||___|   |___._||__|__||____|__|__||_____||__|      |_______|_______|  *
#* http://www.blackpantheros.eu | http://www.blackpanther.hu - kbarcza[]blackpanther.hu * Charles Barcza *
#*************************************************************************************(c)2002-2020********
# Project         : PyCoderAi
# Module          : Development IDE
# File            : PyCoderAi.py
# Version         : 0.9.4
# Authors         : Charles K. Barcza & Miklos Horvath - info@blackpanther.hu
# Created On      : Fri Jan 17 2020
# Last updated    : Tue Feb 27 2026
# Credits         : Miklos Horvath - Fixes and suggestions, Harrison Amoatey - the Qt4 coding
# Purpose         : LightWare Python IDE based on Qt6 with Ai support
#---------------------------------------------------------------

import sys
import os
import logging
import locale

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QIcon

from Extensions_Qt6.UseData import UseData
from Extensions_Qt6.Library.Library import Library
from Extensions_Qt6.About import About
from Extensions_Qt6.Settings.SettingsWidget import SettingsWidget
from Extensions_Qt6.Projects.Projects import Projects
from Extensions_Qt6.BusyWidget import BusyWidget
from Extensions_Qt6 import StyleSheet
from Extensions_Qt6.Start import Start
from Extensions_Qt6.StackSwitcher import StackSwitcher
from Extensions_Qt6.AIPanel import AIPanel
from Extensions_Qt6.OllamaManager import OllamaManager

import gettext
locale.setlocale(locale.LC_ALL, '')
traduction = None
pathname=os.path.dirname(__file__)


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path = getattr(sys, '_MEIPASS', pathname)
    return os.path.join(base_path, relative_path)

try:
    gettext.find('messages',pathname+'/locales')
    traduction = gettext.translation('messages',pathname+'/locales')
    traduction.install();
except:
    traduction = gettext
    gettext.install("pycoderai", pathname+'/locales')

try:
    language = locale.getlocale()[0].split('_')[0]
except:
    language = 'en'

print(_('Welcome to PyCoderAi! The used language for interface is: ') + language)

class PyCoderAi(QtWidgets.QMainWindow):
    """
    Main application window.
    Converted to QMainWindow to support real QDockWidget-based
    rearrangeable and dockable panels (drag, float, tab, save layout).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowIcon(QtGui.QIcon(resource_path(os.path.join("Resources", "images", "icon.png"))))
        self.setWindowTitle(_("PyCoderAi - Loading..."))

        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self.resize(screen.width() - 200, screen.height() - 200)
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height()
        - size.height()) // 2)
        primary_screen = QtGui.QGuiApplication.primaryScreen()
        resolution = primary_screen.availableSize()
        print(_("Primary Monitor:"), primary_screen.manufacturer(), 
        _("Resolution:"), resolution.width(), "x", resolution.height())
        self.move(QtGui.QGuiApplication.primaryScreen().availableGeometry().center()
        - self.rect().center())
        self.lastWindowGeometry = self.geometry()

        # We no longer use a root QVBoxLayout on self.
        # Instead we will build a central widget that contains the main UI,
        # and use QDockWidgets for movable panels.
        central_widget = QtWidgets.QWidget()
        mainLayout = QtWidgets.QVBoxLayout(central_widget)
        mainLayout.setSpacing(0)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central_widget)

        self.useData = UseData()

        logging.basicConfig(format=
        '%(asctime)s - %(levelname)s - %(message)s',
                            filename=self.useData.appPathDict["logfile"],
                            level=logging.DEBUG)
        if sys.version_info.major < 3:
            logging.error(_("This application requires Python 3"))
            sys.exit(1)

        self.library = Library(self.useData)
        self.busyWidget = BusyWidget(app, self.useData, self)

        if self.useData.SETTINGS["UI"] == "Custom":
            app.setStyleSheet(StyleSheet.globalStyle)

        self.projectWindowStack = QtWidgets.QStackedWidget()

        self.projectTitleBox = QtWidgets.QComboBox()
        self.projectTitleBox.setMinimumWidth(180)
        self.projectTitleBox.setStyleSheet(StyleSheet.projectTitleBoxStyle)
        self.projectTitleBox.setItemDelegate(QtWidgets.QStyledItemDelegate())
        self.projectTitleBox.currentIndexChanged.connect(self.projectChanged)
        self.projectTitleBox.activated.connect(self.projectChanged)

        self.settingsWidget = SettingsWidget(self.useData, app,
                                             self.projectWindowStack, 
                                             self.library.codeViewer, self)
        self.settingsWidget.colorScheme.styleEditor(self.library.codeViewer)

        startWindow = Start(self.useData, self)
        self.addProject(startWindow, _("Start"),
                        _("Start"), resource_path(os.path.join("Resources", "images", "flag-green")))

        self.projects = Projects(self.useData, self.busyWidget,
                                 self.library, self.settingsWidget, app,
                                 self.projectWindowStack, 
                                 self.projectTitleBox, self)

        self.createActions()

        hbox = QtWidgets.QHBoxLayout()
        hbox.setContentsMargins(5, 3, 5, 3)
        mainLayout.addLayout(hbox)

        hbox.addStretch(1)

        self.pagesStack = QtWidgets.QStackedWidget()
        mainLayout.addWidget(self.pagesStack)

        self.projectSwitcher = StackSwitcher(self.pagesStack)
        self.projectSwitcher.setStyleSheet(StyleSheet.mainMenuStyle)
        hbox.addWidget(self.projectSwitcher)

        self.addPage(self.projectWindowStack, _("EDITOR"), QtGui.QIcon(
            resource_path(os.path.join("Resources", "images", "hire-me"))))

        self.addPage(self.library, _("LIBRARY"), QtGui.QIcon(
            resource_path(os.path.join("Resources", "images", "library"))))
        self.projectSwitcher.setDefault()

        hbox.addWidget(self.projectTitleBox)
        hbox.setSpacing(5)

        # AI Panel in the main outer view (toggleable, as in the original design)
        # IMPORTANT: NOT a QDockWidget. It lives in the central layout and is toggled
        # with Ctrl+Alt+A. The custom "Menü" button popup is used instead of a native menuBar.
        # Wrapped in a QTabWidget alongside the Ollama Manager.
        self.aiTabWidget = QtWidgets.QTabWidget()
        # Style the tab bar so tabs are clearly visible in dark themes
        self.aiTabWidget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; background: #1e1e1e; }
            QTabBar::tab { background: #333; color: #ccc; padding: 6px 14px; border: 1px solid #444; border-bottom: none; min-width: 80px; }
            QTabBar::tab:selected { background: #555; color: #fff; font-weight: bold; }
            QTabBar::tab:hover { background: #444; }
        """)
        self.aiPanel = AIPanel(self)
        self.aiTabWidget.addTab(self.aiPanel, _("AI Chat"))
        try:
            self.ollamaManager = OllamaManager(self)
            self.aiTabWidget.addTab(self.ollamaManager, _("Ollama"))
        except Exception as e:
            print(f"[WARNING] Failed to create OllamaManager: {e}")
            import traceback
            traceback.print_exc()
        mainLayout.addWidget(self.aiTabWidget)
        self.aiTabWidget.setVisible(False)  # hidden by default, Ctrl+Alt+A to toggle

        self.settingsButton = QtWidgets.QToolButton()
        self.settingsButton.setAutoRaise(True)
        self.settingsButton.setDefaultAction(self.settingsAct)
        hbox.addWidget(self.settingsButton)

        self.fullScreenButton = QtWidgets.QToolButton()
        self.fullScreenButton.setAutoRaise(True)
        self.fullScreenButton.setDefaultAction(self.showFullScreenAct)
        hbox.addWidget(self.fullScreenButton)

        self.aboutButton = QtWidgets.QToolButton()
        self.aboutButton.setAutoRaise(True)
        self.aboutButton.setDefaultAction(self.aboutAct)
        hbox.addWidget(self.aboutButton)

        self.setKeymap()

        if self.useData.settings["firstRun"] == 'True':
            self.showMaximized()
        else:
            try:
                self.restoreUiState()
            except Exception as e:
                # Never let bad persisted UI state (old geometry, bad dockState, etc.) prevent startup
                print(f"Warning: restoreUiState failed ({e}), starting with default layout.")
                self.showMaximized()

        self.useData.settings["running"] = 'True'
        self.useData.settings["firstRun"] = 'False'

        # Configure AI Panel with settings
        self.aiPanel.configure_ai_assistant(self.useData.settings)

        # Reconfigure when settings dialog closes (user may change AI provider, key, etc.)
        self.settingsWidget.finished.connect(
            lambda _code: self.aiPanel.configure_ai_assistant(self.useData.settings)
        )

        self.useData.saveSettings()

    def createActions(self):
        self.aboutAct = QtGui.QAction(
            QtGui.QIcon(resource_path(os.path.join("Resources", "images", "properties"))),
            _("About PyCoderAi"), self, statusTip=_("More info of PyCoderAi "),
            triggered=self.showAbout)

        self.showFullScreenAct = \
            QtGui.QAction(
                QtGui.QIcon(resource_path(os.path.join(
                "Resources", "images", "Fullscreen"))),
                _("Fullscreen"), self,
                statusTip="Fullscreen",
                          triggered=self.showFullScreenMode)

        self.settingsAct = QtGui.QAction(
            QtGui.QIcon(resource_path(os.path.join("Resources", "images", "config"))),
            _("Settings"), self,
            statusTip=_("PyCoderAi Settings"), triggered=self.showSettings)

        self.createMenus()

    def createMenus(self):
        """Basic menu bar. No native menuBar is used (the UI relies on the custom
        "Menü" button that pops up a QMenu). Dock toggle menus are not added here.
        Per the design, there is a "Menü" button with submenus instead of a top menu bar.
        """
        # We intentionally do not call self.menuBar() or add top-level menus like "View"/"Megjelenés"
        # because the application uses a custom popup menu from a button.
        pass  # createActions already created the actions used in the popup menus elsewhere if needed.

    def addPage(self, pageWidget, name, iconPath):
        self.projectSwitcher.addButton(name=name, icon=iconPath)
        self.pagesStack.addWidget(pageWidget)

    def loadProject(self, path, show=False, new=False):
        self.projects.loadProject(path, show, new)

    def newProject(self):
        self.projects.newProjectDialog.exec()

    def showProject(self, path):
        if not os.path.exists(path):
            message = QtWidgets.QMessageBox.warning(
                self, _("Open Project"), _("Project cannot be be found!"))
        else:
            if path in self.useData.OPENED_PROJECTS:
                for i in range(self.projectWindowStack.count() - 1):
                    window = self.projectWindowStack.widget(i)
                    p_path = window.projectPathDict["root"]
                    if os.path.samefile(path, p_path):
                        self.projectTitleBox.setCurrentIndex(i)
                        return True
        return False

    def addProject(self, window, name, type='Project', iconPath=None):
        self.projectWindowStack.insertWidget(0, window)
        if type == 'Project':
            self.projectTitleBox.insertItem(0, QtGui.QIcon(
                resource_path(os.path.join("Resources", "images", "project"))),
                name, [window, type])
        else:
            self.projectTitleBox.insertItem(0, QtGui.QIcon(
                iconPath), name, [window, type])

    def projectChanged(self, index):
        # Save current project's dock layout (and legacy splitter state) before switching away.
        # This ensures the user's last manual resize of the project region / bottom panel
        # is persisted even if they just switch projects without closing.
        current = self.projectWindowStack.currentWidget()
        if current and hasattr(current, 'saveUiState'):
            current.saveUiState()

        data = self.projectTitleBox.itemData(index)
        window = data[0]
        windowType = data[1]
        if windowType == "Start":
            self.setWindowTitle(_("PyCoderAi - Start"))
        elif windowType == "Project":
            title = window.editorTabWidget.getEditorData("filePath")
            self.updateWindowTitle(title)
            # Update AI Panel with current editor (prefer real editor widget over tab page)
            if self.aiTabWidget.isVisible():
                etw = getattr(window, 'editorTabWidget', None)
                current_editor = None
                if etw:
                    current_editor = getattr(etw, 'focusedEditor', lambda: None)() or getattr(etw, 'getEditor', lambda: None)()
                if not current_editor:
                    current_editor = window.editorTabWidget.currentWidget() if etw else None
                if current_editor:
                    self.aiPanel.set_editor(current_editor)
        self.projectWindowStack.setCurrentWidget(window)

    def removeProject(self, window):
        for index in range(self.projectTitleBox.count() - 1):
            data = self.projectTitleBox.itemData(index)
            windowWidget = data[0]
            if windowWidget == window:
                self.projectWindowStack.removeWidget(window)
                self.projectTitleBox.removeItem(index)

    def updateWindowTitle(self, title):
        if title is None:
            title = _("PyCoderAi - ") + _("Unsaved")
        else:
            window = self.projectTitleBox.itemData(
                self.projectTitleBox.currentIndex())[0]
            if title.startswith(window.projectPathDict["sourcedir"]):
                src_dir = window.projectPathDict["sourcedir"]
                n = title.partition(src_dir)[-1]
                title = 'PyCoderAi - ' + n
            else:
                title = "PyCoderAi - " + title
        self.setWindowTitle(title)

    def showAbout(self):
        aboutPane = About(self)
        aboutPane.exec()

    def showSettings(self):
        self.settingsWidget.show()

    def showFullScreenMode(self):
        if self.isFullScreen():
            self.showNormal()
            self.setGeometry(self.lastWindowGeometry)
        else:
            # get current size ahd show Fullscreen
            # so we can later restore to proper position
            self.lastWindowGeometry = self.geometry()
            self.showFullScreen()

    def saveUiState(self):
        settings = QtCore.QSettings("PyCoder", "config")
        settings.beginGroup("MainWindow")

        # Proper QMainWindow geometry + dock state (the key new thing for rearrangeable panels)
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("dockState", self.saveState())   # <-- saves positions of all QDockWidgets

        # Keep the old splitter states (still used inside EditorWindow / Library)
        settings.setValue("lsplitter", self.library.mainSplitter.saveState())
        settings.setValue(
            "snippetsMainsplitter",
            self.settingsWidget.snippetEditor.mainSplitter.saveState())
        settings.setValue("windowMaximized", self.isMaximized())
        settings.endGroup()

    def restoreUiState(self):
        settings = QtCore.QSettings("PyCoder", "config")
        settings.beginGroup("MainWindow")

        # Restore docks first (QDockWidget positions, visibility, etc.)
        # This is new after switching to QMainWindow + dockable panels.
        dock_state = settings.value("dockState")
        if dock_state:
            try:
                self.restoreState(dock_state)
            except Exception:
                pass  # corrupted or incompatible state from very old version

        maximized = settings.value("windowMaximized", True, type=bool)

        geom = settings.value("geometry")
        if geom:
            try:
                # New format (since we switched to QMainWindow): QByteArray from saveGeometry()
                if isinstance(geom, (QtCore.QByteArray, bytes, bytearray, memoryview)):
                    self.restoreGeometry(geom)
                else:
                    # Old format (before the QMainWindow + dock changes): was a QRect
                    # Use setGeometry for backward compatibility.
                    self.setGeometry(geom)
            except Exception:
                # If anything goes wrong (bad data, old format we didn't catch, etc.)
                # just fall through to a normal show.
                pass

        if maximized:
            self.showMaximized()
        else:
            self.show()

        # Old splitter states (still used inside Library and Settings)
        try:
            self.library.mainSplitter.restoreState(settings.value("lsplitter"))
            self.settingsWidget.snippetEditor.mainSplitter.restoreState(
                settings.value("snippetsMainsplitter"))
        except Exception:
            pass

        settings.endGroup()

    def closeEvent(self, event):
        for i in range(self.projectWindowStack.count() - 1):
            window = self.projectWindowStack.widget(i)
            closed = window.closeWindow()
            if not closed:
                self.projectTitleBox.setCurrentIndex(i)
                event.ignore()
                return
            else:
                pass
        self.saveUiState()
        self.useData.saveUseData()
        app.closeAllWindows()

        event.accept()

    def setKeymap(self):
        shortcuts = self.useData.CUSTOM_SHORTCUTS

        self.shortFullscreen = QtGui.QShortcut(
            shortcuts["Ide"]["Fullscreen"], self)
        self.shortFullscreen.activated.connect(self.showFullScreenMode)

        # Add AI Panel shortcut
        self.shortAIPanel = QtGui.QShortcut(
            shortcuts["Ide"].get("AIPanel", "Ctrl+Alt+A"), self)
        self.shortAIPanel.activated.connect(self.toggleAIPanel)

    def toggleAIPanel(self):
        """Toggle AI Panel visibility (the one in the main outer view).
        Uses Ctrl+Alt+A. The panel lives in the central layout (not as a dock).
        The app uses a custom "Menü" button popup, not a native menu bar.
        """
        current_visibility = self.aiTabWidget.isVisible()
        self.aiTabWidget.setVisible(not current_visibility)

        # If we just showed it, feed the current editor for context
        if not current_visibility:
            current_index = self.projectWindowStack.currentIndex()
            if current_index >= 0:
                current_window = self.projectWindowStack.currentWidget()
                if hasattr(current_window, 'editorTabWidget'):
                    etw = current_window.editorTabWidget
                    current_editor = getattr(etw, 'focusedEditor', lambda: None)() or getattr(etw, 'getEditor', lambda: None)()
                    if not current_editor:
                        current_editor = etw.currentWidget()
                    if current_editor:
                        self.aiPanel.set_editor(current_editor)

app = QtWidgets.QApplication(sys.argv)
QtWidgets.QApplication.setWindowIcon(QIcon('pycoder'))
splash = QtWidgets.QSplashScreen(
    QtGui.QPixmap(resource_path(os.path.join("Resources", "images", "splash.png"))))
splash.show()

main = PyCoderAi()
splash.finish(main)
sys.exit(app.exec())
