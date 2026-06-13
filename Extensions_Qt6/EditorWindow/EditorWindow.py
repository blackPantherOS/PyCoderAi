import os
import re
import sys
import traceback
import logging

import xml.etree.ElementTree as ET  # QtXml migration

from PyQt6 import QtCore, QtGui, QtWidgets

from Extensions_Qt6.FileExplorer import FileExplorer
from Extensions_Qt6.BottomWidgets.FindInFiles import FindInFiles
from Extensions_Qt6.Projects.ProjectManager.ProjectManager import ProjectManager
from Extensions_Qt6.SearchWidget import SearchWidget
from Extensions_Qt6.Outline.Outline import Outline
from Extensions_Qt6.EditorTabWidget import EditorTabWidget
from Extensions_Qt6.WritePad import WritePad
from Extensions_Qt6.Favourites import Favourites
from Extensions_Qt6.ExternalLauncher import ExternalLauncher
from Extensions_Qt6.BottomWidgets.Assistant import Assistant
from Extensions_Qt6.BottomWidgets.TasksWidget import Tasks
from Extensions_Qt6.BottomWidgets.BookmarkWidget import BookmarkWidget
from Extensions_Qt6.BottomWidgets.RunWidget import RunWidget
from Extensions_Qt6.BottomWidgets.Messages import MessagesWidget
from Extensions_Qt6.StackSwitcher import StackSwitcher
from Extensions_Qt6.AIPanel import AIPanel
from Extensions_Qt6 import StyleSheet
from Extensions_Qt6.EditorWindow.BuildStatusWidget import BuildStatusWidget
from Extensions_Qt6.EditorWindow.VerticalSplitter import VerticalSplitter
from Extensions_Qt6.BottomWidgets.Profiler import Profiler
from Extensions_Qt6.OllamaManager import OllamaManager


class EditorWindow(QtWidgets.QMainWindow):
    """
    Per-project editor window, now a QMainWindow so that its internal
    regions (project side panel, bottom tools panel, and editor area)
    can be turned into real QDockWidgets. This allows the user to
    drag, float, rearrange, tab, and dock the "projekt régió" (side)
    and the "alsó panel" (bottom) around the editor within the project view.
    """

    def __init__(self, projectPathDict, library, busyWidget,
                 colorScheme, useData, app, parent):
        QtWidgets.QMainWindow.__init__(self, parent)

        self.app = app
        self.useData = useData
        self.library = library
        self.projects = parent
        self.colorScheme = colorScheme

        self.projectPathDict = projectPathDict
        self.loadProjectData()

        self.busyWidget = busyWidget
        self.buildStatusWidget = BuildStatusWidget(self.app, self.useData)

        self.standardToolbar = QtWidgets.QToolBar("Standard")
        self.standardToolbar.setMovable(False)
        self.standardToolbar.setIconSize(QtCore.QSize(22,22))
        # vector: planned for new setting
        #self.standardToolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        #self.standardToolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.standardToolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonFollowStyle)
        #self.standardToolbar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        self.standardToolbar.setMaximumHeight(64)
        self.standardToolbar.setObjectName("StandardToolBar")

        # Editor region container (will be the central widget)
        editor_central = QtWidgets.QWidget()
        editor_vbox = QtWidgets.QVBoxLayout(editor_central)
        editor_vbox.setContentsMargins(0, 0, 0, 0)
        editor_vbox.setSpacing(0)

        # Add toolbar to the editor region
        editor_vbox.addWidget(self.standardToolbar)

        # The 'widget' that will hold the editorTabWidget + search + find dashboard
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        editor_vbox.addWidget(widget)

        # We keep vSplitter/hSplitter/sideSplitter/bottomStack for compatibility
        # with widgets that were passed them and for loading old per-project layout state.
        # The docking system (see below) now handles the visual layout of side and bottom.
        self.vSplitter = VerticalSplitter()
        self.hSplitter = QtWidgets.QSplitter()
        self.hSplitter.setObjectName("hSplitter")
        self.sideSplitter = QtWidgets.QSplitter()
        self.sideSplitter.setObjectName("sidebarItem")
        self.sideSplitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.bottomStack = QtWidgets.QStackedWidget()

        # Note: we do not add the splitters to any layout here.
        # The side will go to a left dock, bottom to a bottom dock,
        # editor_central will be set as central widget.

        self.bottomStackSwitcher = StackSwitcher(self.bottomStack)
        self.bottomStackSwitcher.setStyleSheet(StyleSheet.bottomSwitcherStyle)

        self.messagesWidget = MessagesWidget(
            self.bottomStackSwitcher, self.vSplitter)

        self.createActions()

        self.manageFavourites = Favourites(

            self.projectData['favourites'], self.messagesWidget, self)

        self.externalLauncher = ExternalLauncher(
            self.projectData["launchers"], self)

        self.writePad = WritePad(self.projectPathDict[
                                 "notes"], self.projectPathDict["name"], self)

        self.bookmarkToolbar = QtWidgets.QToolBar("Bookmarks")
        self.bookmarkToolbar.setMovable(False)
        self.bookmarkToolbar.setFloatable(False)
        self.standardToolbar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        self.bookmarkToolbar.setObjectName("Bookmarks")
        self.bookmarkToolbar.addSeparator()

        self.editorTabWidget = EditorTabWidget(
            self.useData, self.projectPathDict, self.projectData[
                "settings"], self.messagesWidget,
            self.colorScheme, self.busyWidget, self.bookmarkToolbar, self.app, self.manageFavourites,
            self.externalLauncher, self)
        vbox.addWidget(self.editorTabWidget)

        # vector: better looks for editor widget at first start 
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(2)

        self.editorTabWidget.setSizePolicy(sizePolicy)
        self.editorTabWidget.setMinimumWidth(500)
        self.editorTabWidget.setMinimumHeight(300)

        self.manageFavourites.openFile.connect(self.editorTabWidget.loadfile)

        self.editorTabWidget.updateRecentFilesList.connect(
            self.updateRecentFiles)
        self.editorTabWidget.updateLinesCount.connect(self.updateLineCount)
        self.editorTabWidget.updateEncodingLabel.connect(
            self.updateEncodingLabel)
        self.editorTabWidget.cursorPositionChanged.connect(
            self.showCursorPosition)
        self.editorTabWidget.currentChanged.connect(
            self.updateAIPanelEditor)

        self.searchWidget = SearchWidget(
            self.useData, self.editorTabWidget)
        vbox.addWidget(self.searchWidget)

        self.findInFiles = FindInFiles(
            self.useData, self.editorTabWidget, projectPathDict, self.bottomStackSwitcher)
        vbox.addWidget(self.findInFiles.dashboard)
        self.findInFiles.dashboard.hide()

        self.projectManager = ProjectManager(
            self.editorTabWidget, self.messagesWidget, projectPathDict, self.projectData[
                "settings"], self.useData, app,
            self.busyWidget, self.buildStatusWidget, self.projects)
        self.projectManager.projectView.fileActivated.connect(
            self.editorTabWidget.loadfile)

        self.outline = Outline(
            self.useData, self.editorTabWidget)

        # Side content container (will be placed in a dock, not in old splitters)
        self.sideBottomTab = QtWidgets.QTabWidget()
        self.sideBottomTab.setObjectName("sideBottomTab")

        # (old splitter adds removed; docking system handles layout now)
        # We still keep sideSplitter for legacy saved state restore (it won't be the visual container).

        self.sideBottomTab.addTab(self.projectManager.projectView, QtGui.QIcon(
            os.path.join("Resources", "images", "tree")), _("Project"))

        self.sideBottomTab.addTab(self.outline, QtGui.QIcon(
            os.path.join("Resources", "images", "tree")), _("Classes"))

        self.fileExplorer = FileExplorer(
            self.useData, self.projectData['shortcuts'], self.messagesWidget, self.editorTabWidget)
        self.fileExplorer.fileActivated.connect(self.editorTabWidget.loadfile)
        self.sideBottomTab.addTab(self.fileExplorer, QtGui.QIcon(
            os.path.join("Resources", "images", "tree")), _("File System"))

        # Add the tab to the (legacy) sideSplitter so that old saved 'sidesplitter' state can be restored without error.
        # The actual visible side panel will be the one in the dock (reparented).
        self.sideSplitter.addWidget(self.sideBottomTab)

        # ------------------------------------------------------------------
        # Make the main regions dockable inside this EditorWindow (QMainWindow)
        # ------------------------------------------------------------------
        # 1. Central = editor region (toolbar + editor + search + find dashboard)
        self.setCentralWidget(editor_central)

        # 2. Project region dock (the side tab: Project / Classes / File System)
        #    This is "a projekt régió"
        project_dock = QtWidgets.QDockWidget(_("Project Region"), self)
        project_dock.setObjectName("ProjectDock")
        project_dock.setWidget(self.sideBottomTab)
        project_dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea |
                                     QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        project_dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, project_dock)
        self.projectDock = project_dock

        # 3. Bottom panel dock (the entire alsó panel with all tools + switcher)
        #    This is "az egész alsó panelt".
        #    Allowed areas now include Left/Right too (for ultrawide monitors),
        #    in addition to the traditional Bottom/Top. The internal VBoxLayout
        #    will adapt when the dock is placed on the side.
        bottom_container = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        bottom_layout.addWidget(self.bottomStack)  # panels/content on top

        # switcher buttons below the panels, left-aligned, keep original button widths
        # (not stretched full width)
        switcher_bar = QtWidgets.QWidget()
        switcher_hbox = QtWidgets.QHBoxLayout(switcher_bar)
        switcher_hbox.setContentsMargins(0, 0, 0, 0)
        switcher_hbox.setSpacing(0)
        switcher_hbox.addWidget(self.bottomStackSwitcher)
        switcher_hbox.addStretch(1)
        bottom_layout.addWidget(switcher_bar)

        bottom_dock = QtWidgets.QDockWidget(_("Tools Panel"), self)
        bottom_dock.setObjectName("BottomDock")
        bottom_dock.setWidget(bottom_container)
        bottom_dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.BottomDockWidgetArea |
            QtCore.Qt.DockWidgetArea.TopDockWidgetArea |
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea |
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        bottom_dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Allow full collapsing of the bottom panel by dragging below current min height.
        # The stack (panels) can shrink to 0; the switcher bar will remain as the bottom control.
        # This restores the old VerticalSplitter behavior where you could fully close the bottom
        # when not needed.
        self.bottomStack.setMinimumHeight(0)
        switcher_bar.setMinimumHeight(0)
        bottom_container.setMinimumHeight(0)
        bottom_dock.setMinimumHeight(0)

        # Prefer shrinking the stack over the bar
        self.bottomStack.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Ignored
        )

        self.addDockWidget(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea, bottom_dock)
        self.bottomDock = bottom_dock

        # Flags to protect dock restore and the "X = return to main" logic from each other.
        self._docks_restoring = False
        self._docks_restored = False

        # User's requested behavior for closable docks:
        # When the user clicks the X (close) on a docked panel (Project Region or Bottom Panel),
        # do NOT hide/leave it closed. Instead, put the panel back into the main window
        # (re-dock it to its home area). This way the "close" acts as "return to main layout".
        # The panels remain movable and floatable.
        #
        # We use eventFilter on Close events instead of visibilityChanged, because
        # visibilityChanged fires too often (during restore, show, tab changes, etc.)
        # and was causing the docks to become "locked" (non-movable) as a regression.
        self.projectDock.installEventFilter(self)
        self.bottomDock.installEventFilter(self)

        # Defer dock layout restore until after the parent layout (stacked widget in outer QMainWindow)
        # has assigned our final size. Otherwise restoreState may apply relative dock sizes to an
        # uninitialized geometry, causing default sizes on next open.
        # This ensures the user's last resized dock widths/heights (project region + bottom panel) are remembered.
        QtCore.QTimer.singleShot(0, self._restoreDockLayout)

        # Note: the editor region itself stays as central widget (standard for IDEs).
        # The project region and bottom panel are now fully dockable/rearrangeable/floatable
        # inside this project's view. User can drag their title bars, dock to other sides,
        # float as separate windows, tab them together, etc.

        # create menus
        self.mainMenu = QtWidgets.QMenu()
        self.mainMenu.addMenu(self.editorTabWidget.newFileMenu)
        self.mainMenu.addAction(self.editorTabWidget.openFileAct)
        self.mainMenu.addAction(self.editorTabWidget.saveAct)
        self.mainMenu.addAction(self.editorTabWidget.saveAllAct)
        self.mainMenu.addAction(self.editorTabWidget.saveAsAct)
        self.mainMenu.addAction(self.editorTabWidget.saveCopyAsAct)
        self.mainMenu.addAction(self.editorTabWidget.printAct)

        self.projectMenu = QtWidgets.QMenu(_("Project"))
        if projectPathDict["type"] == _("Desktop Application") or projectPathDict["type"] == "Desktop Application":
            self.projectMenu.addAction(self.buildAct)
            self.projectMenu.addAction(self.openBuildAct)
        self.projectMenu.addAction(self.configureAct)
        self.projectMenu.addSeparator()
        self.projectMenu.addAction(self.exportProjectAct)
        self.projectMenu.addAction(self.closeProjectAct)
        self.mainMenu.addMenu(self.projectMenu)

        self.mainMenu.addSeparator()
        self.mainMenu.addAction(self.gotoLineAct)
        self.mainMenu.addAction(self.viewSwitcherAct)
        helpMenu = self.mainMenu.addMenu(_("Help"))
        helpMenu.addAction(self.userGuideAct)
        helpMenu.addAction(self.pythonManualsAct)
        helpMenu.addSeparator()
        helpMenu.addAction(self.feedbackAct)
        helpMenu.addAction(self.checkUpdatesAct)
        self.mainMenu.addSeparator()
        self.mainMenu.addMenu(self.manageFavourites.favouritesMenu)
        self.recentFilesMenu = self.mainMenu.addMenu(_("Recent Files"))
        self.recentFilesMenu.setIcon(
            QtGui.QIcon(os.path.join("Resources", "images", "history")))
        self.loadRecentFiles()
        self.mainMenu.addMenu(self.externalLauncher.launcherMenu)
        self.mainMenu.addSeparator()
        self.mainMenu.addAction(self.exitAct)

        self.createToolbars()

        # create StatusBar
        self.statusbar = QtWidgets.QStatusBar()

        self.statusbar.addPermanentWidget(self.buildStatusWidget)

        #*** Position
        self.cursorPositionButton = QtWidgets.QToolButton()
        self.cursorPositionButton.setAutoRaise(True)
        self.cursorPositionButton.clicked.connect(
            self.editorTabWidget.goToCursorPosition)
        self.statusbar.addPermanentWidget(self.cursorPositionButton)
        #*** lines
        self.linesLabel = QtWidgets.QLabel(_("Lines: 0"))
        self.linesLabel.setMinimumWidth(50)
        self.statusbar.addPermanentWidget(self.linesLabel)
        #*** encoding
        self.encodingLabel = QtWidgets.QLabel(_("Coding: utf-8"))
        self.statusbar.addPermanentWidget(self.encodingLabel)
        #*** uptime
        self.uptimeLabel = QtWidgets.QLabel()
        self.uptimeLabel.setText(_("Uptime: 0min"))
        self.statusbar.addPermanentWidget(self.uptimeLabel)

        # For QMainWindow, use the native status bar (placed at the very bottom of this project window)
        self.setStatusBar(self.statusbar)

        # ── AI Panel is FIRST (tab index 0, shown by default) ──
        self.aiPanel = AIPanel(self.bottomStackSwitcher)
        self.addBottomWidget(self.aiPanel,
                             QtGui.QIcon(os.path.join("Resources", "images", "hire-me")), _("AI Assistant"))

        self.runWidget = RunWidget(
            self.bottomStackSwitcher, self.projectData[
                "settings"], self.useData,
            self.editorTabWidget, self.vSplitter,
            self.runProjectAct, self.stopRunAct, self.runFileAct)
        self.addBottomWidget(self.runWidget,
                             QtGui.QIcon(os.path.join("Resources", "images", "graphic-design")),  _("Output"))
        # Give RunWidget reference to the stack so it can switch itself visible when content appears
        self.runWidget.bottomStack = self.bottomStack

        self.assistantWidget = Assistant(
            self.editorTabWidget, self.bottomStackSwitcher)
        self.addBottomWidget(self.assistantWidget,
                             QtGui.QIcon(os.path.join("Resources", "images", "flag")), _("Alerts"))

        bookmarkWidget = BookmarkWidget(
            self.editorTabWidget, self.bottomStackSwitcher)
        self.addBottomWidget(bookmarkWidget,
                             QtGui.QIcon(os.path.join("Resources", "images", "tag")), _("Bookmarks"))

        tasksWidget = Tasks(self.editorTabWidget, self.bottomStackSwitcher)
        self.addBottomWidget(tasksWidget,
                             QtGui.QIcon(os.path.join("Resources", "images", "issue")), _("Tasks"))

        self.addBottomWidget(self.messagesWidget,
                             QtGui.QIcon(os.path.join("Resources", "images", "speech_bubble")), _("Messages"))

        self.profiler = Profiler(self.useData, self.bottomStackSwitcher)
        self.addBottomWidget(self.profiler,
                             QtGui.QIcon(os.path.join("Resources", "images", "settings")), _("Profiler"))
        self.runWidget.loadProfile.connect(
            self.profiler.viewProfile)

        self.addBottomWidget(self.findInFiles,
                             QtGui.QIcon(os.path.join("Resources", "images", "attibutes")), _("Find-in-Files"))

        # ── Ollama Manager as last tab ──
        self.ollamaManager = OllamaManager(self.bottomStackSwitcher)
        self.addBottomWidget(self.ollamaManager,
                             QtGui.QIcon(os.path.join("Resources", "images", "lightning")), _("Ollama"))
        print("[DEBUG] OllamaManager added to bottom panel as last tab")

        # Disable the default first-button highlight — AI Panel is set as current below
        self.bottomStackSwitcher.setDefault()
        # Default to AIPanel (AI Assistant) on startup. Only switch to Output (Run/Kimenet) when it gets active content (see RunWidget).
        self.bottomStackSwitcher.setCurrentWidget(self.aiPanel)

        # Note: bottom switcher + stack are placed inside the "Bottom Panel" dock (see dock creation below).
        # The statusbar is set via self.setStatusBar() above. No need for the old mainLayout hbox.

        self.uptime = 0
        self.uptimeTimer = QtCore.QTimer()
        self.uptimeTimer.setInterval(60000)
        self.uptimeTimer.timeout.connect(self.updateUptime)
        self.uptimeTimer.start()

        # remember layout (legacy splitter states from before dock refactor;
        # wrapped to avoid crashes on old saved data that doesn't match current
        # number of sections in the (now mostly unused for layout) splitters)
        # We relax the OPENED_PROJECTS guard (same reason as for dockstate):
        # on first open in a session the project may not be in the list yet when
        # EditorWindow is constructed, causing saved sizes not to be applied.
        settings = QtCore.QSettings("PyCoder", "PyCoder")
        settings.beginGroup(projectPathDict['root'])
        try:
            self.hSplitter.restoreState(settings.value('hsplitter'))
            self.vSplitter.restoreState(settings.value('vsplitter'))
            self.sideSplitter.restoreState(
                settings.value('sidesplitter'))
            self.vSplitter.updateStatus()
            self.writePad.setGeometry(settings.value('writepad'))
        except Exception:
            pass  # old layout data incompatible with new dock-based structure; ignore
        settings.endGroup()

        self.setKeymap()

    def resizeView(self, hview, vview):
        hSizes = self.hSplitter.sizes()
        vSizes = self.vSplitter.sizes()
        if len(hSizes) >= 2:
            if hview == 1:
                self.hSplitter.setSizes([hSizes[0] + 2, hSizes[1] - 2])
            elif hview == -1:
                self.hSplitter.setSizes([hSizes[0] - 2, hSizes[1] + 2])

        if len(vSizes) >= 2:
            if vview == 1:
                self.vSplitter.setSizes([vSizes[0] + 2, vSizes[1] - 2])
            elif vview == -1:
                self.vSplitter.setSizes([vSizes[0] - 2, vSizes[1] + 2])

    def createActions(self):
        self.gotoLineAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "mail_check")),
                _("Goto Line"), self,
                statusTip=_("Goto Line"), triggered=self.showGotoLineWidget)
        self.gotoLineAct.setToolTip(_("Can enter a number and it will jump to there"))

        self.viewSwitcherAct = QtGui.QAction(
            _("Switch Views"), self, statusTip=_("Switch to Overview/Diff View"),
            triggered=self.showSnapShotSwitcher)
        self.viewSwitcherAct.setToolTip(_("Open a switch bar to switch between Overview/Diff View"))

        self.exitAct = \
            QtGui.QAction(_("Exit"), self, statusTip=_("Exit the application"),
                          triggered=self.projects.closeProgram)
        self.exitAct.setToolTip(_("Finish work and close the PyCoder6"))

        # Menubar Actions ----------------------------------------------------

        self.userGuideAct = QtGui.QAction(
            _("User Guide"), self, statusTip=_("User Guide of Application"),
                                         triggered=self.launchHelp)
        self.userGuideAct.setToolTip(_("User Guide of Application.."))

        self.pythonManualsAct = QtGui.QAction(_("Python Manuals"), self,
                                              statusTip=_("Open the Python Manuals"),
                                              triggered=self.launchPythonHelp)
        self.pythonManualsAct.setToolTip(_("Open Python manuals if installed on your system"))

        self.checkUpdatesAct = QtGui.QAction(_("Check For Updates"), self,
                                             statusTip=_("Check For Updates"),
                                             triggered=self.visitHomepage)
        self.checkUpdatesAct.setToolTip(_("Check the PyCoder6 updates"))

        self.feedbackAct = QtGui.QAction(_("Send Feedback"), self,
                                         statusTip=_("Send Feedback"),
                                        triggered=self.openFeedbackLink)
        self.feedbackAct.setToolTip(_("Finish work and close the PyCoder6"))

        #----------------------------------------------------------------------
        self.runFileAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "rerun")),
            _("Run File"), self, triggered=self.runFile)
        self.runFileAct.setToolTip(_("Run current file only"))

        self.runProjectAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "run")),
            _("Run Project"), self,
            statusTip=_("Run The Full Project"), triggered=self.runProject)
        self.runProjectAct.setToolTip(_("Run the full project.."))

        self.stopRunAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "stop")),
            _("Stop"), self,
            statusTip=_("Stop execution"),triggered=self.stopProcess)
        self.stopRunAct.setToolTip(_("Press stop to finish current execution.."))

        self.runParamAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "shell")),
            _("Set Run"), self,
            statusTip=_("Set Run Parameters"), triggered=self.setRunParameters)
        self.runParamAct.setToolTip(_("Set parameters for run. Debug level, etc."))

        #---------------------------------------------------------------------

        self.finderAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "scope")),
            _("Find"), self,
            statusTip=_("Find files or content"), triggered=self.showFinderWidget)
        self.finderAct.setToolTip(_("Find files or content"))

        self.replaceAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "edit-replace")),
                _("Replace"), self,
                statusTip=_("Replace"),
                          triggered=self.showReplaceWidget)
        self.replaceAct.setToolTip(_("Replace a pattern to another"))

        self.findInFilesAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "find_in_files")),
            _("Find-in-Files"), self,
            statusTip=_("A pattern find-in-files"), triggered=self.showFindInFilesWidget)
        self.findInFilesAct.setToolTip(_("A pattern find-in-files"))

        self.addToLibraryAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "add")),
                _("Add To Library"), self,
                statusTip=_("Add current module to Library"),
                          triggered=self.addToLibrary)
        self.addToLibraryAct.setToolTip(_("Add current module to Library"))

        self.clearRecentFilesAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "clear")),
                _("Clear History"), self, statusTip=_("Clear History"),
                triggered=self.clearRecentFiles)
        self.clearRecentFilesAct.setToolTip(_("Clear History"))

        self.writePadAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "pencil")),
                _("Writepad"), self, statusTip=_("Open internal Writepad"),
                triggered=self.showWritePad)
        self.writePadAct.setToolTip(_("Open internal WritePad"))

        self.buildAct = \
            QtGui.QAction(
                _("Build"), self,
                statusTip=_("Build project to binary"),
                triggered=self.buildProject)
        self.buildAct.setToolTip(_("Build this project to static binary"))

        self.openBuildAct = \
            QtGui.QAction(
                _("Open Build"), self, statusTip=_("Open Build Folder"),
                triggered=self.openBuild)
        self.finderAct.setToolTip(_("Open the build folder where placed binary of project"))

        self.configureAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "settings")),
                _("Configuration"), self, statusTip=_("Open Configuration"),
                triggered=self.showProjectConfiguration)
        self.finderAct.setToolTip(_("Open Configuration Dialog"))

        self.exportProjectAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "archive")),
                _("Export as Zip..."), self, statusTip=_("Project Export as Zip"),
                triggered=self.exportProject)
        self.finderAct.setToolTip(_("Export full project as a zip file..."))

        self.closeProjectAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "inbox--minus")),
                _("Close Project"), self, statusTip=_("Close this project"),
                triggered=self.closeProject)
        self.finderAct.setToolTip(_("It only closes the project, files won't be deleted."))

    def visitHomepage(self):
        QtGui.QDesktopServices().openUrl(QtCore.QUrl(
            """https://github.com/blackPantherOS/PyCoder"""))

    def showProjectConfiguration(self):
        self.editorTabWidget.showProjectConfiguration()

    def buildProject(self):
        self.projectManager.buildProject()

    def openBuild(self):
        self.projectManager.openBuild()

    def exportProject(self):
        self.projectManager.exportProject()

    def closeProject(self):
        self.projects.closeProject()

    def updateEncodingLabel(self, text):
        self.encodingLabel.setText(text)

    def showGotoLineWidget(self):
        self.editorTabWidget.showGotoLineWidget()

    def showSnapShotSwitcher(self):
        self.editorTabWidget.showSnapShotSwitcher()

    def addBottomWidget(self, widget, icon, name):
        self.bottomStack.addWidget(widget)
        self.bottomStackSwitcher.addButton(toolTip=name, icon=icon)

    def showWritePad(self):
        self.writePad.show()

    def showFinderWidget(self):
        self.findInFiles.dashboard.hide()
        self.searchWidget.showFinder()

    def showReplaceWidget(self):
        self.findInFiles.dashboard.hide()
        self.searchWidget.showReplaceWidget()

    def showFindInFilesWidget(self):
        self.searchWidget.hide()
        self.findInFiles.dashboard.show()

    def _find_editor_widget(self, widget):
        """Recursively find an editor widget with text() method"""
        if hasattr(widget, 'text'):
            return widget

        # Check if it's a stacked widget and get current widget
        if isinstance(widget, QtWidgets.QStackedWidget):
            current = widget.currentWidget()
            if current and hasattr(current, 'text'):
                return current
            elif current:
                return self._find_editor_widget(current)

        # Check children
        for child in widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'text'):
                return child
            # Recursively check grandchildren
            result = self._find_editor_widget(child)
            if result:
                return result

        return None

    def updateAIPanelEditor(self):
        """Update AI panel with current editor"""
        current_editor = self.editorTabWidget.currentWidget()
        if current_editor:
            # Try to find the actual editor widget
            editor_widget = self._find_editor_widget(current_editor)
            if editor_widget:
                self.aiPanel.set_editor(editor_widget)
            else:
                self.aiPanel.set_editor(None)
        else:
            self.aiPanel.set_editor(None)

    def createToolbars(self):

        self.editorMenuButton = QtWidgets.QToolButton()
        self.editorMenuButton.setText(_("Menu"))
        self.editorMenuButton.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.editorMenuButton.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonFollowStyle)
        self.editorMenuButton.setAutoRaise(True)
        self.editorMenuButton.setArrowType(QtCore.Qt.ArrowType.UpArrow)
        self.editorMenuButton.setObjectName("toolButton")

        self.editorMenuButton.setIcon(QtGui.QIcon(
            os.path.join("Resources", "images", "Dashboard")))
        self.editorMenuButton.setMenu(self.mainMenu)

        self.standardToolbar.addWidget(self.editorMenuButton)
        self.standardToolbar.addAction(self.editorTabWidget.openFileAct)
        self.standardToolbar.addAction(self.editorTabWidget.newPythonFileAct)

        self.standardToolbar.addSeparator()
        self.standardToolbar.addAction(self.editorTabWidget.saveAct)
        self.standardToolbar.addAction(self.editorTabWidget.saveAllAct)

        self.standardToolbar.addSeparator()
        self.standardToolbar.addAction(self.editorTabWidget.undoAct)
        self.editorTabWidget.undoAct.setDisabled(True)
        self.standardToolbar.addAction(self.editorTabWidget.redoAct)
        self.editorTabWidget.redoAct.setDisabled(True)

        self.standardToolbar.addSeparator()
        self.standardToolbar.addAction(self.runFileAct)
        self.standardToolbar.addAction(self.runProjectAct)
        self.standardToolbar.addAction(self.stopRunAct)
        self.stopRunAct.setVisible(False)
        self.standardToolbar.addAction(self.runParamAct)

        self.standardToolbar.addSeparator()
        self.standardToolbar.addAction(self.editorTabWidget.dedentAct)
        self.standardToolbar.addAction(self.editorTabWidget.indentAct)

        self.standardToolbar.addAction(self.finderAct)
        self.standardToolbar.addAction(self.replaceAct)
        self.standardToolbar.addAction(self.findInFilesAct)
        self.standardToolbar.addSeparator()
        self.standardToolbar.addAction(self.addToLibraryAct)
        self.standardToolbar.addAction(self.writePadAct)

        self.standardToolbar.addSeparator()
        self.standardToolbar.addAction(self.editorTabWidget.cutAct)
        self.editorTabWidget.cutAct.setDisabled(True)
        self.standardToolbar.addAction(self.editorTabWidget.copyAct)
        self.editorTabWidget.copyAct.setDisabled(True)
        self.standardToolbar.addAction(self.editorTabWidget.pasteAct)

        self.bookmarkToolbar.addAction(
            self.editorTabWidget.findNextBookmarkAct)
        self.bookmarkToolbar.addAction(
            self.editorTabWidget.findPrevBookmarkAct)
        self.bookmarkToolbar.addAction(self.editorTabWidget.removeBookmarksAct)
        self.standardToolbar.addWidget(self.bookmarkToolbar)

    def recentFileActivated(self, action):
        path = action.text().split('  ', 1)[1]
        if os.path.exists(path):
            self.editorTabWidget.loadfile(path)
        else:
            message = QtWidgets.QMessageBox.warning(self, _("Open"),
                                                _("File is unavailable!"))

    def loadRecentFiles(self):
        if len(self.projectData['recentfiles']) > 0:
            self.recentFile_actionGroup = QtGui.QActionGroup(self)
            self.recentFile_actionGroup.triggered.connect(
                self.recentFileActivated)
            self.recentFilesMenu.clear()
            c = 1
            for i in self.projectData['recentfiles']:
                action = QtGui.QAction(str(c) + '  ' + i, self)
                self.recentFile_actionGroup.addAction(action)
                self.recentFilesMenu.addAction(action)
                c += 1
            self.recentFilesMenu.addSeparator()
            self.recentFilesMenu.addAction(self.clearRecentFilesAct)
        else:
            self.recentFilesMenu.addAction(_("No Recent Files"))

    def updateRecentFiles(self, filePath):
        if filePath in self.projectData['recentfiles']:
            self.projectData['recentfiles'].remove(filePath)
            self.projectData['recentfiles'].insert(0, filePath)
        else:
            if len(self.projectData['recentfiles']) < 15:
                self.projectData['recentfiles'].insert(0, filePath)
            else:
                del self.projectData['recentfiles'][-1]
                self.projectData['recentfiles'].insert(0, filePath)
        self.loadRecentFiles()

    def clearRecentFiles(self):
        self.projectData['recentfiles'] = []
        self.recentFilesMenu.clear()
        self.loadRecentFiles()
        self.messagesWidget.addMessage(0, _('Recent Files:'),
                                       [_("Recent files history has been cleared!")])

    def addToLibrary(self):
        self.library.addToLibrary(self.editorTabWidget)

    def openFeedbackLink(self):
        QtGui.QDesktopServices().openUrl(QtCore.QUrl(
            """https://github.com/blackPantherOS/PyCoder/issues"""))

    def updateUptime(self):
        self.uptime += 1
        if self.uptime == 60:
            new_time = "1hr"
        elif self.uptime > 60:
            t = int(str(self.uptime / 60).split('.')[0])
            h = str(t) + "hr"
            m = str(self.uptime - (t * 60)) + _("min")
            new_time = h + m
        else:
            new_time = str(self.uptime) + _("min")
        self.uptimeLabel.setText(_("Uptime: ") + new_time)

    def saveAll(self):
        self.editorTabWidget.saveAll()

    def fileUrl(self, fname):
        """Select the right file url scheme according to the operating system"""
        if os.name == 'nt':
            # Local file
            if re.search(r'^[a-zA-Z]:', fname):
                return 'file:///' + fname
            # UNC based path
            else:
                return 'file://' + fname
        else:
            return 'file://' + fname

    def getPythonDocPath(self):
        """
        Return Python documentation path
        (Windows: return the PythonXX.chm path if available)
        """
        if os.name == 'nt':
            path = os.path.dirname(
                self.projectData['settings']["DefaultInterpreter"])
            doc_path = os.path.join(path, "Doc")
            if not os.path.isdir(doc_path):
                return
            python_chm = [path for path in os.listdir(doc_path)
                          if re.match(r"(?i)Python[0-9]{3}.chm", path)]
            if python_chm:
                return self.fileUrl(os.path.join(doc_path, python_chm[0]))
        else:
            vinf = sys.version_info
            doc_path = '/usr/share/doc/python%d.%d/html' % (vinf[0], vinf[1])
        python_doc = os.path.join(doc_path, "index.html")
        if os.path.isfile(python_doc):
            return self.fileUrl(python_doc)

    def launchHelp(self):
        message = QtWidgets.QMessageBox.warning(
            self, _("User Guide"), _("Will be available when i am out of beta."))

    def launchPythonHelp(self):
        try:
            doc_path = self.getPythonDocPath()
            os.startfile(doc_path)
        except Exception as err:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.error(repr(traceback.format_exception(exc_type, exc_value,
                         exc_traceback)))
            message = QtWidgets.QMessageBox.critical(self, _("Python Manuals"),
                                                 (_("Failed to launch the Python Manuals!\n\n"
                                                  "It is either not available for the current python "
                                                  "version or Python is not installed in your system.")))

    def setRunParameters(self):
        self.editorTabWidget.showSetRunParameters()

    def runFile(self):
        self.runWidget.runFile()

    def runProject(self):
        self.runWidget.runProject()

    def stopProcess(self):
        self.runWidget.stopProcess()

    def showPythonInterpreter(self):
        process = QtCore.QProcess()
        process.startDetached(self.useData.SETTINGS["DefaultInterpreter"])

    def showCommandPrompt(self):
        prompt = os.environ["COMSPEC"]
        process = QtCore.QProcess()
        process.startDetached(prompt, [], QtCore.QDir().rootPath())

    def showCursorPosition(self):
        line, index = self.editorTabWidget.currentEditor.getCursorPosition()
        self.cursorPositionButton.setText(
            _("Line {0} : Column {1}").format(line + 1, index + 1))

    def updateLineCount(self, lines):
        self.linesLabel.setText(_("Lines: ") + str(lines))

    def saveUiState(self):
        name = self.projectPathDict["root"]
        settings = QtCore.QSettings("PyCoder", "PyCoder")
        settings.beginGroup(name)
        settings.setValue('hsplitter', self.hSplitter.saveState())
        settings.setValue('vsplitter', self.vSplitter.saveState())
        settings.setValue('sidesplitter', self.sideSplitter.saveState())
        settings.setValue('writepad', self.writePad.geometry())
        # Save the user's dock layout (new dockable panels: project region + bottom panel)
        settings.setValue('dockstate', self.saveState())
        settings.endGroup()

        # Persist the current open tabs (the "last opened files") as well when
        # saving UI state on project switch. This fixes the regression where
        # tabs were not restored on re-open (restoreSession only saw stale/empty
        # session file because save only happened on full project close before).
        try:
            self.editorTabWidget.saveSession()
        except Exception:
            pass

    def _restoreDockLayout(self):
        """Restore the user's dock layout (sizes, positions, floating state etc.)
        for the project region and bottom panel docks.
        Called via QTimer.singleShot(0) so that the parent layout (the stacked
        projectWindowStack inside the outer QMainWindow) has already assigned
        our final size. This is required for restoreState to correctly apply
        the saved relative dock widths/heights instead of defaults.

        We always attempt dock restore if a saved 'dockstate' exists (even on
        first open in the session), because the previous guard on OPENED_PROJECTS
        prevented saved layouts from being applied for newly opened projects.
        """
        settings = QtCore.QSettings("PyCoder", "PyCoder")
        settings.beginGroup(self.projectPathDict['root'])
        restored_something = False
        try:
            dock_state = settings.value('dockstate')
            if dock_state:
                self._docks_restoring = True
                try:
                    self.restoreState(dock_state)
                    restored_something = True
                    # Re-apply movability etc. after restoreState. Some Qt versions
                    # or complex parent layouts (QStackedWidget) can leave docks
                    # in a temporarily non-interactive state.
                    self.projectDock.setFeatures(
                        QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
                        QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                        QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
                    )
                    self.bottomDock.setFeatures(
                        QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
                        QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                        QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
                    )
                finally:
                    self._docks_restoring = False
            # Mark as restored (so showEvent doesn't keep re-trying).
            # Even if there was no saved state, the initial addDockWidget
            # calls in __init__ set up the default layout we want.
            self._docks_restored = True
        except Exception:
            self._docks_restoring = False
            # Still mark done to avoid repeated attempts
            self._docks_restored = True
            pass
        settings.endGroup()

        # Post-restore sanity for our main panels.
        # If after restoreState a panel has no dock area (e.g. it was "closed"
        # in an old saved state from before we made X mean "return to main"),
        # force it into its home area. This ensures the panels are always
        # usable and movable, without overriding user-saved positions/sizes
        # when the saved state did include them.
        for dock, home_area in [
            (self.projectDock, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea),
            (self.bottomDock, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea),
        ]:
            if self.dockWidgetArea(dock) == QtCore.Qt.DockWidgetArea.NoDockWidgetArea:
                self.addDockWidget(home_area, dock)
                dock.setVisible(True)
                dock.setFloating(False)
                dock.setFeatures(
                    QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
                    QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                    QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
                )

        return restored_something

    def eventFilter(self, obj, event):
        """Intercept Close events on our docks.
        This implements the user's request: clicking the X on a "kidokkolt" panel
        (Project Region or Tools Panel) does not actually close/hide it.
        Instead we immediately put it back ("tegye vissza") into the main window
        docked at its home area.

        Using Close event (instead of visibilityChanged) is much less noisy.
        visibilityChanged fires on every show/hide during restore, window show,
        internal tab switches, etc. That was causing constant addDockWidget calls
        which locked the docks (regression in movability and restore).

        Close event only fires on actual user X click (or programmatic close()).
        We consume the event so the dock doesn't hide, then force re-dock.
        """
        if event.type() == QtCore.QEvent.Type.Close:
            if obj is self.projectDock or obj is self.bottomDock:
                # Consume the close so it doesn't hide/remove the dock from layout.
                event.accept()
                # Defer the re-dock to let Qt finish the current close attempt cleanly.
                QtCore.QTimer.singleShot(0, lambda d=obj: self._forceRedockDockToMainWindow(d))
                return True  # event filtered
        return super().eventFilter(obj, event)

    def _forceRedockDockToMainWindow(self, dock):
        """Safely force a dock (that the user tried to close with X) back into
        the main EditorWindow layout at its "home" area.
        Called via singleShot(0) to avoid recursion and dock state issues.
        """
        if dock is self.projectDock:
            area = QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
        elif dock is self.bottomDock:
            area = QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
        else:
            return

        try:
            # Block signals during the forced re-dock to prevent any
            # secondary visibilityChanged emissions from re-triggering logic.
            dock.blockSignals(True)
            dock.setFloating(False)
            dock.setVisible(True)
            self.addDockWidget(area, dock)
            # Re-apply features after re-docking (defensive).
            dock.setFeatures(
                QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
                QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
        finally:
            dock.blockSignals(False)

    def showEvent(self, event):
        """Ensure dock layout is restored once we have real geometry.
        The deferred singleShot in __init__ may run before this EditorWindow
        is the current widget in the outer QStackedWidget or before the outer
        window has final size. Retrying on first show fixes "default layout only"
        and "docks not movable" symptoms for many users.
        """
        super().showEvent(event)
        if not getattr(self, '_docks_restored', False):
            # One more deferred attempt now that we are visible.
            QtCore.QTimer.singleShot(0, self._tryRestoreDocksOnce)

    def _tryRestoreDocksOnce(self):
        """Wrapper so we only attempt restore once from showEvent path."""
        if not getattr(self, '_docks_restored', False):
            self._restoreDockLayout()
            # If there was no saved state, still mark as done so we don't
            # keep trying on every show.
            self._docks_restored = True

    def restoreSession(self):
        self.editorTabWidget.restoreSession()

    def closeWindow(self):
        if self.runWidget.currentProcess is not None:
            mess = _("Close running program?")
            reply = QtWidgets.QMessageBox.warning(self, _("Close"),
                                              mess, 
                                              QtWidgets.QMessageBox.StandardButton.Yes | 
                                              QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.runWidget.stopProcess()
            else:
                return False
        modified = []
        for i in range(self.editorTabWidget.count()):
            if self.editorTabWidget.getEditor(i).isModified():
                modified.append(i)
        if len(modified) == 0:
            pass
        else:
            for i in range(len(modified)):
                v = modified.pop(-1)
                self.editorTabWidget.setCurrentIndex(v)
                mess = _('Save changes to "{0}"?').format(
                    self.editorTabWidget.tabText(v))
                reply = QtWidgets.QMessageBox.warning(self, _("Close"), mess,
                                                  QtWidgets.QMessageBox.StandardButton.Yes | 
                                                  QtWidgets.QMessageBox.StandardButton.No |
                                                  QtWidgets.QMessageBox.StandardButton.Cancel)
                if reply == QtWidgets.QMessageBox.StandardButton.No:
                    if len(modified) == 0:
                        pass
                elif reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    saved = self.editorTabWidget.save()
                    if saved:
                        pass
                    else:
                        return False
                elif reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                    return False
        self.saveUiState()
        self.editorTabWidget.saveSession()
        self.projectData["settings"]["Closed"] = "True"
        self.saveProjectData()
        self.editorTabWidget.refactor.closeRope()

        return True

    def loadProjectData(self):
        # QtXml migration: use ElementTree for legacy projectdata.xml
        projectdata_path = os.path.join(self.projectPathDict["root"], "Data", "projectdata.xml")
        try:
            tree = ET.parse(projectdata_path)
            root = tree.getroot()
        except Exception as e:
            print("Failed to parse projectdata.xml:", e)
            self.projectData = {
                "shortcuts": [],
                "favourites": [],
                "recentfiles": [],
                "settings": {"LastCloseSuccessful": "True", "Closed": "False"},
                "launchers": {}
            }
            return

        shortcuts = []
        recentfiles = []
        favourites = []
        launchers = {}
        settingsList = []

        for child in root:
            tag = child.tag
            if tag == "shortcuts":
                for item in child:
                    if item.text:
                        shortcuts.append(item.text)
            elif tag == "recentfiles":
                for item in child:
                    p = item.text or ""
                    if os.path.exists(p):
                        recentfiles.append(p)
            elif tag == "favourites":
                for item in child:
                    if item.text:
                        favourites.append(item.text)
            elif tag == "settings":
                for item in child:
                    text = item.text or ""
                    if "=" in text:
                        settingsList.append(tuple(text.split("=", 1)))
            elif tag == "launchers":
                for item in child:
                    path = item.get("path", "")
                    param = item.get("param", "")
                    if path:
                        launchers[path] = param

        settingsDict = dict(settingsList)
        settingsDict['LastCloseSuccessful'] = settingsDict.get('Closed', 'True')
        settingsDict['Closed'] = "False"

        self.projectData = {}
        self.projectData["shortcuts"] = shortcuts
        self.projectData["favourites"] = favourites
        self.projectData["recentfiles"] = recentfiles
        self.projectData["settings"] = settingsDict
        self.projectData["launchers"] = launchers

        # in order that a crash can be reported
        self.saveProjectData()

    def saveProjectData(self):
        # QtXml migration: use ElementTree to write projectdata.xml (keep format for compatibility)
        root = ET.Element("projectdata")

        # shortcuts
        shortcuts_elem = ET.SubElement(root, "shortcuts")
        for i in self.projectData.get('shortcuts', []):
            tag = ET.SubElement(shortcuts_elem, "shortcut")
            tag.text = i

        # recentfiles
        recent_elem = ET.SubElement(root, "recentfiles")
        for i in self.projectData.get('recentfiles', []):
            tag = ET.SubElement(recent_elem, "recent")
            tag.text = i

        # favourites
        fav_elem = ET.SubElement(root, "favourites")
        for i in self.projectData.get('favourites', []):
            tag = ET.SubElement(fav_elem, "fav")
            tag.text = i

        # launchers
        launch_elem = ET.SubElement(root, "launchers")
        for path, param in self.projectData.get('launchers', {}).items():
            tag = ET.SubElement(launch_elem, "item")
            tag.set("path", path)
            tag.set("param", param)

        # settings
        settings_elem = ET.SubElement(root, "settings")
        for key, value in self.projectData.get('settings', {}).items():
            tag = ET.SubElement(settings_elem, "key")
            tag.text = f"{key}={value}"

        path = os.path.join(self.projectPathDict["root"], "Data", "projectdata.xml")
        try:
            tree = ET.ElementTree(root)
            tree.write(path, encoding="UTF-8", xml_declaration=True)
        except Exception as e:
            print("Failed to save projectdata.xml with ET:", e)

    def setKeymap(self):
        shortcuts = self.useData.CUSTOM_SHORTCUTS

        self.shortGotoLine = QtGui.QShortcut(
            shortcuts["Ide"]["Go-to-Line"], self)
        self.shortGotoLine.activatedAmbiguously.connect(
            self.showGotoLineWidget)
        self.gotoLineAct.setShortcut(shortcuts["Ide"]["Go-to-Line"])

        self.shortBuild = QtGui.QShortcut(shortcuts["Ide"]["Build"], self)
        self.shortBuild.activatedAmbiguously.connect(self.buildProject)
        self.buildAct.setShortcut(shortcuts["Ide"]["Build"])

        self.shortFind = QtGui.QShortcut(shortcuts["Ide"]["Find"], self)
        self.shortFind.activated.connect(self.showFinderWidget)

        self.shortReplace = QtGui.QShortcut(
            shortcuts["Ide"]["Replace"], self)
        self.shortReplace.activated.connect(self.showReplaceWidget)

        self.shortRunFile = QtGui.QShortcut(
            shortcuts["Ide"]["Run-File"], self)
        self.shortRunFile.activated.connect(self.runFile)

        self.shortRunProject = QtGui.QShortcut(
            shortcuts["Ide"]["Run-Project"], self)
        self.shortRunProject.activated.connect(self.runProject)

        self.shortStopRun = QtGui.QShortcut(
            shortcuts["Ide"]["Stop-Execution"], self)
        self.shortStopRun.activated.connect(self.stopProcess)

        self.shortPythonManuals = QtGui.QShortcut(
            shortcuts["Ide"]["Python-Manuals"], self)
        self.shortPythonManuals.activatedAmbiguously.connect(
            self.launchPythonHelp)
        self.pythonManualsAct.setShortcut(
            shortcuts["Ide"]["Python-Manuals"])
