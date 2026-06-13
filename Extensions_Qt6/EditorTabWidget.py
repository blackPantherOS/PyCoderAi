import os
import sys
import ctypes
import time
import traceback
import logging

import json
import xml.etree.ElementTree as ET

from PyQt6 import QtCore, QtGui, QtPrintSupport, QtWidgets

# QtXml cleanup in progress for session data.
from PyQt6.Qsci import QsciScintilla

from Extensions_Qt6.Diff import DiffWindow
from Extensions_Qt6.CodeEditor import CodeEditor
from Extensions_Qt6.TextEditor import TextEditor
from Extensions_Qt6.ViewSwitcher import ViewSwitcher
from Extensions_Qt6.TextSnapshot import TextSnapshot
from Extensions_Qt6.CodeSnapshot import CodeSnapshot
from Extensions_Qt6.GotoLineWidget import GotoLineWidget
from Extensions_Qt6.EditorSplitter import EditorSplitter
from Extensions_Qt6 import Global
from Extensions_Qt6.Refactor.Refactor import Refactor
from Extensions_Qt6.BottomWidgets.RunWidget import SetRunParameters
from Extensions_Qt6.Projects.ProjectManager.ConfigureProject import ConfigureProject
from Extensions_Qt6 import StyleSheet

import locale
import gettext
gettext.install("pycoder6", 'locales')

class EditorTabBar(QtWidgets.QTabBar):

    def __init__(self, app, renameFileAct,
                 moduleToPackageAct, parent):
        QtWidgets.QTabBar.__init__(self, parent)

        self.setExpanding(True)
        self.setDrawBase(False)

        self.editorTabWidget = parent
        self.app = app
        self.renameFileAct = renameFileAct
        self.moduleToPackageAct = moduleToPackageAct

        self.createActions()


    def setKeymap(self):
        shortcuts = self.editorTabWidget.useData.CUSTOM_SHORTCUTS

        self.shortSplitFileReload = QtGui.QShortcut(
            shortcuts["Ide"]["Reload-File"], self)
        self.shortSplitFileReload.activated.connect(
            self.reload)
        self.reloadTabAct.setShortcut(shortcuts["Ide"]["Reload-File"])

    def contextMenuEvent(self, event):
        filePath = self.editorTabWidget.getEditorData('filePath')
        isProjectFile = self.editorTabWidget.isProjectFile(filePath)

        isPyFile = (self.editorTabWidget.getEditorData("fileType") == "python")
        self.cloneTabAct.setEnabled(isPyFile)
        if isProjectFile:
            self.moduleToPackageAct.setEnabled(isPyFile)
            self.renameFileAct.setEnabled(isPyFile)
        else:
            self.moduleToPackageAct.setEnabled(False)
            self.renameFileAct.setEnabled(False)

        state = (filePath is not None)
        self.copyPathAct.setEnabled(state)
        self.openFileLocationAct.setEnabled(state)
        self.favouritesAct.setEnabled(state)
        self.reloadTabAct.setEnabled(state)

        self.menu.exec(event.globalPos())

    def createActions(self):
        self.closeTabAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "cross_")),
            _("Close"), self, statusTip=_("Close Tab"), triggered=self.closeTab)

        self.copyPathAct = QtGui.QAction(_("Copy File Path"), self,
                                         statusTip=_("Copy Selected File Path"),
                                         triggered=self.copyPath)

        self.openFileLocationAct = \
            QtGui.QAction(
                _("Open File Location"), self, statusTip=_("Open File Location"),
                triggered=self.openFileLocation)

        self.cloneTabAct = \
            QtGui.QAction(
                _("Clone"), self, statusTip=_("Create a copy of current tab"),
                triggered=self.cloneTab)

        self.reloadTabAct = \
            QtGui.QAction(
                _("Reload"), self, statusTip=_("Reload"),
                triggered=self.reload)

        self.favouritesAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "plus")),
                _("Add to Favourites"), self,
                statusTip=_("Add to Favourites"),
                          triggered=self.editorTabWidget.addToFavourites)

        self.menu = QtWidgets.QMenu(self)
        self.menu.addAction(self.closeTabAct)
        self.menu.addSeparator()
        self.menu.addAction(self.cloneTabAct)
        self.menu.addAction(self.editorTabWidget.writeLockAct)
        self.moduleToPackageAct = self.moduleToPackageAct
        self.menu.addAction(self.moduleToPackageAct)
        self.renameFileAct = self.renameFileAct
        self.menu.addAction(self.reloadTabAct)
        self.menu.addAction(self.renameFileAct)
        self.menu.addSeparator()
        self.menu.addAction(self.copyPathAct)
        self.menu.addAction(self.openFileLocationAct)
        self.menu.addSeparator()
        self.menu.addAction(self.favouritesAct)

    def reload(self):
        reply = QtWidgets.QMessageBox.warning(self, _("Reload"),
                                          _("Do you really want to reload?"),
                                          QtWidgets.QMessageBox.StandardButton.Yes | 
                                          QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.editorTabWidget.reloadModules()
        else:
            return

    def closeTab(self):
        index = self.currentIndex()
        self.editorTabWidget.closeEditorTab(index)

    def copyPath(self):
        filePath = self.editorTabWidget.getEditorData('filePath')
        cb = self.app.clipboard()
        cb.setText(filePath)

    def openFileLocation(self):
        filePath = self.editorTabWidget.getEditorData('filePath')
        if sys.platform.startswith('win'):
            ctypes.windll.shell32.ShellExecuteW(None, 'open', 'explorer.exe',
                                        '/n,/select, ' + filePath, None, 1)
        else:
            if subprocess.run(['which', 'qdbus'], stdout=subprocess.PIPE).returncode == 0:
                subprocess.run(['qdbus', 'org.freedesktop.FileManager1', '/org/freedesktop/FileManager1', 'org.freedesktop.FileManager1.ShowItems', filePath, '""'])
            elif subprocess.run(['which', 'gdbus'], stdout=subprocess.PIPE).returncode == 0:
                subprocess.run(['gdbus', 'call', '-e', '-d', 'org.freedesktop.FileManager1', '-o', '/org/freedesktop/FileManager1', '-m', 'org.freedesktop.FileManager1.ShowItems', filePath, "''"])
            else:
                subprocess.run(['xdg-open', filePath])

    def cloneTab(self):
        index = self.currentIndex()
        name = self.tabText(index)
        new_index = index + 1
        subStack = self.editorTabWidget.newEditor(new_index, name)
        self.editorTabWidget.setCurrentIndex(new_index)
        self.editorTabWidget.updateTabName(new_index)
        editor = subStack.widget(0).widget(0)
        editor.setText(self.editorTabWidget.getEditor(index).text())

class EditorTabWidget(QtWidgets.QTabWidget):

    currentEditorTextChanged = QtCore.pyqtSignal()
    bookmarksChanged = QtCore.pyqtSignal()
    updateLinesCount = QtCore.pyqtSignal(int)
    updateRecentFilesList = QtCore.pyqtSignal(str)
    updateWindowTitle = QtCore.pyqtSignal(str)
    updateEncodingLabel = QtCore.pyqtSignal(str)
    cursorPositionChanged = QtCore.pyqtSignal()

    def __init__(
        self, useData, projectPathDict, projectSettings, messagesWidget, colorScheme, busyWidget, bookmarkToolbar,
            app, manageFavourites, externalLauncher, editorWindow, parent=None):
        QtWidgets.QTabWidget.__init__(self, parent)

        self.setElideMode(QtCore.Qt.TextElideMode.ElideRight)

        self.useData = useData
        self.projectPathDict = projectPathDict
        self.colorScheme = colorScheme
        self.messagesWidget = messagesWidget
        self.app = app
        self.busyWidget = busyWidget
        self.projectSettings = projectSettings
        self.bookmarkToolbar = bookmarkToolbar
        self.editorWindow = editorWindow


        self.toolWidgetList = []
        # backup keys are generated from the system time, but sometimes
        # tabs are loaded so fast they end up having same backup keys.
        # this variable is an int that will will be incremented for every
        # backup kry that is generated and will be used to prevent key
        # collision
        self.backupKeyDiferentiator = 0

        self.backupTimer = QtCore.QTimer()
        self.backupTimer.setSingleShot(False)
        self.backupTimer.setInterval(60000)
        self.backupTimer.timeout.connect(self.createBackup)

        self.configDialog = ConfigureProject(
            projectPathDict, projectSettings, useData, self)

        self.manageFavourites = manageFavourites
        self.manageFavourites.showMe.connect(self.showFavouritesManager)

        self.externalLauncher = externalLauncher
        self.externalLauncher.showMe.connect(self.showExternalLauncher)

        self.setRunParameters = SetRunParameters(
            self.projectSettings, self.projectPathDict, self.useData)

        self.refactor = Refactor(
            self, self.busyWidget, self)

        self.viewSwitcher = ViewSwitcher(self)
        self.gotoLineWidget = GotoLineWidget(self)

        self.mainLayout = QtWidgets.QVBoxLayout()
        self.setLayout(self.mainLayout)
        if self.useData.SETTINGS["UI"] == "Custom":
            self.adjustToStyleSheet(True)
        else:
            self.adjustToStyleSheet(False)

        self.topVBox = QtWidgets.QVBoxLayout()
        self.mainLayout.addLayout(self.topVBox)

        self.mainLayout.addStretch(1)

        self.addToolWidget(self.configDialog)
        self.addToolWidget(self.externalLauncher)
        self.addToolWidget(self.manageFavourites)
        self.addToolWidget(self.setRunParameters)
        self.addToolWidget(self.viewSwitcher)
        self.addToolWidget(self.gotoLineWidget)

        self.filesWatch = QtCore.QFileSystemWatcher()
        self.filesWatch.fileChanged.connect(self.fileChanged)

        self.createActions()

        self.tabBar = EditorTabBar(self.app,
                                   self.refactor.renameModuleAct,
                                   self.refactor.moduleToPackageAct, self)
        self.tabBar.setMovable(True)
        self.tabBar.setTabsClosable(True)

        self.openedTabsMenu = QtWidgets.QMenu()

        self.tabSelectButton = QtWidgets.QToolButton()
        self.tabSelectButton.setAutoRaise(True)
        self.tabSelectButton.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.DelayedPopup)
        self.tabSelectButton.setIcon(
            QtGui.QIcon(os.path.join("Resources", "images", "tile")))
        self.tabSelectButton.setMenu(self.openedTabsMenu)

        self.setTabBar(self.tabBar)
        self.setAcceptDrops(True)
        self.setUsesScrollButtons(True)
        self.setCornerWidget(self.tabSelectButton)
        self.currentChanged.connect(self.editorTabChanged)
        self.tabCloseRequested.connect(self.closeEditorTab)

        self.setKeymap()
        self.backupTimer.start()

        self.newFileMenu = QtWidgets.QMenu(_("New File"))
        self.newFileMenu.addAction(self.newPythonFileAct)
        self.newFileMenu.addAction(self.newXmlFileAct)
        self.newFileMenu.addAction(self.newHtmlFileAct)
        self.newFileMenu.addAction(self.newCssFileAct)

    def resizeView(self, hview, vview):
        self.editorWindow.resizeView(hview, vview)

    def adjustToStyleSheet(self, adjust):
        if adjust:
            self.mainLayout.setContentsMargins(0, 22, 14, 12)
        else:
            self.mainLayout.setContentsMargins(0, 24, 25, 12)

    def addToolWidget(self, widget):
        hbox = QtWidgets.QHBoxLayout()
        hbox.addStretch(1)
        hbox.addWidget(widget)
        self.topVBox.addLayout(hbox)

        self.toolWidgetList.append(widget)
        widget.hide()

    def createActions(self):
        self.undoAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "undo")),
            _("Undo"), self,
            statusTip=_("Undo last edit action"),
            triggered=self.undoAction)
        self.undoAct.setToolTip(_("Undo last edit action"))
        
        self.redoAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "redo")),
            _("Redo"), self,
            statusTip=_("Redo last edit action"),
            triggered=self.redoAction)
        self.redoAct.setToolTip(_("Reddo last edit action"))

        self.cutAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "cut")),
            _("Cut"), self,
            statusTip=_("Cut selected text"), triggered=self.cutItem)
        self.cutAct.setToolTip(_("Cut selected text"))

        self.copyAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "copy")),
            _("Copy"), self,
            statusTip=_("Copy selected text"), triggered=self.copyItem)
        self.copyAct.setToolTip(_("Copy selected text"))

        self.pasteAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "paste")),
            _("Paste"), self,
            statusTip=_("Paste text from clipboard"),
            triggered=self.pasteFromClipboard)
        self.pasteAct.setToolTip(_("Paste content from clipboard"))

        #----------------------------------------------------------------------

        self.indentAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "increase_indent")),
                _("Indent"), self,
                statusTip=_("Indent Region"),
                triggered=self.increaseIndent)
        self.indentAct.setToolTip(_("Indent Region"))

        self.dedentAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "decrease_indent")),
                _("Unindent"), self,
                statusTip=_("Unindent Region"),
                triggered=self.decreaseIndent)
        self.dedentAct.setToolTip(_("Unindent Region"))

        self.writeLockAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "block")),
                _("Write Lock"), self,
                statusTip=("Write Lock"),
                          triggered=self.writeLock)
        self.writeLockAct.setToolTip(_("Write lock to this tab"))

        self.findNextBookmarkAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "Arrow2-down")),
                _("Next Bookmark"), self, statusTip=_("Next Bookmark"),
                triggered=self.findNextBookmark)
        self.findNextBookmarkAct.setToolTip(_("Find Next Bookmark in this code"))

        self.findPrevBookmarkAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "Arrow2-up")),
                _("Previous Bookmark"), self, statusTip=_("Previous Bookmark"),
                triggered=self.findPreviousBookmark)
        self.findPrevBookmarkAct.setToolTip(_("Find Previous Bookmark in this code"))

        self.removeBookmarksAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "block__")),
                _("Remove Bookmarks"), self, statusTip=_("Remove Bookmarks"),
                triggered=self.removeBookmarks)
        self.removeBookmarksAct.setToolTip(_("Remove All Placed Bookmarks"))

        #---------------------------------------------------------------------

        self.newPythonFileAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "new")),
            _("New [.py]"), self,
            statusTip=_("Create a new python file"),
            triggered=self._newPythonFile)
        self.newPythonFileAct.setToolTip(_("Create a new python file"))

        self.newXmlFileAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "new")),
            "Xml", self,
            statusTip=_("Create a new Xml file"),
            triggered=self._newXmlFile)
        self.newXmlFileAct.setToolTip(_("Create a new Xml file"))

        self.newHtmlFileAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "new")),
            "Html", self,
            statusTip=_("Create a new Html file"),
            triggered=self._newHtmlFile)
        self.newHtmlFileAct.setToolTip(_("Create a new Html file"))

        self.newCssFileAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "new")),
            "Css", self,
            statusTip=_("Create a new Css file"),
            triggered=self._newCssFile)
        self.newCssFileAct.setToolTip(_("Create a new Css file"))

        self.openFileAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "open_file")),
                _("Open File..."), self,
                statusTip=_("Open python file"),
                          triggered=self.openFile)
        self.openFileAct.setToolTip(_("Open file to editing"))

        self.saveAct = QtGui.QAction(
            QtGui.QIcon(os.path.join("Resources", "images", "save_")),
            _("Save"), self,
            statusTip=_("Save file"), triggered=self._save)
        self.saveAct.setToolTip(_("Save current file"))

        self.saveAllAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "disks-black")),
                _("Save All"), self,
                statusTip=_("Save All Changes"),
                          triggered=self.saveAll)
        self.saveAllAct.setToolTip(_("Save All Changes in Current Project"))
        
        
        self.saveAsAct = QtGui.QAction(_("Save As..."), 
                                           self, statusTip=_("Save file as..."),
                                           triggered=self.saveAs)

        self.saveCopyAsAct = QtGui.QAction(_("Save Copy As..."), 
                                           self, statusTip=_("Save a Copy As..."), 
                                           triggered=self.saveCopyAs)

        self.printAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "_0013_Printer")),
                _("Print"), self,
                statusTip=_("Print the content"), triggered=self.printCode)
        #----------------------------------------------------------------------

        self.vSplitEditorAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "border-horizontal")),
                _("Split Vertical"), self,
                statusTip=_("View Split Vertical"), triggered=self.splitVertical)

        self.hSplitEditorAct = \
            QtGui.QAction(
                QtGui.QIcon(
                    os.path.join("Resources", "images", "border-vertical")),
                _("Split Horizontal"), self,
                statusTip=_("View Split Horizontal"), triggered=self.splitHorizontal)

        self.noSplitEditorAct = \
            QtGui.QAction(
                QtGui.QIcon(os.path.join("Resources", "images", "border")),
                _("Remove Split"), self,
                statusTip=_("Remove Editor Split"), triggered=self.removeSplit)

    def addToFavourites(self):
        path = self.getEditorData("filePath")
        self.manageFavourites.addToFavourites(path)

    def fileChanged(self, file):
        if os.path.exists(file):
            pass
        else:
            for i in range(self.count()):
                path = self.getEditorData("filePath", i)
                if path == file:
                    self.updateEditorData("filePath", None, i)
                    self.showNotification(
                        _("File renamed or moved."), i)
                    break

    def focusedEditor(self, index=None):
        if index is None:
            index = self.currentIndex()
        subStack = self.widget(index)
        return subStack.widget(0).getFocusedEditor()

    def getEditor(self, index=None):
        if index is None:
            index = self.currentIndex()
        subStack = self.widget(index)
        #vector return subStack.widget(0).getEditor(0)
        if subStack is not None:
            return subStack.widget(0).getEditor(0)
        else:
            return None

    def getCloneEditor(self, index=None):
        if index is None:
            index = self.currentIndex()
        if self.widget(index) is not None:
            return self.widget(index).widget(0).getEditor(1)
        else:
            return None

    def getSnapshot(self, index=None):
        if index is None:
            index = self.currentIndex()
        return self.widget(index).widget(1)

    def getUnifiedDiff(self, index=None):
        if index is None:
            index = self.currentIndex()
        return self.widget(index).widget(2)

    def getContextDiff(self, index=None):
        if index is None:
            index = self.currentIndex()
        return self.widget(index).widget(3)

    def clearMarkerAndIndicators(self):
        self.currentEditor.clearMarkerAndIndicators()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if os.path.isfile(urls[0].toLocalFile()):
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        mimeData = event.mimeData()
        if mimeData.hasUrls():
            urls = event.mimeData().urls()
            fname = urls[0].toLocalFile()
            self.loadfile(os.path.normpath(fname))
        else:
            pass
        event.acceptProposedAction()

    def showNotification(self, message, index=None):
        if index is None:
            index = self.currentIndex()
        self.focusedEditor(index).notification.showMessage(message)

    def undoAction(self):
        self.currentEditor.undo()

    def redoAction(self):
        self.currentEditor.redo()

    def cutItem(self):
        self.currentEditor.cut()

    def copyItem(self):
        self.currentEditor.copy()

    def deleteItem(self):
        self.currentEditor.removeSelectedText()

    def selectAll(self):
        self.currentEditor.selectAll()

    def selectToMatchingBrace(self):
        self.currentEditor.selectToMatchingBrace()

    def clearBackups(self):
        # empty backups
        for i in os.listdir(self.projectPathDict["backupdir"]):
            remPath = os.path.join(self.projectPathDict["backupdir"], i)
            try:
                os.remove(remPath)
            except:
                pass

    def createBackup(self):
        for i in range(self.count()):
            key = self.getEditorData("backupKey", i)
            editor = self.getEditor(i)

            if not os.path.exists(self.projectPathDict["backupdir"]):
                os.makedirs(self.projectPathDict["backupdir"], exist_ok=True)

            savePath = os.path.join(self.projectPathDict["backupdir"], key)

            file = open(savePath, 'w')
            file.write(editor.text())
            file.close()
        self.saveSession(True)

    def saveSession(self, backup=False):
        # JSON after QtXml cleanup.
        session_data = []
        current_idx = self.currentIndex()
        for i in range(self.count()):
            editor = self.getEditor(i)
            path = self.getEditorData("filePath", i)
            if not backup and path is None:
                continue
            entry = {
                "path": str(path) if path else "",
                "active": (i == current_idx),
                "locked": bool(editor.isReadOnly()),
                "lines": int(editor.lines()),
                "cursorPosition": ",".join(map(str, editor.getCursorPosition())),
                "firstVisibleLine": int(editor.firstVisibleLine()),
                "bookmarks": str(editor.getBookmarks()).replace(', ', '-').strip('[]'),
                "folds": str(editor.contractedFolds()).replace(', ', '-').strip('[]')
            }
            if backup:
                entry["backupKey"] = self.getEditorData("backupKey", i)
                entry["baseName"] = self.tabText(i)
            session_data.append(entry)

        if backup:
            savePath = self.projectPathDict["backupfile"]
        else:
            savePath = self.projectPathDict["session"]
        try:
            with open(savePath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Session save failed:", e)

    def restoreSession(self):
        # TODO: When backup is True and it turns out empty because
        # it previousely loaded from backup, cleared it's backup
        # cache and was instantly shut down again, the previous
        # session must be reloaded.
        backup = self.projectSettings["LastCloseSuccessful"] == "False"

        if backup:
            loadPath = self.projectPathDict["backupfile"]
        else:
            self.clearBackups()
            loadPath = self.projectPathDict["session"]

        # QtXml cleanup: support JSON (new, list or object) and legacy XML for session restore.
        # Note: saveSession writes a JSON *list* (starts with '['), so check for [ or {.
        # Legacy XML had <file ...> children (possibly under <session> or root).
        try:
            with open(loadPath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            session_data = []
            if content:
                # Prefer JSON (new format after QtXml cleanup: always a list [...] of tab entries)
                if content[0] in '[{':
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, list):
                            session_data = parsed
                    except Exception:
                        pass
                # Fallback to legacy XML (old <file path=...> etc, possibly wrapped)
                if not session_data:
                    try:
                        root = ET.fromstring(content)
                        for child in root:
                            if child.tag == "file":
                                entry = {
                                    "path": child.get("path", ""),
                                    "active": child.get("active", "False") == "True",
                                    "locked": child.get("locked", "False") == "True",
                                    "lines": int(child.get("lines", 0)),
                                    "cursorPosition": child.get("cursorPosition", "0,0"),
                                    "firstVisibleLine": int(child.get("firstVisibleLine", 0)),
                                    "bookmarks": child.get("bookmarks", ""),
                                    "folds": child.get("folds", ""),
                                }
                                if backup:
                                    entry["backupKey"] = child.get("backupKey", "")
                                    entry["baseName"] = child.get("baseName", "")
                                session_data.append(entry)
                    except Exception:
                        pass
        except Exception as e:
            print("Failed to load session:", e)
            session_data = []

        activeIndex = 0
        restoredBackups = 0

        for entry in session_data:
            try:
                # Always append successfully loaded tabs in session order.
                # Using self.count() as insert index ensures we append.
                # This avoids fragile currentIindex tracking that could cause
                # getEditor wrong index or insert position errors (esp. with
                # missing files or legacy data).
                append_idx = self.count()

                if backup and os.path.exists(loadPath):
                    backupKey = entry.get("backupKey", "")
                    backupPath = os.path.join(self.projectPathDict["backupdir"], backupKey)
                    realPath = entry.get("path", "")
                    if realPath == '':
                        try:
                            with open(backupPath, 'r') as f:
                                backupText = f.read()
                            subStack = self.newEditor(append_idx)
                            # Note: subStack.widget(0) is splitter, its .widget(0) or getEditor
                            editor = subStack.widget(0).getEditor(0) if hasattr(subStack.widget(0), 'getEditor') else subStack.widget(0).widget(0)
                            editor.setText(backupText)
                            editor.setModified(False)
                            editor.setFocus()
                            restoredBackups += 1
                        except Exception:
                            pass
                    else:
                        try:
                            real_mod_time = os.stat(realPath).st_mtime
                            backup_mod_time = os.stat(backupPath).st_mtime
                            if backup_mod_time > real_mod_time:
                                with open(backupPath, 'r') as f:
                                    backupText = f.read()
                                with open(realPath, "w") as f:
                                    f.write(backupText)
                                restoredBackups += 1
                        except Exception:
                            pass

                        loaded = self.loadfile(realPath, False, append_idx)
                else:
                    realPath = entry.get("path", "")
                    loaded = self.loadfile(realPath, False, append_idx)

                if not loaded:
                    continue

                # After successful load, the new tab is at count-1
                tab_idx = self.count() - 1

                # Apply locked state
                if entry.get("locked") in (True, 'True'):
                    self.writeLock()

                # Track active tab (last one wins if multiple marked, or the one from session)
                if entry.get("active") in (True, 'True'):
                    activeIndex = tab_idx

                # Basic cursor and visible line
                cp = entry.get("cursorPosition", "0,0").split(',')
                line = int(cp[0]) if len(cp) > 0 else 0
                idx = int(cp[1]) if len(cp) > 1 else 0
                firstVisibleLine = int(entry.get("firstVisibleLine", 0))

                editor = self.getEditor(tab_idx)
                if editor:
                    try:
                        editor.setCursorPosition(line, idx)
                        editor.setFirstVisibleLine(firstVisibleLine)
                    except Exception:
                        pass

                # Bookmarks
                m = entry.get("bookmarks", "")
                if m and editor:
                    try:
                        bookmarks = [int(x) for x in m.split('-') if x.strip()]
                        for bline in bookmarks:
                            editor.toggleBookmark(1, bline)
                    except Exception:
                        pass

                # Folds
                f = entry.get("folds", "")
                if f and editor:
                    try:
                        folds = [int(x) for x in f.split('-') if x.strip()]
                        editor.setContractedFolds(folds)
                    except Exception:
                        pass

            except Exception as e:
                print("Error restoring session entry:", e)
                continue

        # Set the active tab from session (or 0)
        if self.count() > 0:
            if activeIndex >= self.count():
                activeIndex = 0
            self.setCurrentIndex(activeIndex)

        if self.count() == 0:
            self._newPythonFile()

        self.clearBackups()
        if restoredBackups > 0:
            self.messagesWidget.addMessage(
                0, _("Restored"), [str(restoredBackups) + _(' file(s) restored from previous crash.')])

    def getSource(self, index=None):
        if index is None:
            return self.getEditor().text()
        else:
            return self.getEditor(index).text()

    def getSelection(self):
        return self.currentEditor.selectedText()

    def closeEditorTab(self, index):
        if self.getEditor(index).isModified():
            self.requestSaveMess(index)
        else:
            if self.count() == 1:
                self._newPythonFile()
            self.removeTabBackup(index)
            path = self.getEditorData('filePath')
            if path is None:
                self.filesWatch.removePath(path)
            self.removeTab(index)
            self.updateOpenedTabsMenu()

    def editorTabChanged(self, index):
        self.currentEditor = self.getEditor()
        self.cloneEditor = self.getCloneEditor()
        self.currentEditor.undoActModifier()
        self.currentEditor.redoActModifier()
        self.currentEditor.copyActModifier()

        if self.getEditorData("filePath") is None:
            self.updateWindowTitle.emit(_("Unsaved"))
            self.updateEncodingLabel.emit(_("Coding: {0}").format(
                self.getEditorData("codingFormat")))
        else:
            self.updateWindowTitle.emit(self.getEditorData("filePath"))
            self.updateEncodingLabel.emit(_("Coding: {0}").format(
                self.getEditorData("codingFormat")))

        self.enableBookmarkButtons(self.currentEditor.bookmarksExist())
        self.currentEditor.updateLineCount()
        self.cursorPositionChanged.emit()
        self.updateOpenedTabsMenu()

    def enableBookmarkButtons(self, enable):
        self.bookmarkToolbar.setEnabled(enable)
        self.bookmarksChanged.emit()

    def makeCurrentTab(self, action):
        self.setCurrentIndex(action.data())

    def updateOpenedTabsMenu(self):
        self.openedTabsActionGroup = QtGui.QActionGroup(self)
        self.openedTabsActionGroup.setExclusive(True)
        self.openedTabsActionGroup.triggered.connect(self.makeCurrentTab)
        self.openedTabsMenu.clear()
        for i in range(self.count()):
            name = self.tabText(i)
            action = QtGui.QAction(name, self)
            action.setCheckable(True)
            if self.currentIndex() == i:
                action.setChecked(True)
            action.setData(i)
            self.openedTabsActionGroup.addAction(action)
            self.openedTabsMenu.addAction(action)

    def pasteFromClipboard(self):
        self.focusedEditor().paste()

    def increaseIndent(self):
        self.focusedEditor().increaseIndent()

    def decreaseIndent(self):
        self.focusedEditor().decreaseIndent()

    def showMe(self, widget):
        for toolWidget in self.toolWidgetList:
            toolWidget.hide()
        widget.show()

    def showProjectConfiguration(self):
        self.showMe(self.configDialog)

    def showGotoLineWidget(self):
        self.showMe(self.gotoLineWidget)
        self.gotoLineWidget.lineNumberLine.setFocus()

    def showSnapShotSwitcher(self):
        self.showMe(self.viewSwitcher)

    def showSetRunParameters(self):
        if self.setRunParameters.isVisible():
            self.setRunParameters.hide()
        else:
            self.showMe(self.setRunParameters)

    def showFavouritesManager(self):
        self.showMe(self.manageFavourites)

    def showExternalLauncher(self):
        self.showMe(self.externalLauncher)

    def showLine(self, lineNum, highlight=True):
        self.focusedEditor().showLine(lineNum, highlight)

    def writeLock(self):
        if self.focusedEditor().isReadOnly() is False:
            self.focusedEditor().setReadOnly(True)
            self.setTabIcon(self.currentIndex(),
                            QtGui.QIcon(os.path.join("Resources", "images", "locked_script")))
        else:
            self.focusedEditor().setReadOnly(False)
            if self.getEditorData("fileType") == "python":
                if self.focusedEditor().isModified():
                    self.setTabIcon(self.currentIndex(),
                                    QtGui.QIcon(os.path.join("Resources", "images", "script_grey")))
                else:
                    self.setTabIcon(self.currentIndex(),
                                    QtGui.QIcon(os.path.join("Resources", "images", "script")))
            else:
                self.setTabIcon(self.currentIndex(),
                                Global.iconFromPath(self.getEditorData("filePath")))

    def findNextBookmark(self):
        editor = self.focusedEditor()
        editor.findNextBookmark()

    def findPreviousBookmark(self):
        editor = self.focusedEditor()
        editor.findPreviousBookmark()

    def removeBookmarks(self):
        reply = QtWidgets.QMessageBox.warning(self, _("Remove Bookmarks"),
                                          _("Do you really want to remove all bookmarks?"),
                                          QtWidgets.QMessageBox.StandardButton.Yes | 
                                          QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            pass
        else:
            return
        self.currentEditor.removeBookmarks()
        self.enableBookmarkButtons(False)

    def goToCursorPosition(self):
        line, index = self.focusedEditor().getCursorPosition()
        self.focusedEditor().showLine(line, False)

    def comment(self):
        self.focusedEditor().comment()

    def unComment(self):
        self.focusedEditor().unComment()

    def errorsInProject(self):
        errors = False
        for i in range(self.count()):
            path = self.getEditorData("filePath", i)
            if path is not None:
                if self.isProjectFile(path):
                    if self.getEditorData("fileType", i) == "python":
                        errorLine = self.getEditorData("errorLine", i)
                        if errorLine is not None:
                            errors = True
                            self.setCurrentIndex(i)
                            break
        return errors

    def isProjectFile(self, filePath):
        if filePath is None:
            return False
        return filePath.startswith(self.projectPathDict["sourcedir"])

    def getTabName(self, tabIndex=None):
        if tabIndex is None:
            name = self.tabText(self.currentIndex())
        else:
            name = self.tabText(tabIndex)
        return name

    def getEditorData(self, attrib, tabIndex=None):
        if tabIndex is None:
            tabIndex = self.currentIndex()
        else:
            pass
        # vector for crashfix
        try:
            data = self.widget(tabIndex).widget(0).DATA[attrib]
        except:
            data = ''
        return data

    def updateEditorData(self, attrib, value, tabIndex=None):
        if tabIndex is None:
            tabIndex = self.currentIndex()
        else:
            pass
        self.getEditor(tabIndex).DATA[attrib] = value
        if attrib == "filePath":
            if value is None:
                self.updateWindowTitle.emit("Unsaved")
            else:
                self.setTabText(tabIndex, os.path.basename(value))
                self.updateWindowTitle.emit(value)

    def updateTabName(self, index=None):
        if index is None:
            index = self.currentIndex()
        else:
            pass
        path = self.getEditorData("filePath", index)
        if path is None:
            return
        text = os.path.basename(path)
        editor = self.getEditor(index)
        if editor.isModified():
            text = text + " *"
        self.setTabText(index, text)
        self.setTabToolTip(index, path)

    def removeTabBackup(self, tabIndex):
        key = self.getEditorData("backupKey", tabIndex)
        try:
            os.remove(os.path.join(self.projectPathDict["backupdir"], key))
        except:
            pass

    def requestSaveMess(self, tabIndex):
        mess = _("Save changes to '{0}'?").format(self.tabText(tabIndex))
        reply = QtWidgets.QMessageBox.information(self, _("Save"), mess,
                                              QtWidgets.QMessageBox.StandardButton.Save | 
                                              QtWidgets.QMessageBox.StandardButton.Discard |
                                              QtWidgets.QMessageBox.StandardButton.Cancel)
        if reply == QtWidgets.QMessageBox.StandardButton.Save:
            self.save()
        elif reply == QtWidgets.QMessageBox.StandardButton.Discard:
            if self.count() == 1:
                self.newFile()
            else:
                self.removeTabBackup(tabIndex)
                self.removeTab(tabIndex)

    def _save(self):
        self.save()

    def save(self, index=None):
        if index is None:
            index = self.currentIndex()
        savePath = self.getEditorData("filePath", index)
        if savePath is None:
            saved = self.saveAs(index)
            return saved
        else:
            try:
                file = open(savePath, "w")
                editor = self.getEditor(index)
                file.write(editor.text())
                file.close()
                editor.setModified(False)

                return True
            except Exception as err:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.error(repr(traceback.format_exception(exc_type, exc_value,
                             exc_traceback)))
                self.saveErrorMess(str(err))

                return False

    def saveToTemp(self, type, index=None):
        if index is None:
            index = self.currentIndex()
        try:
            if type == 'pep8':
                file = open(os.path.join("temp", "temp8.py"), "w")
            editor = self.getEditor(index)
            file.write(editor.text())
            file.close()
            return True
        except:
            return False

    def saveAs(self, index=None, copyOnly=False):
        fileName, _ = QtWidgets.QFileDialog.getSaveFileName(self,
                                                     "Save As", os.path.join(self.useData.getLastOpenedDir(), self.getTabName()),
                                                             self.getFilter())
        if fileName:
            self.useData.saveLastOpenedDir(os.path.split(fileName)[0])
            try:
                if index is None:
                    index = self.currentIndex()
                fileName = os.path.normpath(fileName)
                editor = self.getEditor(index)
                file = open(fileName, "w")
                file.write(editor.text())
                file.close()
                editor.setModified(False)
                self.updateTabName(index)
                if not copyOnly:
                    self.updateEditorData("filePath", fileName)
                self.filesWatch.addPath(fileName)
                return True
            except Exception as err:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.error(repr(traceback.format_exception(exc_type, exc_value,
                             exc_traceback)))
                self.saveErrorMess(str(err.args[1]))
                return False
        else:
            return False

    def saveCopyAs(self):
        self.saveAs(copyOnly=True)

    def getFilter(self):
        fileType = self.getEditorData("fileType")
        if fileType == "python":
            filter = "Console (*.py);;No Console (*.pyw)"
        elif fileType == ".xml":
            filter = "Xml (*.xml)"
        elif fileType == ".html":
            filter = "Html (*.html)"
        elif fileType == ".css":
            filter = "Css (*.css)"
        else:
            filter = "All Files (*)"
        return filter

    def saveAll(self):
        for i in range(self.count()):
            self.save(i)

    def saveProject(self):
        saved = True
        source_dir = self.projectPathDict["sourcedir"]
        for i in range(self.count()):
            path = self.getEditorData("filePath", i)
            if path is not None:
                if self.isProjectFile(path):
                    # its a project file
                    editor = self.getEditor(i)
                    if editor.isModified():
                        saved = self.save(i)
                        if not saved:
                            break
        return saved

    def saveErrorMess(self, mess):

        message = QtWidgets.QMessageBox.critical(self,
                                             _("Save"), _("Error saving file!\n\n") + mess)

    def printCode(self):
        document = self.currentEditor.document()
        printer = QtPrintSupport.QPrinter()


        dlg = QtPrintSupport.QPrintDialog(printer, self)
        dlg.setOption(QtPrintSupport.QPrintOption.DontUseNativeDialog)
        dlgret = dlg.exec()
        if dlg.exec() != QtWidgets.QDialog.accepted:
            return
        document.print_(printer)

    def openFile(self):
        fileName = QtWidgets.QFileDialog.getOpenFileName(self,
                                                     _("Select File"), self.useData.getLastOpenedDir(
                                                     ),
                                                     _("All Files (*);;Console (*.py);;No Console (*.pyw);;Xml (*.xml);;Html (*.html);;Css (*.css)"))[0]
        if fileName:
            self.useData.saveLastOpenedDir(os.path.split(fileName)[0])
            self.loadfile(os.path.normpath(fileName))

    def _newPythonFile(self):
        self.newEditor()

    def _newXmlFile(self):
        self.newEditor(fileName=_("Untitled.xml"))

    def _newHtmlFile(self):
        self.newEditor(fileName=_("Untitled.html"))

    def _newCssFile(self):
        self.newEditor(fileName=_("Untitled.css"))

    def newEditor(self, index=None, fileName=_("Untitled.py"),
                  filePath=None, encoding=None):
        extension = os.path.splitext(fileName)[1].lower()
        pyFile = extension in [".py", ".pyw"]
        if pyFile:
            extension = "python"

        DATA = {}
        DATA["filePath"] = filePath
        DATA["backupKey"] = str(time.time()) + '.' + str(
            self.backupKeyDiferentiator)
        self.backupKeyDiferentiator += 1
        DATA["bookmarkList"] = []

        if encoding is None:
            DATA["codingFormat"] = "utf-8"
        else:
            DATA["codingFormat"] = encoding
        if pyFile:
            DATA["errorLine"] = None
            DATA["fileType"] = "python"
            editor = CodeEditor(self.useData, self.refactor, self.colorScheme,
                                DATA, self)
            editor2 = CodeEditor(self.useData, self.refactor, self.colorScheme,
                                 DATA, self)
            snapShot = CodeSnapshot(self.useData, self.colorScheme)
        else:
            if extension in [".htm", ".html"]:
                extension = ".html"
            DATA["fileType"] = extension
            editor = TextEditor(self.useData, DATA, self.colorScheme, self,
                                encoding)
            editor2 = TextEditor(self.useData, DATA, self.colorScheme, self,
                                 encoding)
            snapShot = TextSnapshot(self.useData, self.colorScheme, extension)

        mode = QsciScintilla.EolMode.EolUnix
        editor.setEolMode(mode)
        editor2.setEolMode(mode)
        snapShot.setEolMode(mode)

        snapShot.setReadOnly(True)
        subStack = QtWidgets.QStackedWidget()

        editorSplitter = EditorSplitter(editor, editor2, DATA, self, subStack)

        editor2.setDocument(editor.document())
        subStack.addWidget(editorSplitter)
        subStack.addWidget(snapShot)
        diffWindow = DiffWindow(editor, snapShot)
        diffWindow.setStyleSheet(StyleSheet.editorStyle)
        subStack.addWidget(diffWindow)
        diffWindow = DiffWindow(editor, snapShot)
        diffWindow.setStyleSheet(StyleSheet.editorStyle)
        subStack.addWidget(diffWindow)

        if extension in self.useData.supportedFileTypes:
            icon = QtGui.QIcon(os.path.join("Resources", "images", "script"))
        else:
            icon = Global.iconFromPath(filePath)
        if index is None:
            index = self.currentIndex()
        self.insertTab(index, subStack, icon, fileName)

        if filePath is None:
            pass
        else:
            self.filesWatch.addPath(filePath)

        editor.textChanged.connect(self.currentEditorTextChanged.emit)
        editor.cursorPositionChanged.connect(self.cursorPositionChanged.emit)
        editor2.cursorPositionChanged.connect(self.cursorPositionChanged.emit)

        self.setCurrentWidget(subStack)

        return subStack

    def splitVertical(self):
        splitter = self.currentWidget().widget(0)
        splitter.addSplitHorizontal()
        splitter.editor2.show()

    def splitHorizontal(self):
        splitter = self.currentWidget().widget(0)
        splitter.addSplitVertical()
        splitter.editor2.show()

    def removeSplit(self):
        splitter = self.currentWidget().widget(0)
        #splitter.widget(1).hide()
        splitter.editor2.hide()
        #editor2.hide()

    def reloadModules(self, pathList=[]):
        index_list = []
        currentIndex = self.currentIndex()
        if len(pathList) == 0:
            index_list.append(currentIndex)
        else:
            for i in range(self.count()):
                path = self.getEditorData("filePath", i)
                if path in pathList:
                    index_list.append(i)
        for i in index_list:
            filePath = self.getEditorData("filePath", i)
            editor = self.getEditor(i)
            text, encoding, eolMode = self.useData.readFile(filePath)
            firstLine = editor.firstVisibleLine()
            editor.setText(text)
            editor.convertEols(eolMode)
            editor.setEolMode(eolMode)
            editor.setFirstVisibleLine(firstLine)
            editor.setModified(False)
            if i == currentIndex:
                self.getEditor(i).removeBookmarks()
                self.enableBookmarkButtons(False)

    def alreadyOpened(self, filePath):
        for i in range(self.count()):
            fpath = self.getEditorData("filePath", i)
            if fpath is None:
                pass
            else:
                if os.path.samefile(fpath, filePath):
                    self.setCurrentIndex(i)
                    return True
        return False

    def loadfile(self, filePath, showError=True, index=None):

        filePath = os.path.normpath(filePath)
        # prevent same file from being opened more than once
        if self.alreadyOpened(filePath):
            return True

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            text, encoding, eolMode = self.useData.readFile(filePath)
            baseName = os.path.basename(filePath)
            subStack = self.newEditor(index, baseName, filePath, encoding)

            editor = subStack.widget(0).getEditor(0)
            editor.setText(text)
            editor.convertEols(eolMode)
            editor.setEolMode(eolMode)

            snapshotWidget = subStack.widget(1)
            snapshotWidget.setText(text)
            snapshotWidget.convertEols(eolMode)
            snapshotWidget.setEolMode(eolMode)
        except Exception as err:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.error(repr(traceback.format_exception(exc_type, exc_value,
                         exc_traceback)))
            QtWidgets.QApplication.restoreOverrideCursor()
            if showError:
                message = QtWidgets.QMessageBox.warning(self, "Open", str(err))
            else:
                pass
            return False

        QtWidgets.QApplication.restoreOverrideCursor()

        editor.setModified(False)
        editor.setFocus()
        self.updateRecentFilesList.emit(filePath)
        self.updateOpenedTabsMenu()

        return True

    def get_current_word(self):
        current_word = self.focusedEditor().get_current_word()
        return current_word

    def getOffset(self):
        offset = self.focusedEditor().getOffset()
        return offset

    def changeTab(self):
        if (self.count() - 1) != self.currentIndex():
            self.setCurrentIndex(self.currentIndex() + 1)
        else:
            self.setCurrentIndex(0)

    def reverseTab(self):
        if self.currentIndex() != 0:
            self.setCurrentIndex(self.currentIndex() - 1)
        else:
            self.setCurrentIndex(self.count() - 1)

    def changeSplitFocus(self):
        splitter = self.currentWidget().widget(0)
        firstEditor = splitter.widget(0)
        if firstEditor.hasFocus():
            splitter.widget(1).setFocus()
        else:
            firstEditor.setFocus()

    def setKeymap(self):
        self.tabBar.setKeymap()
        shortcuts = self.useData.CUSTOM_SHORTCUTS

        self.shortSplitVertical = QtGui.QShortcut(
            shortcuts["Ide"]["Split-Vertical"], self)
        self.shortSplitVertical.activatedAmbiguously.connect(
            self.splitVertical)
        self.vSplitEditorAct.setShortcut(shortcuts["Ide"]["Split-Vertical"])

        self.shortSplitHorizontal = QtGui.QShortcut(
            shortcuts["Ide"]["Split-Horizontal"], self)
        self.shortSplitHorizontal.activatedAmbiguously.connect(
            self.splitHorizontal)
        self.hSplitEditorAct.setShortcut(
            shortcuts["Ide"]["Split-Horizontal"])

        self.shortRemoveSplit = QtGui.QShortcut(
            shortcuts["Ide"]["Remove-Split"], self)
        self.shortRemoveSplit.activatedAmbiguously.connect(self.removeSplit)
        self.noSplitEditorAct.setShortcut(shortcuts["Ide"]["Remove-Split"])

        self.shortChangeTab = QtGui.QShortcut(
            shortcuts["Ide"]["Change-Tab"], self)
        self.shortChangeTab.activated.connect(self.changeTab)

        self.shortReverseTab = QtGui.QShortcut(
            shortcuts["Ide"]["Change-Tab-Reverse"], self)
        self.shortReverseTab.activated.connect(self.reverseTab)

        self.shortChangeSplitFocus = QtGui.QShortcut(
            shortcuts["Ide"]["Change-Split-Focus"], self)
        self.shortChangeSplitFocus.activated.connect(self.changeSplitFocus)

        self.shortNewFile = QtGui.QShortcut(
            shortcuts["Ide"]["New-File"], self)
        self.shortNewFile.activatedAmbiguously.connect(self._newPythonFile)
        self.newPythonFileAct.setShortcut(shortcuts["Ide"]["New-File"])

        self.shortOpenFile = QtGui.QShortcut(
            shortcuts["Ide"]["Open-File"], self)
        self.shortOpenFile.activatedAmbiguously.connect(self.openFile)
        self.openFileAct.setShortcut(shortcuts["Ide"]["New-File"])

        self.shortSaveFile = QtGui.QShortcut(
            shortcuts["Ide"]["Save-File"], self)
        self.shortSaveFile.activatedAmbiguously.connect(self._save)
        self.saveAct.setShortcut(shortcuts["Ide"]["Save-File"])

        self.shortSaveAll = QtGui.QShortcut(
            shortcuts["Ide"]["Save-All"], self)
        self.shortSaveAll.activatedAmbiguously.connect(self.saveAll)
        self.saveAllAct.setShortcut(shortcuts["Ide"]["Save-All"])

        self.shortPrint = QtGui.QShortcut(shortcuts["Ide"]["Print"], self)
        self.shortPrint.activatedAmbiguously.connect(self.printCode)
        self.printAct.setShortcut(shortcuts["Ide"]["Print"])
