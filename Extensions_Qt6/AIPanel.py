#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Panel for PyCoderAi
Provides a user interface for AI assistant features
"""

import sys
import os
import datetime

# Debug logger – appends important events to DEBUG_LOG.md always, and
# verbose debug prints when PYCODER_DEBUG_AI=1.
# Critical events (ERROR, WARN, CHAIN, FAIL) are always captured so the user
# can always debug problems without setting an env var.
DEBUG_AI = os.getenv("PYCODER_DEBUG_AI", "0") == "1"

def debug_print(message):
    """Append a debug line to DEBUG_LOG.md.
    Always writes messages containing ERROR, WARN, CHAIN, or FAIL.
    Other DEBUG messages only when PYCODER_DEBUG_AI=1.
    """
    is_critical = any(tag in message for tag in ["[ERROR", "[WARN", "[CHAIN", "[RESPONSE", "[USER", "FAIL", "ERROR SIGNAL"])
    if not DEBUG_AI and not is_critical:
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    try:
        with open("DEBUG_LOG.md", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception:
        # If we cannot write the file, fall back to stdout so we don't crash
        print(message)

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
import gettext
import os

# gettext setup for internationalization
def _(message):
    """Simple translation wrapper - returns the message as-is for now."""
    return message

from Extensions_Qt6.AIAssistant import AIAssistant, AIWorkerThread
# Import the ollama module/variable from AIAssistant's scope (fixed: no comma-tuple bug)
import Extensions_Qt6.AIAssistant as _ai_assistant_module
ollama = getattr(_ai_assistant_module, 'ollama', None)


def _safe_parent(obj):
    """Get the Qt parent widget of a QObject safely. In PyQt6, parent() is a
    method, NOT an attribute — so getattr(obj, 'parent', None) returns the bound
    method, never the actual parent. This helper calls the method properly.
    Falls back to None on any error."""
    if obj is None:
        return None
    try:
        return obj.parent()
    except (AttributeError, TypeError):
        return None


class FlowLayout(QtWidgets.QLayout):
    """A simple flow layout that wraps widgets to the next line when they don't fit.
    Used for AIPanel controls so they can stack vertically when the dock is narrow
    (e.g. side-docked on ultrawide monitors).
    """
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        # PyQt6 is very inconsistent across different builds/installations
        # regarding whether Qt.Orientations exists (the flags type).
        # The method MUST NOT raise, otherwise Qt's layout engine spams
        # this error on every resize/layout pass (as seen with the trio
        # excepthook noise).
        #
        # Strategy: try the "correct" ways first, then fall back to
        # Qt.Orientation(0) which some builds accept for the zero-flags case,
        # and finally plain 0 as last resort (even if it may cause a TypeError
        # in very strict bindings, at least we stop the AttributeError loop).
        for candidate in (
            lambda: Qt.Orientations(Qt.Orientation(0)),
            lambda: Qt.Orientations(0),
            lambda: QtCore.Qt.Orientations(QtCore.Qt.Orientation(0)),
            lambda: QtCore.Qt.Orientations(0),
            lambda: Qt.Orientation(0),
            lambda: 0,
        ):
            try:
                return candidate()
            except (AttributeError, TypeError):
                continue
        # If absolutely everything fails, return 0.
        return 0

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QtCore.QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacing = self.spacing()
        for item in self.itemList:
            nextX = x + item.sizeHint().width() + spacing
            if nextX - spacing > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spacing
                nextX = x + item.sizeHint().width() + spacing
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()

    def addSpacing(self, size):
        """Support addSpacing() for compatibility with original HBox code.
        Inserts a fixed-width horizontal spacer item.
        """
        self.addItem(QtWidgets.QSpacerItem(
            size, 0,
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Minimum
        ))

    def addStretch(self, stretch=0):
        """Support addStretch() (optional, for completeness).
        Inserts an expanding spacer.
        """
        self.addItem(QtWidgets.QSpacerItem(
            0, 0,
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum
        ))



# ── Python syntax highlighter for chat code blocks ────────────────────

class _PythonHighlighter(QtCore.QObject):
    """Apply Python syntax highlighting to a QTextEdit.
    Usage: _PythonHighlighter(text_edit).highlight(document)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Build regex patterns
        self.keywords = set([
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else", "except",
            "finally", "for", "from", "global", "if", "import", "in", "is",
            "lambda", "nonlocal", "not", "or", "pass", "raise", "return",
            "try", "while", "with", "yield", "self", "cls",
        ])
        self.builtins = set([
            "print", "len", "range", "int", "str", "float", "list", "dict",
            "set", "tuple", "bool", "open", "type", "super", "isinstance",
            "hasattr", "getattr", "setattr", "delattr", "repr", "abs",
            "all", "any", "bin", "chr", "dir", "enumerate", "eval",
            "exec", "filter", "format", "frozenset", "globals", "hex",
            "id", "input", "iter", "locals", "map", "max", "min",
            "next", "object", "oct", "ord", "pow", "property",
            "reversed", "round", "slice", "sorted", "staticmethod",
            "sum", "vars", "zip", "__import__",
        ])
        # PyQt6 specific
        self.pyqt_classes = set([
            "QWidget", "QDialog", "QMainWindow", "QFrame", "QLabel",
            "QPushButton", "QComboBox", "QCheckBox", "QTextEdit",
            "QListWidget", "QListWidgetItem", "QTimer", "QThread",
            "QVBoxLayout", "QHBoxLayout", "QGridLayout", "QSplitter",
            "QAction", "QMenu", "QSystemTrayIcon", "QMessageBox",
            "QProgressBar", "QApplication", "QIcon", "QColor", "QFont",
            "QObject", "pyqtSignal", "pyqtSlot", "Qt",
            "QSizePolicy", "QSpacerItem", "QFileDialog", "QInputDialog",
            "QToolTip", "QCursor",
        ])

    def _apply_format(self, text_edit, start, length, color, bold=False, italic=False):
        """Apply a QTextCharFormat to a range in the document."""
        cursor = text_edit.textCursor()
        cursor.setPosition(start)
        cursor.movePosition(
            QtGui.QTextCursor.MoveOperation.NextCharacter,
            QtGui.QTextCursor.MoveMode.KeepAnchor,
            length
        )
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QColor(color))
        if bold:
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        cursor.mergeCharFormat(fmt)

    def highlight_text(self, text_edit):
        """Apply syntax highlighting to the QTextEdit content.
        Uses a simple two-pass approach: first comment/string detection,
        then keyword/identifier coloring on the remaining text.
        """
        doc = text_edit.document()
        plain = doc.toPlainText()

        # Track ranges that are already colored (comments, strings)
        colored_ranges = set()

        # ── 1. Comments (# ...) ──
        import re as _re3
        for m in _re3.finditer(r"#[^\n]*", plain):
            start, end = m.start(), m.end()
            self._apply_format(text_edit, start, end - start, "#6a9955")  # green
            for i in range(start, end):
                colored_ranges.add(i)

        # ── 2. Strings ('''/""" single/multi-line, '...', "...") ──
        for m in _re3.finditer(r"(\"\"\"[^\"]*\"\"\"|'''[^']*'''|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")", plain):
            start, end = m.start(), m.end()
            self._apply_format(text_edit, start, end - start, "#ce9178")  # orange
            for i in range(start, end):
                colored_ranges.add(i)

        # ── 3. F-strings (f"...") ──
        for m in _re3.finditer(r'(f"[^"]*"|f\'[^\']*\')', plain):
            start, end = m.start(), m.end()
            self._apply_format(text_edit, start, end - start, "#ce9178")
            for i in range(start, end):
                colored_ranges.add(i)

        # ── 4. Decorators (@...) ──
        for m in _re3.finditer(r"@\w+", plain):
            start, end = m.start(), m.end()
            self._apply_format(text_edit, start, end - start, "#dcdcaa")  # yellow
            for i in range(start, end):
                colored_ranges.add(i)

        # ── 5. Numbers ──
        for m in _re3.finditer(r"\b(0x[0-9a-fA-F]+|\d+\.?\d*[eE]?[+-]?\d*|\.\d+)\b", plain):
            start, end = m.start(), m.end()
            # Skip if inside a colored range
            if any(i in colored_ranges for i in range(start, end)):
                continue
            self._apply_format(text_edit, start, end - start, "#b5cea8")  # light green
            for i in range(start, end):
                colored_ranges.add(i)

        # ── 6. Keywords + PyQt classes + builtins ──
        for m in _re3.finditer(r"\b([a-zA-Z_]\w*)\b", plain):
            start, end = m.start(), m.end()
            if any(i in colored_ranges for i in range(start, end)):
                continue
            word = m.group(1)
            if word in self.keywords:
                self._apply_format(text_edit, start, end - start, "#569cd6", bold=True)  # blue bold
            elif word in self.pyqt_classes:
                self._apply_format(text_edit, start, end - start, "#4ec9b0", bold=True)  # teal bold
            elif word in self.builtins:
                self._apply_format(text_edit, start, end - start, "#dcdcaa")  # yellow
            for i in range(start, end):
                colored_ranges.add(i)


class AIPanel(QtWidgets.QWidget):
    """
    AI Panel widget that provides AI assistant functionality
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.ai_assistant = AIAssistant(self)
        self.current_editor = None

        # History tracking
        self.history_count = 0
        self._pending_prompt = ""  # Store last sent prompt for history
        self.prompt_history = []  # List of previous user prompts for Up/Down navigation
        self.history_index = -1
        self.message_count = 0  # For numbering messages in chat (for quote/reply)

        # Continuation state for the agent tool loop
        self._pending_ai_question = None  # When ASK_USER is used, saved here for next-turn context

        # Orchestration state for multi-model pipeline
        self._orchestration_manager = None
        self._pipeline_result_buffer = ""

        # Font size tracking
        self.font_size = 12  # Default font size for prompt and chat messages

        # Streaming state for progressive editor writing
        self._stream_buffer = ""        # accumulated token buffer for current response
        self._in_code_block = False     # True when inside a ``` block
        self._code_block_buffer = ""    # accumulated code content inside a ``` block
        self._lang = ""                 # language tag of current code block
        self._backtick_count = 0        # count consecutive backticks to detect end

        # Auto-preload state: when a request arrives and the model isn't loaded,
        # we automatically preload and then dispatch the pending request.
        self._pending_request = None    # (request_type, code) tuple for deferred dispatch
        self._auto_preloading = False   # True when auto-preload is in progress
        self._explicitly_preloaded = False  # True after successful preload (manual or auto)

        # Allow the panel to expand and shrink as needed
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        # Setup UI
        self.init_ui()
        self.setup_connections()

        # Initialize language to first (Hungarian) and set on assistant
        self.lang_combo.setCurrentIndex(0)
        self._on_language_changed(0)

        # Load persisted chat history (until clear or max 50)
        self._load_chat_history()

    def _resource_path(self, relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller"""
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        # Go up one level to get to Resources
        base_path = os.path.dirname(base_path)
        return os.path.join(base_path, relative_path)

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Header
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QtWidgets.QLabel(_("AI Assistant"))
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.header_label)

        header_layout.addStretch()

        self.busy_indicator = QtWidgets.QLabel()
        self.busy_indicator.setPixmap(QtGui.QPixmap(self._resource_path("Resources/images/gear.png")))
        self.busy_indicator.setVisible(False)
        header_layout.addWidget(self.busy_indicator)

        main_layout.addLayout(header_layout)

        # Model / control bar - now uses FlowLayout so buttons and dropdowns can wrap
        # to the next line (stack vertically) when the panel is narrow, e.g. when the
        # Tools Panel is docked to the left or right side on ultrawide monitors.
        # This removes the previous fixed minimum width caused by the rigid HBox.
        model_controls = QtWidgets.QWidget()
        model_flow = FlowLayout(model_controls)
        model_flow.setContentsMargins(0, 0, 0, 0)
        model_flow.setSpacing(6)
        model_controls.setLayout(model_flow)

        model_flow.addWidget(QtWidgets.QLabel(_("Model:")))
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setMinimumWidth(180)  # slightly reduced to help wrapping
        model_flow.addWidget(self.model_combo)

        # Preload button
        self.preload_btn = QtWidgets.QPushButton(_("Preload"))
        self.preload_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/reload.png")))
        self.preload_btn.setToolTip(_("Preload selected model into memory"))
        # Removed setFixedWidth so the button can be smaller when space is tight
        self.preload_btn.setEnabled(False)
        model_flow.addWidget(self.preload_btn)

        # Auto-preload checkbox for the last selected/remembered model (convenience)
        self.auto_preload_cb = QtWidgets.QCheckBox(_("Auto-preload"))
        self.auto_preload_cb.setToolTip(_("Automatically preload the last selected model on startup (Ollama only)"))
        model_flow.addWidget(self.auto_preload_cb)

        # Cancel button
        self.cancel_btn = QtWidgets.QPushButton(_("Cancel"))
        self.cancel_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/stop.png")))
        self.cancel_btn.setToolTip(_("Cancel current AI request"))
        self.cancel_btn.setEnabled(False)
        model_flow.addWidget(self.cancel_btn)

        # Action buttons: Suggest | Debug | Explain | Fix
        self.suggest_btn = QtWidgets.QPushButton(_("Suggest"))
        self.suggest_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/lightbulb.png")))
        self.suggest_btn.setToolTip(_("Get AI suggestions for code improvements"))
        self.suggest_btn.setStyleSheet("QPushButton { background-color: #ffff66; color: black; border: 1px solid #ffcc00; border-radius: 3px; padding: 4px; }")
        model_flow.addWidget(self.suggest_btn)

        self.debug_btn = QtWidgets.QPushButton(_("Debug"))
        self.debug_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/issue.png")))
        self.debug_btn.setToolTip(_("Find bugs and errors in the code"))
        self.debug_btn.setStyleSheet("QPushButton { background-color: #ff7f50; color: white; border: 1px solid #ff4500; border-radius: 3px; padding: 4px; }")
        model_flow.addWidget(self.debug_btn)

        self.explain_btn = QtWidgets.QPushButton(_("Explain"))
        self.explain_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/about.png")))
        self.explain_btn.setToolTip(_("Get AI explanation of the code"))
        self.explain_btn.setStyleSheet("QPushButton { background-color: #66ffff; color: black; border: 1px solid #00ccff; border-radius: 3px; padding: 4px; }")
        model_flow.addWidget(self.explain_btn)

        self.fix_btn = QtWidgets.QPushButton(_("Fix"))
        self.fix_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/gear.png")))
        self.fix_btn.setToolTip(_("Get AI suggestions to fix errors"))
        self.fix_btn.setStyleSheet("QPushButton { background-color: #66ff66; color: black; border: 1px solid #33cc33; border-radius: 3px; padding: 4px; }")
        model_flow.addWidget(self.fix_btn)

        # Language selector
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems([_("Hungarian"), _("English"), _("Slovak"), _("German")])
        self.lang_combo.setMinimumWidth(110)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        model_flow.addWidget(self.lang_combo)

        # Chain / Pipeline mode selector
        self.chain_combo = QtWidgets.QComboBox()
        self.chain_combo.addItems([
            _("Simple"),
            _("2-Model Chain"),
            _("3-Model Chain"),
            _("Full Pipeline"),
        ])
        self.chain_combo.setToolTip(
            _("Simple: single model only (fastest, for simple questions).\n")
            + _("2-Model Chain: interpreter → coder (faster, no review).\n")
            + _("3-Model Chain: interpreter → coder → reviewer (best quality).\n")
            + _("Full Pipeline: interpreter → coder → reviewer + fix loop (old OrchestrationManager).")
        )
        self.chain_combo.setCurrentIndex(0)  # default: simple
        chain_label = QtWidgets.QLabel(_("AI Mode:"))
        chain_label.setStyleSheet("font-size: 10px; color: #888;")
        model_flow.addWidget(chain_label)
        model_flow.addWidget(self.chain_combo)

        # Helper model selector (for chain/pipeline — interpreter role)
        self.helper_model_combo = QtWidgets.QComboBox()
        self.helper_model_combo.setMinimumWidth(140)
        self.helper_model_combo.setToolTip(
            _("Model used as interpreter (analysis) in chain/pipeline modes.\n")
            + _("Leave as 'Auto' to auto-select a small model, or pick one manually.")
        )
        self.helper_label = QtWidgets.QLabel(_("Helper:"))
        self.helper_label.setStyleSheet("font-size: 10px; color: #888;")
        # Hidden by default — only shown in chain modes
        self.helper_model_combo.setVisible(False)
        self.helper_label.setVisible(False)
        model_flow.addWidget(self.helper_label)
        model_flow.addWidget(self.helper_model_combo)

        # Reviewer model selector (for 3-model chain and pipeline)
        self.reviewer_model_combo = QtWidgets.QComboBox()
        self.reviewer_model_combo.setMinimumWidth(140)
        self.reviewer_model_combo.setToolTip(
            _("Model used as reviewer in 3-model chain / pipeline.\n")
            + _("Leave as 'Auto' to reuse the Helper model (saves RAM).")
        )
        self.reviewer_label = QtWidgets.QLabel(_("Reviewer:"))
        self.reviewer_label.setStyleSheet("font-size: 10px; color: #888;")
        # Hidden by default — only shown in 3-model chain modes
        self.reviewer_model_combo.setVisible(False)
        self.reviewer_label.setVisible(False)
        model_flow.addWidget(self.reviewer_label)
        model_flow.addWidget(self.reviewer_model_combo)

        # Enable helper/reviewer selectors based on mode
        self.chain_combo.currentIndexChanged.connect(self._on_chain_mode_changed)

        # === Context window safety control ===
        model_flow.addSpacing(6)
        self.context_window_cb = QtWidgets.QCheckBox(_("Context window"))
        self.context_window_cb.setToolTip(
            _("Enable custom context window size (num_ctx) for Ollama models.\n")
            + _("When disabled the model uses its own default.\n")
            + _("Enabling this is the safety net for large files / long conversations.")
        )
        self.context_window_cb.setChecked(False)
        model_flow.addWidget(self.context_window_cb)

        self.context_window_combo = QtWidgets.QComboBox()
        self.context_window_combo.addItems([
            _("Model default"),
            _("4k (4096)"),
            _("8k (8192)"),
            _("16k (16384)"),
            _("32k (32768)")
        ])
        self.context_window_combo.setMinimumWidth(105)
        self.context_window_combo.setEnabled(False)  # only when checkbox is on
        model_flow.addWidget(self.context_window_combo)

        # Wire up
        self.context_window_cb.toggled.connect(self.context_window_combo.setEnabled)
        self.context_window_cb.toggled.connect(self._on_context_window_changed)
        self.context_window_combo.currentIndexChanged.connect(self._on_context_window_changed)

        # Progress bar for AI processing animation
        self.preload_progress = QtWidgets.QProgressBar()
        self.preload_progress.setMaximum(100)
        self.preload_progress.setValue(0)
        self.preload_progress.setVisible(False)
        model_flow.addWidget(self.preload_progress)

        # Add busy timer for progress bar animation during AI processing (sweeping indicator for normal requests).
        self._busy_timer = QtCore.QTimer(self)
        self._busy_timer.timeout.connect(self._step_progress)
        self._busy_timer.setInterval(50)
        self._busy_progress_value = 0
        self._is_processing = False

        # Preload progress animation: slowly ramps the bar from 10 → ~85% while the
        # model loads. When real progress arrives via _on_preload_progress it overrides.
        # On finish/error/cancel the timer is stopped.
        self._preload_timer = QtCore.QTimer(self)
        self._preload_timer.timeout.connect(self._step_preload_progress)
        self._preload_timer.setInterval(250)

        # Periodic check for model loaded state (to re-enable Preload button
        # and update its color when keep-alive expires and ollama unloads the model).
        self._model_state_timer = QtCore.QTimer(self)
        self._model_state_timer.timeout.connect(self._update_preload_button_state)
        self._model_state_timer.start(30000)  # every 30 seconds

        main_layout.addWidget(model_controls)

        # === Main chat area (conversation view) ===
        # Placed right after model controls, before input (per PLAN.md: chat on top, input at bottom)
        self.chat_display = QtWidgets.QListWidget()
        self.chat_display.setStyleSheet(
            #"background-color: #1e1e1e; color: #e0e0e0; border: 1px solid #333; border-radius: 4px;"
            "background-color: #1e1e1e; color: #e0e0e0; border: none; border-radius: 4px;"
        )
        self.chat_display.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.chat_display.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Finer wheel scrolling (smaller singleStep = smoother / more precise mouse wheel)
        vbar = self.chat_display.verticalScrollBar()
        vbar.setSingleStep(10)   # pixels per wheel notch - fine control
        vbar.setPageStep(80)
        self.chat_display.itemClicked.connect(self.on_history_item_clicked)
        # Note: chat_display is added to a QSplitter below (with composer) for resizable areas.

        # === Bottom composer (input field at the bottom - true chat experience) ===
        # Prompt input + controls live here so the conversation history fills the space above
        composer_container = QtWidgets.QFrame()
        composer_container.setStyleSheet(
            "QFrame { background-color: #252526; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        composer_v = QtWidgets.QVBoxLayout(composer_container)
        composer_v.setContentsMargins(6, 6, 6, 6)
        composer_v.setSpacing(4)

        self.prompt_input = QtWidgets.QTextEdit()
        self.prompt_input.setPlaceholderText(_("Type your question or instruction for the AI... (Enter = send, Shift+Enter = new line)"))
        self.prompt_input.setStyleSheet(
            "background-color: #1a1a1a; color: #ffffff; font-family: 'Courier New', monospace; border: none; padding: 4px;"
        )
        self.prompt_input.setMinimumHeight(48)
        # No hard maximum - the QSplitter handle above controls the overall composer height.
        # Allow the input to expand vertically within the resizable composer area.
        self.prompt_input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        composer_v.addWidget(self.prompt_input)

        # Enter-to-send (Shift+Enter = newline) - installed after widget creation
        self.prompt_input.installEventFilter(self)

        # Send row at bottom of composer - also uses FlowLayout for wrapping
        # when the panel (and thus the composer) is narrow.
        send_container = QtWidgets.QWidget()
        send_flow = FlowLayout(send_container)
        send_flow.setContentsMargins(0, 0, 0, 0)
        send_flow.setSpacing(4)
        send_container.setLayout(send_flow)

        self.send_btn = QtWidgets.QPushButton(_("Send"))
        self.send_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/flag-green.png")))
        self.send_btn.setToolTip(_("Send (or Enter)"))
        send_flow.addWidget(self.send_btn)

        self.clear_btn = QtWidgets.QPushButton(_("Clear"))
        self.clear_btn.setToolTip(_("Clear prompt"))
        send_flow.addWidget(self.clear_btn)

        # Small font controls
        self.decrease_font_btn = QtWidgets.QPushButton("–A")
        self.decrease_font_btn.setToolTip(_("Decrease font size"))
        send_flow.addWidget(self.decrease_font_btn)

        self.increase_font_btn = QtWidgets.QPushButton("+A")
        self.increase_font_btn.setToolTip(_("Increase font size"))
        send_flow.addWidget(self.increase_font_btn)

        # Clear chat (new for modern chat UX)
        self.clear_chat_btn = QtWidgets.QPushButton(_("🗑 Chat"))
        self.clear_chat_btn.setToolTip(_("Clear chat history"))
        send_flow.addWidget(self.clear_chat_btn)

        composer_v.addWidget(send_container)

        # Use a vertical QSplitter so user can drag the handle ("fogantyú") to resize
        # the prompt area height (composer) vs the chat area. This gives the requested
        # adjustable prompt field height.
        chat_prompt_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        chat_prompt_splitter.addWidget(self.chat_display)
        chat_prompt_splitter.addWidget(composer_container)
        chat_prompt_splitter.setStretchFactor(0, 1)  # chat grows more
        chat_prompt_splitter.setStretchFactor(1, 0)
        chat_prompt_splitter.setChildrenCollapsible(False)
        # Reasonable initial split (chat dominant)
        chat_prompt_splitter.setSizes([500, 90])

        main_layout.addWidget(chat_prompt_splitter)

        # Status bar (always at very bottom)
        self.status_label = QtWidgets.QLabel(_("Done"))
        self.status_label.setStyleSheet("color: #888; font-size: 9pt; padding-left: 4px;")
        main_layout.addWidget(self.status_label)

    def setup_connections(self):
        """Setup signal connections"""
        # Flag to prevent _on_model_changed → _save_last_model during initial
        # setup. Without this, _check_for_preloaded_model (which selects a model
        # and triggers currentIndexChanged) overwrites the saved model BEFORE
        # _load_last_model_setting can restore the user's actual last choice.
        self._setup_complete = False

        self.suggest_btn.clicked.connect(self.on_suggest_clicked)
        self.debug_btn.clicked.connect(self.on_debug_clicked)
        self.explain_btn.clicked.connect(self.on_explain_clicked)
        self.fix_btn.clicked.connect(self.on_fix_clicked)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        self.send_btn.clicked.connect(self.on_send_clicked)
        self.clear_btn.clicked.connect(self.on_clear_clicked)
        self.clear_chat_btn.clicked.connect(self.on_clear_chat_clicked)
        self.increase_font_btn.clicked.connect(self.on_increase_font)
        self.decrease_font_btn.clicked.connect(self.on_decrease_font)
        self.preload_btn.clicked.connect(self.on_preload_clicked)
        # Connect model combo box changes to preload model
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        # Connect language combo box changes
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)

        self.ai_assistant.chain_ready.connect(self._on_chain_ready)
        self.ai_assistant.chain_status.connect(self._on_chain_status)
        self.ai_assistant.suggestion_ready.connect(self.on_suggestion_ready)
        self.ai_assistant.explanation_ready.connect(self.on_explanation_ready)
        self.ai_assistant.custom_ready.connect(self.on_custom_response_ready)
        self.ai_assistant.fix_ready.connect(self.on_fix_ready)
        self.ai_assistant.error_occurred.connect(self.on_error)
        self.ai_assistant.stream_token.connect(self._on_stream_token)

        # Set icon theme based on system theme
        self.update_icon_theme()

        # Load models after connections are set up
        self.load_models()

        # Restore last selected model first, so the combo reflects user's preference
        # before we check preload state. This way _check_for_preloaded_model can
        # correctly set _explicitly_preloaded only for the currently-selected model.
        self._load_last_model_setting()
        self._load_auto_preload_setting()

        # Check for already loaded model — sets _explicitly_preloaded = True only
        # if the CURRENT combo model is found in ollama ps.
        self._check_for_preloaded_model()
        self._update_preload_button_state()

        # Setup complete — allow _on_model_changed to save changes from now on
        self._setup_complete = True

    def _is_ollama_model_loaded(self, model_name: str) -> bool:
        """Check /api/ps to see if the model is already resident with keep-alive.
        This makes the Preload button instantly "complete" if the model was
        loaded by other means (terminal ollama run, previous keep-alive, etc.).
        """
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/ps", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("models", []):
                    name = m.get("model") or m.get("name", "")
                    if name == model_name or name.startswith(model_name + ":"):
                        return True
        except Exception as e:
            debug_print(f"[WARN] ps check failed: {e}")
        return False

    def on_preload_clicked(self):
        """Handle preload button click - manually trigger model preload."""
        model = self.model_combo.currentText()
        raw_model = model.split(" (")[0]
        debug_print(f"[DEBUG] Preload started for: {raw_model}")
        if raw_model.startswith("ollama:"):
            model_name = raw_model[7:]

            # Fast path: if ollama ps already shows it loaded (with keep-alive),
            # complete the UI immediately. This fixes the case where terminal
            # or other means loaded the model, but the app's greeting-generate
            # was still "running" or the bar was stuck.
            if self._is_ollama_model_loaded(model_name):
                self.preload_progress.setVisible(True)
                self.preload_progress.setValue(100)
                QtCore.QTimer.singleShot(250, lambda: self.preload_progress.setVisible(False))
                self.preload_btn.setEnabled(False)
                self.cancel_btn.setEnabled(False)
                self.status_label.setText("Model already loaded (detected via ollama ps)")
                debug_print(f"[INFO] Preload skipped - {model_name} already in ps")
                # Mark as explicitly preloaded since user clicked preload
                self._explicitly_preloaded = True
                self._update_preload_button_state()
                return

            # Clean up any previous preload thread (safe, no crash on still-running)
            if getattr(self, 'preload_thread', None) and self.preload_thread.isRunning():
                try:
                    self.preload_thread.cancel()
                    self.preload_thread.quit()
                    self.preload_thread.wait(500)  # short wait only
                except Exception:
                    pass
                # Drop reference; let the old thread's own finished->deleteLater connection
                # handle its destruction when it actually exits.
                self.preload_thread = None
                # Reset UI from the aborted previous attempt (simple bar reset)
                self.preload_progress.setVisible(False)
                self.preload_progress.setValue(0)
                self.preload_btn.setEnabled(True)

            self.preload_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.preload_progress.setVisible(True)
            self.preload_progress.setValue(10)
            self.status_label.setText("Model loading... (first generation may be slow for large models)")
            # removed color to follow theme (was #0066cc blue, not visible)

            # Use greeting for preload in selected language (also sets keep_alive in the wrapper)
            lang = self.lang_combo.currentText().lower()
            if lang.startswith("hungar"):
                preload_prompt = "Hello! Welcome to PyCoder AI!"
            else:
                preload_prompt = f"Hello! Please greet me in {lang}."

            self.preload_thread = AIWorkerThread(
                None, raw_model, preload_prompt, "preload", False, True, 30
            )
            self.preload_thread.result_ready.connect(self._on_preload_ready)
            self.preload_thread.error_occurred.connect(self._on_preload_error)
            self.preload_thread.progress_update.connect(self._on_preload_progress)
            self.preload_thread.finished.connect(self._on_preload_finished)

            # Critical for avoiding "QThread: Destroyed while thread is still running":
            # We connect finished to deleteLater at creation time. This connection is
            # sacred — _cleanup_preload_thread must never disconnect it or call deleteLater.
            # The only safe moment to delete the QThread C++ object is from its own
            # finished signal, after the OS thread has fully exited.
            self.preload_thread.finished.connect(self.preload_thread.deleteLater)

            # Start animation: slowly ramp the bar from 10 → ~85% during loading.
            self._preload_timer.start()

            self.preload_thread.start()
        else:
            self.status_label.setText("Non-Ollama model - no preload needed")
            debug_print(f"[INFO] {raw_model} is a Claude model, no preload needed")

    # ── preload progress helpers ──────────────────────────────────────────

    def _step_preload_progress(self):
        """Animate the preload progress bar slowly toward ~85% during loading."""
        v = self.preload_progress.value()
        if v >= 85:
            self._preload_timer.stop()
            return
        # Slow, natural-looking progression
        step = max(1, (85 - v) // 15)
        self.preload_progress.setValue(min(v + step, 85))

    def _is_current_preload_thread(self):
        """Check whether the signal sender is still the active preload thread.
        Prevents stale results from cancelled/old threads corrupting UI.
        """
        sender = self.sender()
        return (
            sender is None
            or sender is getattr(self, 'preload_thread', None)
        )

    def _on_preload_progress(self, value):
        """Update progress bar during preload."""
        if not self._is_current_preload_thread():
            return
        debug_print(f"[DEBUG] Preload progress: {value}%")
        if value > self.preload_progress.value():
            self.preload_progress.setValue(min(100, value))

    def _on_preload_ready(self, result, _=None):
        """Handle preload completion from thread."""
        if not self._is_current_preload_thread():
            self._cleanup_preload_thread()
            return
        if not getattr(self, 'preload_progress', None) or not self.preload_progress.isVisible():
            self._cleanup_preload_thread()
            return

        self._preload_timer.stop()
        self.preload_progress.setValue(100)
        # Small delay so user sees 100% before hiding (back to the original simple 10->100 behavior)
        QtCore.QTimer.singleShot(300, lambda: self.preload_progress.setVisible(False))
        self.cancel_btn.setEnabled(False)
        self.preload_btn.setEnabled(True)
        self.status_label.setText("Model preloaded successfully")
        debug_print("[INFO] Preload complete (greeting response discarded, not shown in chat)")
        self._cleanup_preload_thread()
        # Mark as explicitly preloaded in THIS session
        self._explicitly_preloaded = True
        self._update_preload_button_state()  # now loaded -> green, disabled

        # ── Auto-preload dispatch ──
        # If start_ai_request deferred a request while we were preloading,
        # dispatch it now that the model is loaded.
        if getattr(self, '_auto_preloading', False) and hasattr(self, '_pending_request'):
            pending = self._pending_request
            self._auto_preloading = False
            self._pending_request = None
            debug_print(f"[INFO] Auto-preload done — dispatching deferred request: {pending[0]}")
            if pending:
                # Clean up any streaming item from preload's "Hello" generation
                self._remove_streaming_item()
                self.start_ai_request(pending[0], pending[1])

    def _on_preload_error(self, error):
        """Handle preload error."""
        if not self._is_current_preload_thread():
            self._cleanup_preload_thread()
            return
        if not getattr(self, 'preload_progress', None) or not self.preload_progress.isVisible():
            self._cleanup_preload_thread()
            return
        self._preload_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.cancel_btn.setEnabled(False)
        self.preload_btn.setEnabled(True)
        self.status_label.setText(f"Preload failed: {error}")
        debug_print(f"[ERROR] Preload failed: {error}")
        self._cleanup_preload_thread()

        # Clear any pending auto-preload request so we don't retry
        if getattr(self, '_auto_preloading', False):
            self._auto_preloading = False
            self._pending_request = None
            self._set_controls_enabled(True)

    def load_models(self):
        """Load available AI models with their sizes.
        Robust to both our ollama_wrapper (dicts) and the official 'ollama' pip package
        (which returns ListResponse / Model objects with attribute access).
        This fixes the long-standing "modellméretek nem látszanak" issue.
        """
        models = self.ai_assistant.get_available_models()
        if models:
            self.model_combo.clear()
            # Get model sizes from Ollama if using Ollama provider
            model_sizes = {}
            provider = getattr(self.ai_assistant, 'api_provider', 'ollama')
            if provider == "ollama" and self.ai_assistant.use_ollama and ollama:
                try:
                    ollama_result = ollama.list()
                    # Handle different return formats (dict from wrapper, or iter of Model/dict)
                    if isinstance(ollama_result, dict):
                        models_list = ollama_result.get('models', []) or []
                    elif hasattr(ollama_result, '__iter__') and not isinstance(ollama_result, (str, bytes)):
                        models_list = list(ollama_result)
                    else:
                        models_list = []

                    for m in models_list:
                        if isinstance(m, dict):
                            name = m.get('model') or m.get('name') or ''
                            size = m.get('size', 0)
                        else:
                            # official ollama.Model objects: attrs .model, .name, .size
                            name = getattr(m, 'model', None) or getattr(m, 'name', None) or ''
                            size = getattr(m, 'size', 0) or 0
                        if name and size:
                            model_sizes[name] = f" ({size / (1024**3):.1f} GB)"
                except Exception as e:
                    debug_print(f"[WARN] Could not fetch model sizes: {e}")

            for model in models:
                display_name = model
                # If get_available_models already attached a size suffix (recommended path), keep it.
                # Otherwise fall back to the second size map (for older/compat cases).
                if not (" (" in model and " GB)" in model):
                    pure_name = model[7:] if model.startswith("ollama:") else model
                    if pure_name in model_sizes:
                        display_name = f"{model}{model_sizes[pure_name]}"
                self.model_combo.addItem(display_name)

            # Try to select the default model
            default_model = self.ai_assistant.selected_model or "claude-3-5-sonnet-20241022"
            found = False
            for i in range(self.model_combo.count()):
                if self.model_combo.itemText(i).startswith(default_model):
                    self.model_combo.setCurrentIndex(i)
                    found = True
                    break
            if not found and self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)

            # Enable preload button if an Ollama model is selected
            self._update_preload_button_state()

            # Populate helper + reviewer model selectors with "Auto" + all local Ollama models
            self.helper_model_combo.clear()
            self.reviewer_model_combo.clear()
            self.helper_model_combo.addItem("Auto (auto-select)")
            self.reviewer_model_combo.addItem("Auto (reuse Helper)")
            for i in range(self.model_combo.count()):
                txt = self.model_combo.itemText(i)
                if txt and txt.startswith("ollama:"):
                    self.helper_model_combo.addItem(txt)
                    self.reviewer_model_combo.addItem(txt)
        else:
            self.model_combo.clear()
            self.model_combo.addItem("claude-3-5-sonnet-20241022")

        # Load persisted context window setting (checkbox + dropdown).
        # The "bekapcsolása" (enabling) must work immediately.
        self._load_context_window_setting()

    def _update_preload_button_state(self):
        """Update Preload button state and color.
        Shows 'Loaded' (green) only after explicit preload completed in THIS session.
        Shows 'Preload' (red) if not explicitly preloaded yet.
        """
        model = self.model_combo.currentText()
        raw_model = model.split(" (")[0]

        if not raw_model.startswith("ollama:"):
            self.preload_btn.setEnabled(False)
            self.preload_btn.setStyleSheet("")
            self.preload_btn.setToolTip("Preload is only for Ollama models")
            return

        # Only show Preloaded if we explicitly preloaded THIS session
        explicitly_preloaded = getattr(self, '_explicitly_preloaded', False)
        if explicitly_preloaded:
            self.preload_btn.setEnabled(False)
            self.preload_btn.setText(_("Loaded"))
            self.preload_btn.setStyleSheet(
                "QPushButton { background-color: #66ff66; color: black; border: 1px solid #33cc33; border-radius: 3px; padding: 4px; }"
            )
            self.preload_btn.setToolTip("Model was preloaded in this session")
        else:
            self.preload_btn.setEnabled(True)
            self.preload_btn.setText(_("Preload"))
            self.preload_btn.setStyleSheet(
                "QPushButton { background-color: #ff6265; color: white; border: 1px solid #ff6265; border-radius: 3px; padding: 4px; }"
            )
            self.preload_btn.setToolTip("Click to preload model (avoids slow first response)")

    def _on_model_changed(self, index):
        """Called when a new model is selected from the combo box.
        Updates the AI assistant's model and enables/disables the preload button.
        Only saves to QSettings when setup is complete (prevents initial setup
        code — _check_for_preloaded_model, _load_last_model_setting — from
        overwriting the user's saved choice).
        """
        model = self.model_combo.itemText(index)
        # Strip size info if present (e.g., "ollama:model (4.2 GB)")
        raw_model = model.split(" (")[0]
        debug_print(f"[DEBUG] Model changed to: {model} (raw: {raw_model})")
        self.ai_assistant.selected_model = raw_model
        if getattr(self, '_setup_complete', False):
            self._save_last_model(raw_model)
        # Reset explicitly_preloaded flag when model changes
        # Only reset after setup is complete — during initial setup the flag may
        # have been set by _check_for_preloaded_model (model found in ollama ps).
        if getattr(self, '_setup_complete', False):
            self._explicitly_preloaded = False
        self._update_preload_button_state()

        # If auto-preload is enabled, preload the newly chosen model (Ollama)
        if getattr(self, 'auto_preload_cb', None) and self.auto_preload_cb.isChecked():
            self._maybe_auto_preload_current_model()

    def _on_language_changed(self, index):
        """Handle language selection change."""
        lang = self.lang_combo.itemText(index)
        self.ai_assistant.set_language(lang)  # e.g. "Hungarian"
        debug_print(f"[DEBUG] Language set to: {lang}")

    def _on_context_window_changed(self):
        """Called when the user toggles the context window checkbox or changes the size.
        Priority: enabling the control must actually affect the model (num_ctx).
        """
        enabled = self.context_window_cb.isChecked()
        text = self.context_window_combo.currentText()

        if "Model default" in text or not enabled:
            size = 0
        else:
            # parse number from "8k (8192)" etc.
            try:
                size = int(text.split("(")[1].split(")")[0])
            except Exception:
                size = 8192

        self.ai_assistant.set_context_window(enabled, size)
        debug_print(f"[DEBUG] Context window: enabled={enabled}, size={size}")

        # Persist
        self._save_context_window_setting(enabled, size)

    def _save_context_window_setting(self, enabled, size):
        try:
            settings = QtCore.QSettings("PyCoder", "AIPanel")
            settings.setValue("context_window_enabled", bool(enabled))
            settings.setValue("context_window_size", int(size) if size else 0)
        except Exception:
            pass

    def _load_context_window_setting(self):
        try:
            settings = QtCore.QSettings("PyCoder", "AIPanel")
            enabled = settings.value("context_window_enabled", False, type=bool)
            size = settings.value("context_window_size", 0, type=int)

            self.context_window_cb.setChecked(bool(enabled))
            # find matching item in combo
            if size and size > 0:
                for i in range(self.context_window_combo.count()):
                    if str(size) in self.context_window_combo.itemText(i):
                        self.context_window_combo.setCurrentIndex(i)
                        break
            else:
                self.context_window_combo.setCurrentIndex(0)  # Model default

            # apply to assistant
            self.ai_assistant.set_context_window(bool(enabled), size)
            # keep combo enabled state consistent
            self.context_window_combo.setEnabled(bool(enabled))
        except Exception as e:
            debug_print(f"[WARN] Could not load context window setting: {e}")

    def _save_last_model(self, raw_model: str):
        """Save the last selected model with its display text (including size).
        Storing the FULL combo text ensures exact matches on restore.
        """
        try:
            full_text = raw_model
            # Find the exact combo text matching this model
            for i in range(self.model_combo.count()):
                txt = self.model_combo.itemText(i)
                if txt == raw_model or txt.startswith(raw_model):
                    full_text = txt
                    break
            settings = QtCore.QSettings("PyCoder", "AIPanel")
            settings.setValue("last_selected_model", full_text)
            settings.setValue("last_selected_model_raw", raw_model)
            settings.sync()
        except Exception:
            pass

    def _load_last_model_setting(self):
        """Restore the last manually selected model (if any) instead of always defaulting.
        Tries exact full-text match first, then prefix/startswith, then raw name.
        This is called AFTER _check_for_preloaded_model so the user's saved choice
        takes precedence over auto-detected preloaded models.
        """
        try:
            settings = QtCore.QSettings("PyCoder", "AIPanel")
            full = settings.value("last_selected_model", "", type=str)
            raw = settings.value("last_selected_model_raw", "", type=str)
            candidates = [c for c in (full, raw) if c]
            if not candidates:
                return
            # Try each candidate against combo items: exact > startswith > contains
            for cand in candidates:
                for i in range(self.model_combo.count()):
                    txt = self.model_combo.itemText(i)
                    if txt == cand or txt.startswith(cand) or cand in txt:
                        self.model_combo.setCurrentIndex(i)
                        self.ai_assistant.selected_model = raw or cand
                        debug_print(f"[DEBUG] Restored last selected model: {txt}")
                        self._update_preload_button_state()
                        return
            # Not found in combo (model was deleted or list changed)
            if raw:
                self.ai_assistant.selected_model = raw
                debug_print(f"[DEBUG] Stored model '{full}' not found in combo, keeping it in memory")
                self._update_preload_button_state()
        except Exception as e:
            debug_print(f"[WARN] Could not restore last model: {e}")

    def _save_auto_preload_setting(self, enabled: bool):
        try:
            settings = QtCore.QSettings("PyCoder", "AIPanel")
            settings.setValue("auto_preload_enabled", bool(enabled))
            settings.sync()
        except Exception:
            pass

    def _load_auto_preload_setting(self):
        try:
            settings = QtCore.QSettings("PyCoder", "AIPanel")
            enabled = settings.value("auto_preload_enabled", False, type=bool)
            self.auto_preload_cb.setChecked(bool(enabled))
            self.auto_preload_cb.toggled.connect(self._on_auto_preload_toggled)

            # If enabled and we have a selected (remembered) ollama model, auto-preload it
            if enabled:
                self._maybe_auto_preload_current_model()
        except Exception as e:
            debug_print(f"[WARN] Could not load auto-preload setting: {e}")

    def _on_auto_preload_toggled(self, checked: bool):
        self._save_auto_preload_setting(checked)
        if checked:
            self._maybe_auto_preload_current_model()

    def _maybe_auto_preload_current_model(self):
        """If auto-preload is on, try to preload the current (remembered) model if it's Ollama."""
        if not getattr(self, 'auto_preload_cb', None) or not self.auto_preload_cb.isChecked():
            return
        model = self.model_combo.currentText()
        if not model:
            return
        raw = model.split(" (")[0]
        if not raw.startswith("ollama:"):
            return
        # Don't spam if already loaded
        if self._is_ollama_model_loaded(raw[7:]):
            return
        debug_print(f"[DEBUG] Auto-preloading remembered model: {raw}")
        # Use the same mechanism as the button (non-blocking)
        try:
            self.on_preload_clicked()
        except Exception:
            pass

    def _check_for_preloaded_model(self):
        """Check if any Ollama model is already loaded in memory (ollama ps).
        Called after _load_last_model_setting so the combo already reflects the
        user's preference. Sets _explicitly_preloaded = True ONLY when the
        currently selected combo model is found in ps. If a different model is
        loaded, switches to that model as a convenience.
        """
        if not self.ai_assistant.use_ollama:
            return

        try:
            import requests
            response = requests.get("http://localhost:11434/api/ps", timeout=5)
            if response.status_code != 200:
                return
            loaded_data = response.json()
            loaded_models = loaded_data.get('models', [])
            if not loaded_models:
                debug_print("[DEBUG] No models loaded in ollama ps")
                return

            # Get the current combo model name (strip size info and "ollama:" prefix)
            current_item = self.model_combo.currentText()
            current_raw = current_item.split(" (")[0]
            current_model_name = current_raw[7:] if current_raw.startswith("ollama:") else ""

            # Collect all loaded model names from ps
            loaded_names = []
            for m in loaded_models:
                name = m.get('model', m.get('name', ''))
                if name:
                    loaded_names.append(name)

            # CASE 1: Current combo model is already loaded → mark as preloaded
            if current_model_name and current_model_name in loaded_names:
                debug_print(f"[DEBUG] Current model '{current_model_name}' is already loaded in Ollama")
                self._explicitly_preloaded = True
                self._update_preload_button_state()
                return

            # CASE 2: Current model not loaded, but another model is → switch to it
            first_loaded = loaded_names[0]
            debug_print(f"[DEBUG] Current model not loaded, but found '{first_loaded}' loaded — switching")
            raw_model = f"ollama:{first_loaded}"
            found = False
            for i in range(self.model_combo.count()):
                if self.model_combo.itemText(i).startswith(raw_model):
                    found = True
                    self.model_combo.setCurrentIndex(i)
                    break
            if not found:
                self.model_combo.addItem(raw_model)
                self.model_combo.setCurrentText(raw_model)
            self.ai_assistant.selected_model = raw_model
            self._explicitly_preloaded = True
            self._update_preload_button_state()
            debug_print(f"[DEBUG] Switched to preloaded model: {raw_model}")
        except Exception as e:
            debug_print(f"[WARN] Could not check for preloaded models: {e}")

    def _step_progress(self):
        """Animate the progress bar during AI processing."""
        if self._is_processing:
            self._busy_progress_value = (self._busy_progress_value + 2) % 102
            self.preload_progress.setValue(self._busy_progress_value)
            self.preload_progress.setVisible(True)

    # Preload progress bar logic reverted to simple 10 -> 100 jump for reliability.
    # The ramp simulation (introduced to show "progress" during long model loads) caused
    # complex interactions with cancel, _busy_timer (shared bar), thread finished signals,
    # and subsequent Suggest requests, leading to stuck bars, ignored results, and UI freezes.
    # We keep the thread safety (cleanup, short waits, ignore late results, full reset on cancel)
    # which were added separately.

    def _on_preload_finished(self):
        """Safety net: QThread.finished signal.
        If we reach here and the UI is still showing preload in progress (stuck at 93%),
        force completion. This guards against cases where result_ready or error_occurred
        were not emitted for any reason (e.g. early return on cancel, unexpected response shape).
        Late signals after cancel are ignored.
        """
        if not self._is_current_preload_thread():
            self._cleanup_preload_thread()
            return
        if not getattr(self, 'preload_progress', None) or not self.preload_progress.isVisible():
            self._cleanup_preload_thread()
            return
        self._preload_timer.stop()
        if self.preload_progress.isVisible() and self.preload_progress.value() < 100:
            # Safety net for cases where ready/error didn't fire (e.g. after cancel or odd thread exit).
            # Back to simple behavior: jump to 100 and hide.
            self.preload_progress.setValue(100)
            QtCore.QTimer.singleShot(200, lambda: self.preload_progress.setVisible(False))
            self.cancel_btn.setEnabled(False)
            self.preload_btn.setEnabled(True)
            self.status_label.setText("Model preloaded successfully")
            debug_print("[INFO] Preload finished via thread.finished fallback")
        self._cleanup_preload_thread()

    def _cleanup_preload_thread(self):
        """Disconnect user signals and drop our reference.
        Unlike the existing code we ALSO disconnect the finished → _on_preload_finished
        and finished → _cleanup_preload_thread connections, to prevent a stale thread
        from corrupting the state of a subsequently started preload.
        The QThread object must only ever be deleted via the
        `finished.connect(self.preload_thread.deleteLater)` connection that was
        established at creation time. Disconnecting that or calling deleteLater
        from here is what triggers the 'Destroyed while thread is still running' crash.
        We take care NOT to touch the deleteLater connection.
        """
        th = getattr(self, 'preload_thread', None)
        if not th:
            return

        self.preload_thread = None  # drop reference first

        # Disconnect ALL of OUR signal handlers from the old thread.
        # We deliberately do NOT disconnect the finished → deleteLater connection.
        for signal, slot in (
            (th.result_ready, self._on_preload_ready),
            (th.error_occurred, self._on_preload_error),
            (th.progress_update, self._on_preload_progress),
            (th.finished, self._on_preload_finished),
        ):
            try:
                signal.disconnect(slot)
            except Exception:
                pass

        # If the thread is still alive, just ask it nicely to stop.
        # We do not wait long and we do not delete it here.
        if th.isRunning():
            try:
                th.cancel()
                th.quit()
            except Exception:
                pass
        # No deleteLater, no long wait. Deletion is owned by the finished signal.

    def set_editor(self, editor):
        """Set the current editor (cached). Sending paths will also do a robust
        re-resolve from active project/editorTabWidget so stale caches don't
        cause 'model does not see the open code'."""
        self.current_editor = editor

    def _get_active_code_and_context(self):
        """Robustly obtain the open editor code + current file path + project root.
        Used at send time so that even if set_editor() was never/stale-called
        (e.g. global AIPanel toggled late, tab switches not propagated to outer panel),
        the model still receives the code the user has open and knows which project/file it is.
        Walks the parent chain to support both the outer global AIPanel (child of PyCoder)
        and the per-project bottom AIPanel (hosted inside EditorWindow).
        """
        code = ""
        file_path = ""
        project_root = ""

        # 1) Try the explicitly set current_editor first
        editor = getattr(self, "current_editor", None)
        if editor:
            try:
                if hasattr(editor, "text"):
                    code = editor.text() or ""
                elif hasattr(editor, "toPlainText"):
                    code = editor.toPlainText() or ""
            except Exception:
                pass

        # 2) Walk parents (up to a few levels) to locate an EditorWindow-like object
        #    that has editorTabWidget + projectPathDict, or the main PyCoder with projectWindowStack.
        parent = self.parent
        for _ in range(6):
            if not parent:
                break
            try:
                if hasattr(parent, "editorTabWidget"):
                    # Likely an EditorWindow (or similar container)
                    etw = parent.editorTabWidget
                    if not code:
                        # Prefer focusedEditor / getEditor if available (returns real scintilla)
                        ed = None
                        if hasattr(etw, "focusedEditor"):
                            ed = etw.focusedEditor()
                        if not ed and hasattr(etw, "getEditor"):
                            ed = etw.getEditor()
                        if ed and hasattr(ed, "text"):
                            code = ed.text() or ""
                        elif ed and hasattr(ed, "toPlainText"):
                            code = ed.toPlainText() or ""
                    file_path = etw.getEditorData("filePath") if hasattr(etw, "getEditorData") else ""
                    if hasattr(parent, "projectPathDict") and isinstance(parent.projectPathDict, dict):
                        project_root = parent.projectPathDict.get("root") or parent.projectPathDict.get("sourcedir") or ""
                    # If project_root is still empty, don't break yet – continue the parent walk
                    # to reach a higher ancestor that may have projectWindowStack or projectPathDict.
                    if project_root:
                        break  # we have everything we need
                    # Otherwise fall through to the parent walk below (don't break)

                if hasattr(parent, "projectWindowStack"):
                    # This is the top-level PyCoder main window
                    try:
                        cur_win = parent.projectWindowStack.currentWidget()
                        if cur_win and hasattr(cur_win, "editorTabWidget"):
                            etw = cur_win.editorTabWidget
                            if not code:
                                ed = None
                                if hasattr(etw, "focusedEditor"):
                                    ed = etw.focusedEditor()
                                if not ed and hasattr(etw, "getEditor"):
                                    ed = etw.getEditor()
                                if ed and hasattr(ed, "text"):
                                    code = ed.text() or ""
                                elif ed and hasattr(ed, "toPlainText"):
                                    code = ed.toPlainText() or ""
                            file_path = etw.getEditorData("filePath") if hasattr(etw, "getEditorData") else ""
                            if hasattr(cur_win, "projectPathDict") and isinstance(cur_win.projectPathDict, dict):
                                project_root = cur_win.projectPathDict.get("root") or cur_win.projectPathDict.get("sourcedir") or ""
                    except Exception:
                        pass
                    break
            except Exception:
                pass
            # climb
            parent = _safe_parent(parent) or getattr(parent, "projects", None) or getattr(parent, "window", None)

        return code, file_path, project_root

    def _get_recent_run_output(self, max_lines: int = 80) -> str:
        """Try to extract the most recent output from the RunWidget (or similar output
        scintilla) in the parent chain. This captures the traceback the user just saw
        when they pressed "Futtatás" and then "keresd meg a hibát".
        This is critical for grounding the Fix prompt with the actual error
        (e.g. the QRect float TypeError in paintEvent).
        """
        collected = []
        seen_widgets = set()
        parent = self.parent
        for _ in range(10):
            if not parent:
                break
            # Direct attributes that often hold the run output
            for attr_name in ("runWidget", "run_widget", "runOutput", "outputWidget", "bottomRun"):
                rw = getattr(parent, attr_name, None)
                if rw and id(rw) not in seen_widgets:
                    seen_widgets.add(id(rw))
                    text = self._extract_text_from_scintilla_like(rw)
                    if text:
                        collected.append(text)

            # Search children (splitters, stacks, docks often contain the RunWidget)
            try:
                for child in parent.findChildren(QtWidgets.QWidget):
                    cname = type(child).__name__
                    if "Run" in cname or "Output" in cname or "Console" in cname:
                        if id(child) not in seen_widgets:
                            seen_widgets.add(id(child))
                            text = self._extract_text_from_scintilla_like(child)
                            if text and ("Traceback" in text or "TypeError" in text or ">>> " in text or "Futtatás" in text or "Running:" in text or "Run:" in text):
                                collected.append(text)
            except Exception:
                pass

            parent = (_safe_parent(parent) or
                      getattr(parent, "projects", None) or
                      getattr(parent, "window", None) or
                      getattr(parent, "vSplitter", None))

        if not collected:
            # Ultimate fallback: search ALL top-level widgets via QApplication.
            # This is robust against dock reparenting, floating panels, and other
            # widget hierarchy edge cases where the parent walk fails to reach
            # the EditorWindow.
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for w in app.allWidgets():
                        if id(w) in seen_widgets:
                            continue
                        cname = type(w).__name__
                        if "Run" in cname or "Console" in cname:
                            seen_widgets.add(id(w))
                            text = self._extract_text_from_scintilla_like(w)
                            if text and ("Traceback" in text or "NameError" in text or "TypeError" in text or ">>> " in text or "Error" in text or "Futtatás" in text or "Running:" in text):
                                collected.append(text)
            except Exception:
                pass

        if not collected:
            return ""

        # Take the last (most recent) substantial block
        full = "\n".join(collected)
        lines = full.splitlines()
        recent = lines[-max_lines:]
        return "\n".join(recent).strip()

    def _extract_text_from_scintilla_like(self, widget) -> str:
        """Safely pull text from a QsciScintilla or similar output widget.
        Never calls text() without a line argument — QsciScintilla requires it.
        Joins lines with newlines so keyword/pattern matching works.
        """
        if widget is None:
            return ""
        try:
            # QsciScintilla.text() requires a line number — first try reading all
            # text via the lines() + text(line) pattern.
            if hasattr(widget, "lines") and hasattr(widget, "text"):
                n = widget.lines()
                if n and n > 0:
                    start = max(0, n - 80)
                    parts = []
                    for i in range(start, n):
                        try:
                            line_text = widget.text(i)
                            if line_text is not None:
                                parts.append(str(line_text))
                        except Exception:
                            pass
                    if parts:
                        joined = "\n".join(parts)
                        if len(joined) > 20:
                            return joined

            # Fallback for non-Scintilla widgets with a no-arg text() e.g. QTextEdit
            if hasattr(widget, "toPlainText"):
                t = widget.toPlainText()
                if isinstance(t, str) and len(t) > 20:
                    return t
            if hasattr(widget, "text") and not isinstance(widget.text, int):
                try:
                    t = widget.text()
                    if callable(t):
                        t = t()
                    if isinstance(t, str) and len(t) > 20:
                        return t
                except TypeError:
                    pass
        except Exception:
            pass
        return ""

    def _get_project_root(self):
        """Return the current project root if available. Falls back to last known from prompt context."""
        # First try live parent chain (most reliable when inside a project window)
        parent = self.parent
        for _ in range(8):
            if not parent:
                break
            if hasattr(parent, "projectPathDict") and isinstance(getattr(parent, "projectPathDict", None), dict):
                root = parent.projectPathDict.get("root") or parent.projectPathDict.get("sourcedir")
                if root and os.path.isdir(root):
                    self._last_known_project_root = root
                    return root
            if hasattr(parent, "projectWindowStack"):
                try:
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "projectPathDict") and isinstance(cur.projectPathDict, dict):
                        root = cur.projectPathDict.get("root") or cur.projectPathDict.get("sourcedir")
                        if root and os.path.isdir(root):
                            self._last_known_project_root = root
                            return root
                except Exception:
                    pass
            parent = _safe_parent(parent) or getattr(parent, "projects", None) or getattr(parent, "window", None)

        # Fallback to last known (from previous prompt construction)
        if hasattr(self, "_last_known_project_root") and self._last_known_project_root:
            return self._last_known_project_root

        # Last resort: try to derive root from the current open file path (if available via
        # parent chain or the editor itself). This handles cases where the Qt parent chain
        # doesn't reach the main PyCoder window (detached panel, broken hierarchy, etc.).
        try:
            _code, _fp, _root = self._get_active_code_and_context()
            if _fp and os.path.isfile(_fp):
                # Walk up from the file's directory looking for a project marker
                candidate = os.path.dirname(os.path.abspath(_fp))
                for _ in range(4):  # up to 4 levels
                    if not candidate or candidate == "/":
                        break
                    if os.path.isdir(os.path.join(candidate, ".git")) or \
                       os.path.isfile(os.path.join(candidate, "setup.py")) or \
                       os.path.isfile(os.path.join(candidate, "pyproject.toml")) or \
                       os.path.isfile(os.path.join(candidate, "requirements.txt")):
                        self._last_known_project_root = candidate
                        return candidate
                    candidate = os.path.dirname(candidate)
                # Even without a marker, use the file's parent dir as minimal root
                parent_dir = os.path.dirname(os.path.abspath(_fp))
                if os.path.isdir(parent_dir):
                    self._last_known_project_root = parent_dir
                    return parent_dir
        except Exception:
            pass

        return ""

    def _list_project_files(self, max_depth=5, max_files=300):
        """Return a list of relative file paths in the project (for the model to explore).
        For brand new / empty projects (common when user says "Írj egy példakódot a szerkesztőbe" in a fresh tab):
        we also surface the names of currently open editor tabs (even unsaved "Untitled" ones).
        This prevents the model from hallucinating mainwindow.py / folder_name/subfile.txt etc.
        """
        root = self._get_project_root()
        files = []
        if root and os.path.isdir(root):
            ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'build', 'dist', '.idea', '.vscode'}
            ignore_exts = {'.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg'}
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath[len(root):].count(os.sep)
                if depth > max_depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith('.')]
                for fname in filenames:
                    if any(fname.endswith(ext) for ext in ignore_exts):
                        continue
                    rel = os.path.relpath(os.path.join(dirpath, fname), root)
                    files.append(rel.replace(os.sep, '/'))
                    if len(files) >= max_files:
                        break
                if len(files) >= max_files:
                    break

        # Always augment with open editor tabs (the "live" view the user actually has).
        # This is crucial for new projects where nothing is saved on disk yet.
        try:
            open_tabs = self._get_open_files() or []
            for p in open_tabs:
                rp = p.replace('\\', '/')
                if root:
                    try:
                        rp = os.path.relpath(p, root).replace('\\', '/')
                    except Exception:
                        pass
                if rp not in files:
                    files.append(rp)
        except Exception:
            pass

        if not files:
            # Last resort: at least tell the truth instead of letting model invent structure.
            files = ["(no saved files on disk - only an empty or unnamed editor tab is open)"]
        return files

    def _read_project_file(self, rel_path: str):
        """Read a file from the project by relative path. Returns content or error message."""
        root = self._get_project_root()
        if not root or not rel_path:
            return "Error: No project root or path provided."
        # normalize
        rel_path = rel_path.strip().replace('\\', '/').lstrip('/')
        full = os.path.normpath(os.path.join(root, rel_path))
        if not full.startswith(os.path.normpath(root)):
            return "Error: Path outside project."
        if not os.path.isfile(full):
            return f"Error: File not found: {rel_path}"
        try:
            with open(full, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    def _get_open_files(self):
        """Return list of currently open file paths (relative if possible)."""
        try:
            parent = self.parent
            for _ in range(6):
                if not parent:
                    break
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                    if hasattr(etw, "get_open_files"):
                        return etw.get_open_files()
                    # fallback: walk tabs
                    paths = []
                    for i in range(etw.count()):
                        p = etw.getEditorData("filePath", i)
                        if p:
                            paths.append(p)
                    return paths
                if hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        etw = cur.editorTabWidget
                        if hasattr(etw, "get_open_files"):
                            return etw.get_open_files()
                parent = _safe_parent(parent) or getattr(parent, "projects", None)
        except Exception:
            pass
        return []

    def _open_file_in_editor(self, rel_path: str):
        """Open a file in the editor (new tab or focus existing). Returns success message."""
        root = self._get_project_root()
        if not root:
            return "Error: No project root."
        full = os.path.normpath(os.path.join(root, rel_path.strip().replace('\\', '/')))
        if not os.path.isfile(full):
            return f"Error: File not found {rel_path}"
        try:
            # Walk to find an EditorTabWidget
            parent = self.parent
            for _ in range(6):
                if not parent:
                    break
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                    etw.loadfile(full)
                    return f"Opened: {rel_path}"
                if hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        cur.editorTabWidget.loadfile(full)
                        return f"Opened: {rel_path}"
                parent = _safe_parent(parent) or getattr(parent, "projects", None)
            return "Error: Could not find editor to open file in."
        except Exception as e:
            return f"Error opening file: {e}"

    def _get_available_tools_description(self):
        """Short tool reference for the agent-based mode."""
        return """You have access to the following tools. Output tool calls in this EXACT format:

TOOL: tool_name key1=value1 key2="value with spaces"

Available tools:
- ask_user question="your question here" — ask the user for clarification. After the user replies, your next invocation will include "=== CONTINUATION ===" showing both your question and their answer. Use this instead of guessing.
- replace_text path=relative/path.py old="exact text to find" new="new text"
    Note: old="" means create new file or insert at top of existing file
- read_run_output — get the latest run console output (errors, tracebacks, print output)
- list_project_files — list all project files (max depth 5)
- read_file path=relative/path.py — read file content
- open_file path=relative/path.py — open file in editor tab
- get_open_files — list currently open editor tabs

When you receive a [SYSTEM TOOL RESULTS] block, analyze it and either call another tool or give your final response.

Rules:
- NEVER output "Tool result for", "Tool output for" or similar meta text.
- NEVER simulate system responses.
- If you need more information or something is unclear, use ask_user rather than guessing.
- If the code has a run error, use read_run_output to check the console.
- If a change could be destructive, ask the user for permission first.
- Use replace_text for targeted edits, not full file rewrites, when only a small change is needed.
- orchestrate task="..." scope="fix|suggest|explain" — run a complex task through a multi-model pipeline
    (interpreter → coder → reviewer). The system will automatically select suitable smaller models.
    Use this for complex bug fixes, code generation, or when you need additional verification.
    For simple questions answer directly without orchestration.
"""

    def _replace_text_in_file(self, rel_path: str, old_text: str, new_text: str):
        """Safe search-replace. Tries to do it through an open editor first (live + undoable),
        falls back to disk. Returns success or error message.
        Special: old_text="" (empty) means write/overwrite the full new_text (for new files or empty editors).

        For creation requests (old_text == ""), we intentionally allow empty rel_path and/or
        missing project root: the primary goal is to write into the *live focused or current empty
        editor tab* (works great for brand new projects and unsaved "Untitled" tabs).
        """
        rel_path = (rel_path or "").strip()
        old_text = old_text or ""

        root = self._get_project_root()

        if old_text == "":
            # Full write / creation mode.
            # Allow missing path and/or root. We default the label and will try live editor first.
            if not rel_path:
                rel_path = "main.py"
            # SAFETY: if we have no project root, use the directory of the currently open file
            # instead of allowing bare relative paths (which would resolve against CWD and could
            # escape via ".." traversal). Small models often hallucinate paths.
            if not root:
                _code, _fp, _ = self._get_active_code_and_context()
                if _fp and os.path.isfile(_fp):
                    root = os.path.dirname(os.path.abspath(_fp))
                else:
                    root = os.getcwd()
            # --- Smart insertion: if old_text="" but the open editor already has significant content,
            # do NOT overwrite — instead INSERT the new code into the file. This handles the common
            # case where a small local model uses old="" for "write X into the file" even though the
            # file already has content, which would otherwise destroy the existing code.
            try:
                _ce = self.parent
                _etw = None
                for _ in range(6):
                    if not _ce: break
                    if hasattr(_ce, "editorTabWidget"): _etw = _ce.editorTabWidget; break
                    _ce = _safe_parent(_ce) or getattr(_ce, "projects", None) or getattr(_ce, "window", None) or getattr(_ce, "vSplitter", None)
                if _etw is not None:
                    for i in range(_etw.count()):
                        ed = _etw.getEditor(i)
                        txt = (ed.text() if hasattr(ed, "text") else ed.toPlainText()) or ""
                        if txt.strip() and len(txt) > 20:
                            # If the new text is short/insertion-like, INSERT it rather than overwrite.
                            # Heuristic: if new_text is < 200 chars and doesn't look like a complete
                            # file (no import/def/class headers), treat it as an insertion.
                            is_short_insert = len(new_text.strip()) < 200 and not any(
                                kw in new_text for kw in ["\nimport ", "\nfrom ", "\ndef ", "\nclass "]
                            )
                            if is_short_insert:
                                # Prepend the new content to the file (preserves existing code).
                                if txt.rstrip().endswith("\n") or txt.rstrip().endswith("\r"):
                                    merged = txt.rstrip() + "\n" + new_text.strip() + "\n"
                                elif txt.rstrip():
                                    merged = txt.rstrip() + "\n\n" + new_text.strip() + "\n"
                                else:
                                    merged = new_text.strip() + "\n"
                                if hasattr(ed, "setText"):
                                    ed.setText(merged)
                                else:
                                    ed.setPlainText(merged)
                                if hasattr(ed, "setModified"):
                                    ed.setModified(True)
                                debug_print(f"[DEBUG] _replace: INSERTED new code into existing content (old=\"\" smart path)")
                                return f"Text inserted into file (model used old=\"\", so the system appended the new code to existing content).\nOriginal content preserved, inserted section:\n{new_text.strip()}"
                            else:
                                # Looks like a full file replacement — trust the model.
                                debug_print(f"[DEBUG] _replace: old=\"\" on non-empty file but new_text is long, treating as full replacement (len={len(new_text)})")
            except Exception:
                pass
            # Do NOT return early. The live editor walk below can succeed without root.
            debug_print(f"[DEBUG] _replace creation (old=''): rel_path={rel_path}, root={bool(root)}, new_text_len={len(new_text)}")
        else:
            if not root or not rel_path:
                return "Error: missing path for replace."

        # Only compute a full disk path when we actually have a root + name.
        # The "outside project" check only makes sense in that case.
        full = ""
        if root and rel_path:
            # Block explicit parent-directory traversal — small models often
            # hallucinate paths like "../SajatProjekt/main.py" thinking they're
            # being helpful. Because root already resolves relative paths that
            # stay inside the project, any "../" in rel_path is an escape attempt.
            _normalized_rel = rel_path.replace('\\', '/')
            if '/../' in _normalized_rel or _normalized_rel.startswith('../'):
                return "Error: path outside project (parent directory traversal is blocked)."
            full = os.path.normpath(os.path.join(root, _normalized_rel))
            if not full.startswith(os.path.normpath(root)):
                return "Error: path outside project."

        # Try to apply through open editor (best for live feedback)
        # For creation (old_text=="") we use an extra aggressive walk (modeled after _get_active_code_and_context)
        # because when testing with empty/untitled editor in a new or minimal "project", the parent chain
        # from AIPanel may require more levels or different attributes (window, vSplitter, etc.).
        try:
            parent = self.parent
            etw = None
            for _ in range(10):  # more levels for complex docking / new project / untitled tab cases
                if not parent:
                    break
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                    break
                if hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        etw = cur.editorTabWidget
                        break
                # additional climbing options that _get_active uses
                parent = (_safe_parent(parent) or
                          getattr(parent, "projects", None) or
                          getattr(parent, "window", None) or
                          getattr(parent, "vSplitter", None))

            if etw:
                # For creation (old_text==""), we want to support writing to the *currently focused or any open editor tab*
                # even when the project is brand new, the tab is unsaved ("Untitled", filePath="", no disk file yet),
                # or the model used a slightly wrong path name. This is the key for "empty editor + Írj egy példakódot a szerkesztőbe".
                target_editor = None
                target_idx = None
                target_label = rel_path or "current"
                if old_text == "":
                    # Prefer the focused editor (the one the user is looking at)
                    focused = None
                    if hasattr(etw, "focusedEditor"):
                        focused = etw.focusedEditor()
                    if focused:
                        target_editor = focused
                        target_label = etw.getEditorData("filePath", etw.currentIndex()) or "current"
                    else:
                        # Fallback: first empty editor, or simply the current tab's editor
                        for i in range(etw.count()):
                            ed = etw.getEditor(i)
                            txt = (ed.text() if hasattr(ed, "text") else ed.toPlainText()) or ""
                            if not txt.strip():
                                target_editor = ed
                                target_label = etw.getEditorData("filePath", i) or f"tab{i}"
                                break
                        if target_editor is None and etw.count() > 0:
                            ci = etw.currentIndex() if hasattr(etw, "currentIndex") else 0
                            target_editor = etw.getEditor(ci)
                            target_label = etw.getEditorData("filePath", ci) or "current"
                else:
                    for i in range(etw.count()):
                        if etw.getEditorData("filePath", i) == full or etw.getEditorData("filePath", i) == rel_path:
                            target_editor = etw.getEditor(i)
                            target_idx = i
                            break

                if target_editor is not None and old_text == "":
                    # Write full content into the live (possibly unsaved/empty) editor tab
                    if hasattr(target_editor, "setText"):
                        target_editor.setText(new_text)
                    else:
                        target_editor.setPlainText(new_text)
                    if hasattr(target_editor, "setModified"):
                        target_editor.setModified(True)
                    debug_print(f"[DEBUG] _replace: live editor write via etw path succeeded, target={target_label}")
                    return f"Wrote full content to open editor ({target_label}) via live editor (old=\"\")"
                if target_editor is not None and old_text and old_text in (target_editor.text() if hasattr(target_editor, "text") else target_editor.toPlainText()):
                    current_text = target_editor.text() if hasattr(target_editor, "text") else target_editor.toPlainText()
                    new_full = current_text.replace(old_text, new_text, 1)
                    if hasattr(target_editor, "setText"):
                        target_editor.setText(new_full)
                    else:
                        target_editor.setPlainText(new_full)
                    if hasattr(target_editor, "setModified"):
                        target_editor.setModified(True)
                    return f"Edited open file: {rel_path or target_label} (via editor)"

                # If we had a specific path match attempt for non-empty old and it failed, fall through to error/disk
                if old_text and not target_editor:
                    return f"Error: old_text not found exactly in open editor for {rel_path}"
        except Exception as e:
            # fall through to disk
            debug_print(f"[DEBUG] _replace etw walk exception: {e}")

        # Ultra-direct creation write fallback (for empty/untitled tabs in new/minimal projects).
        # The etw walk above may still miss the EditorTabWidget depending on docking/parent structure.
        # We replicate the active editor discovery from _get_active_code_and_context (which is known to
        # work for getting context even in bare editor cases) and force-write to whatever current editor
        # we can grab. This is the last safety net so "Írj egy példakódot a szerkesztőbe" on empty editor
        # actually puts the code in the tab the user is looking at.
        if old_text == "" and not any("Wrote full content to open editor" in r for r in [ ""] ):  # only if we haven't succeeded yet
            try:
                parent = self.parent
                active_ed = None
                target_label = "current-direct"
                for _ in range(10):
                    if not parent:
                        break
                    etw = None
                    if hasattr(parent, "editorTabWidget"):
                        etw = parent.editorTabWidget
                    elif hasattr(parent, "projectWindowStack"):
                        cur = parent.projectWindowStack.currentWidget()
                        if cur and hasattr(cur, "editorTabWidget"):
                            etw = cur.editorTabWidget
                    if etw:
                        try:
                            if hasattr(etw, "focusedEditor"):
                                active_ed = etw.focusedEditor()
                            if not active_ed and hasattr(etw, "getEditor"):
                                active_ed = etw.getEditor()
                            if not active_ed and hasattr(etw, "currentIndex") and hasattr(etw, "getEditor"):
                                ci = etw.currentIndex()
                                active_ed = etw.getEditor(ci)
                            if active_ed:
                                target_label = etw.getEditorData("filePath", etw.currentIndex() if hasattr(etw, "currentIndex") else 0) or "current-direct"
                                break
                        except Exception:
                            pass
                    parent = (_safe_parent(parent) or
                              getattr(parent, "projects", None) or
                              getattr(parent, "window", None) or
                              getattr(parent, "vSplitter", None))
                if active_ed and (hasattr(active_ed, "setText") or hasattr(active_ed, "setPlainText")):
                    if hasattr(active_ed, "setText"):
                        active_ed.setText(new_text)
                    else:
                        active_ed.setPlainText(new_text)
                    if hasattr(active_ed, "setModified"):
                        active_ed.setModified(True)
                    debug_print("[DEBUG] _replace: DIRECT active editor write succeeded for creation (ultra-fallback)")
                    return f"Wrote full content to open editor ({target_label}) via direct active editor (old=\"\")"
            except Exception as e:
                debug_print(f"[DEBUG] _replace direct creation fallback exception: {e}")

        # Ultimate fallback using QApplication (works even if parent chain is weird for docks/new projects)
        if old_text == "":
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    candidates = list(app.allWidgets()) + list(app.topLevelWidgets())
                    for w in candidates:
                        etw = None
                        if hasattr(w, "editorTabWidget") and w.editorTabWidget:
                            etw = w.editorTabWidget
                        elif hasattr(w, "editorTabWidget"):
                            etw = w.editorTabWidget
                        if etw:
                            active_ed = None
                            try:
                                if hasattr(etw, "focusedEditor"):
                                    active_ed = etw.focusedEditor()
                                if not active_ed and hasattr(etw, "getEditor"):
                                    active_ed = etw.getEditor()
                                if not active_ed and hasattr(etw, "currentIndex") and hasattr(etw, "getEditor"):
                                    active_ed = etw.getEditor(etw.currentIndex())
                            except Exception:
                                pass
                            if active_ed and (hasattr(active_ed, "setText") or hasattr(active_ed, "setPlainText")):
                                if hasattr(active_ed, "setText"):
                                    active_ed.setText(new_text)
                                else:
                                    active_ed.setPlainText(new_text)
                                if hasattr(active_ed, "setModified"):
                                    active_ed.setModified(True)
                                debug_print("[DEBUG] _replace: QApp allWidgets fallback write succeeded for creation")
                                return f"Wrote full content to open editor (via-qapp) via live editor (old=\"\")"
            except Exception as e:
                debug_print(f"[DEBUG] _replace qapp ultimate fallback exception: {e}")

        # Disk fallback
        if old_text == "":
            # Create or overwrite full content for new/empty file
            if not full:
                return "Error: cannot create file on disk (no project root and no open editor found)."
            try:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, 'w', encoding='utf-8') as f:
                    f.write(new_text)
                return f"Created/wrote full content to file: {rel_path} (via disk)"
            except Exception as e:
                return f"Error writing file: {e}"
        if not os.path.isfile(full):
            return f"Error: file not found on disk: {rel_path}"
        try:
            with open(full, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if old_text not in content:
                return f"Error: old_text not found in {rel_path}"
            new_content = content.replace(old_text, new_text, 1)
            with open(full, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return f"Edited file on disk: {rel_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    KNOWN_TOOLS = {"list_project_files", "read_file", "open_file", "get_open_files", "replace_text",
                   "read_run_output", "ask_user", "orchestrate"}

    def _execute_ai_tool(self, name: str, args: dict):
        """Execute a tool the model requested. Keep execution auditable."""
        name = (name or "").lower().strip()
        try:
            if name == "list_project_files":
                files = self._list_project_files()
                if files:
                    return "\n".join(files)
                return "(no file in the project - empty/new project or only the open editor tab exists)"
            elif name == "read_file":
                path = args.get("path") or args.get("rel_path") or args.get("file") or ""
                return self._read_project_file(path)
            elif name == "open_file":
                path = args.get("path") or args.get("rel_path") or ""
                return self._open_file_in_editor(path)
            elif name == "get_open_files":
                return "\n".join(self._get_open_files()) or "No files currently open."
            elif name in ("replace_text", "search_replace", "edit_file"):
                path = args.get("path") or args.get("rel_path") or ""
                old = args.get("old") or args.get("old_text") or ""
                new = args.get("new") or args.get("new_text") or ""
                return self._replace_text_in_file(path, old, new)
            elif name == "read_run_output":
                output = self._get_recent_run_output(max_lines=100)
                if output:
                    return f"=== RUN CONSOLE OUTPUT ===\n{output}\n=== END ==="
                return "(run console is empty or no recent output found)"
            elif name == "ask_user":
                question = args.get("question") or args.get("q") or "(no question provided)"
                self._add_chat_item("ai", f"🤔 *Kérdés:* {question}\n\n_Válaszolj a prompt mezőben, aztán nyomj Entert/Sendet._")
                # Return a special marker. The caller (on_custom_response_ready)
                # checks for this and stops the agent loop instead of re-invoking.
                return "[ASK_USER]"
            elif name == "orchestrate":
                task = args.get("task") or ""
                scope = args.get("scope") or "fix"
                if not task:
                    return "ERROR: orchestrate requires a 'task' parameter."
                result = self._handle_orchestrate_tool(task, scope)
                return result
            else:
                tools_list = ", ".join(sorted(self.KNOWN_TOOLS))
                return f"ERROR: unknown tool name '{name}'. Available tools: {tools_list}."
        except Exception as e:
            return f"Error executing tool {name}: {str(e)}"

    def _handle_orchestrate_tool(self, task: str, scope: str = "fix") -> str:
        """Start the multi-model pipeline for a complex task.
        Returns a human-readable status string for the tool result block.
        The actual result will be sent to the editor when the pipeline completes.
        """
        if not hasattr(self, 'ai_assistant') or self.ai_assistant is None:
            return "ERROR: AI Assistant not available"

        # Get current code context
        code_context = ""
        try:
            parent = self.parent
            etw = None
            for _ in range(10):
                if not parent:
                    break
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                    break
                parent = (getattr(parent, "parent", lambda: None)() or
                          getattr(parent, "projects", None) or
                          getattr(parent, "window", None) or
                          getattr(parent, "vSplitter", None))
            if etw is not None:
                idx = etw.currentIndex()
                if idx >= 0:
                    ed = etw.getEditor(idx)
                    if ed:
                        if hasattr(ed, "text"):
                            code_context = ed.text()
                        else:
                            code_context = ed.toPlainText()
        except Exception:
            pass

        # Show pipeline start in chat
        self._add_chat_item("ai", f"🔷 *Pipeline indítása...* (értelmező → kódoló → áttekintő)\n"
                                  f"Feladat: {task}\nKör: {scope}")

        # Start orchestration
        self._pipeline_result_buffer = ""
        mgr = self.ai_assistant._orchestrate(task, code_context,
                                              language=self.lang_combo.currentText())

        if mgr is None:
            self._add_chat_item("ai", "⚠️ *Pipeline nem indítható* — nincs elég szabad memória a több modellhez. "
                                      "A feladatot egyetlen modell fogja feldolgozni.")
            return "[PIPELINE_SKIPPED: insufficient memory]"

        # Connect signals
        self._orchestration_manager = mgr
        mgr.pipeline_progress.connect(self._on_pipeline_progress)
        mgr.pipeline_result.connect(self._on_pipeline_result)
        mgr.pipeline_error.connect(self._on_pipeline_error)

        return f"[PIPELINE_STARTED: task='{task}', models=auto-selected]"

    def _start_pipeline_for_fix(self, task_desc: str, code: str,
                                 lang_inst: str, error_text: str = "") -> bool:
        """Try to start the multi-model pipeline for fix/suggest.
        Returns True if pipeline started, False if fallback to single model needed.
        """
        if not hasattr(self, 'ai_assistant') or self.ai_assistant is None:
            return False

        # Update UI — disable ALL controls, show progress bar
        self._set_controls_enabled(False)
        self.preload_progress.setVisible(True)
        self._is_processing = True
        self._busy_progress_value = 0
        self._busy_timer.start(50)
        self.status_label.setText("Pipeline: interpreter → coder → reviewer")
        debug_print("[DEBUG] UI BUSY set for pipeline mode")

        self._pipeline_result_buffer = ""
        mgr = self.ai_assistant._orchestrate(
            task_desc,
            code,
            language=self.lang_combo.currentText()
        )

        if mgr is None:
            # Hardware can't support pipeline — reset UI
            self._is_processing = False
            if self._busy_timer.isActive():
                self._busy_timer.stop()
            self.preload_progress.setVisible(False)
            self.busy_indicator.setVisible(False)
            self.status_label.setText("Ready")
            debug_print("[DEBUG] Pipeline unavailable (insufficient RAM), falling back to single model")
            return False

        # Show pipeline start in chat
        self._add_chat_item("ai", f"🔷 *Pipeline: értelmező → kódoló → áttekintő*\n"
                                  f"Feladat: {task_desc}")

        # Connect signals
        self._orchestration_manager = mgr
        mgr.pipeline_progress.connect(self._on_pipeline_progress)
        mgr.pipeline_result.connect(self._on_pipeline_result)
        mgr.pipeline_error.connect(self._on_pipeline_error)

        return True

    def _on_pipeline_progress(self, phase: str, message: str):
        """Show pipeline phase changes as chat bubbles."""
        phase_icons = {
            "interpreter": "🔍",
            "coder": "✏️",
            "reviewer": "✅",
        }
        icon = phase_icons.get(phase, "➡️")
        self._add_chat_item("ai", f"{icon} *Pipeline — {phase.capitalize()}:* {message}")

    def _on_pipeline_result(self, code_content: str):
        """Handle pipeline completion — write code to editor + reset UI."""
        # Reset busy state — re-enable all controls
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self._set_controls_enabled(True)
        self.status_label.setText("Ready")

        self._pipeline_result_buffer = code_content

        if not code_content or not code_content.strip():
            self._add_chat_item("ai", "⚠️ *Pipeline kész,* de a kód üres volt.")
            return

        # Write to editor
        written = self._write_code_to_editor(code_content, lang="python")
        if written:
            self._add_chat_item("ai", "✅ *Pipeline kész.* A kód beírva a szerkesztőbe.")
        else:
            self._add_chat_item("ai", "✅ *Pipeline kész.* A kód a chat-ben látható (nem lett szerkesztőbe írva).")

        self._orchestration_manager = None

    def _on_pipeline_error(self, error_msg: str):
        """Handle pipeline errors + reset UI."""
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self._set_controls_enabled(True)
        self.status_label.setText("Hiba")
        self._add_chat_item("ai", f"❌ *Pipeline hiba:* {error_msg}")
        self._orchestration_manager = None

    # ------------------------------------------------------------------ #
    #  Enable/disable ALL controls during processing (only Cancel stays) #
    # ------------------------------------------------------------------ #
    def _set_controls_enabled(self, enabled: bool):
        """Disable or re-enable ALL interactive controls.
        When disabled (processing), only the Cancel button stays active.
        """
        all_controls = [
            getattr(self, 'model_combo', None),
            getattr(self, 'chain_combo', None),
            getattr(self, 'helper_model_combo', None),
            getattr(self, 'reviewer_model_combo', None),
            getattr(self, 'lang_combo', None),
            getattr(self, 'send_btn', None),
            getattr(self, 'suggest_btn', None),
            getattr(self, 'explain_btn', None),
            getattr(self, 'fix_btn', None),
            getattr(self, 'preload_btn', None),
            getattr(self, 'clear_btn', None),
            getattr(self, 'clear_chat_btn', None),
            getattr(self, 'increase_font_btn', None),
            getattr(self, 'decrease_font_btn', None),
            getattr(self, 'auto_preload_cb', None),
            getattr(self, 'context_window_cb', None),
            getattr(self, 'context_window_combo', None),
        ]
        for ctrl in all_controls:
            if ctrl is not None:
                try:
                    ctrl.setEnabled(enabled)
                except Exception:
                    pass
        # Cancel button: active only when processing (inverse of enabled)
        if hasattr(self, 'cancel_btn') and self.cancel_btn is not None:
            self.cancel_btn.setEnabled(not enabled)

    # ── Editor content helpers ────────────────────────────────────────
    def _get_editor_text(self) -> str:
        """Get the current text content of the focused editor (if any)."""
        try:
            parent = self.parent
            for _ in range(10):
                if not parent:
                    break
                etw = None
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                elif hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        etw = cur.editorTabWidget
                if etw and hasattr(etw, "focusedEditor"):
                    target = etw.focusedEditor()
                    if target:
                        # QsciScintilla path
                        if hasattr(target, "text") and hasattr(target, "lines"):
                            n = target.lines()
                            return "\n".join(target.text(i) for i in range(n))
                        # Plain QTextEdit path
                        if hasattr(target, "toPlainText"):
                            return target.toPlainText()
                        return ""
                parent = _safe_parent(parent)
        except Exception:
            pass
        return ""

    def _detect_syntax_errors(self, code: str) -> bool:
        """Quick check: try compile() to see if Python code has syntax errors."""
        if not code or not code.strip():
            return False
        try:
            compile(code, "<chain_output>", "exec")
            return False  # no errors
        except SyntaxError as e:
            debug_print(f"[CHAIN] Syntax error in generated code: {e}")
            return True
        except Exception:
            return True  # other errors (UnicodeDecodeError, etc.)

    # ------------------------------------------------------------------ #
    #  Force-write code to the active editor (no new tabs, no validator) #
    # ------------------------------------------------------------------ #
    def _force_write_to_editor(self, code: str) -> bool:
        """Directly write code into the focused editor, REPLACING all content.
        Unlike _write_code_to_editor, this bypasses:
        - Full-file-replacement heuristics
        - Import validator (chain output is explicitly a fix/suggest replacement)
        - New-tab fallback for 'snippets'
        Returns True on success, False if no editor found.
        """
        if not code or not code.strip():
            return False
        try:
            parent = self.parent
            for _ in range(10):
                if not parent:
                    break
                etw = None
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                elif hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        etw = cur.editorTabWidget
                if etw and hasattr(etw, "focusedEditor"):
                    target = etw.focusedEditor()
                    if target:
                        if hasattr(target, "setText"):
                            target.setText(code)
                        elif hasattr(target, "setPlainText"):
                            target.setPlainText(code)
                        if hasattr(target, "setModified"):
                            target.setModified(True)
                        debug_print(f"[CHAIN] Force-wrote {len(code)} chars to editor (new-tab free)")
                        return True
                parent = _safe_parent(parent)
        except Exception as e:
            debug_print(f"[CHAIN] Force-write failed: {e}")
        return False

    # ------------------------------------------------------------------ #
    #  Chain mode change: enable/disable helper model selector            #
    # ------------------------------------------------------------------ #
    def _on_chain_mode_changed(self, index: int):
        """Show/hide helper/reviewer selectors based on mode."""
        is_chain = index >= 1  # 1=2-Chain, 2=3-Chain, 3=Full Pipeline
        needs_reviewer = index >= 2  # 2=3-Chain, 3=Full Pipeline
        # Show helper in any chain mode, hide in Simple
        self.helper_model_combo.setVisible(is_chain)
        self.helper_label.setVisible(is_chain)
        # Show reviewer only in 3-model chain / pipeline modes
        self.reviewer_model_combo.setVisible(needs_reviewer)
        self.reviewer_label.setVisible(needs_reviewer)

    # ------------------------------------------------------------------ #
    #  Model chain (ChainWorker) — sequential interpreter→coder[→reviewer] #
    # ------------------------------------------------------------------ #
    def _start_chain_request(self, task: str, code: str, lang_inst: str, num_models: int = 3):
        """Start the sequential model chain.
        num_models=2 → interpreter + coder (no reviewer).
        num_models=3 → interpreter + coder + reviewer.
        Reads user-selected helper/reviewer models from the dropdowns.
        Shows which models are being used in the chat.
        """
        # Read user-selected helper model (if not Auto)
        helper_model = ""
        if hasattr(self, 'helper_model_combo') and self.helper_model_combo.isEnabled():
            helper_text = self.helper_model_combo.currentText()
            if helper_text and not helper_text.startswith("Auto"):
                helper_model = helper_text.split(" (")[0].strip()

        # Read user-selected reviewer model (if not Auto)
        reviewer_model = ""
        if num_models >= 3 and hasattr(self, 'reviewer_model_combo'):
            reviewer_text = self.reviewer_model_combo.currentText()
            if reviewer_text and not reviewer_text.startswith("Auto"):
                reviewer_model = reviewer_text.split(" (")[0].strip()

        # UI: disable ALL controls, show busy indicator, start progress bar
        self._set_controls_enabled(False)
        self.preload_progress.setVisible(True)
        self._is_processing = True
        self._busy_progress_value = 0
        self._busy_timer.start(50)
        mode_label = f"{num_models}-Model Chain: 🔍 Interpreter → ✏️ Coder"
        if num_models >= 3:
            mode_label += " → ✅ Reviewer"
        self.status_label.setText(mode_label)
        debug_print(f"[CHAIN] Starting {num_models}-model chain (helper={helper_model or 'auto'})")

        # Show start in chat with model info
        phases = "értelmező → kódoló" + (" → áttekintő" if num_models >= 3 else "")
        task_trunc = task[:200]
        current_main = self.model_combo.currentText() if hasattr(self, 'model_combo') else "?"
        model_info = f"Kódoló: **{current_main}**"
        if helper_model:
            model_info += f"\nÉrtelmező: **{helper_model}** (kézi)"
        else:
            model_info += "\nÉrtelmező: **auto** (kis modell ha elérhető)"
        if num_models >= 3:
            if reviewer_model:
                model_info += f"\nEllenőrző: **{reviewer_model}** (kézi)"
            else:
                model_info += "\nEllenőrző: **auto** (ugyanaz mint Értelmező)"
        msg = f"🔷 *{num_models}-modelles lánc: {phases}*\nFeladat: {task_trunc}\n\n_{model_info}_"
        self._add_chat_item("ai", msg)
        debug_print(f"[CHAIN] START: {model_info}")

        # Lang instruction contains full sentence like "Respond in Hungarian."
        # Extract just the language name for the chain worker
        lang = "English"
        if lang_inst:
            for known in ["Hungarian", "English", "German", "French", "Spanish"]:
                if known.lower() in lang_inst.lower():
                    lang = known
                    break

        self.ai_assistant._start_chain(task, code, lang=lang, num_models=num_models,
                                        model_interpreter=helper_model,
                                        model_reviewer=reviewer_model)

    def _on_chain_ready(self, result: str):
        """Handle chain completion — write final code to the active editor.
        Unlike the streaming code path (which processes each ```python block
        independently through _auto_write_code_blocks), this method tries
        to write the COMPLETE code as a single unit so it replaces the active
        editor content instead of opening new tabs."""
        debug_print(f"[CHAIN] _on_chain_ready received: {len(result)} chars")
        debug_print(f"[RESPONSE] Chain raw (len={len(result)}):\n{result}\n[END RESPONSE]")
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self._set_controls_enabled(True)
        self.status_label.setText("Ready")

        if not result or not result.strip():
            self._add_chat_item("ai", "⚠️ *A lánc elkészült,* de a kód üres volt.")
            return

        # Clean + display in chat
        result = self._clean_ai_response(result)
        self._add_chat_item("ai", result)

        # ── Attempt to write the code to the active editor ──
        import re as _re
        # Extract all ```python blocks and concatenate into one file
        blocks = _re.findall(r'```(?:python|py)?\s*\n(.*?)\n```', result, _re.DOTALL)
        full_code = ""
        if blocks:
            # Use the longest block (models often output one complete file + fragments)
            longest = max(blocks, key=len).strip()
            if len(longest) > 80:
                full_code = longest
            else:
                # All blocks are tiny — try concatenating unique ones
                seen = set()
                for b in blocks:
                    b = b.strip()
                    if b and b not in seen:
                        seen.add(b)
                        full_code += b + "\n\n"
                full_code = full_code.strip()

        if not full_code:
            # No ``` blocks — check if the whole response looks like code
            if _re.search(r'^(import |from |def |class )', result, _re.MULTILINE):
                full_code = result.strip()

        if full_code:
            # ── SAFETY GUARD: detect partial code that would DESTROY the file ──
            skip_write = False
            if not self._detect_syntax_errors(full_code):
                pass  # no syntax errors found, continue

            original_text = self._get_editor_text()
            if original_text and len(original_text.strip()) > 500:
                ratio = len(full_code) / max(len(original_text.strip()), 1)
                if ratio < 0.4 and not full_code.startswith(("#!/", "# -*-", "import ", "from ")):
                    # New code is <40% of original AND doesn't look like a full file start
                    skip_write = True
                    warn = (
                        "⚠️ *A lánc által generált kód ({new_len} char) sokkal rövidebb, "
                        "mint az eredeti fájl ({orig_len} char).*\n"
                        "A modell valószínűleg csak a megváltoztatott részt adta vissza, "
                        "nem a teljes fájlt.\n\n"
                        "A kód a chat-ben látható fent — kézzel másold be a megfelelő helyre!"
                    ).format(new_len=len(full_code), orig_len=len(original_text.strip()))
                    self._add_chat_item("ai", warn)
                    debug_print(f"[CHAIN] SAFETY: partial code detected ({ratio:.0%} of original), skipped write")
                    # Show the partial code with a note but DO NOT overwrite
                    self._add_chat_item("ai", f"📋 *Generált részlet:*\n```python\n{full_code}\n```")

            if not skip_write:
                # PRIMARY: force-write to the active editor (replaces content, no new tabs)
                ed_written = self._force_write_to_editor(full_code)
                if ed_written:
                    mode_label = "Pipeline" if "Pipeline" in self.status_label.text() else "Lánc"
                    self._add_chat_item("ai", f"✅ *{mode_label} kész.* A kód beírva a szerkesztőbe.")
                    debug_print(f"[CHAIN] Force-wrote {len(full_code)} chars to editor")
                else:
                    debug_print(f"[CHAIN] Force-write failed, NO FALLBACK — would create new tab")
                    # DO NOT fall back to _write_code_to_editor — it creates new tabs
                    # Instead, log and let user copy from chat
        else:
            # No ``` blocks — check if the whole response looks like code
            import re as _re2
            if _re2.search(r'^(import |from |def |class )', result, _re2.MULTILINE):
                ed_written3 = self._force_write_to_editor(result.strip())
                if ed_written3:
                    self._add_chat_item("ai", "✅ *Kód beírva a szerkesztőbe (nyers szövegből).*")
                else:
                    debug_print(f"[CHAIN] Force-write of raw code failed, NO FALLBACK")
            else:
                debug_print(f"[CHAIN] Result is text-only, no code to write")

    def _on_chain_status(self, status: str):
        """Update status label with current chain phase.
        Keep all controls disabled while chain is running — only Cancel is active."""
        self.status_label.setText(status)
        if status:
            self._set_controls_enabled(False)
            debug_print(f"[CHAIN] {status}")
        # else: empty status = chain finished/error — _on_chain_ready or on_error will reset UI

    def _parse_tool_calls(self, text: str):
        """Strict parser: only lines that start with 'TOOL:' after stripping echoed result text.
        Only accepts known tool names. Returns list of (name, args_dict).
        For replace_text creation we also tolerate the code being provided *after* the TOOL line
        (in a fence or as the remainder of the response). The caller will enrich args["new"] if missing.
        """
        import re
        known_tools = self.KNOWN_TOOLS
        calls = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.upper().startswith("TOOL:"):
                continue
            # Skip if it looks like an echoed result line we already cleaned
            lower = line.lower()
            if any(p in lower for p in ["tool result for", "tool output for"]):
                continue
            rest = line[5:].strip()
            m = re.match(r'(\w+)(.*)$', rest, re.IGNORECASE)
            if not m:
                continue
            name = m.group(1).lower()
            if name not in known_tools:
                continue  # ignore unknown
            argstr = m.group(2) or ""
            args = {}
            for k, v in re.findall(r'(\w+)=(".*?"|\S+)', argstr):
                v = v.strip('"')
                args[k] = v
            calls.append((name, args))
        return calls

    @staticmethod
    def _is_full_file_replacement(code: str, existing: str) -> bool:
        """Heuristic: is this code block likely a full-file replacement?
        Returns True if the code looks like a complete standalone program
        (imports + __main__ guard or substantial class/def structure)
        that should REPLACE the editor content rather than being appended.

        CRITICAL: must return False for partial snippets that look like
        full files but are missing imports that the existing file has.
        Small local models often emit 70-80% of a file but miss critical
        imports — treating those as full replacements is destructive.
        """
        if not code or not code.strip():
            return False
        lines = code.splitlines()
        has_import = any(l.strip().startswith(("import ", "from ")) for l in lines)
        has_main = "if __name__" in code
        has_class_def = any(l.strip().startswith(("class ", "def ")) for l in lines)
        is_long = len(lines) > 15

        # ── ANTI-DESTRUCTION CHECKS ──────────────────────────────────
        # If the existing file has imports that are clearly needed but
        # missing in the new code, the model only output a snippet.
        if existing and len(code) < len(existing) * 0.95:
            # Extract module-level import names from existing content
            import re as _re
            code_imports = set()
            for l in lines:
                m = _re.match(r'^\s*(?:import\s+(\S+)|from\s+(\S+)\s+import)', l)
                if m:
                    code_imports.add(m.group(1) or m.group(2))
            existing_lines = existing.splitlines()
            existing_imports = set()
            for l in existing_lines:
                m = _re.match(r'^\s*(?:import\s+(\S+)|from\s+(\S+)\s+import)', l)
                if m:
                    existing_imports.add(m.group(1) or m.group(2))
            # If existing has unique imports that the code block lacks,
            # this is a snippet, not a full replacement.
            missing = existing_imports - code_imports
            if missing and len(missing) >= len(existing_imports) * 0.5:
                return False

        # ── POSITIVE MATCHES ──────────────────────────────────────────
        # Complete program: imports + __main__ guard
        if has_import and has_main and is_long:
            return True
        # Large class/def structure with imports
        if has_import and has_class_def and is_long and len(code) > 300:
            return True
        # Code is very close to existing size (>= 90%) — likely a replacement
        if existing and len(code) > len(existing) * 0.9 and is_long:
            return True
        return False

    def _write_code_to_editor(self, code: str, lang: str = "python") -> bool:
        """Write a code block into the editor.
        Behaviour depends on editor state and code content:
        - Empty editor → always replaces content
        - Code looks like a full-file replacement
          (has imports + __main__, or imports + class/def + >300 chars,
           or >70% of existing size) → REPLACES content even if non-empty
        - Non-empty editor + snippet (not a full program) →
          opens new tab to avoid data loss

        Strips internal markers (# --- AI generated code ---) from both the
        incoming code and the existing content before comparison/writing.

        Returns True if the code was successfully written.
        Used by the auto-edit / stream mode to bypass the ReAct tool format entirely.
        """
        if not code or not code.strip():
            return False
        # Strip our own append markers from incoming code so they don't accumulate
        import re
        code = re.sub(r'^# --- AI generated code ---\s*\n?', '', code, flags=re.MULTILINE).strip()
        try:
            parent = self.parent
            for _ in range(10):
                if not parent:
                    break
                etw = None
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                elif hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        etw = cur.editorTabWidget
                if etw:
                    target = None
                    existing = ""
                    if hasattr(etw, "focusedEditor"):
                        target = etw.focusedEditor()
                    if target is None:
                        ci = etw.currentIndex() if hasattr(etw, "currentIndex") else 0
                        target = etw.getEditor(ci) if hasattr(etw, "getEditor") else None
                    if target:
                        try:
                            existing = target.text() if hasattr(target, "text") else ""
                            if not existing:
                                existing = target.toPlainText() if hasattr(target, "toPlainText") else ""
                            # Strip our own append markers from existing content for clean comparison
                            existing = re.sub(r'^# --- AI generated code ---\s*\n?', '', existing, flags=re.MULTILINE).strip()
                        except Exception:
                            existing = ""

                    empty = not existing.strip()

                    is_full = self._is_full_file_replacement(code, existing)
                    debug_print(f"[AUTO-EDIT] Decision: empty={empty}, is_full_replacement={is_full}, "
                                f"code_len={len(code)}, existing_len={len(existing)}")

                    if empty:
                        # Empty editor → safe to overwrite
                        if hasattr(target, "setText"):
                            target.setText(code)
                        elif hasattr(target, "setPlainText"):
                            target.setPlainText(code)
                        if hasattr(target, "setModified"):
                            target.setModified(True)
                        debug_print(f"[AUTO-EDIT] Code written to empty editor ({lang})")
                        return True

                    if is_full:
                        # Full-file replacement: guard against import-destructive rewrites.
                        # Small models often output code that's 80% correct but MISSES imports
                        # that the existing file references (e.g. QMainWindow, QApplication).
                        # If critical referenced names are not in the new import lines,
                        # reject the replacement and open a new tab instead.
                        can_replace = True
                        if existing:
                            import re as _re2
                            # Names used AFTER the import section in the existing file
                            existing_after_imports = "\n".join(
                                l for l in existing.splitlines()
                                if not l.strip().startswith(("import ", "from "))
                            )
                            used_qt_names = set()
                            for m in _re2.finditer(
                                r'\b(QApplication|QMainWindow|QWidget|QLabel|QPushButton|'
                                r'QTextEdit|QTimer|QImage|QPixmap|QtCore|QtGui|QtWidgets'
                                r'|QAction|QMenu|QToolBar|QStatusBar|QDialog|QVBoxLayout|QHBoxLayout'
                                r'|QLineEdit|QComboBox|QCheckBox|QRadioButton)\b',
                                existing_after_imports
                            ):
                                used_qt_names.add(m.group(1))
                            # Check if those names appear in the incoming code's import lines
                            incoming_import_lines = [l for l in code.splitlines()
                                                     if l.strip().startswith(("import ", "from "))]
                            incoming_import_text = " ".join(incoming_import_lines)
                            missing = {n for n in used_qt_names if n not in incoming_import_text}
                            # ALSO check for qualified references: models often use
                            # `QtCore.QTimer()` (qualified) instead of importing `QTimer` directly.
                            # If the incoming code has `from PyQt5 import QtCore` but uses
                            # `QtCore.QTimer`, the bare name 'QTimer' won't be in the import text,
                            # but it IS available via the qualified reference. We account for this
                            # by scanning the incoming code for `module.NAME` patterns where the
                            # module was imported as a top-level name (from PyQt5 import QtCore).
                            if missing:
                                for mod_name in list(missing):
                                    # Check if any incoming module import provides this as qualified ref
                                    for mod in ('QtCore', 'QtGui', 'QtWidgets'):
                                        if mod in incoming_import_text:
                                            # Does the incoming code body reference `mod.mod_name`?
                                            if _re2.search(rf'\b{_re2.escape(mod)}\.{_re2.escape(mod_name)}\b', code):
                                                missing.discard(mod_name)
                                                break
                            if missing:
                                can_replace = False
                                debug_print(
                                    f"[AUTO-EDIT] Full replacement REJECTED — missing imports for: {missing}. "
                                    f"Opening new tab instead to avoid data loss."
                                )

                        if can_replace:
                            if hasattr(target, "setText"):
                                target.setText(code)
                            elif hasattr(target, "setPlainText"):
                                target.setPlainText(code)
                            if hasattr(target, "setModified"):
                                target.setModified(True)
                            debug_print(f"[AUTO-EDIT] Code REPLACED editor content ({lang})")
                            return True

                    # Filter out tiny fragments: models often output multiple ```python blocks
                    # (a single import, a comment, etc.) that are useless as standalone code.
                    # Only write to new tab when the block is either large enough or has real
                    # code structure (class/def/main).
                    MIN_SNIPPET_SIZE = 150  # chars; smaller is likely an analysis fragment
                    _has_structure = any(
                        kw in code for kw in ["\ndef ", "\nclass ", "\nif __name__"]
                    )
                    if len(code) < MIN_SNIPPET_SIZE and not _has_structure:
                        debug_print(f"[AUTO-EDIT] Skipping tiny fragment ({len(code)} chars) — too small for new tab")
                        return True  # silently skip

                    if etw and hasattr(etw, "newEditor"):
                        # Non-empty editor + snippet (or rejected full replacement):
                        # open a new tab — NEVER append to active file.
                        ext = ".py" if lang in ("python", "py", "") else f".{lang}"
                        # Unique tab name to avoid pile-up of identically-named tabs
                        import time as _time
                        _ts = str(_time.time()).replace('.', '')[-6:]
                        new_name = f"ai_generated_{_ts}{ext}"
                        etw.newEditor(fileName=new_name)
                        # newEditor sets the new tab as current, so focusedEditor()
                        # gives us the newly created editor — set its content.
                        new_editor = etw.focusedEditor()
                        if new_editor:
                            if hasattr(new_editor, "setText"):
                                new_editor.setText(code)
                            elif hasattr(new_editor, "setPlainText"):
                                new_editor.setPlainText(code)
                        debug_print(f"[AUTO-EDIT] Code written to new tab '{new_name}' ({lang})")
                        return True
                    else:
                        debug_print(f"[AUTO-EDIT] Cannot write code: no newEditor on etw={etw}")
                        return False
                parent = _safe_parent(parent)
                if parent is None or parent == getattr(self, 'parent', None):
                    break
        except Exception as e:
            debug_print(f"[AUTO-EDIT] Failed to write to editor: {e}")
        return False

    @staticmethod
    def _is_analysis_quote(code: str, existing_content: str = "") -> bool:
        """Heuristic: is this code block just quoting code for context/analysis,
        rather than being an actual code fix to write to the editor?
        Small models often embed quoted code lines in ```python blocks.
        Writing those floods the editor with code fragments.

        existing_content: the current editor content. Code blocks that are a
        verbatim subset of the existing content are likely analysis quotes.
        """
        stripped = code.strip()
        if not stripped:
            return True
        lines = [l.strip() for l in stripped.splitlines() if l.strip()]
        num_lines = len(lines)
        total_chars = len(stripped)

        # Tiny snippets (< 30 chars or single line < 60) are always quotes
        if total_chars < 30:
            return True
        if num_lines <= 1 and total_chars < 60:
            return True

        # Code with structural elements (import, def, class, __main__)
        # is likely a real fix/output, not an analysis quote
        has_structural = any(
            l.startswith(("import ", "from ", "def ", "class ", "for ", "while "))
            for l in lines
        ) or "if __name__" in stripped

        if has_structural:
            return False

        # If the code block is entirely contained in existing content,
        # it's an analysis quote, not a fix
        if existing_content and stripped in existing_content:
            return True

        # 1-2 lines with no structure → likely a quote
        if num_lines <= 2 and total_chars < 100:
            return True

        # 3+ lines or substantial → likely real code
        return False

    def _extract_all_code_blocks(self, text: str, existing_content: str = "") -> list:
        """Extract ALL ```...``` code blocks from model output.
        Filters out analysis quotes (code already present in existing_content).
        Returns list of (language, code) tuples.
        """
        if not text:
            return []
        import re
        blocks = []
        # Match ```lang ... ``` or ``` ... ```
        pattern = r"```(\w*)\s*\r?\n(.*?)\r?\n```"
        for m in re.finditer(pattern, text, re.DOTALL):
            lang = m.group(1).strip().lower() or "python"
            code = m.group(2).strip()
            if code and len(code) > 10 and not self._is_analysis_quote(code, existing_content):
                blocks.append((lang, code))
        if not blocks:
            # Fallback for inline code without closing newlines
            pattern2 = r"```(\w*)\s*(.*?)```"
            for m in re.finditer(pattern2, text, re.DOTALL):
                lang = m.group(1).strip().lower() or "python"
                code = m.group(2).strip()
                if code and len(code) > 15 and not self._is_analysis_quote(code, existing_content):
                    blocks.append((lang, code))
        return blocks

    def _auto_write_code_blocks(self, content: str) -> list:
        """Extract code blocks from AI response and write them to the active editor.
        Deduplicates identical blocks so the same code isn't written multiple times
        (common with small models that repeat the same ```python block in explanations).
        Returns list of (language, status) tuples.
        Written blocks get a chat note; non-code text stays in chat as-is.
        """
        # Get existing editor content to filter analysis quotes
        existing = ""
        try:
            parent = self.parent
            for _ in range(10):
                if not parent:
                    break
                etw = None
                if hasattr(parent, "editorTabWidget"):
                    etw = parent.editorTabWidget
                elif hasattr(parent, "projectWindowStack"):
                    cur = parent.projectWindowStack.currentWidget()
                    if cur and hasattr(cur, "editorTabWidget"):
                        etw = cur.editorTabWidget
                if etw:
                    target = None
                    if hasattr(etw, "focusedEditor"):
                        target = etw.focusedEditor()
                    if target is None:
                        ci = etw.currentIndex() if hasattr(etw, "currentIndex") else 0
                        target = etw.getEditor(ci) if hasattr(etw, "getEditor") else None
                    if target:
                        if hasattr(target, "text"):
                            existing = target.text()
                        elif hasattr(target, "toPlainText"):
                            existing = target.toPlainText()
                    break
                parent = _safe_parent(parent)
        except Exception:
            existing = ""

        blocks = self._extract_all_code_blocks(content, existing)
        if not blocks:
            return []
        # Deduplicate: identical code blocks are only written once
        seen = set()
        unique_blocks = []
        for lang, code in blocks:
            key = (lang, code.strip())
            if key not in seen:
                seen.add(key)
                unique_blocks.append((lang, code))
        results = []
        for lang, code in unique_blocks:
            ok = self._write_code_to_editor(code, lang)
            results.append((lang, "written" if ok else "failed"))
            debug_print(f"[AUTO-EDIT] Block {lang}: {'written to editor' if ok else 'write failed'}")
        if len(blocks) != len(unique_blocks):
            debug_print(f"[AUTO-EDIT] Deduplicated {len(blocks) - len(unique_blocks)} identical block(s)")
        return results

    def _extract_code_from_response(self, text: str) -> str:
        """Best-effort extraction of a python code block from model output.
        Used as fallback for creation requests when the model did not (or could not) put
        the full code inside a single-line new="..." arg. This makes 'Írj egy példakódot a szerkesztőbe'
        work even with smaller models that just emit a normal ```python response.
        """
        if not text:
            return ""
        import re
        # Prefer ```python ... ``` or ``` ... ``` (handle optional \r, missing newlines after ``` etc.)
        patterns = [
            r"```python\s*\r?\n(.*?)\r?\n```",
            r"```\s*\r?\n(.*?)\r?\n```",
            r"```python\s*(.*?)```",
            r"```(.*?)```",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            if m:
                code = m.group(1).strip()
                if len(code) > 20 and ("import " in code or "def " in code or "class " in code or "from " in code or "PySide" in code or "QApplication" in code):
                    # Guard: don't treat our own few-shot skeleton as the payload
                    if "import sys" in code and "PyCoder" not in code and len(code) < 120:
                        continue
                    return code
        # Fallback: if the response after a TOOL: replace line contains a lot of indented or typical python, take a large chunk
        # (we will validate at call site that we are in creation + editor empty).
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.strip().upper().startswith("TOOL:") and "replace" in ln.lower():
                tail = "\n".join(lines[i+1:]).strip()
                # cut at next obvious marker
                for marker in ["[SYSTEM", "TOOL:", "Response:", "Ready", "Code written", "Tool interaction"]:
                    if marker in tail:
                        tail = tail.split(marker)[0].strip()
                if len(tail) > 30 and ("import " in tail or "from " in tail or "def " in tail or "class " in tail):
                    return tail
        # Last resort for creation: the model just dumped a big python program as plain text
        # (no fences, no preceding TOOL line) – common with small models on "írj a szerkesztőbe".
        # Only use when we are in explicit creation context (caller decides) and it looks like real code.
        if "def " in text or "class " in text or ("import " in text and ("PySide" in text or "QApplication" in text or "cv2." in text)):
            # Heuristic: strip obvious leading chat / explanation lines, keep from first plausible code line
            lines = text.splitlines()
            code_lines = []
            started = False
            for ln in lines:
                s = ln.strip()
                if not started:
                    if s.startswith(("#", "import ", "from ", "def ", "class ", "\"\"\"", "'''")) or "PySide" in s or "QApplication" in s:
                        started = True
                if started:
                    # stop before obvious trailing chat
                    if s.startswith(("If the tool", "Code written", "Done", "Response:", "Tool interaction")):
                        break
                    code_lines.append(ln)
            candidate = "\n".join(code_lines).strip()
            if len(candidate) > 40:
                return candidate
        return ""

    def _smart_truncate_for_context(self, code: str, file_path: str = "", safety_note: bool = True) -> str:
        """Intelligent truncation when custom context window is enabled.
        Goal: never let the code part blow up the model's context window.
        Strategy:
        - If not enabled or code is small → return as-is.
        - Rough token estimate (code is ~3.5-4 chars per token).
        - Keep head (imports, class/function signatures, top of file) + tail (recent logic).
        - For bug hunting ("keress hibákat") we keep a bit more of the middle by using
          larger head/tail fractions and we always surface the original file identity.
        - Add a clear note so the model knows it was truncated (transparency).
        This is the "okos + intelligens" part on top of the safety dropdown.
        """
        if not getattr(self.ai_assistant, 'context_window_enabled', False):
            return code

        size = getattr(self.ai_assistant, 'context_window_size', 0) or 8192
        max_code_tokens = max(1024, int(size * 0.50))
        max_chars = int(max_code_tokens * 3.8)

        if len(code) <= max_chars:
            return code

        lines = code.splitlines(keepends=True)
        n = len(lines)
        if n <= 8:
            truncated = code[:max_chars]
        else:
            # Slightly more generous for analysis/bug finding than pure "50%".
            head = lines[: max(5, n // 2)]
            tail = lines[-max(4, n // 3):]
            truncated = ''.join(head) + "\n\n# ... [code truncated to fit context window ({})] ...\n\n".format(size) + ''.join(tail)

        if safety_note:
            fp = file_path or "(unknown file)"
            truncated += f"\n\n# [Note: the content above is a truncated view of the live open file because custom context window ({size} tokens) is enabled. Original file: {fp}]"

        debug_print(f"[DEBUG] Smart truncated code from {len(code)} to ~{len(truncated)} chars for context window")
        return truncated

    def _localized_action(self, action: str) -> str:
        """Return a localized short description for the quick action buttons (Suggest/Explain/Fix).
        The visible 'user' bubble in the chat should be in the same language as the selected
        AI response language (from the dropdown), so the conversation flow feels consistent.
        """
        lang = ""
        if hasattr(self, "lang_combo") and self.lang_combo is not None:
            lang = self.lang_combo.currentText().lower()
        else:
            lang = getattr(self.ai_assistant, "get_language", lambda: "English")().lower()

        if lang.startswith("hungar"):
            if action == "suggest":
                return "Javasolj fejlesztéseket a megnyitott kódhoz"
            elif action == "debug":
                return "Keress hibákat a megnyitott kódban"
            elif action == "explain":
                return "Magyarázd el részletesen a megnyitott kódot"
            elif action == "fix":
                return "Javítsd ki a hibákat a megnyitott kódban"
        elif lang.startswith("german"):
            if action == "suggest":
                return "Schlage Verbesserungen für den geöffneten Code vor"
            elif action == "debug":
                return "Finde Fehler im geöffneten Code"
            elif action == "explain":
                return "Erkläre den geöffneten Code detailliert"
            elif action == "fix":
                return "Behebe Fehler im geöffneten Code"
        elif lang.startswith("slovak"):
            if action == "suggest":
                return "Navrhni vylepšenia pre otvorený kód"
            elif action == "debug":
                return "Nájdi chyby v otvorenom kóde"
            elif action == "explain":
                return "Vysvetli podrobne otvorený kód"
            elif action == "fix":
                return "Oprav chyby v otvorenom kóde"
        else:
            # English fallback
            if action == "suggest":
                return "Suggest improvements for the open code"
            elif action == "debug":
                return "Find bugs in the open code"
            elif action == "explain":
                return "Explain the open code in detail"
            elif action == "fix":
                return "Fix errors in the open code"
        return action

    def configure_ai_assistant(self, settings):
        """Configure AI assistant with settings dict.

        Called at startup and whenever the settings dialog is closed.
        """
        api_provider = settings.get("ai_api_provider", "ollama")
        api_key = settings.get("ai_api_key", "")
        api_url = settings.get("ai_api_url", "http://localhost:11434")
        default_model = settings.get("ai_default_model", "claude-3-5-sonnet-20241022")
        timeout = int(settings.get("ai_timeout", 120))
        cache_enabled = settings.get("ai_cache_enabled", "True") == "True"

        # Preserve current model selection before reloading
        prev_model = self.model_combo.currentText() if self.model_combo.count() > 0 else ""

        # Configure the AI assistant with the new provider
        self.ai_assistant.set_api_config(
            api_url, api_key, default_model,
            timeout=timeout, cache_enabled=cache_enabled,
            provider=api_provider,
        )

        # Reload the model dropdown since the provider may have changed
        # Reset setup_complete to prevent _on_model_changed from saving during reload
        was_setup_complete = getattr(self, '_setup_complete', False)
        self._setup_complete = False
        self.load_models()
        self._setup_complete = was_setup_complete

        # Restore previous model selection if possible
        if prev_model:
            idx = self.model_combo.findText(prev_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
                # _on_model_changed will be triggered but _setup_complete was restored,
                # so saving happens only if it was already True before reload
            else:
                # Previous model not found — try _load_last_model_setting as fallback
                self._load_last_model_setting()

        print(f"DEBUG: AI Assistant configured - Provider: {api_provider}, Model: {default_model}, "
              f"Timeout: {timeout}s, Cache: {cache_enabled}")

    def _reset_busy_state(self):
        """Defensive full reset of any previous busy state before starting a new action.
        Shared by Suggest, Debug, Explain, and Fix handlers.
        """
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        if hasattr(self, '_preload_ramp_timer') and self._preload_ramp_timer.isActive():
            self._preload_ramp_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.busy_indicator.setVisible(False)
        self._ignore_next_ai_result = False

    def on_suggest_clicked(self):
        """Handle suggest improvements button click — only code improvements, no bug finding."""
        debug_print("[USER] Suggest button clicked")
        self._reset_busy_state()

        code, file_path, project_root = self._get_active_code_and_context()
        if not code or not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to analyze!")
            self._set_controls_enabled(True)
            return

        # Smart truncation when user enabled a limited context window (safety feature).
        truncated = self._smart_truncate_for_context(code, file_path)

        context_header = ""
        if project_root or file_path:
            context_header = f"CURRENTLY OPEN FILE:\nProject root: {project_root}\nCurrent file: {file_path}\n\n"

        lang_inst = self.ai_assistant._get_lang_instruction()

        self._add_chat_item("user", self._localized_action("suggest"))

        task_desc = "Analyze code and suggest improvements"
        chain_mode = getattr(self, 'chain_combo', None) and self.chain_combo.currentIndex()
        if chain_mode == 3:
            # Full Pipeline (old OrchestrationManager)
            pipeline_ok = self._start_pipeline_for_fix(task_desc, truncated, lang_inst)
            if not pipeline_ok:
                # Fallback to single model if pipeline can't start
                rich_code = (
                    f"{context_header}"
                    "=== CODE ===\n"
                    f"{truncated}\n"
                    "=== END ===\n\n"
                    "Review the code above. Suggest concrete improvements, refactoring "
                    "opportunities, and best practices. Be brief and specific."
                    f"{lang_inst}"
                )
                self.start_ai_request("suggestion", rich_code)
        elif chain_mode in (1, 2):
            # 2-Model Chain or 3-Model Chain
            self._start_chain_request(task_desc, truncated, lang_inst, num_models=chain_mode + 1)
        else:
            # Simple — single model
            rich_code = (
                f"{context_header}"
                "=== CODE ===\n"
                f"{truncated}\n"
                "=== END ===\n\n"
                "Review the code above. Suggest concrete improvements, refactoring "
                "opportunities, and best practices. Be brief and specific."
                f"{lang_inst}"
            )
            self.start_ai_request("suggestion", rich_code)

    def on_debug_clicked(self):
        """Handle debug button click — find bugs and tracebacks in the code."""
        debug_print("[USER] Debug button clicked")
        self._reset_busy_state()

        code, file_path, project_root = self._get_active_code_and_context()
        if not code or not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to analyze!")
            self._set_controls_enabled(True)
            return

        # Smart truncation when user enabled a limited context window (safety feature).
        truncated = self._smart_truncate_for_context(code, file_path)

        context_header = ""
        if project_root or file_path:
            context_header = f"CURRENTLY OPEN FILE:\nProject root: {project_root}\nCurrent file: {file_path}\n\n"

        # Debug always includes recent error output if available
        recent_error = self._get_recent_run_output(max_lines=60)
        error_part = ""
        if recent_error:
            error_part = (
                ">>> LATEST RUN ERROR / TRACEBACK:\n"
                f"{recent_error}\n\n"
            )

        lang_inst = self.ai_assistant._get_lang_instruction()

        self._add_chat_item("user", self._localized_action("debug"))

        task_desc = error_part or "Find bugs and errors in the code"
        chain_mode = getattr(self, 'chain_combo', None) and self.chain_combo.currentIndex()
        if chain_mode == 3:
            # Full Pipeline (old OrchestrationManager)
            pipeline_ok = self._start_pipeline_for_fix(task_desc, truncated, lang_inst)
            if not pipeline_ok:
                # Fallback to single model if pipeline can't start
                rich_code = (
                    f"{context_header}"
                    f"{error_part}"
                    "=== CODE ===\n"
                    f"{truncated}\n"
                    "=== END ===\n\n"
                    "Analyze the code above for bugs and errors. If there is a traceback, "
                    "find the bug causing it. Quote the relevant line. "
                    "Suggest concrete fixes. Be brief."
                    f"{lang_inst}"
                )
                self.start_ai_request("debug", rich_code)
        elif chain_mode in (1, 2):
            # 2-Model Chain or 3-Model Chain
            self._start_chain_request(task_desc, truncated, lang_inst, num_models=chain_mode + 1)
        else:
            # Simple — single model
            rich_code = (
                f"{context_header}"
                f"{error_part}"
                "=== CODE ===\n"
                f"{truncated}\n"
                "=== END ===\n\n"
                "Analyze the code above for bugs and errors. If there is a traceback, "
                "find the bug causing it. Quote the relevant line. "
                "Suggest concrete fixes. Be brief."
                f"{lang_inst}"
            )
            self.start_ai_request("debug", rich_code)

    def on_explain_clicked(self):
        """Handle explain code button click"""
        # Defensive full reset (same as Suggest)
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        if hasattr(self, '_preload_ramp_timer') and self._preload_ramp_timer.isActive():
            self._preload_ramp_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.busy_indicator.setVisible(False)
        self._ignore_next_ai_result = False

        code, file_path, project_root = self._get_active_code_and_context()
        if not code or not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to explain!")
            self._set_controls_enabled(True)
            return

        truncated = self._smart_truncate_for_context(code, file_path)

        context_header = ""
        if project_root or file_path:
            context_header = f"Project root: {project_root}\nCurrent file: {file_path}\n\n"
        lang_inst = self.ai_assistant._get_lang_instruction()
        rich_code = (
            f"{context_header}"
            "=== CODE ===\n"
            f"{truncated}\n"
            "=== END ===\n"
            "Explain what this code does — key parts, data flow, non-obvious behavior. Be clear."
            f"{lang_inst}"
        )

        self._add_chat_item("user", self._localized_action("explain"))
        self.start_ai_request("explanation", rich_code)

    def update_icon_theme(self):
        """Update icon theme based on system theme.
        If the environment provides a dark/light preference, we can in the future
        swap icon sets (e.g. light vs dark variants). Currently we use color icons
        that are designed to work on both.
        """
        # We already adapt the main editor color scheme in UseData based on system.
        # For icons, keep the existing robust color ones.
        pass

    def _is_likely_casual_chat(self, text: str) -> bool:
        """Heuristic to decide the prompt style for custom Send.

        - True (direct/simple path): greetings, status, or direct "find the bug / review this open file" requests.
          These should get a clean, direct analysis prompt (like the good "better_response" backup the user saved).
          No forced agent role, no tool calling instructions, no "you must output TOOL: replace_text".

        - False (full agent path): only when the user explicitly wants the AI to act as an autonomous
          coder agent that explores the project with tools and performs edits (e.g. "szerkeszd bele",
          "használd a replace_text toolt", "listázd a fájlokat és javítsd ki a hibákat a toolokkal").
        """
        t = (text or "").strip().lower()
        if not t:
            return True
        if len(t) <= 4:
            return True

        casual_markers = [
            # English
            "ready", "hello", "hi ", "hey", "thanks", "thank you",
            "are you there", "listening", "you there", "ready to work",
            "run the file", "run", "execute", "start", "launch",
            # Hungarian (original)
            "kész vagy", "itt vagy", "szia", "szevasz",
            "megy", "minden oké", "oké", "kösz", "köszönöm", "hogy vagy",
            "van itt valaki", "figyelsz", "hallasz", "készen állsz", "munkára",
            "futtasd", "futtass", "futtasd a fájlt", "indítsd", "futtasd el",
        ]
        for m in casual_markers:
            if m in t:
                return True

        # Direct bug finding / code review on the *currently open file* (the common useful case).
        # These should behave like the good previous version: strong context + direct sensible answer.
        # Do NOT force the full tool-calling reviewer agent for these.
        direct_review_markers = [
            # English
            "find the bug", "find bug", "review the code", "review this code",
            "code review", "bug hunt", "look for bugs", "search for error",
            "find error", "find mistake",
            # Hungarian
            "keress hib", "keresd meg a hib", "keres hib", "hibát keres", "hibakeres",
            "keresd a hibát", "mutasd a hibát",
            "nézd meg a hibát", "elemzed a hibát",
            "nézd át a kódot", "vizsgáld meg a kódot", "hibát a kódban",
        ]
        for m in direct_review_markers:
            if m in t:
                return True

        # Action keywords that usually mean "do something with the open code"
        action_kw = [
            # English
            "review", "analyze", "check", "examine", "look at", "read", "show",
            "fix", "edit", "change", "modify", "refactor", "improve", "update",
            "code", "file", "project", "error", "bug", "function",
            # Hungarian (original)
            "vizsgál", "nézd", "nézd át", "javíts", "javít", "szerkesz", "szerkeszd",
            "olvasd", "mutasd", "elemezd",
            "kódot", "fájlt", "projektet", "hibát", "refaktor",
        ]
        has_action = any(kw in t for kw in action_kw)

        if len(t) < 70 and not has_action:
            return True

        return False

    def _clean_ai_response(self, content: str) -> str:
        """Central cleaning to strip any leaked prompt instructions, tool results,
        or meta text from AI responses (prevents the "Analyze ONLY...", "Remember: the entire answer..."
        style leakage seen in custom and quick button outputs).

        Also strips bracket-style tool markers ([read_file], [/read_file], [list_project_files], etc.)
        that the model may emit as part of its response and which have no place in the user-visible chat.
        Now properly removes the ENTIRE [tool]...[/tool] block (including contents) before
        any per-line filtering, and then chains the existing echo/leak cleanup on the result.
        """
        if not content:
            return content

        import re

        # 1) Remove lines that start with TOOL:
        lines = content.splitlines()
        cleaned = [l for l in lines if not l.strip().upper().startswith("TOOL:")]
        text = "\n".join(cleaned)

        # 2) Remove complete [tool_name]...[/tool_name] blocks (with their content).
        #    Run this BEFORE individual tag removal so content inside blocks is also removed.
        for tool_pattern in [r'\[list_project_files\].*?\[/list_project_files\]',
                              r'\[read_file\].*?\[/read_file\]',
                              r'\[replace_text\].*?\[/replace_text\]',
                              r'\[tool_results\].*?\[/tool_results\]',
                              r'\[/results\].*?\[/end\]']:
            text = re.sub(tool_pattern, '', text, flags=re.DOTALL)

        # 3) Remove any remaining lone [tag] or [/tag] lines that weren't inside a complete block
        text = re.sub(r'^\s*\[/?\w+\]\s*$', '', text, flags=re.MULTILINE)

        # 4) Now re-split into lines for the existing echo/leak filtering
        lines = text.splitlines()

        # 5) Filter echoed/system phrase lines
        # NOTE: only filter ENGLISH system-prompt leakage, NOT Hungarian user content.
        # Previously Hungarian phrases like "a hibás sor", "a kódot módosítottam",
        # "javaslatok a valós kódra" were filtered here — but those are perfectly normal
        # model responses in Hungarian and got stripped, making it look like the model
        # wasn't responding or wasn't writing code. The user saw only response fragments.
        echoed = [
            "tool result for", "tool output for", "tool result for tool:", "tool result for you:",
            "analyze only the code", "quote the exact", "explain the real root cause",
            "do not invent unrelated", "do not repeat yourself", "do not talk about previous chats",
            "remember: the entire answer must be",
        ]
        cleaned = [l for l in lines if not any(p in l.lower() for p in echoed)]

        # 6) Filter leaked instruction/artifact lines (English only — same reasoning as above)
        leaked = [
            "CRITICAL RULE", "You are a helpful AI assistant inside the PyCoder IDE",
            "Analyze ONLY the code and error above", "Do not invent unrelated functions",
            "Remember: the entire answer must be in",  # matches both English and Hungarian variants
            "[SYSTEM TOOL RESULTS", "[END SYSTEM TOOL RESULTS]",
            "Tool result for tool:",
        ]
        cleaned = [l for l in cleaned if not any(ph.lower() in l.lower() for ph in leaked)]
        text = "\n".join(cleaned).strip()

        # 7) Detect and truncate repetitive / looping patterns.
        #    Models sometimes get stuck repeating the same sentence or paragraph structure.
        #    We detect this by counting how many lines/paragraphs repeat and truncating.
        text = self._truncate_repetition(text)

        # 8) Fix hallucinated Qt framework imports (PyQt6→PySide6 or vice versa).
        #    This runs AFTER all other cleaning so we don't waste effort on leaked lines.
        try:
            text = self._fix_framework_imports(text)
        except Exception:
            pass  # Don't crash if editor access fails
        return text

    def _truncate_repetition(self, text: str) -> str:
        """Detect and truncate repetitive / looping patterns in model output.
        If the same sentence or paragraph structure repeats 3+ times,
        truncate at the first occurrence of the cycle.

        Handles numbered lists where the numbering changes but the content
        is identical (e.g. "3  Az osztálykon...", "4  Az osztálykon...").
        """
        if not text:
            return text

        import re

        # Strip leading numbering from a line/paragraph for comparison
        _num_re = re.compile(r'^\d+\s*[\.\)]?\s*')

        # ── Strategy 1: Detect repeated paragraphs ──
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) >= 4:
            from collections import Counter
            # Strip numbering before comparing
            stripped_paras = [_num_re.sub('', p).strip() for p in paragraphs]
            para_counter = Counter(stripped_paras)
            most_common_stripped, count = para_counter.most_common(1)[0]
            if count >= 3 and len(most_common_stripped) > 20:
                # Find the FIRST original paragraph that matches
                first_original = None
                for p in paragraphs:
                    if _num_re.sub('', p).strip() == most_common_stripped:
                        first_original = p
                        break
                if first_original:
                    cut_text = "\n\n".join(paragraphs)
                    first_idx = cut_text.index(first_original)
                    debug_print(f"[INFO] Truncated repetitive response at para #{count}x "
                                f"(first: {most_common_stripped[:60]}...)")
                    return cut_text[:first_idx].rstrip() + "\n\n[...]"

        # ── Strategy 2: Detect repeated sentence-level patterns ──
        lines = text.split("\n")
        if len(lines) >= 6:
            seen_structures = []
            repeat_start = -1
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                # Normalize: strip numbering, then replace quoted/backticked content
                normalized = _num_re.sub('', stripped)
                normalized = re.sub(r'`[^`]+`', '`...`', normalized)
                normalized = re.sub(r'"[^"]+"', '"..."', normalized)
                # Find if we've seen this structure before
                if normalized in seen_structures:
                    if repeat_start < 0:
                        repeat_start = i
                    # If same structure appears 3+ times, truncate
                    if seen_structures.count(normalized) >= 2:
                        debug_print(f"[INFO] Truncated looping response at line {i} "
                                    f"(repeated structure: {normalized[:60]}...)")
                        return "\n".join(lines[:repeat_start]).rstrip() + "\n\n[...]"
                else:
                    seen_structures.append(normalized)

        return text

    def _build_creation_prompt(self, user_prompt: str, file_path: str) -> str:
        """Simple, clean prompt for high-quality code generation.
        With auto-edit / stream mode the model NEVER needs to know about tools.
        It just outputs code in ``` blocks — our client-side logic extracts those
        blocks and writes them into the active editor tab automatically.
        No ReAct format, no TOOL: lines, no tool instructions — just pure code.
        """
        target = (file_path or "").strip()
        if not target or "untitled" in target.lower() or not target.endswith(".py"):
            target = "main.py"

        p = (
            "YOU ARE A HIGH QUALITY MODERN PYTHON CODE GENERATOR.\n\n"
            "Task: given the user request below, produce the best possible complete, immediately executable Python code.\n\n"
            "CODE QUALITY REQUIREMENTS (THIS IS THE MOST IMPORTANT PART):\n"
            "- Complete, self-contained script — nothing missing, no \"...\", no TODO, no placeholders.\n"
            "- Use clean PySide6 (do NOT mix with PyQt5 or PyQt6 anywhere).\n"
            "- Handle processes, errors, release(), thread safety where needed (QTimer on the main thread).\n"
            "- Modern, readable style: connect(), good variable names, comments only where truly needed.\n\n"
            "FORMAT:\n"
            "Your answer may include text (explanation for the user), "
            "and the code MUST be placed inside ```python ... ``` blocks.\n"
            "Any ```python block is automatically written into the editor.\n\n"
            f"TARGET FILE: {target}\n"
            f"USER REQUEST: {user_prompt}\n\n"
            "Now generate the best code your model can produce. "
            "The code goes inside ```python ... ``` blocks; any text stays OUTSIDE the block."
        )
        return p

    def _framework_instruction(self, code: str) -> str:
        """Detect which Qt framework the code uses and return the appropriate
        import instruction for the prompt. Prevents hallucinations where the
        model suggests PyQt6 imports for PySide6 code (or vice versa).
        The instruction is deliberately strong and specific — small models
        (3B-8B parameters) tend to hallucinate PyQt6→PySide6 migration steps
        even when the code already uses PySide6 correctly.
        """
        lower = code.lower()
        if "pyside6" in lower:
            return (
                "- IMPORTANT: This code ALREADY uses PySide6 correctly.\n"
                "- DO NOT suggest changing imports from PyQt6 to PySide6 — there are NO PyQt6 imports.\n"
                "- DO NOT invent a 'PyQt6 import error' — the code has none.\n"
                "- Keep all 'from PySide6 import ...' lines exactly as they are."
            )
        elif "pyqt6" in lower:
            return "- IMPORTANT: This code uses PyQt6. Only use 'from PyQt6 import ...' (NOT PyQt5 or PySide6)."
        elif "pyqt5" in lower:
            return "- IMPORTANT: This code uses PyQt5. Only use 'from PyQt5 import ...'."
        else:
            return "- If the code uses a Qt framework, stick with whatever it already imports."

    def _fix_framework_imports(self, content: str) -> str:
        """Post-processing: fix hallucinated Qt framework imports in model responses.
        Scans the original editor code to determine the correct framework,
        then auto-corrects any hallucinated imports in the model's response.
        This catches cases where the model ignores the framework instruction
        and suggests PyQt6 imports for PySide6 code (or vice versa).
        """
        code = self._get_editor_text() or ""
        lower = code.lower()
        if "pyside6" in lower:
            # Code uses PySide6 → replace any hallucinated PyQt6 imports
            content = content.replace("from PyQt6.", "from PySide6.")
            content = content.replace("from PyQt6 import", "from PySide6 import")
            return content
        elif "pyqt6" in lower:
            # Code uses PyQt6 → replace any hallucinated PySide6 imports
            content = content.replace("from PySide6.", "from PyQt6.")
            content = content.replace("from PySide6 import", "from PyQt6 import")
            return content
        return content

    def on_send_clicked(self):
        """Handle send button click - send prompt to AI.
        UNIFIED PROMPT ARCHITECTURE:
        - User prompt is sent to the model in English with full context
        - The model's response language is controlled by the language dropdown
        - No keyword detection / classification (creation/edit/review)
        - The model outputs ```python blocks for code; auto-edit handles writing
        - Analysis/explanation code blocks are filtered by _is_analysis_quote
        - Full agent (tool-based) mode is only used when explicitly requested
        """
        debug_print(f"[USER] Send button clicked — user typed in composer")

        prompt_text = self.prompt_input.toPlainText()
        debug_print(f"[USER] User raw input (len={len(prompt_text)}):\n{prompt_text}\n[END USER INPUT]")
        if not prompt_text.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "Please enter a prompt!")
            return

        # Resolve code context
        code, file_path, project_root = self._get_active_code_and_context()
        if project_root and os.path.isdir(project_root):
            self._last_known_project_root = project_root

        truncated_code = self._smart_truncate_for_context(code, file_path) if (code and code.strip()) else ""

        # ALWAYS capture recent run output — the most common complaint was that
        # the model didn't see the traceback the user was looking at.
        recent_error = self._get_recent_run_output(max_lines=80)
        error_block = ""
        if recent_error:
            error_block = (
                ">>> LATEST RUN ERROR / TRACEBACK (the user just ran the program):\n"
                f"{recent_error}\n\n"
            )

        # Language directive for the model output (prompt stays English)
        lang_instruction = self.ai_assistant._get_lang_instruction()

        # ── CONTINUATION FROM ASK_USER ──
        # If the model previously used TOOL: ask_user, the user's next Send
        # should be treated as a reply to that question, not a new request.
        continuation_block = ""
        pending_question = getattr(self, '_pending_ai_question', None)
        if pending_question:
            continuation_block = (
                "=== CONTINUATION (the AI asked a question, and the user is answering) ===\n"
                f"AI asked: {pending_question}\n"
                f"User's answer: {prompt_text}\n"
                "=== END CONTINUATION ===\n\n"
                "Continue from here. The user is responding to your question above. "
                "If their answer is clear, proceed with the task. "
                "If you need to ask a follow-up, use TOOL: ask_user again.\n\n"
            )
            self._pending_ai_question = None  # consumed

        # ── SIMPLE UNIFIED PROMPT (NO TOOL DESCRIPTIONS FOR SMALL MODELS) ──
        # Tool descriptions (TOOL: ask_user, TOOL: replace_text, TOOL: orchestrate)
        # are deliberately EXCLUDED from the regular prompt. Small local models
        # get confused by dual instructions (tools vs code blocks) and output
        # TOOL: lines that get stripped from chat, making it appear the model
        # doesn't respond. Only use simple code-block output instructions here.
        # Tool descriptions are included ONLY in continuation/re-invocation prompts.
        code_block = truncated_code or "(empty editor)"
        full_prompt = (
            "You are a Python coding assistant in the PyCoder IDE.\n"
            "You are working with a real open project. The code below is the "
            "actual current content of the editor.\n\n"
            f"Project root: {project_root or '(none)'}\n"
            f"Current file: {file_path or 'untitled'}\n\n"
            f"{error_block}"
            "=== CURRENT EDITOR CONTENT ===\n"
            f"{code_block}\n"
            "=== END OF EDITOR CONTENT ===\n\n"
            f"{self._framework_instruction(code_block)}\n\n"
            f"{continuation_block}"
            f"User request: {prompt_text}\n\n"
            "Instructions:\n"
            "- Analyze the code carefully. Base your answer on the actual content above.\n"
            "- If there is a run error / traceback above, use it to find the real bug.\n"
            "- If a change could be destructive, describe what you plan to change.\n"
            "- For code output: place changed code inside ```python blocks.\n"
            "  These blocks are automatically written into the editor.\n"
            "- Text outside ```python stays in the chat conversation.\n"
            "- Be brief and precise.\n\n"
            f"{lang_instruction}"
        )

        if pending_question:
            debug_print("[DEBUG] Sending CONTINUATION unified prompt (reply to AI question)")
        else:
            debug_print("[DEBUG] Sending CLEAN UNIFIED prompt")

        # Store prompt for history and add to chat display
        self._pending_prompt = prompt_text
        self._last_custom_prompt = None  # Agent multi-turn loop deactivated for now
        self._tool_turn_count = 0
        self.history_count += 1
        if prompt_text.strip():
            self.prompt_history.append(prompt_text)
            self.history_index = len(self.prompt_history)
        self._add_chat_item("user", prompt_text)

        # Safety: remove any orphaned streaming item before starting a new request
        self._remove_streaming_item()

        self.start_ai_request("custom", full_prompt)

    def start_ai_request(self, request_type, code):
        """Start an AI request.
        If the Ollama model is not yet loaded (cold start from slow storage),
        auto-preload first then dispatch the real request when preload finishes.
        """
        debug_print(f"[DEBUG] start_ai_request: type={request_type}")

        # ── Auto-preload check for cold-start models ──
        # First requests on slow storage (USB SSD) can time out because Ollama
        # must load the model from disk. We preload with a tiny greeting first,
        # then dispatch the real request. Subsequent requests skip this check.
        if self._auto_preloading and self._pending_request:
            # This IS the deferred dispatch after preload — proceed normally.
            pass
        else:
            current_model = self.model_combo.currentText()
            if current_model:
                raw_model = current_model.split(" (")[0]
                if raw_model.startswith("ollama:"):
                    name = raw_model[7:]
                    if not self._explicitly_preloaded and not self._is_ollama_model_loaded(name):
                        debug_print(f"[INFO] Model {name} not loaded — auto-preloading before request")
                        self._pending_request = (request_type, code)
                        self._auto_preloading = True
                        self.status_label.setText("Loading model (cold start)...")
                        self.on_preload_clicked()
                        return
        # ── End auto-preload check ──

        # Log the full prompt for ALL request types so DEBUG_LOG.md always captures
        # what was actually sent to the model (user instructions / generated prompts).
        request_label = {"suggestion": "SUGGEST", "debug": "DEBUG", "explanation": "EXPLAIN", "fix": "FIX", "custom": "CUSTOM"}.get(request_type, request_type.upper())
        debug_print(f"[USER] {request_label} prompt (len={len(code)}):\n{code}\n[END PROMPT]")
        # Disable ALL controls, show processing state
        self._set_controls_enabled(False)
        self.status_label.setText("Processing...")
        debug_print("[DEBUG] UI BUSY set (all controls disabled, _is_processing=True)")
        # removed color to follow theme (was #0066cc blue, not visible)

        # Clear input for new paragraph (prompt already added to chat display in on_send_clicked)
        self.prompt_input.clear()  # new paragraph (empty)

        # Update model - strip size info if present
        current_model = self.model_combo.currentText()
        if current_model:
            raw_model = current_model.split(" (")[0]  # Strip size info like "(4.2 GB)"
            self.ai_assistant.selected_model = raw_model
            debug_print(f"[DEBUG] Selected model set to: {raw_model}")

        # Force-sync language directly from the dropdown at the exact moment the user triggers a request.
        # This prevents regressions where changing the language dropdown had no effect on Suggest/Explain/Fix/Send
        # (e.g. signal timing, multiple AIPanel instances (global vs bottom dock), or init order).
        try:
            if hasattr(self, "lang_combo") and self.lang_combo is not None:
                current_lang = self.lang_combo.currentText()
                if current_lang:
                    self.ai_assistant.set_language(current_lang)
                    debug_print(f"[DEBUG] Language force-synced at request time to: {current_lang}")
        except Exception:
            pass

        # Start progress bar animation for AI processing (sweeping busy indicator).
        # Make sure no preload ramp timer is interfering (reverted preload progress to simple 10/100).
        if hasattr(self, '_preload_ramp_timer') and self._preload_ramp_timer.isActive():
            self._preload_ramp_timer.stop()
        if hasattr(self, '_preload_ramp_active'):
            self._preload_ramp_active = False
        self._is_processing = True
        self._ignore_next_ai_result = False
        self._busy_progress_value = 0
        self.preload_progress.setVisible(True)
        self._busy_timer.start()

        # Make the request
        try:
            # NOTE: The button handlers (on_suggest_clicked, on_debug_clicked,
            # on_explain_clicked, on_fix_clicked) build the complete prompt
            # (code + instructions + language) internally and pass it as `code`.
            # We call _start_worker_thread DIRECTLY to bypass the legacy wrapping
            # helpers (generate_code_suggestions, explain_code) which would
            # double-wrap the prompt inside another === CODE === block.
            if request_type == "suggestion":
                debug_print("[DEBUG] Calling _start_worker_thread (suggestion)")
                self.ai_assistant._start_worker_thread("suggestion", "", code)
            elif request_type == "debug":
                debug_print("[DEBUG] Calling _start_worker_thread (debug)")
                self.ai_assistant._start_worker_thread("debug", "", code)
            elif request_type == "explanation":
                debug_print("[DEBUG] Calling _start_worker_thread (explanation)")
                self.ai_assistant._start_worker_thread("explanation", "", code)
            elif request_type == "fix":
                debug_print("[DEBUG] Calling _start_worker_thread (fix)")
                self.ai_assistant._start_worker_thread("fix", "", code)
            elif request_type == "custom":
                debug_print("[DEBUG] Calling generate_custom_prompt")
                self.ai_assistant.generate_custom_prompt(code)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.on_error(f"Error starting AI: {str(e)}")

    def on_fix_clicked(self):
        """Handle fix errors button click"""
        # Defensive full reset (same as Suggest)
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        if hasattr(self, '_preload_ramp_timer') and self._preload_ramp_timer.isActive():
            self._preload_ramp_timer.stop()
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.busy_indicator.setVisible(False)
        self._ignore_next_ai_result = False

        code, file_path, project_root = self._get_active_code_and_context()
        if not code or not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to fix!")
            self._set_controls_enabled(True)
            return

        truncated = self._smart_truncate_for_context(code, file_path)

        context_header = ""
        if project_root or file_path:
            context_header = f"CURRENTLY OPEN FILE:\nProject root: {project_root}\nCurrent file: {file_path}\n\n"

        recent_error = self._get_recent_run_output(max_lines=60)
        error_part = ""
        if recent_error:
            error_part = (
                ">>> LATEST RUN ERROR / TRACEBACK:\n"
                f"{recent_error}\n\n"
            )

        lang_inst = self.ai_assistant._get_lang_instruction()

        self._add_chat_item("user", self._localized_action("fix"))

        # AI Mode selector: Simple / 2-Chain / 3-Chain / Full Pipeline
        chain_mode = getattr(self, 'chain_combo', None) and self.chain_combo.currentIndex()
        task_desc = error_part or "Fix bugs in the code below"
        if chain_mode == 3:
            # Full Pipeline (old OrchestrationManager)
            pipeline_ok = self._start_pipeline_for_fix(task_desc, truncated, lang_inst)
            if not pipeline_ok:
                # Fallback to single model if pipeline can't start
                rich_code = (
                    f"{context_header}"
                    f"{error_part}"
                    "=== CODE ===\n"
                    f"{truncated}\n"
                    "=== END ===\n\n"
                    "Find and fix bugs in the code above. If there is a traceback, "
                    "it comes from this code. Quote the problematic line, explain the "
                    "root cause, give the minimal fix. Be brief."
                    f"{lang_inst}"
                )
                self.start_ai_request("fix", rich_code)
        elif chain_mode in (1, 2):
            # 2-Model Chain or 3-Model Chain
            self._start_chain_request(task_desc, truncated, lang_inst, num_models=chain_mode + 1)
        else:
            # Simple — single model
            rich_code = (
                f"{context_header}"
                f"{error_part}"
                "=== CODE ===\n"
                f"{truncated}\n"
                "=== END ===\n\n"
                "Find and fix bugs in the code above. If there is a traceback, "
                "it comes from this code. Quote the problematic line, explain the "
                "root cause, give the minimal fix. Be brief."
                f"{lang_inst}"
            )
            self.start_ai_request("fix", rich_code)

    def _build_rich_text_widgets(self, text, text_color, align):
        """Parse text for ```code blocks and return widgets.
        Returns a list of (QLabel|QTextEdit) widgets for insertion into the bubble layout.
        Code blocks get syntax highlighting with dark background and scrollbars as needed.
        Any language tag after the opening ``` is supported (python, javascript, bash, etc.).
        """
        import re as _re3
        widgets = []
        # Split on code block fences. Supports any language tag (or no tag).
        # Use re.DOTALL so .*? matches code across multiple lines.
        pattern = r'(```\w*\s*\n.*?\n```)'
        parts = _re3.split(pattern, text, flags=_re3.DOTALL)

        i = 0
        while i < len(parts):
            part = parts[i]
            if part.startswith("```"):
                # Match code content between backtick fences. Supports any language tag.
                code_match = _re3.match(r'```(\w*)\s*\n(.*?)\s*\n?```', part, _re3.DOTALL)
                if code_match:
                    lang = code_match.group(1) or ""
                    code = code_match.group(2)
                    code_edit = QtWidgets.QTextEdit()
                    code_edit.setPlainText(code)
                    code_edit.setReadOnly(True)
                    code_edit.setFont(QtGui.QFont("Courier New", 10))
                    code_edit.setStyleSheet(
                        "QTextEdit {"
                        "  background-color: #1e1e1e;"
                        "  color: #d4d4d4;"
                        "  border: 1px solid #3a3a3a;"
                        "  border-radius: 4px;"
                        "  padding: 6px;"
                        "  font-family: 'Courier New', monospace;"
                        "  font-size: 10pt;"
                        "}"
                    )
                    # Calculate height from line count for reliability even before layout
                    line_count = code.count('\n') + 1
                    line_height = 18  # approx px for 10pt Courier New
                    estimated_height = line_count * line_height + 20  # + padding
                    # Cap at reasonable max, with scrollbar for overflow
                    max_height = 500
                    code_edit.setFixedHeight(int(min(estimated_height, max_height)))
                    # Enable scrollbars for blocks that exceed the fixed area
                    code_edit.setVerticalScrollBarPolicy(
                        Qt.ScrollBarPolicy.ScrollBarAsNeeded
                    )
                    code_edit.setHorizontalScrollBarPolicy(
                        Qt.ScrollBarPolicy.ScrollBarAsNeeded
                    )
                    code_edit.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Fixed
                    )
                    try:
                        _PythonHighlighter().highlight_text(code_edit)
                    except Exception:
                        pass
                    widgets.append(code_edit)
                else:
                    # Regex didn't match — show raw text in a label (still monospace)
                    lbl = QtWidgets.QLabel(part)
                    lbl.setWordWrap(True)
                    lbl.setFont(QtGui.QFont("Courier New", 10))
                    lbl.setStyleSheet(f"color:{text_color}; background:transparent; padding:1px;")
                    lbl.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Fixed
                    )
                    widgets.append(lbl)
            else:
                if part.strip():
                    lbl = QtWidgets.QLabel(part)
                    lbl.setWordWrap(True)
                    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    lbl.setAlignment(align)
                    lbl.setFont(QtGui.QFont("Courier New", 10))
                    lbl.setStyleSheet(f"color:{text_color}; background:transparent; padding:1px;")
                    lbl.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Preferred,
                        QtWidgets.QSizePolicy.Policy.Fixed
                    )
                    widgets.append(lbl)
            i += 1

        if not widgets:
            lbl = QtWidgets.QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setAlignment(align)
            lbl.setFont(QtGui.QFont("Courier New", 10))
            lbl.setStyleSheet(f"color:{text_color}; background:transparent; padding:1px;")
            widgets.append(lbl)

        return widgets

    def _add_chat_item(self, role, text, add_to_history=True):
        """Add a modern chat bubble item.
        role: "user", "ai", or "error"
        text: full original message (stored for quoting/copy/apply)

        IMPORTANT: We aggressively cap extremely long responses here.
        A runaway repetitive generation from the model (as seen in the "szülinév"
        case) can produce 100k+ chars. Creating QLabels + sizeHint + history
        for that easily exhausts RAM and makes the list widget unusable
        (huge items, "invisible" areas, layout thrashing). We keep the original
        for Copy/Quote when reasonable, but the visual bubble is always safe.
        """
        # --- Memory / UI safety cap against model repetition loops ---
        MAX_DISPLAY_CHARS = 12000
        original_for_actions = text
        if len(text) > MAX_DISPLAY_CHARS:
            text = text[:MAX_DISPLAY_CHARS] + (
                "\n\n[... Response was very long or repetitive, display truncated. "
                "You can try the Copy / Quote buttons for the full version ...]"
            )

        self.message_count += 1
        num = self.message_count
        if add_to_history:
            # Persist only the (capped) version to avoid blowing up QSettings / load time.
            # Never persist internal "tool" execution results (they are not part of the
            # user-visible conversation and used to cause the echoing "Tool result for..."
            # problem when the model saw them in history or we injected similar strings).
            if role != "tool":
                self.chat_history.append((role, text))
                if len(self.chat_history) > 50:
                    self.chat_history.pop(0)
                    if self.chat_display.count() > 0:
                        self.chat_display.takeItem(0)
                self._save_chat_history()

        # === COMPLETELY NEW BUBBLE DESIGN (Messenger / Viber / SMS style) ===
        # - Single cohesive rounded "bubble" frame per message (no split, no external rows)
        # - Text content always visible inside the colored frame
        # - Small meta (time + role + [n]) inside at bottom
        # - Compact action buttons inside at bottom
        # - Consistent left (AI) / right (user) alignment using HBox + stretch
        # - Bubble has max width so it looks like a proper chat bubble (adapts up to the max)
        # - Explicit light text color for visibility on dark bubble backgrounds
        # - Early item creation for all closures
        # - Simple, linear construction to avoid previous layout/visibility bugs

        widget = QtWidgets.QWidget()
        root_layout = QtWidgets.QHBoxLayout(widget)
        #root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setContentsMargins(10, 0, 10, 10)
        root_layout.setSpacing(0)

        # Early item so all mousePress and toggle closures can safely capture it
        item = QtWidgets.QListWidgetItem()

        ts = datetime.datetime.now().strftime("%H:%M")

        if role == "user":
            #bg = "#1f3a1f"
            bg = "#273e3a"
            role_text = "[You]"
            align = Qt.AlignmentFlag.AlignRight
            text_color = "#e8f5e9"
        elif role == "error":
            bg = "#5a1f1f"
            role_text = "Error"
            align = Qt.AlignmentFlag.AlignLeft
            text_color = "#ffcccc"
        elif role == "tool":
            bg = "#2f2f3a"
            role_text = "Tool"
            align = Qt.AlignmentFlag.AlignLeft
            text_color = "#a0c4ff"
        else:
            bg = "#2a2a2e"
            role_text = "[AI]"
            align = Qt.AlignmentFlag.AlignLeft
            text_color = "#e0e0e0"

        # The bubble itself - one rounded frame containing everything
        bubble = QtWidgets.QFrame()
        bubble.setStyleSheet(
            f"background-color:{bg}; "
            "border-radius:9px;"
            "border: none;"
        )
        #    "padding:6px 8px;"
        # No hard max width — the bubble content should adapt to the available/free
        # horizontal space in the chat (as requested). Only height and fixed vertical
        # spacings/margins/padding are controlled. The HBox + stretch gives side
        # alignment (left for AI, right for user) while letting the bubble expand.
        bubble.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )

        #bubble.setMaximumWidth(
        #    int(self.chat_display.viewport().width() * 0.75)
        #)


        bubble_layout = QtWidgets.QVBoxLayout(bubble)
        # ismeretlen zavaró méretek
        #bubble_layout.setContentsMargins(0, 1, 1, 2)
        #bubble_layout.setSpacing(3)
        
        # Force the inner layout to stay tightly packed to its content.
        # This prevents the bubble from getting extra internal height that
        # would create empty space between the text/meta and the action buttons
        # (the red area in the screenshot).
        bubble_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)

        # --- Text content with syntax highlighting ---
        # If the message contains code blocks (```), ALWAYS use rich text widgets
        # directly so syntax highlighting is visible without clicking "show more".
        # The preview toggle is reserved for extremely long text-only messages.
        has_code_blocks = '```' in text
        is_very_long = len(text) > 600

        if has_code_blocks or not is_very_long:
            # Use rich text widgets — code blocks get syntax highlighting,
            # text/non-code content is wrapped in plain QLabels.
            # This handles short messages AND long messages with code blocks.
            rich_widgets = self._build_rich_text_widgets(text, text_color, align)
            for rw in rich_widgets:
                def _quote_rw(ev, wit=rw, iit=item):
                    if ev.button() == Qt.MouseButton.LeftButton:
                        self.on_history_item_clicked(iit)
                if isinstance(rw, QtWidgets.QLabel):
                    rw.mousePressEvent = _quote_rw
                bubble_layout.addWidget(rw)
        else:
            # Very long text-only messages: show preview with toggle
            lines = text.splitlines()
            preview = "\n".join(lines[:3]) + "\n..."
            lbl = QtWidgets.QLabel(preview)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setAlignment(align)
            lbl.setFont(QtGui.QFont("Courier New", self.font_size))
            lbl.setStyleSheet(f"color:{text_color}; background:transparent;")
            lbl.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed
            )
            def _quote_preview(ev, it=item):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self.on_history_item_clicked(it)
            lbl.mousePressEvent = _quote_preview
            bubble_layout.addWidget(lbl)

            toggle = QtWidgets.QPushButton("▼ show more")
            toggle.setStyleSheet("font-size:9pt; color:#888; padding:1px 3px; background:transparent; padding:3px 2px;")
            toggle.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

            toggle._full_text = text
            toggle._full_widgets = []
            toggle._bubble_layout = bubble_layout
            toggle._preview_lbl = lbl

            def _toggle(_=False):

                if not toggle._full_widgets:
                    rich_widgets = self._build_rich_text_widgets(toggle._full_text, text_color, align)
                    for rw in rich_widgets:
                        if isinstance(rw, QtWidgets.QLabel):
                            rw.mousePressEvent = lambda ev, iit=item: (
                                self.on_history_item_clicked(iit) if ev.button() == Qt.MouseButton.LeftButton else None
                            )
                        idx = toggle._bubble_layout.indexOf(toggle)
                        toggle._bubble_layout.insertWidget(idx, rw)
                        rw.setVisible(True)
                        toggle._full_widgets.append(rw)
                    toggle._preview_lbl.setVisible(False)
                    toggle.setText("▲ show less")
                    widget.adjustSize()
                    h = widget.sizeHint().height()
                    avail_w = 800
                    try:
                        vp = self.chat_display.viewport()
                        if vp and vp.width() > 100:
                            avail_w = max(300, vp.width() - 20)
                    except Exception:
                        pass
                    item.setSizeHint(QtCore.QSize(avail_w, h))
                    self.chat_display.updateGeometry()
                    self.chat_display.scrollToBottom()
                else:
                    all_visible = all(w.isVisible() for w in toggle._full_widgets)
                    if all_visible:
                        for w in toggle._full_widgets:
                            w.setVisible(False)
                        toggle._preview_lbl.setVisible(True)
                        toggle.setText("▼ show more")
                    else:
                        for w in toggle._full_widgets:
                            w.setVisible(True)
                        toggle._preview_lbl.setVisible(False)
                        toggle.setText("▲ show less")


            toggle.clicked.connect(_toggle)
            bubble_layout.addWidget(toggle, alignment=align)

        # --- Meta (timestamp + role + count) inside the bubble, bottom of text area ---
        meta = QtWidgets.QLabel(f"{ts} · {role_text} [{num}]")
        meta.setStyleSheet("color:#888; font-size:10pt; font-weight: bold; background:transparent;")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight)
        meta.setWordWrap(False)
        meta.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        bubble_layout.addWidget(meta)

        # --- Action buttons inside the bubble at the very bottom ---
        act = QtWidgets.QHBoxLayout()
        act.setContentsMargins(5, 5, 0, 0)
        act.setSpacing(8)

        def make_btn(txt, tip):
            b = QtWidgets.QPushButton(txt)
            b.setToolTip(tip)
            b.setStyleSheet(
                "font-size:9pt; color:#ccc; padding:3px 6px; border:1px solid #555; "
                "border-radius:3px; background:#222;"
            )
            b.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(17)
            return b

        btn_copy = make_btn("Copy", "Copy to clipboard")
        btn_quote = make_btn("Quote", "Quote in prompt (follow-up)")
        btn_apply = make_btn("Apply", "Apply to editor (coming soon)")

        full_text = original_for_actions

        def do_copy():
            QtWidgets.QApplication.clipboard().setText(full_text)
            self.status_label.setText("Copied ✓")
            QtCore.QTimer.singleShot(1200, lambda: self.status_label.setText("Ready"))

        def do_quote():
            current = self.prompt_input.toPlainText().strip()
            if current:
                self.prompt_input.setPlainText(current + "\n\n" + full_text)
            else:
                self.prompt_input.setPlainText(full_text)
            self.prompt_input.setFocus()
            self.prompt_input.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        def do_apply():
            QtWidgets.QMessageBox.information(
                self, "Apply",
                "Apply diff / code insertion coming soon.\n\n"
                "See KANBAN: 'Allow AI model to edit editor content with permission' + diff viewer."
            )


        btn_copy.clicked.connect(do_copy)
        btn_quote.clicked.connect(do_quote)
        btn_apply.clicked.connect(do_apply)

        if role == "user":
            act.addStretch()
            act.addWidget(btn_copy)
            act.addWidget(btn_quote)
            act.addWidget(btn_apply)
        else:
            act.addWidget(btn_copy)
            act.addWidget(btn_quote)
            act.addWidget(btn_apply)
            act.addStretch()

        # Wrap actions in a container so the VBox treats it as a single Minimum-height
        # item. This keeps the buttons right after the meta without extra empty space
        # being inserted above them when the bubble gets its final height.
        actions_container = QtWidgets.QWidget()
        actions_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        actions_container.setStyleSheet(
            "font-size:12pt; color:#ccf; padding:0px"
            "border-radius:3px;"
        )

        actions_container.setLayout(act)
        bubble_layout.addWidget(actions_container)

        # Place the bubble left (AI) or right (user). Give the bubble a high stretch
        # factor so it expands freely to the available width (instead of staying
        # narrow). The opposite stretch provides the "margin" on the other side.
        if role == "user":
            root_layout.addStretch(1)
            root_layout.addWidget(bubble, stretch=5)
        else:
            root_layout.addWidget(bubble, stretch=5)
            root_layout.addStretch(1)

        # Claim (almost) the full available width for the *item* (not the bubble itself).
        # This gives the inner HBox + high stretch (5) + Expanding policy on the bubble
        # room to expand the bubble content freely sideways to the free space.
        # Height is taken from the current widget (after all children packed).
        # We deliberately do NOT fix the bubble width here — width must stay "expand".
        avail_w = 800
        try:
            vp = self.chat_display.viewport()
            if vp and vp.width() > 100:
                avail_w = max(300, vp.width() - 20)
        except Exception:
            pass

        widget.adjustSize()
        h = widget.sizeHint().height()
        item.setSizeHint(QtCore.QSize(avail_w, h))

        item.setData(32, full_text)
        self.chat_display.addItem(item)
        self.chat_display.setItemWidget(item, widget)
        self.chat_display.scrollToBottom()

        # For long messages: attach so "show more" toggle can update the item height later
        if 'toggle' in locals():
            toggle._widget = widget
            toggle._item = item
            toggle._chat = self.chat_display

    def _add_separator(self):
        """Add a separator line between messages."""
        sep_item = QtWidgets.QListWidgetItem()
        sep_widget = QtWidgets.QWidget()
        sep_layout = QtWidgets.QHBoxLayout(sep_widget)
        sep_layout.setContentsMargins(0, 2, 0, 2)
        sep_line = QtWidgets.QFrame()
        sep_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        sep_line.setStyleSheet("background-color:#ff5512; max-height:1px;")
        sep_layout.addWidget(sep_line)
        sep_item.setSizeHint(sep_widget.sizeHint())
        self.chat_display.addItem(sep_item)
        self.chat_display.setItemWidget(sep_item, sep_widget)

    def on_cancel_clicked(self):
        """Handle cancel button click — re-enables ALL controls and cleans up."""
        debug_print("[USER] Cancel button clicked")
        self.ai_assistant.cancel_request()

        # Cancel any running orchestration pipeline — only show message if active
        pipeline_cancelled = False
        if self._orchestration_manager is not None:
            self._orchestration_manager.cancel()
            self._orchestration_manager = None
            pipeline_cancelled = True

        # Cancel any running 3-model chain — only show message if actually cancelled
        chain_cancelled = False
        if hasattr(self.ai_assistant, 'cancel_chain'):
            chain_cancelled = self.ai_assistant.cancel_chain()

        cancelled_preload = False
        # Properly cancel a running preload thread (separate from normal AI worker_thread)
        if getattr(self, 'preload_thread', None) and self.preload_thread.isRunning():
            cancelled_preload = True
            th = self.preload_thread
            try:
                th.cancel()
                th.quit()
                th.wait(100)
            except Exception:
                pass
            self.preload_thread = None

        # Add status messages only for what was actually cancelled
        if pipeline_cancelled:
            self._add_chat_item("ai", "⏹️ *Pipeline megszakítva*")
        elif chain_cancelled:
            self._add_chat_item("ai", "⏹️ *3-modelles lánc megszakítva*")
        elif not cancelled_preload:
            # Simple mode — normal cancel
            self._add_chat_item("ai", "⏹️ *Megszakítva*")

        # Re-enable ALL controls (model combo, chain mode, lang, send, all buttons, etc.)
        # This replaces the old manual re-enable of only 4 buttons.
        self._set_controls_enabled(True)

        # Stop all timers
        self._preload_timer.stop()
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        if hasattr(self, '_preload_ramp_timer') and self._preload_ramp_timer.isActive():
            self._preload_ramp_timer.stop()
        if hasattr(self, '_preload_ramp_active'):
            self._preload_ramp_active = False

        # Reset preload progress bar
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.busy_indicator.setVisible(False)

        if cancelled_preload:
            self.status_label.setText("Preload cancelled")
            self.status_label.setStyleSheet("color: #cc0000;")

        # Safe cleanup: do not force-delete a still-running thread
        self._cleanup_preload_thread()

        # Mark any pending result from the cancelled request to be ignored.
        self._ignore_next_ai_result = True
        self._is_processing = False

    def on_clear_clicked(self):
        """Clear the current prompt input and reset any temporary state."""
        if hasattr(self, "prompt_input") and self.prompt_input is not None:
            self.prompt_input.clear()
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #666;")

    def on_clear_chat_clicked(self):
        """Clear the entire chat conversation history (modern chat UX)."""
        self.chat_history.clear()
        self.chat_display.clear()
        self.prompt_history.clear()
        self.history_index = -1
        self.message_count = 0
        self.status_label.setText("Chat history cleared")
        self.status_label.setStyleSheet("color: #888;")
        self._save_chat_history()

    def _load_chat_history(self):
        """Restore chat messages from previous session (until clear or max 50)."""
        settings = QtCore.QSettings("PyCoder", "AIPanel")
        hist = settings.value("chat_history", [])
        if isinstance(hist, list):
            self.chat_history = [tuple(x) if isinstance(x, list) else x for x in hist]
        else:
            self.chat_history = []
        # Replay without re-adding to history list (to avoid dup on load).
        # Skip old internal "tool" role entries (they were the source of visible
        # "Tool result for ..." bubbles in previous versions). Only user/ai/error
        # belong in the visible chat.
        for role, text in self.chat_history:
            if role == "tool":
                continue
            self._add_chat_item(role, text, add_to_history=False)

    def _save_chat_history(self):
        """Persist chat history so it survives app restart (until user clears)."""
        settings = QtCore.QSettings("PyCoder", "AIPanel")
        settings.setValue("chat_history", self.chat_history)
        settings.sync()

    def eventFilter(self, obj, event):
        """Handle Enter in prompt_input: Enter = send, Shift+Enter = newline (per PLAN.md).
        Also Up/Down for prompt history navigation (preserve history)."""
        if obj is getattr(self, "prompt_input", None) and event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            # Prompt history navigation with Up/Down (when no Shift, to not conflict with newline)
            if key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down) and not (modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier):
                if not self.prompt_history:
                    return True
                if key == QtCore.Qt.Key.Key_Up:
                    self.history_index = max(0, self.history_index - 1)
                else:  # Down
                    self.history_index = min(len(self.prompt_history) - 1, self.history_index + 1)
                if 0 <= self.history_index < len(self.prompt_history):
                    self.prompt_input.setPlainText(self.prompt_history[self.history_index])
                    self.prompt_input.moveCursor(QtGui.QTextCursor.MoveOperation.End)
                return True  # consume

            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    # Allow multiline (new paragraph support)
                    return False
                else:
                    self.on_send_clicked()
                    return True  # consume the key
        return super().eventFilter(obj, event)

    def on_increase_font(self):
        """Increase the font size of the prompt input."""
        self._adjust_font_size(delta=+1)

    def on_decrease_font(self):
        """Decrease the font size of the prompt input, but never go below size 1."""
        self._adjust_font_size(delta=-1)

    def _adjust_font_size(self, delta: int):
        """Helper to modify the prompt input and chat display font size safely."""
        if not hasattr(self, "prompt_input") or self.prompt_input is None:
            return
        new_size = max(1, self.font_size + delta)
        self.font_size = new_size

        # Update prompt input font
        font = self.prompt_input.font()
        font.setPointSize(new_size)
        self.prompt_input.setFont(font)

        # Update all existing chat items
        for row in range(self.chat_display.count()):
            item = self.chat_display.item(row)
            widget = self.chat_display.itemWidget(item)
            if widget:
                labels = widget.findChildren(QtWidgets.QLabel)
                for label in labels:
                    if label.objectName() != "headerLabel":
                        # Only scale the actual message content, keep header small/fixed
                        label.setFont(QtGui.QFont("Courier New", new_size))

    def _on_stream_token(self, token: str):
        """Handle a single token from the streaming Ollama response.
        Updates the chat display in real-time with the buffered content.
        Detects code blocks (```python ... ```) and buffers content.
        The code is ONLY written to the editor by _auto_write_code_blocks()
        in on_custom_response_ready — NOT during streaming — to avoid
        flooding the editor with hundreds of partial overwrites.
        """
        self._stream_buffer += token

        import re
        # Detect start of code block: ```lang at end of buffer
        if not self._in_code_block:
            m = re.search(r'```(\w*)$', self._stream_buffer)
            if m:
                self._in_code_block = True
                self._code_block_buffer = ""
                self._lang = m.group(1).strip().lower()

        # Inside a code block — accumulate tokens, detect closing ```
        if self._in_code_block:
            if '```' in token:
                self._in_code_block = False
                self._lang = ""

            # Just accumulate — no intermediate writes to editor
            self._code_block_buffer += token

        # ── Real-time chat display ──
        # Update or create a streaming message bubble so the user sees
        # the response being generated live, not just a spinner.
        if not hasattr(self, '_streaming_item_ref'):
            self._streaming_item_ref = None

        # Show streaming content (plain text, updated per token received)
        display = self._stream_buffer
        if self._in_code_block:
            display += "\n```\n..."
        # Limit display to avoid lag (show only last 500 chars)
        visible = display[-500:] if len(display) > 500 else display

        if self._streaming_item_ref is None:
            # Create a temporary streaming message
            lbl = QtWidgets.QLabel(visible)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#ccc; background:transparent; padding:8px;")
            lbl.setFont(QtGui.QFont("Courier New", self.font_size))

            streaming_widget = QtWidgets.QWidget()
            root_lay = QtWidgets.QHBoxLayout(streaming_widget)
            root_lay.setContentsMargins(10, 0, 10, 10)
            bubble = QtWidgets.QFrame()
            bubble.setStyleSheet("background-color:#2a2a2e; border-radius:9px;")
            bubble_lay = QtWidgets.QVBoxLayout(bubble)
            bubble_lay.addWidget(lbl)
            bubble_lay.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
            root_lay.addWidget(bubble)

            streaming_item = QtWidgets.QListWidgetItem()
            streaming_item.setSizeHint(streaming_widget.sizeHint())
            self.chat_display.addItem(streaming_item)
            self.chat_display.setItemWidget(streaming_item, streaming_widget)
            self._streaming_item_ref = streaming_item
            streaming_item._streaming_lbl = lbl
            streaming_item._streaming_widget = streaming_widget
        else:
            # Update existing streaming message
            item = self._streaming_item_ref
            if item and hasattr(item, '_streaming_lbl'):
                item._streaming_lbl.setText(visible)
                item._streaming_widget.adjustSize()
                h = item._streaming_widget.sizeHint().height()
                item.setSizeHint(QtCore.QSize(self.chat_display.viewport().width() - 20, h + 20))
                self.chat_display.scrollToBottom()

    def _remove_streaming_item(self):
        """Remove the streaming-in-progress chat item, if any."""
        if hasattr(self, '_streaming_item_ref') and self._streaming_item_ref is not None:
            ref = self._streaming_item_ref
            # Find and remove the item by widget reference (iterate to handle index shifts)
            for i in range(self.chat_display.count()):
                if self.chat_display.item(i) is ref:
                    self.chat_display.takeItem(i)
                    break
            self._streaming_item_ref = None
            self._stream_buffer = ""

    def on_suggestion_ready(self, suggestion):
        """Handle suggestion ready signal"""
        self._is_processing = False
        self._busy_timer.stop()
        self.preload_progress.setVisible(False)

        if getattr(self, '_ignore_next_ai_result', False):
            self._ignore_next_ai_result = False
            self._is_processing = False
            if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
                self._busy_timer.stop()
            self.preload_progress.setVisible(False)
            self.preload_progress.setValue(0)
            self.busy_indicator.setVisible(False)
            # Re-enable just in case
            self._set_controls_enabled(True)
            return

        # Remove streaming-in-progress item before showing final result
        self._remove_streaming_item()

        # Log the raw model response to DEBUG_LOG.md
        debug_print(f"[RESPONSE] Suggestion raw (len={len(suggestion)}):\n{suggestion}\n[END RESPONSE]")

        # Add suggestion to chat display (clean content to prevent any prompt leakage)
        suggestion = self._clean_ai_response(suggestion)
        self._add_chat_item("ai", suggestion)

        # NOTE: auto-write is intentionally NOT called for suggestions!
        # Suggest mode is for review/analysis only — it should NEVER modify the editor.
        # If the model hallucinates ```python blocks (as small models often do),
        # they would overwrite the user's code. Fix/Custom modes handle auto-write instead.

        self._set_controls_enabled(True)
        self.status_label.setText("Suggestions ready")
        # removed color to follow theme (was #009900 green)

    def on_explanation_ready(self, explanation):
        """Handle explanation ready signal"""
        self._is_processing = False
        self._busy_timer.stop()
        self.preload_progress.setVisible(False)

        if getattr(self, '_ignore_next_ai_result', False):
            self._ignore_next_ai_result = False
            self._is_processing = False
            if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
                self._busy_timer.stop()
            self.preload_progress.setVisible(False)
            self.preload_progress.setValue(0)
            self.busy_indicator.setVisible(False)
            self._set_controls_enabled(True)
            return

        # Remove streaming-in-progress item before showing final result
        self._remove_streaming_item()

        # Log the raw model response to DEBUG_LOG.md
        debug_print(f"[RESPONSE] Explanation raw (len={len(explanation)}):\n{explanation}\n[END RESPONSE]")

        # Add explanation to chat display (clean content to prevent prompt leakage)
        explanation = self._clean_ai_response(explanation)
        self._add_chat_item("ai", explanation)

        self._set_controls_enabled(True)
        self.status_label.setText("Explanation ready")
        # removed color to follow theme (was #009900 green)

    def on_custom_response_ready(self, content):
        """Handle custom response ready signal"""
        self._is_processing = False
        self._busy_timer.stop()
        self.preload_progress.setVisible(False)

        if getattr(self, '_ignore_next_ai_result', False):
            self._ignore_next_ai_result = False
            self._is_processing = False
            if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
                self._busy_timer.stop()
            self.preload_progress.setVisible(False)
            self.preload_progress.setValue(0)
            self.busy_indicator.setVisible(False)
            self._set_controls_enabled(True)
            return

        # Log the RAW model response always — this makes the entire conversation self-contained
        # in DEBUG_LOG.md without needing PYCODER_DEBUG_AI=1, so no manual copying is needed.
        debug_print(f"[RESPONSE] Model raw output (len={len(content)}) follows:\n{content}\n[END RESPONSE]")

        # === Agent / Tool support for custom prompts ===
        # _parse_tool_calls returns list of (name, args) tuples.
        # We must NOT unpack it as 2 values.
        tool_calls = self._parse_tool_calls(content)
        if tool_calls:
            debug_print(f"[DEBUG] PARSED TOOL CALLS from model response: {tool_calls}")

        # Guard against the model hallucinating edits on system files or using wrong formats (e.g. REPLACE_TEXT /etc/...)
        bad_patterns = [
            "/etc/", "blackPanther", "system files", "profile.d",
            "tool result for tool:", "tool result for you:", "tool output for",
            "unknown tool 'tool'", "unknown tool 'you'"
        ]
        is_bad_output = any(p.lower() in content.lower() for p in bad_patterns)

        # Use central cleaner (handles tool echoes + all known prompt leakage phrases)
        cleaned_content = self._clean_ai_response(content)

        if cleaned_content and not is_bad_output:
            # Remove streaming-in-progress item before showing final result
            self._remove_streaming_item()
            self._add_chat_item("ai", cleaned_content)

        # ── Tool-or-auto logic: ──
        # When the model uses tools (TOOL: replace_text, TOOL: ask_user, etc.),
        # the ```python blocks in the response are just for illustration.
        # Execute the tools and do NOT auto-write code blocks.
        # When there are no tools, fall back to auto-edit for ```python blocks.
        internal_results = []
        if tool_calls:
            for name, args in tool_calls:
                # Enrich replace_text for creation: if old=="" but new is missing/empty/short (common
                # because multiline code can't fit the one-line arg parser), pull from full response.
                if name == "replace_text":
                    oldv = args.get("old") or args.get("old_text") or ""
                    newv = args.get("new") or args.get("new_text") or ""
                    if oldv == "" and len(newv) < 30:
                        extracted = self._extract_code_from_response(content)
                        if extracted:
                            args["new"] = extracted
                            args["new_text"] = extracted
                res = self._execute_ai_tool(name, args)
                internal_results.append(f"[{name}]\n{res}\n[/{name}]")

        if not tool_calls:
            # No tools → fall back to auto-edit for ```python blocks
            auto_written = self._auto_write_code_blocks(content)
            if auto_written:
                langs = set(l for l, s in auto_written if s == "written")
                status = ", ".join(sorted(langs))
                note = f"[Code block(s) auto-written to editor: {status}]"
                self._add_chat_item("ai", note)

        # ── Tool result handling (tool loop continuation) ──
        if internal_results:
            tool_block = "\n".join(internal_results)
            debug_print(f"[DEBUG] TOOL RESULTS (executed from model request):\n{tool_block}\n[END TOOL RESULTS]")

            # [ASK_USER] handling: if ask_user was called, do NOT continue the tool loop.
            # The AI has asked a question and is waiting for user input.
            # Save the question so the next user Send continues with context.
            if any("[ASK_USER]" in r for r in internal_results):
                self._add_chat_item("tool", "⏸️ A válaszodra várok. Folytathatod a prompt mezőben.")
                self.suggest_btn.setEnabled(True)
                self.explain_btn.setEnabled(True)
                self.fix_btn.setEnabled(True)
                self.send_btn.setEnabled(True)
                self.cancel_btn.setEnabled(False)
                self.busy_indicator.setVisible(False)
                self.status_label.setText("Waiting for your reply to the AI's question")
                # Save the AI's question so the user's answer continues the conversation
                # Extract from tool args, NOT from raw response (which has hallucinated junk)
                ai_question = "(nincs kérdés szöveg)"
                for t_name, t_args in tool_calls:
                    if t_name == "ask_user":
                        q = t_args.get("question") or t_args.get("q") or ""
                        if q:
                            ai_question = q
                            break
                self._pending_ai_question = ai_question
                # Clear agent tool state — the user types fresh, then we build continuation
                self._last_custom_prompt = None
                self._tool_turn_count = 0
                return

            # Pipeline handling: if orchestration was started, stop the tool loop.
            # The pipeline result arrives async via signals, not via another model call.
            if any("PIPELINE_STARTED" in r or "PIPELINE_SKIPPED" in r for r in internal_results):
                if any("PIPELINE_SKIPPED" in r for r in internal_results):
                    # Insufficient memory — let the model handle it normally
                    pass
                else:
                    # Pipeline running async — stop tool loop, results come via signals
                    self._last_custom_prompt = None
                    self._tool_turn_count = 0
                    self.suggest_btn.setEnabled(True)
                    self.explain_btn.setEnabled(True)
                    self.fix_btn.setEnabled(True)
                    self.send_btn.setEnabled(True)
                    self.cancel_btn.setEnabled(False)
                    self.busy_indicator.setVisible(False)
                    self.status_label.setText("Pipeline running...")
                    return

            # Creation-specific early stop: if we just successfully wrote the full code into the
            # open editor via replace_text old="", stop the agent loop immediately.
            # This prevents the small model from "restarting the task" on every turn because the
            # base creation prompt keeps telling it "you must write the code with the tool".
            creation_write_succeeded = any(
                "Wrote full content to open editor" in r or
                "Created/wrote full content to file" in r
                for r in internal_results
            )

            last_ctx = getattr(self, '_last_custom_prompt', '')
            if last_ctx:
                self._tool_turn_count = getattr(self, '_tool_turn_count', 0) + 1

                # Cap at 4 tool-using turns to prevent infinite loops
                if creation_write_succeeded or self._tool_turn_count > 4:
                    if creation_write_succeeded:
                        self._add_chat_item("ai", "Done – the code was written to the editor via replace_text tool.")
                    else:
                        self._add_chat_item("ai", "Tool interaction limit reached. The AI performed the following actions:\n" + tool_block)
                    # Clear agent state so a future user message starts fresh (prevents stale loops on next send)
                    self._last_custom_prompt = None
                    self._tool_turn_count = 0
                else:
                    extended = (
                        last_ctx +
                        "\n\n[SYSTEM TOOL RESULTS - internal only, do not repeat this format]\n" +
                        tool_block +
                        "\n[END SYSTEM TOOL RESULTS]\n\n" +
                        "The SYSTEM block above contains the result of your tool call (added by the system).\n" +
                        "DO NOT output 'Tool result for', 'Tool output for' or similar text in your response!\n"
                    )
                    # Standard continuation instruction for agent-mode
                    extended += (
                        "The 'EXACT CURRENT CONTENT OF THE OPEN FILE' block at the top of the prompt is the precise current content of the live editor.\n"
                        "Decision: if you still need a tool, output ONE 'TOOL: ...' line (with a known tool name). If done, write a normal short summary.\n"
                        "Do not imitate system messages. Do not start with 'Tool result...'."
                    )
                    self.start_ai_request("custom", extended)
                    return  # next response will handle reset





        if is_bad_output or any("unknown tool" in r.lower() or "ERROR: unknown" in r for r in internal_results):
            # The model produced garbage (wrong tool name like "tool"/"you", echoed result formats,
            # or tried to touch system files). Strong correction re-invoke.
            last_ctx = getattr(self, '_last_custom_prompt', '')
            if last_ctx:
                extended = (
                    last_ctx +
                    "\n\n[SYSTEM CORRECTION: Your previous output contained invalid or unknown tools (e.g. 'tool', 'you'). "
                    "Ignore the previous incorrect 'Tool result...' lines. From now on, only use the file in the top EXACT CURRENT CONTENT "
                    "block and only use one of the documented 5 tools in TOOL: format. "
                    "Respond in the user's language, or call a valid tool.]\n\n"
                    "Continue based on the original user request."
                )
                # Remove streaming item before retry to avoid orphan in chat
                self._remove_streaming_item()
                self.start_ai_request("custom", extended)
                return


        # Ensure any lingering streaming item is cleaned up when no re-invocation occurs
        self._remove_streaming_item()

        # Normal final response path (no more tools or no re-invocation)
        self._set_controls_enabled(True)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Response received")
        # removed color to follow theme (was #009900 green)
        debug_print("[DEBUG] UI RESET: buttons re-enabled, busy hidden, status='Response received'")
        debug_print("[DEBUG] Custom response received and UI reset")
        self._update_preload_button_state()  # response likely loaded/warmed the model
        # Clear any leftover agent state so the next user Send starts a clean non-agent or fresh agent session.
        self._last_custom_prompt = None
        self._tool_turn_count = 0

    def on_fix_ready(self, fix):
        """Handle fix errors ready signal"""
        self._is_processing = False
        self._busy_timer.stop()
        self.preload_progress.setVisible(False)

        if getattr(self, '_ignore_next_ai_result', False):
            self._ignore_next_ai_result = False
            self._is_processing = False
            if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
                self._busy_timer.stop()
            self.preload_progress.setVisible(False)
            self.preload_progress.setValue(0)
            self._set_controls_enabled(True)
            return

        # Remove streaming-in-progress item before showing final result
        self._remove_streaming_item()

        # Log the raw model response to DEBUG_LOG.md
        debug_print(f"[RESPONSE] Fix raw (len={len(fix)}):\n{fix}\n[END RESPONSE]")

        # Add fix to chat display (clean content to prevent prompt leakage)
        fix = self._clean_ai_response(fix)
        self._add_chat_item("ai", fix)

        # Auto-write any ```python blocks from the fix response (the model
        # should output corrected code, not just describe the bug).
        auto_written = self._auto_write_code_blocks(fix)
        if auto_written:
            langs = set(l for l, s in auto_written if s == "written")
            self._add_chat_item("ai", f"[Fix code written to editor: {', '.join(sorted(langs))}]")

        self._set_controls_enabled(True)
        self.status_label.setText("Bugfix ready")
        # removed color to follow theme (was #009900 green)

    def on_history_item_clicked(self, item):
        """Clicking a chat bubble quotes the message into the prompt (convenience).
        Primary actions are the Copy/Quote/Apply buttons inside each bubble.
        """
        text = item.data(32)
        if text:
            # Modern path: use stored full text
            cur = self.prompt_input.toPlainText().strip()
            if cur:
                self.prompt_input.setPlainText(cur + "\n\n" + text)
            else:
                self.prompt_input.setPlainText(text)
            self.prompt_input.setFocus()
            self.prompt_input.moveCursor(QtGui.QTextCursor.MoveOperation.End)
            return

        # Legacy fallback (old plain items)
        txt = item.text() or ""
        if txt:
            self.prompt_input.insertPlainText("\n\n" + txt)

    def on_error(self, error_message):
        """Handle error signal — also stop busy/progress indicators."""
        self._ignore_next_ai_result = False
        # CRITICAL: stop the busy timer + progress bar so the UI is responsive again.
        # Previously these were missing, leaving the progress bar spinning indefinitely
        # on timeout/error (e.g. "No response from Ollama").
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        self._busy_progress_value = 0
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)

        # Use modern error bubble (consistent design)
        self._add_chat_item("error", error_message)

        self._set_controls_enabled(True)
        self.status_label.setText(f"Hiba: {error_message}")
        self.status_label.setStyleSheet("color: #cc0000;")
        debug_print(f"[DEBUG] ERROR SIGNAL RECEIVED: {error_message}")
