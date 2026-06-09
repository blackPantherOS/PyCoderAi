import sys
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.Qsci import QsciScintilla

class Handle(QtWidgets.QFrame):
    """Draggable viewport indicator on the minimap (VSCode-style semi-transparent box)."""
    def __init__(self, parent):
        super().__init__(parent)
        
        self.minimap = parent
        self.editor = parent.editor
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        # VSCode-style viewport slider: more visible semi-transparent box that indicates current view.
        # Uses light color for dark themes; adjust alpha for subtlety.
        self.setStyleSheet("""
            background: rgba(180, 180, 200, 60);
            border: 1px solid rgba(200, 200, 220, 90);
        """)
        
        self.pressed = False
        self.scroll_margins = None
        
        self.minimapScrollBar = self.minimap.editor.verticalScrollBar()
        
    def updateScrollMargins(self, margins):
        self.scroll_margins = margins
        
    def mousePressEvent(self, event):
        self.pressed = True
        self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.pressed = False
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if not self.pressed:
            return
        relativePos = self.mapToParent(event.pos())
        y = int(relativePos.y() - (self.height() / 2))
        if y < 0:
            y = 0
        max_y = self.minimap.height() - self.height()
        if y > max_y:
            y = max_y
        self.move(0, y)
        self.minimap.updateEditorScrollPos(y)

    def updatePosition(self):
        # Approximate height based on visible lines in minimap scale
        lines_on_screen = self.editor.linesOnScreen()
        line_height = self.minimap.textHeight(0)
        height = max(20, line_height * lines_on_screen)
        self.setFixedHeight(height)
        self.scroll_margins = (height, self.minimap.height() - height)
        
    def move_slider(self, y):
        self.move(0, int(y))

class MiniMap(QsciScintilla):
    def __init__(self, editor=None, parent=None):
        QsciScintilla.__init__(self, parent)
        
        self.editor = editor
    
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.viewport().setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMarginWidth(1, 0)
        font = QtGui.QFont()
        font.setPointSize(1)  # miniature overview (VSCode-like dense view)
        self.setFont(font)
        self.setDocument(self.editor.document())
        
        # Follow the editor's color scheme for proper syntax colors in the minimap
        # (instead of default white background / black text)
        # Note: use attribute .lexer (not method call), because editors shadow the QsciScintilla.lexer() method
        # with an instance attribute self.lexer = the_lexer_instance
        current_lexer = getattr(self.editor, 'lexer', None)
        if current_lexer:
            self.setLexer(current_lexer)
        
        # Copy style colors from the main editor so the minimap matches the current theme/scheme
        # (dark theme, syntax highlighting etc.). This makes the minimap show colored "lines"
        # / structure following the editor's ColorScheme instead of plain white background.
        for style in range(0, 256):
            try:
                fore = self.editor.SendScintilla(QsciScintilla.SCI_STYLEGETFORE, style)
                back = self.editor.SendScintilla(QsciScintilla.SCI_STYLEGETBACK, style)
                self.SendScintilla(QsciScintilla.SCI_STYLESETFORE, style, fore)
                self.SendScintilla(QsciScintilla.SCI_STYLESETBACK, style, back)
            except Exception:
                pass
        
        # Set default paper/background to match editor's current scheme
        try:
            default_back = self.editor.SendScintilla(QsciScintilla.SCI_STYLEGETBACK, QsciScintilla.STYLE_DEFAULT)
            self.setPaper(QtGui.QColor(default_back))
            # Also set caret invisible in minimap (no blinking cursor needed)
            self.setCaretWidth(0)
        except Exception:
            pass
        
        # Force tiny font size AFTER style copy, so it's a true minimap overview (condensed structure with colors),
        # not a readable code editor. The style copy brings theme colors, but we override size to 1pt.
        tiny_font = QtGui.QFont("Courier New", 1)
        self.setFont(tiny_font)
        for style in range(0, 256):
            try:
                self.SendScintilla(QsciScintilla.SCI_STYLESETFONT, style, b"Courier New")
                self.SendScintilla(QsciScintilla.SCI_STYLESETSIZE, style, 1)
            except Exception:
                pass
        
        # Width controlled by parent QSplitter (drag the separator between editor and minimap
        # to increase/decrease width - VSCode style adjustable minimap).
        # Defaults; overridden by EditorSplitter to enforce 100-300.
        self.setMinimumWidth(100)
        
        self.editorVerticalScrollBar = self.editor.verticalScrollBar()
        
        self.handle = Handle(self)
        self.turnOn()
        
        # Initial updates so the handle (viewport slider) is visible and positioned correctly from the start
        self.updateHandleGeometry()
        self.updateHandlePosition()
        self.handle.show()
        self.handle.raise_()
        
        # Live sync with main editor (VSCode-like: minimap always reflects current view + content)
        self.editor.verticalScrollBar().valueChanged.connect(self.updateHandlePosition)
        self.editor.textChanged.connect(self.updateHandleGeometry)
        if hasattr(self.editor, 'firstVisibleLineChanged'):
            try:
                self.editor.firstVisibleLineChanged.connect(self.updateHandlePosition)
            except Exception:
                pass

        # Load saved zoom and create hover +/- controls for adjusting minimap font size (content scale)
        settings = QtCore.QSettings("PyCoder", "PyCoder")
        zoom = settings.value("minimapZoom", 1, type=int)
        self.current_zoom = max(1, min(8, zoom))
        self._apply_mini_font(self.current_zoom)

        self._create_zoom_controls()

    def _create_zoom_controls(self):
        """Small +/- buttons shown on hover over minimap to adjust the overview scale."""
        self.zoom_widget = QtWidgets.QWidget(self)
        self.zoom_widget.setStyleSheet("background: rgba(40,40,40,180); border: 1px solid #666;")
        hbox = QtWidgets.QHBoxLayout(self.zoom_widget)
        hbox.setContentsMargins(1,1,1,1)
        hbox.setSpacing(1)
        self.btn_zoom_out = QtWidgets.QPushButton("−", self.zoom_widget)
        self.btn_zoom_in = QtWidgets.QPushButton("+", self.zoom_widget)
        for btn in (self.btn_zoom_out, self.btn_zoom_in):
            btn.setFixedSize(14, 14)
            btn.setStyleSheet("font-size: 9pt; padding: 0px; color: white; background: transparent;")
            btn.setFlat(True)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        hbox.addWidget(self.btn_zoom_out)
        hbox.addWidget(self.btn_zoom_in)
        self.zoom_widget.adjustSize()
        self.zoom_widget.hide()

    def enterEvent(self, event):
        if hasattr(self, 'zoom_widget') and self.zoom_widget:
            self.zoom_widget.show()
            self.zoom_widget.raise_()
            w = self.zoom_widget.width()
            self.zoom_widget.move(self.width() - w - 3, 3)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if hasattr(self, 'zoom_widget') and self.zoom_widget:
            # small delay so moving mouse to the buttons doesn't hide immediately
            QtCore.QTimer.singleShot(400, self._maybe_hide_zoom)
        super().leaveEvent(event)

    def _maybe_hide_zoom(self):
        if hasattr(self, 'zoom_widget') and self.zoom_widget:
            if not self.underMouse() and not self.zoom_widget.underMouse():
                self.zoom_widget.hide()

    def zoom_in(self):
        self.current_zoom = min(8, self.current_zoom + 1)
        self._apply_mini_font(self.current_zoom)
        self._save_zoom()

    def zoom_out(self):
        self.current_zoom = max(1, self.current_zoom - 1)
        self._apply_mini_font(self.current_zoom)
        self._save_zoom()

    def _apply_mini_font(self, size):
        """Apply the given point size to the minimap for zoom effect."""
        self.current_zoom = size
        tiny_font = QtGui.QFont("Courier New", size)
        self.setFont(tiny_font)
        for style in range(0, 256):
            try:
                self.SendScintilla(QsciScintilla.SCI_STYLESETFONT, style, b"Courier New")
                self.SendScintilla(QsciScintilla.SCI_STYLESETSIZE, style, size)
            except Exception:
                pass
        self.updateHandleGeometry()
        self.updateHandlePosition()

    def _save_zoom(self):
        settings = QtCore.QSettings("PyCoder", "PyCoder")
        settings.setValue("minimapZoom", self.current_zoom)
        settings.sync()

    def resizeEvent(self, event):
        super(MiniMap, self).resizeEvent(event)
        self.handle.setFixedWidth(self.width())
        self.updateHandleGeometry()
        self.updateHandlePosition()
        # reposition zoom controls if visible
        if hasattr(self, 'zoom_widget') and self.zoom_widget.isVisible():
            w = self.zoom_widget.width()
            self.zoom_widget.move(self.width() - w - 3, 3)
        
    def mousePressEvent(self, event):
        """Clicking anywhere on the minimap jumps the editor (VSCode scrollbar-like behavior)."""
        super(MiniMap, self).mousePressEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Proportional jump: click position in minimap -> corresponding position in main editor
            y = event.pos().y()
            total_lines = max(1, self.editor.lines())
            target_line = int((y / max(1, self.height())) * total_lines)
            self.editor.showLine(target_line)
            # Update handle immediately
            self.updateHandlePosition()
        
    def updateHandlePosition(self):
        """Keep the handle (viewport box) in sync with the main editor's scroll position."""
        if self.handle.pressed:
            return
        try:
            first = self.editor.firstVisibleLine()
            total = max(1, self.editor.lines())
            frac = first / total
            y = int(frac * max(1, self.height() - self.handle.height()))
            self.handle.move_slider(y)
        except Exception:
            pass
        
    def updateHandleGeometry(self):
        """Update the handle size based on visible portion (VSCode-like overview box)."""
        if self.handle.pressed:
            return
        try:
            lines_on_screen = self.editor.linesOnScreen()
            line_height = self.textHeight(0)
            height = max(20, line_height * lines_on_screen)
            self.handle.setFixedHeight(height)
            self.handle.updateScrollMargins((height, self.height() - height))
            self.updateHandlePosition()
        except Exception:
            pass
            
    def updateEditorScrollPos(self, y):
        """Called from handle drag: scroll the main editor proportionally (scrollbar behavior)."""
        try:
            max_y = max(1, self.height() - self.handle.height())
            frac = y / max_y
            sb = self.editorVerticalScrollBar
            sb.setValue(int(frac * sb.maximum()))
        except Exception:
            pass
            
    def wheelEvent(self, event):
        super(MiniMap, self).wheelEvent(event)
        self.editor.wheelEvent(event)
        
    def turnOn(self):
        self.editor.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.handle.setFixedWidth(self.width() if self.width() > 0 else 120)
        self.show()
        
    def turnOff(self):
        self.editor.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.hide()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    main = MiniMap()
    main.show()

    sys.exit(app.exec())
