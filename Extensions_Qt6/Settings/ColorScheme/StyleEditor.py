import sys
import os
import json
import xml.etree.ElementTree as ET

from PyQt6 import QtCore, QtGui, QtWidgets

# QtXml cleanup - JSON for editor properties.
from PyQt6.Qsci import QsciScintilla

from Extensions_Qt6.Settings.ColorScheme.ColorChooser import ColorChooser


class StyleEditor(QtWidgets.QWidget):

    paperChanged = QtCore.pyqtSignal()

    def __init__(self, useData, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        self.useData = useData

        mainLayout = QtWidgets.QHBoxLayout()
        self.setLayout(mainLayout)
        mainLayout.setContentsMargins(0, 0, 0, 0)

        properties = self.loadDefaultProperties()
        self.propertyListWidget = QtWidgets.QListWidget()
        self.propertyListWidget.setSortingEnabled(True)
        for key, value in properties.items():
            if key != "Paper":
                self.propertyListWidget.addItem(QtWidgets.QListWidgetItem(key))
        self.propertyListWidget.itemSelectionChanged.connect(
            self.newPropertySelected)
        mainLayout.addWidget(self.propertyListWidget)

        vbox = QtWidgets.QVBoxLayout()
        mainLayout.addLayout(vbox)

        label = QtWidgets.QLabel("Background")
        label.setStyleSheet("background: lightgrey; padding: 2px;")
        vbox.addWidget(label)

        self.backgroundColorChooser = ColorChooser()
        self.backgroundColorChooser.colorChanged.connect(self.updateBackground)
        vbox.addWidget(self.backgroundColorChooser)

        label = QtWidgets.QLabel("Foreground")
        label.setStyleSheet("background: lightgrey; padding: 2px;")
        vbox.addWidget(label)

        self.foregroundColorChooser = ColorChooser()
        self.foregroundColorChooser.colorChanged.connect(self.updateForeground)
        vbox.addWidget(self.foregroundColorChooser)

        # Additional settings for elements that need them -------------------

        self.extra_settings_stack = QtWidgets.QStackedLayout()
        vbox.addLayout(self.extra_settings_stack)

        # empty stack for display when current property has no need of extra
        # settings
        stackWidget = QtWidgets.QWidget()
        self.extra_settings_stack.addWidget(stackWidget)

        # CALLTIP Highlight Color

        stackWidget = QtWidgets.QWidget()
        stackBox = QtWidgets.QVBoxLayout()
        stackBox.setContentsMargins(0, 0, 0, 0)
        stackWidget.setLayout(stackBox)
        self.extra_settings_stack.addWidget(stackWidget)

        label = QtWidgets.QLabel("Highlight Text")
        label.setStyleSheet("background: lightgrey; padding: 2px;")
        stackBox.addWidget(label)

        hbox = QtWidgets.QHBoxLayout()
        stackBox.addLayout(hbox)

        self.callTipHighlightColorChooser = ColorChooser()
        self.callTipHighlightColorChooser.colorChanged.connect(
            self.updateCalltipHighlight)
        hbox.addWidget(self.callTipHighlightColorChooser)

        # MARGIN FONT

        stackWidget = QtWidgets.QWidget()
        stackBox = QtWidgets.QVBoxLayout()
        stackBox.setContentsMargins(0, 0, 0, 0)
        stackWidget.setLayout(stackBox)
        self.extra_settings_stack.addWidget(stackWidget)

        label = QtWidgets.QLabel("Margin Font")
        label.setStyleSheet("background: lightgrey; padding: 2px;")
        stackBox.addWidget(label)

        self.fontButton = QtWidgets.QPushButton("Font")
        self.fontButton.clicked.connect(self.fontChanged)
        stackBox.addWidget(self.fontButton)

        # ----------------------------------------------------------------
        vbox.addStretch(1)

        self.paperBG = QtWidgets.QButtonGroup()

        label = QtWidgets.QLabel("Paper")
        label.setStyleSheet("background: lightgrey; padding: 2px;")
        vbox.addWidget(label)

        hbox = QtWidgets.QHBoxLayout()
        vbox.addLayout(hbox)

        self.paperPlainButton = QtWidgets.QRadioButton("Plain")
        self.paperBG.addButton(self.paperPlainButton)
        self.paperPlainButton.toggled.connect(self.paperScopeChanged)
        hbox.addWidget(self.paperPlainButton)

        self.paperCustomButton = QtWidgets.QRadioButton("Custom")
        self.paperBG.addButton(self.paperCustomButton)
        self.paperCustomButton.setChecked(True)
        self.paperCustomButton.toggled.connect(self.paperScopeChanged)
        hbox.addWidget(self.paperCustomButton)

        self.paperColorChooser = ColorChooser()
        self.paperColorChooser.colorChanged.connect(self.updatePaper)
        hbox.addWidget(self.paperColorChooser)

        self.setCurrentProperty("Default", "Python")

        self.paperColorChooser.setColor(self.currentProperties["Paper"][1])
        if self.currentProperties["Paper"][0] == "Plain":
            self.paperColorChooser.setDisabled(True)

        self.propertyListWidget.setCurrentRow(0)

    def paperScopeChanged(self):
        if self.paperBG.checkedButton().text() == 'Plain':
            self.paperColorChooser.setDisabled(True)
        else:
            self.paperColorChooser.setDisabled(False)
        self.currentProperties["Paper"][
            0] = self.paperBG.checkedButton().text()
        self.paperColorChooser.setColor(self.currentProperties["Paper"][1])
        self.paperChanged.emit()

    def loadDefaultProperties(self):
        # Platform specific fonts
        if sys.platform == 'win32':
            defaultFont = 'Consolas'
        elif sys.platform == 'darwin':
            defaultFont = 'Monaco'
        else:
            defaultFont = 'Bitstream Vera Sans Mono'

        properties = {"Edge Line": ['#aa557f', '#ffc6c2'],
                      "Number Margin": ['#ffffff', '#949494', defaultFont, 8, False, False],
                      "Fold Margin": ['#ffffff', '#ffffff'],
                      "Fold Markers": ['#ffffff', '#bababa'],
                      "Active Line": ['#d4ffd4', '#101010'],
                      "Selection": ['#aaddff', '#1e1e1e'],
                      "White Spaces": ['#ffffff', '#000000'],
                      "Matched Braces": ['#CCCCCC', '#000000'],
                      "Unmatched Braces": ['#ff5555', '#000000'],
                      "Calltips": ["#000000", "#ffffff", "#FF3333"],
                      "Indentation Guide": ['#ffffff', '#a8a8a8'],
                      "Warnings": ['#000000', '#ffffa9'],
                      "Errors": ['#000000', '#ffaaa7'],
                      "Paper": ['Plain', '#7FE87F']}
        return properties

    def newPropertySelected(self):
        self.currentPropertyName = \
            self.propertyListWidget.currentItem().text()
        self.currentPropertyAttrib = \
            self.currentProperties[
                self.currentPropertyName]

        self.backgroundColorChooser.setColor(self.currentPropertyAttrib[0])
        self.foregroundColorChooser.setColor(self.currentPropertyAttrib[1])

        if self.currentPropertyName == "Calltips":
            self.callTipHighlightColorChooser.setColor(
                self.currentPropertyAttrib[2])
            self.extra_settings_stack.setCurrentIndex(1)
        elif self.currentPropertyName == "Number Margin":
            self.extra_settings_stack.setCurrentIndex(2)
        else:
            self.extra_settings_stack.setCurrentIndex(0)

    def updateBackground(self, color):
        self.currentPropertyAttrib[0] = color

    def updateNumberMarginFont(self):
        self.currentProperties["Number Margin"][2] = self.fontBox.currentText()
        self.currentProperties["Number Margin"][
            3] = self.fontSizeBox.currentText()

    def showLineBackground(self):
        color = QtGui.QColor(self.backgroundHexLine.text())
        if color.isValid():
            self.updateBackground(color)

    def updateCalltipHighlight(self, color):
        self.currentPropertyAttrib[2] = color

    def updateForeground(self, color):
        self.currentPropertyAttrib[1] = color

    def updatePaper(self, color):
        self.currentProperties["Paper"][1] = color
        self.paperChanged.emit()

    def setCurrentProperty(self, propertyName, groupName):
        self.currentProperties = self.loadProperties(propertyName, groupName)
        if self.currentProperties["Paper"][0] == "Plain":
            self.paperPlainButton.setChecked(True)
        else:
            self.paperCustomButton.setChecked(True)

    def fontChanged(self):
        #currentfont = QtGui.QFont(self.currentPropertyAttrib[
        #                          2], self.currentPropertyAttrib[3])
        #currentfont.setBold(self.currentPropertyAttrib[4])
        #currentfont.setItalic(self.currentPropertyAttrib[5])
        #font = QtWidgets.QFontDialog().getFont(currentfont, self)
        currentfont = QtGui.QFont(self.currentPropertyAttrib[2], self.currentPropertyAttrib[3])
        currentfont.setBold(self.currentPropertyAttrib[4])
        currentfont.setItalic(self.currentPropertyAttrib[5])

        font, accepted = QtWidgets.QFontDialog().getFont(currentfont, self)

        #if font[1]:
        #if accepted:
        #    font = font[0]
        #    name = font.rawName()
        #    size = font.pointSize()
        #    bold = font.bold()
        #    italic = font.italic()
        #    self.currentPropertyAttrib[2] = name
        #    self.currentPropertyAttrib[3] = size
        #    self.currentPropertyAttrib[4] = bold
        #    self.currentPropertyAttrib[5] = italic

    def applyChanges(self, viewWidget, properties=None):
        if properties == None:
            properties = self.currentProperties

        viewWidget.setSelectionBackgroundColor(
            QtGui.QColor(properties["Selection"][0]))
        viewWidget.setSelectionForegroundColor(
            QtGui.QColor(properties["Selection"][1]))

        viewWidget.setIndentationGuidesBackgroundColor(
            QtGui.QColor(properties["Indentation Guide"][0]))
        viewWidget.setIndentationGuidesForegroundColor(
            QtGui.QColor(properties["Indentation Guide"][1]))

        viewWidget.setCallTipsBackgroundColor(
            QtGui.QColor(properties["Calltips"][0]))
        viewWidget.setCallTipsForegroundColor(
            QtGui.QColor(properties["Calltips"][1]))
        viewWidget.setCallTipsHighlightColor(QtGui.QColor(
            properties["Calltips"][2]))

        # Margins colors
        # line numbers margin
        viewWidget.setMarginsBackgroundColor(
            QtGui.QColor(properties["Number Margin"][0]))
        viewWidget.setMarginsForegroundColor(
            QtGui.QColor(properties["Number Margin"][1]))

        marginFont = QtGui.QFont(properties["Number Margin"][2],
                                 properties["Number Margin"][3])
        marginFont.setBold(properties["Number Margin"][4])
        marginFont.setItalic(properties["Number Margin"][5])
        viewWidget.setMarginsFont(marginFont)

        # folding margin colors (foreground, background)
        viewWidget.setFoldMarginColors(
            QtGui.QColor(properties["Fold Margin"][0]),
            QtGui.QColor(properties["Fold Margin"][1]))

        # Edge Mode shows a vertical bar at specific number of chars
        viewWidget.setEdgeColor(QtGui.QColor(
            properties["Edge Line"][1]))

        # Folding visual : we will use boxes
        viewWidget.setFoldMarkersColors(
            QtGui.QColor(properties["Fold Markers"][0]),
            QtGui.QColor(properties["Fold Markers"][1]))

        # Braces matching
        viewWidget.setMatchedBraceBackgroundColor(
            QtGui.QColor(properties["Matched Braces"][0]))
        viewWidget.setMatchedBraceForegroundColor(
            QtGui.QColor(properties["Matched Braces"][1]))
        viewWidget.setUnmatchedBraceBackgroundColor(
            QtGui.QColor(properties["Unmatched Braces"][0]))
        viewWidget.setUnmatchedBraceForegroundColor(
            QtGui.QColor(properties["Unmatched Braces"][1]))

        # Editing line color
        viewWidget.setCaretWidth(2)
        viewWidget.setCaretLineBackgroundColor(
            QtGui.QColor(properties["Active Line"][0]))
        viewWidget.setCaretForegroundColor(
            QtGui.QColor(properties["Active Line"][1]))

        viewWidget.setWhitespaceBackgroundColor(
            QtGui.QColor(properties["White Spaces"][0]))
        viewWidget.setWhitespaceForegroundColor(
            QtGui.QColor(properties["White Spaces"][1]))

        viewWidget.annotationWarningStyle = QsciScintilla.STYLE_LASTPREDEFINED + 1
        viewWidget.SendScintilla(QsciScintilla.SCI_STYLESETFORE,
                                 viewWidget.annotationWarningStyle, QtGui.QColor(properties["Warnings"][0]))
        viewWidget.SendScintilla(QsciScintilla.SCI_STYLESETBACK,
                                 viewWidget.annotationWarningStyle, QtGui.QColor(properties["Warnings"][1]))

        viewWidget.annotationErrorStyle = viewWidget.annotationWarningStyle + 1
        viewWidget.SendScintilla(QsciScintilla.SCI_STYLESETFORE,
                                 viewWidget.annotationErrorStyle, QtGui.QColor(properties["Errors"][0]))
        viewWidget.SendScintilla(QsciScintilla.SCI_STYLESETBACK,
                                 viewWidget.annotationErrorStyle, QtGui.QColor(properties["Errors"][1]))

        return properties["Paper"]

    def loadProperties(self, style_name, groupName):
        if style_name == "Default":
            properties = self.loadDefaultProperties()

            return properties

        # QtXml cleanup: JSON + legacy XML support via ET
        for ext in (".json", ".xml"):
            try:
                path = os.path.join(self.useData.appPathDict[
                                "stylesdir"], groupName, style_name + ext)
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if ext == ".json":
                    data = json.loads(content)
                    props = {}
                    for name, val in data.get("editor", {}).items():
                        props[name] = [val.get("background", ""), val.get("foreground", "")]
                        if name == "Calltips":
                            props[name].append(val.get("highLight", ""))
                        if name == "Number Margin":
                            props[name].append(val.get("font", ""))
                            props[name].append(int(val.get("size", 10)))
                            props[name].append(bool(val.get("bold", False)))
                            props[name].append(bool(val.get("italic", False)))
                    return props
                else:
                    # Legacy XML: only parse <editor> section
                    root = ET.fromstring(content)
                    editorElement = root.find(".//editor")
                    props = {}
                    if editorElement is not None:
                        for tag in editorElement.findall("property"):
                            name = tag.text or ""
                            props[name] = [
                                tag.get("background", ""),
                                tag.get("foreground", "")
                            ]
                            if name == "Calltips":
                                props[name].append(tag.get("highLight", ""))
                            if name == "Number Margin":
                                props[name].append(tag.get("font", ""))
                                props[name].append(int(tag.get("size", 10)))
                                props[name].append(tag.get("bold", "False") == "True")
                                props[name].append(tag.get("italic", "False") == "True")
                    return props
            except Exception:
                continue
        return {}
