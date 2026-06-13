"""
Manages all opened projects such as the creation and closing of projects
"""

import os
import sys
import shutil
import traceback
import logging
import json
import xml.etree.ElementTree as ET  # QtXml migration - legacy project.xml etc.

from PyQt6 import QtCore, QtGui, QtWidgets

from Extensions_Qt6.EditorWindow.EditorWindow import EditorWindow
from Extensions_Qt6.Projects.NewProjectDialog import NewProjectDialog


class CreateProjectThread(QtCore.QThread):

    def run(self):
        self.error = False
        try:
            self.projectPath = os.path.join(self.projDataDict["location"],
                                            self.projDataDict["name"])
            os.mkdir(self.projectPath)

            data = os.path.join(self.projectPath, "Data")
            os.mkdir(data)
            file = open(os.path.join(data, "wpad.txt"), "w")
            file.close()

            ropeFolder = os.path.join(self.projectPath, "Rope")
            print("Rope:",ropeFolder )
            os.mkdir(ropeFolder)
            shutil.copy(os.path.join("Resources", "default_config.py"),
                        os.path.join(ropeFolder, "config.py"))

            os.mkdir(os.path.join(self.projectPath, "Resources"))
            os.mkdir(os.path.join(self.projectPath, "Resources", "VirtualEnv"))
            os.mkdir(
                os.path.join(self.projectPath, "Resources", "VirtualEnv", "Linux"))
            os.mkdir(
                os.path.join(self.projectPath, "Resources", "VirtualEnv", "Mac"))
            os.mkdir(
                os.path.join(self.projectPath, "Resources", "VirtualEnv", "Windows"))
            os.mkdir(os.path.join(self.projectPath, "Resources", "Icons"))

            os.mkdir(os.path.join(self.projectPath, "temp"))
            os.mkdir(os.path.join(self.projectPath, "temp", "Backup"))
            os.mkdir(os.path.join(self.projectPath, "temp", "Backup", "Files"))

            sourceDir = os.path.join(self.projectPath, "src")
            if self.projDataDict["importdir"] != '':
                shutil.copytree(self.projDataDict["importdir"], sourceDir)
            else:
                os.mkdir(os.path.join(self.projectPath, "src"))

            if self.projDataDict["type"] == _("Desktop Application") or self.projDataDict["type"] == "Desktop Application":
                build = os.path.join(self.projectPath, "Build")
                os.mkdir(build)
                os.mkdir(os.path.join(build, "Linux"))
                os.mkdir(os.path.join(build, "Mac"))
                os.mkdir(os.path.join(build, "Windows"))

            self.mainScript = os.path.join(self.projectPath, "src",
                                           self.projDataDict["mainscript"])
            file = open(self.mainScript, 'w')
            file.close()

            if self.projDataDict["type"] == _("Desktop Application") or self.projDataDict["type"] == "Desktop Application":
                self.writeBuildProfile()
            self.writeDefaultSession()
            self.writeProjectData()
            self.writeRopeProfile()
        except Exception as err:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.error(repr(traceback.format_exception(exc_type, exc_value,
                         exc_traceback)))
            self.error = str(err)

    def writeProjectData(self):
        # QtXml migration: use ElementTree
        root = ET.Element("properties")
        project = ET.SubElement(root, "pycoder_project")
        project.set("Version", "0.1")
        project.set("Name", self.projDataDict["name"])
        project.set("Type", self.projDataDict["type"])
        project.set("MainScript", self.projDataDict["mainscript"])

        tree = ET.ElementTree(root)
        with open(os.path.join(self.projectPath, "project.xml"), "wb") as f:
            tree.write(f, encoding="UTF-8", xml_declaration=True)

        # QtXml migration: use ElementTree for projectdata.xml
        root = ET.Element("projectdata")

        for section in ["shortcuts", "recentfiles", "favourites", "settings"]:
            ET.SubElement(root, section)

        # settings with defaults
        settings_elem = root.find("settings")
        defaults = {
            'ClearOutputWindowOnRun': 'False',
            'LastOpenedPath': '',
            'RunType': _('Run'),
            'BufferSize': '900',
            'RunArguments': '',
            'DefaultInterpreter': 'python3',
            'TraceType': '3',
            'RunWithArguments': 'False',
            'RunInternal': 'True',
            'UseVirtualEnv': 'False',
            'Closed': 'True',
            'Icon': '',
            'ShowAllFiles': 'True',
            'LastCloseSuccessful': 'True'
        }
        for key, value in defaults.items():
            tag = ET.SubElement(settings_elem, "key")
            tag.text = f"{key}={value}"

        path = os.path.join(self.projectPath, "Data", "projectdata.xml")
        tree = ET.ElementTree(root)
        with open(path, "wb") as f:
            tree.write(f, encoding="UTF-8", xml_declaration=True)

    def writeDefaultSession(self):
        # QtXml migration: minimal empty session as JSON (to match new format)
        # Note: the session format was migrated to JSON list of dicts in EditorTabWidget.
        # For new projects, write an empty list as JSON.
        session_path = os.path.join(self.projectPath, "Data", "session.xml")
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump([], f)  # empty session; will be populated on first use

    def writeRopeProfile(self):
        # QtXml migration: write simple rope profile as XML using ET (to keep compatibility with rope)
        root = ET.Element("rope")

        for tag_name, text in [
            ("ignoresyntaxerrors", ""),
            ("ignorebadimports", ""),
            ("maxhistoryitems", "32"),
        ]:
            elem = ET.SubElement(root, tag_name)
            elem.text = text

        ext_elem = ET.SubElement(root, "Extensions_Qt6")
        for ext in ["*.py", "*.pyw"]:
            item = ET.SubElement(ext_elem, "item")
            item.text = ext

        ignore_elem = ET.SubElement(root, "IgnoredResources")
        for ign in ["*.pyc", "*~", ".ropeproject", ".hg", ".svn", "_svn", ".git", "__pycache__"]:
            item = ET.SubElement(ignore_elem, "item")
            item.text = ign

        ET.SubElement(root, "CustomFolders")

        tree = ET.ElementTree(root)
        with open(os.path.join(self.projectPath, "Rope", "profile.xml"), "wb") as f:
            tree.write(f, encoding="UTF-8", xml_declaration=True)

    def writeBuildProfile(self):
        # QtXml migration: full build profile using ET (replaces the old QDom version)
        root = ET.Element("build")

        # Basic metadata
        for tag_name, text in [
            ("name", ""),
            ("author", ""),
            ("version", "0.1"),
            ("comments", ""),
            ("description", ""),
            ("company", ""),
            ("copyright", ""),
            ("trademarks", ""),
            ("product", ""),
            ("base", self.projDataDict.get("windowtype", "")),
        ]:
            elem = ET.SubElement(root, tag_name)
            elem.text = text

        # Icon
        icon = ET.SubElement(root, "icon")
        icon.text = ""

        # Options
        for tag_name, text in [
            ("compress", "Compress"),
            ("optimize", "Optimize"),
            ("copydeps", "Copy Dependencies"),
            ("appendscripttoexe", "Append Script to Exe"),
            ("appendscripttolibrary", "Append Script to Library"),
        ]:
            elem = ET.SubElement(root, tag_name)
            elem.text = text

        # Various lists (empty by default for new project)
        lists = [
            "Includes", "Excludes", "Constants Modules", "Packages",
            "Replace Paths", "Bin Includes", "Bin Excludes",
            "Bin Path Includes", "Bin Path Excludes", "Zip Includes",
            "Include Files", "Namespace Packages"
        ]
        for i in lists:
            ET.SubElement(root, i.replace(' ', '-'))

        tree = ET.ElementTree(root)
        with open(os.path.join(self.projectPath, "Build", "profile.xml"), "wb") as f:
            tree.write(f, encoding="UTF-8", xml_declaration=True)

    def create(self, data):
        self.projDataDict = data

        self.start()


class Projects(QtWidgets.QWidget):

    def __init__(self, useData, busyWidget, library, settingsWidget, app,
                 projectWindowStack, projectTitleBox, parent):
        QtWidgets.QWidget.__init__(self, parent)

        self.createProjectThread = CreateProjectThread()
        self.createProjectThread.finished.connect(self.finalizeNewProject)

        self.newProjectDialog = NewProjectDialog(useData, self)
        self.newProjectDialog.projectDataReady.connect(self.createProject)

        self.busyWidget = busyWidget
        self.useData = useData
        self.app = app
        self.projectWindowStack = projectWindowStack
        self.projectTitleBox = projectTitleBox
        self.library = library
        self.settingsWidget = settingsWidget
        self.pycoder = parent

    def closeProgram(self):
        self.pycoder.close()

    def readProject(self, path):
        # validate project - now much more robust after QtXml cleanup
        project_file = os.path.join(path, "project.xml")
        valid_data = None

        if os.path.exists(project_file):
            try:
                tree = ET.parse(project_file)
                root = tree.getroot()
                name = root.tag
                # Support legacy direct-root <pycoder_project .../> and current <properties><pycoder_project .../></properties>
                proj = root
                if name != "pycoder_project":
                    cand = root.find("pycoder_project")
                    if cand is not None:
                        proj = cand
                data = {
                    "Version": proj.get("Version", ""),
                    "Type": proj.get("Type", ""),
                    "Name": proj.get("Name", ""),
                    "MainScript": proj.get("MainScript", "")
                }
                if proj.tag == "pycoder_project" and (data.get("Name") or data.get("MainScript")):
                    valid_data = ("pycoder_project", data)
            except Exception as e:
                print("Failed to parse existing project.xml with ET:", e)
                # fall through to repair

        if valid_data is None:
            # Try to auto-create/repair a minimal project.xml
            # This handles cases where project was created in broken state (missing or bad project.xml)
            try:
                p_name = os.path.basename(path)
                src = os.path.join(path, "src")
                main_script = "main.py"
                if os.path.isdir(src):
                    pys = [f for f in os.listdir(src) if f.endswith('.py')]
                    if pys:
                        main_script = pys[0]
                # Create minimal
                root = ET.Element("properties")
                proj = ET.SubElement(root, "pycoder_project")
                proj.set("Version", "0.1")
                proj.set("Name", p_name)
                proj.set("Type", "Desktop Application")
                proj.set("MainScript", main_script)

                tree = ET.ElementTree(root)
                with open(project_file, "wb") as f:
                    tree.write(f, encoding="UTF-8", xml_declaration=True)

                print("Auto-repaired/created project.xml for", path)
                valid_data = ("pycoder_project", {
                    "Version": "0.1",
                    "Type": "Desktop Application",
                    "Name": p_name,
                    "MainScript": main_script
                })
            except Exception as e:
                print("Failed to auto-repair project.xml for", path, ":", e)
                return False

        return valid_data

    def loadProject(self, path, show, new):
        print("DEBUG loadProject called for:", path)
        if not self.pycoder.showProject(path):
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            projectPathDict = {
                "notes": os.path.join(path, "Data", "wpad.txt"),
                "session": os.path.join(path, "Data", "session.xml"),
                "usedata": os.path.join(path, "Data", "usedata.xml"),
                "windata": os.path.join(path, "Data", "windata.xml"),
                "projectdata": os.path.join(path, "Data", "projectdata.xml"),
                "snippetsdir": os.path.join(path, "Data", "templates"),
                "tempdir": os.path.join(path, "temp"),
                "backupdir": os.path.join(path, "temp", "Backup", "Files"),
                "backupfile": os.path.join(path, "temp", "Backup", "bak"),
                "sourcedir": os.path.join(path, "src"),
                "ropeFolder": "../Rope",
                "buildprofile": os.path.join(path, "Build", "profile.xml"),
                "ropeprofile": os.path.join(path, "Rope", "profile.xml"),
                "projectmainfile": os.path.join(path, "project.xml"),
                "iconsdir": os.path.join(path, "Resources", "Icons"),
                "root": path
                }

            if sys.platform == 'win32':
                projectPathDict["venvdir"] = os.path.join(path,
                               "Resources", "VirtualEnv", "Windows", "Venv")
            elif sys.platform == 'darwin':
                projectPathDict["venvdir"] = os.path.join(path,
                               "Resources", "VirtualEnv", "Mac", "Venv")
            else:
                projectPathDict["venvdir"] = os.path.join(path,
                               "Resources", "VirtualEnv", "Linux", "Venv")

            try:
                project_data = self.readProject(path)
                if project_data is False:
                    print("DEBUG: readProject returned False for", path)
                    QtWidgets.QApplication.restoreOverrideCursor()
                    message = QtWidgets.QMessageBox.warning(self, _("Open Project"),
                                                        _("Failed:\n\n") + path)
                    return
                print("DEBUG: readProject succeeded for", path, "data:", project_data[1])
                projectPathDict["name"] = project_data[1]["Name"]
                projectPathDict["type"] = project_data[1]["Type"]
                projectPathDict["mainscript"] = os.path.join(path, "src",
                               project_data[1]["MainScript"])
                if sys.platform == 'win32':
                    projectPathDict["builddir"] = os.path.join(
                        path, "Build", "Windows")
                elif sys.platform == 'darwin':
                    projectPathDict["builddir"] = os.path.join(
                        path, "Build", "Mac")
                else:
                    projectPathDict["builddir"] = os.path.join(
                        path, "Build", "Linux")

                # Ensure basic project structure exists (for projects that were partially/brokenly created)
                for d in ["src", "Data", "Rope", "temp", projectPathDict.get("builddir", "")]:
                    if d and not os.path.exists(d if os.path.isabs(d) else os.path.join(path, d)):
                        try:
                            os.makedirs(d if os.path.isabs(d) else os.path.join(path, d), exist_ok=True)
                        except:
                            pass

                # Create the directory that the user accidentally deleted
                if not os.path.exists(projectPathDict["builddir"]):
                    os.makedirs(projectPathDict["builddir"], exist_ok=True)
                p_name = os.path.basename(path)

                projectWindow = EditorWindow(projectPathDict, self.library,
                                             self.busyWidget, self.settingsWidget.colorScheme,
                                             self.useData, self.app, self)
                if new:
                    projectWindow.editorTabWidget.loadfile(
                        projectPathDict["mainscript"])
                else:
                    projectWindow.restoreSession()
                projectWindow.editorTabWidget.updateWindowTitle.connect(
                    self.pycoder.updateWindowTitle)

                self.pycoder.addProject(projectWindow, p_name)
                # Load library view for the newly opened project
                self.library.loadLibrary()

                if path in self.useData.OPENED_PROJECTS:
                    self.useData.OPENED_PROJECTS.remove(path)
                    self.useData.OPENED_PROJECTS.insert(0, path)
                else:
                    self.useData.OPENED_PROJECTS.insert(0, path)
                if show:
                    self.pycoder.showProject(path)
                # Create library directory if it does not exist
                lib_dir = os.path.join(path, "Resources", "Library")
                os.makedirs(lib_dir, exist_ok=True)
                # Trigger library load (the library is shared across all projects)
                # No need to call projectWindow.loadLibrary() since Library singleton
            except Exception as err:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.error(
                    repr(traceback.format_exception(exc_type, exc_value,
                             exc_traceback)))
                print("DEBUG: exception in loadProject for", path, ":", str(err))
                QtWidgets.QApplication.restoreOverrideCursor()
                message = QtWidgets.QMessageBox.warning(self, _("Failed Open"),
                                                    _("Problem opening project: \n\n") + str(err))
            QtWidgets.QApplication.restoreOverrideCursor()

    def closeProject(self):
        window = self.projectWindowStack.currentWidget()
        path = window.projectPathDict["root"]
        closed = window.closeWindow()
        if closed:
            self.pycoder.removeProject(window)
            self.useData.OPENED_PROJECTS.remove(path)

    def createProject(self, data):
        self.createProjectThread.create(data)
        self.busyWidget.showBusy(True, _("Creating project... please wait!"))

    def finalizeNewProject(self):
        self.busyWidget.showBusy(False)
        if self.createProjectThread.error is not False:
            message = QtWidgets.QMessageBox.warning(self, _("New Project"),
                                                _("Failed to create project:\n\n") + self.createProjectThread.error)
        else:
            projectPath = os.path.normpath(
                self.createProjectThread.projectPath)  # otherwise an error will occur in rope
            self.loadProject(projectPath, True, True)
