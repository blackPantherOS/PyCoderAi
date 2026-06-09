import sys
import os
import zipfile
import traceback
from PyQt6 import QtCore, QtGui, QtWidgets

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    # Get the directory where this module is located
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        # Normal development: use the directory of this file
        base_path = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to get to the project root (where Resources is)
        base_path = os.path.dirname(base_path)
    return os.path.join(base_path, relative_path)


class CreateWorkSpaceThread(QtCore.QThread):

    def run(self):
        self.errors = None
        try:
            # Create the target directory (and parents) if it doesn't exist.
            # Previous code had "if not os.path.exists:" (missing call) which never created anything.
            os.makedirs(self.path, exist_ok=True)
        except:
            self.errors = traceback.format_exc()
        try:
            zip = zipfile.ZipFile(
                resource_path(os.path.join("Resources", "PyCoderProjects.zip")), 'r')
            zip.extractall(self.path)
        except:
            self.errors = traceback.format_exc()

    def createWorkspace(self, path):
        self.path = path

        self.start()


class GetPathLine(QtWidgets.QWidget):

    textChanged = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        mainLayout = QtWidgets.QHBoxLayout()
        mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(mainLayout)

        self.destinationLine = QtWidgets.QLineEdit()
        self.destinationLine.textChanged.connect(self.textChanged.emit)
        mainLayout.addWidget(self.destinationLine)

        homePath = QtCore.QDir().homePath()

        # Default suggestion for new workspace.
        # "Create new" will create a "PyCoderProjects" subfolder inside this path.
        # So choosing ~/Projects will result in workspace at ~/Projects/PyCoderProjects
        if sys.platform == 'win32':
            path = os.path.join(homePath, "My Documents")
        elif sys.platform == 'darwin':
            path = os.path.join(homePath, "Documents")
        else:
            path = os.path.join(homePath, "Projects")
        path = os.path.normpath(path)
        self.destinationLine.setText(path)

        self.browseButton = QtWidgets.QPushButton('...')
        self.browseButton.clicked.connect(self.browsePath)
        mainLayout.addWidget(self.browseButton)

    def browsePath(self):
        homePath = QtCore.QDir().homePath()
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Folder",
            homePath)
        if directory:
            self.destinationLine.setText(os.path.normpath(directory))

    def text(self):
        return self.destinationLine.text()


class WorkSpace(QtWidgets.QDialog):

    def __init__(self, parent=None):
        QtWidgets.QDialog.__init__(self, parent,
                               QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.setWindowTitle("Workspace")
        self.setWindowIcon(
            QtGui.QIcon(resource_path(os.path.join("Resources", "images", "icon.png"))))
        self.setFixedSize(500, 130)

        self.createWorkSpaceThread = CreateWorkSpaceThread()
        self.createWorkSpaceThread.finished.connect(self.completeWorkspace)

        mainLayout = QtWidgets.QVBoxLayout()
        self.setLayout(mainLayout)

        mainLayout.addWidget(
            QtWidgets.QLabel("Choose the location of your Workspace:"))

        self.choiceBox = QtWidgets.QComboBox()
        self.choiceBox.addItem("Choose an existing one")
        self.choiceBox.addItem("Create new")
        # For completely new installations (workspace=None or missing), default to "Create new"
        # so the user doesn't immediately hit "Path does not exist."
        self.choiceBox.setCurrentIndex(1)
        mainLayout.addWidget(self.choiceBox)

        self.getPathLine = GetPathLine()
        mainLayout.addWidget(self.getPathLine)

        mainLayout.addStretch(1)

        hbox = QtWidgets.QHBoxLayout()
        mainLayout.addLayout(hbox)

        self.statusLabel = QtWidgets.QLabel()
        hbox.addWidget(self.statusLabel)

        hbox.addStretch(1)

        self.okButton = QtWidgets.QPushButton("Done")
        self.okButton.clicked.connect(self.accept)
        hbox.addWidget(self.okButton)

        self.cancelButton = QtWidgets.QPushButton("Cancel")
        self.cancelButton.clicked.connect(self.cancel)
        hbox.addWidget(self.cancelButton)

        self.created = False

        self.exec()

    def completeWorkspace(self):
        QtWidgets.QApplication.restoreOverrideCursor()
        if self.createWorkSpaceThread.errors is None:
            self.path = os.path.join(
                self.createWorkSpaceThread.path, "PyCoderProjects")
            self.created = True
            self.close()
        else:
            self.statusLabel.clear()
            message = QtWidgets.QMessageBox.warning(
                self, "Workspace", "Error creating workspace:\n\n{0}".format(self.createWorkSpaceThread.errors))
            self.okButton.setDisabled(False)
            self.cancelButton.setDisabled(False)
            self.getPathLine.setDisabled(False)
            self.choiceBox.setDisabled(False)

    def accept(self):
        path = self.getPathLine.text()
        if self.choiceBox.currentIndex() == 0:
            if os.path.exists(path):
                # Check if the path is a PyCoderProjects directory
                if os.path.basename(path) == "PyCoderProjects":
                    self.path = path
                    self.created = True
                    self.close()
                # Check if the path contains a PyCoderProjects subdirectory
                elif os.path.isdir(os.path.join(path, "PyCoderProjects")):
                    self.path = os.path.join(path, "PyCoderProjects")
                    self.created = True
                    self.close()
                else:
                    message = QtWidgets.QMessageBox.warning(
                        self, "Workspace", "The workspace is not valid!\n\nPlease select a PyCoderProjects directory or a directory containing a PyCoderProjects subdirectory.")
                    return
            else:
                message = QtWidgets.QMessageBox.warning(
                    self, "Workspace",
                    "Path does not exist.\n\n"
                    "For a first-time setup, switch to 'Create new' (it is pre-selected for new installs), "
                    "pick a parent folder (e.g. ~/Projects), and click Done. "
                    "A 'PyCoderProjects' subfolder will be created and populated inside it.")
        else:
            self.okButton.setDisabled(True)
            self.cancelButton.setDisabled(True)
            self.getPathLine.setDisabled(True)
            self.choiceBox.setDisabled(True)
            self.statusLabel.setText("Creating workspace...")
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

            self.createWorkSpaceThread.createWorkspace(path)

    def cancel(self):
        self.created = False
        self.close()
