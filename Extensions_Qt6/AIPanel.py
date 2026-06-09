#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Panel for PyCoderAi
Provides a user interface for AI assistant features
"""

import sys
import os
import datetime

# Debug logger – appends DEBUG_* prints to DEBUG_LOG.md ONLY when PYCODER_DEBUG_AI=1
# This prevents log spam in normal use. Enable for AI development / PLAN.md chat redesign work.
DEBUG_AI = os.getenv("PYCODER_DEBUG_AI", "0") == "1"

def debug_print(message):
    """Append a debug line to DEBUG_LOG.md with a timestamp (opt-in via env)."""
    if not DEBUG_AI:
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
from Extensions_Qt6.AIAssistant import AIAssistant, AIWorkerThread
# Import the ollama module/variable from AIAssistant's scope (fixed: no comma-tuple bug)
import Extensions_Qt6.AIAssistant as _ai_assistant_module
ollama = getattr(_ai_assistant_module, 'ollama', None)


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

        # Font size tracking
        self.font_size = 12  # Default font size for prompt and chat messages

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

        self.header_label = QtWidgets.QLabel("AI Assistant")
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.header_label)

        header_layout.addStretch()

        self.busy_indicator = QtWidgets.QLabel()
        self.busy_indicator.setPixmap(QtGui.QPixmap(self._resource_path("Resources/images/gear.png")))
        self.busy_indicator.setVisible(False)
        header_layout.addWidget(self.busy_indicator)

        main_layout.addLayout(header_layout)

        # Model selection - all elements in one row
        model_layout = QtWidgets.QHBoxLayout()
        model_layout.setContentsMargins(0, 0, 0, 0)

        model_layout.addWidget(QtWidgets.QLabel("Model:"))
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setMinimumWidth(200)
        model_layout.addWidget(self.model_combo)

        # More space between dropdown and buttons (as requested)
        model_layout.addSpacing(12)

        # Preload button
        self.preload_btn = QtWidgets.QPushButton("Preload")
        self.preload_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/reload.png")))
        self.preload_btn.setToolTip("Preload selected model into memory")
        self.preload_btn.setFixedWidth(120)
        self.preload_btn.setEnabled(False)
        model_layout.addWidget(self.preload_btn)

        # Cancel button
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/stop.png")))
        self.cancel_btn.setToolTip("Cancel current AI request")
        self.cancel_btn.setFixedWidth(120)
        self.cancel_btn.setEnabled(False)
        model_layout.addWidget(self.cancel_btn)

        # Action buttons: Suggest | Explain | Fix
        self.suggest_btn = QtWidgets.QPushButton("Suggest")
        self.suggest_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/lightbulb.png")))
        self.suggest_btn.setToolTip("Get AI suggestions for code improvements")
        self.suggest_btn.setFixedWidth(120)
        model_layout.addWidget(self.suggest_btn)

        self.explain_btn = QtWidgets.QPushButton("Explain")
        self.explain_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/about.png")))
        self.explain_btn.setToolTip("Get AI explanation of the code")
        self.explain_btn.setFixedWidth(120)
        model_layout.addWidget(self.explain_btn)

        self.fix_btn = QtWidgets.QPushButton("Fix")
        self.fix_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/gear.png")))
        self.fix_btn.setToolTip("Get AI suggestions to fix errors")
        self.fix_btn.setFixedWidth(120)
        model_layout.addWidget(self.fix_btn)

        # Language selector
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems(["Hungarian", "English", "Slovak", "German"])
        self.lang_combo.setMinimumWidth(120)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        model_layout.addWidget(self.lang_combo)

        # === Context window safety control (user priority: "bekapcsolása a prioritás") ===
        # Checkbox enables custom num_ctx for Ollama. When off → model default (no override).
        # Dropdown offers common safe sizes. "Model default" means we don't force num_ctx.
        # This + smart truncation below = the "összetett / okos + intelligens" solution.
        model_layout.addSpacing(10)
        self.context_window_cb = QtWidgets.QCheckBox("Context window")
        self.context_window_cb.setToolTip(
            "Enable custom context window size (num_ctx) for Ollama models.\n"
            "When disabled the model uses its own default.\n"
            "Enabling this is the safety net for large files / long conversations."
        )
        self.context_window_cb.setChecked(False)
        model_layout.addWidget(self.context_window_cb)

        self.context_window_combo = QtWidgets.QComboBox()
        self.context_window_combo.addItems([
            "Model default",
            "4k (4096)",
            "8k (8192)",
            "16k (16384)",
            "32k (32768)"
        ])
        self.context_window_combo.setMinimumWidth(115)
        self.context_window_combo.setEnabled(False)  # only when checkbox is on
        model_layout.addWidget(self.context_window_combo)

        # Wire up
        self.context_window_cb.toggled.connect(self.context_window_combo.setEnabled)
        self.context_window_cb.toggled.connect(self._on_context_window_changed)
        self.context_window_combo.currentIndexChanged.connect(self._on_context_window_changed)

        # Progress bar for AI processing animation - after language selector, no fixed width limit
        self.preload_progress = QtWidgets.QProgressBar()
        self.preload_progress.setMaximum(100)
        self.preload_progress.setValue(0)
        self.preload_progress.setVisible(False)
        # no setFixedWidth to allow it to size naturally
        model_layout.addWidget(self.preload_progress)

        # Add busy timer for progress bar animation during AI processing (sweeping indicator for normal requests).
        # Preload now uses simple 10 -> 100 jump (reverted from ramp simulation, as that change introduced
        # state machine problems with cancel, subsequent Suggest, and shared progress bar).
        self._busy_timer = QtCore.QTimer(self)
        self._busy_timer.timeout.connect(self._step_progress)
        self._busy_timer.setInterval(50)
        self._busy_progress_value = 0
        self._is_processing = False

        # Periodic check for model loaded state (to re-enable Preload button
        # and update its color when keep-alive expires and ollama unloads the model).
        self._model_state_timer = QtCore.QTimer(self)
        self._model_state_timer.timeout.connect(self._update_preload_button_state)
        self._model_state_timer.start(30000)  # every 30 seconds

        model_layout.addStretch()

        main_layout.addLayout(model_layout)

        # === Main chat area (conversation view) ===
        # Placed right after model controls, before input (per PLAN.md: chat on top, input at bottom)
        self.chat_display = QtWidgets.QListWidget()
        self.chat_display.setStyleSheet(
            "background-color: #1e1e1e; color: #e0e0e0; border: 1px solid #333; border-radius: 4px;"
        )
        self.chat_display.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.chat_display.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.chat_display.itemClicked.connect(self.on_history_item_clicked)
        main_layout.addWidget(self.chat_display)

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
        self.prompt_input.setPlaceholderText("Írd ide a kérdésedet vagy utasításodat az AI-nak... (Enter = küldés, Shift+Enter = új sor)")
        self.prompt_input.setStyleSheet(
            "background-color: #1a1a1a; color: #ffffff; font-family: 'Courier New', monospace; border: none; padding: 4px;"
        )
        self.prompt_input.setMinimumHeight(48)
        self.prompt_input.setMaximumHeight(110)
        self.prompt_input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        composer_v.addWidget(self.prompt_input)

        # Enter-to-send (Shift+Enter = newline) - installed after widget creation
        self.prompt_input.installEventFilter(self)

        # Send row at bottom of composer
        send_layout = QtWidgets.QHBoxLayout()
        send_layout.setContentsMargins(0, 0, 0, 0)
        send_layout.setSpacing(4)

        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/flag-green.png")))
        self.send_btn.setToolTip("Küldés (vagy Enter)")
        self.send_btn.setFixedWidth(90)
        send_layout.addWidget(self.send_btn)

        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setToolTip("Prompt törlése")
        self.clear_btn.setFixedWidth(70)
        send_layout.addWidget(self.clear_btn)

        # Small font controls
        self.decrease_font_btn = QtWidgets.QPushButton("–A")
        self.decrease_font_btn.setToolTip("Betűméret csökkentése")
        self.decrease_font_btn.setFixedWidth(32)
        send_layout.addWidget(self.decrease_font_btn)

        self.increase_font_btn = QtWidgets.QPushButton("+A")
        self.increase_font_btn.setToolTip("Betűméret növelése")
        self.increase_font_btn.setFixedWidth(32)
        send_layout.addWidget(self.increase_font_btn)

        # Clear chat (new for modern chat UX)
        self.clear_chat_btn = QtWidgets.QPushButton("🗑 Chat")
        self.clear_chat_btn.setToolTip("Chat előzmények törlése")
        self.clear_chat_btn.setFixedWidth(70)
        send_layout.addWidget(self.clear_chat_btn)

        send_layout.addStretch()
        composer_v.addLayout(send_layout)

        main_layout.addWidget(composer_container)

        # Status bar (always at very bottom)
        self.status_label = QtWidgets.QLabel("Kész")
        self.status_label.setStyleSheet("color: #888; font-size: 9pt; padding-left: 4px;")
        main_layout.addWidget(self.status_label)

    def setup_connections(self):
        """Setup signal connections"""
        self.suggest_btn.clicked.connect(self.on_suggest_clicked)
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

        self.ai_assistant.suggestion_ready.connect(self.on_suggestion_ready)
        self.ai_assistant.explanation_ready.connect(self.on_explanation_ready)
        self.ai_assistant.custom_ready.connect(self.on_custom_response_ready)
        self.ai_assistant.fix_ready.connect(self.on_fix_ready)
        self.ai_assistant.error_occurred.connect(self.on_error)

        # Set icon theme based on system theme
        self.update_icon_theme()

        # Load models after connections are set up
        self.load_models()

        # Check for already loaded model after loading all models
        self._check_for_preloaded_model()
        self._update_preload_button_state()

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
            self.status_label.setText("Model betöltése... (az első generálás lassú lehet nagy modelleknél)")
            self.status_label.setStyleSheet("color: #0066cc;")

            # Use greeting for preload in selected language (also sets keep_alive in the wrapper)
            lang = self.lang_combo.currentText().lower()
            if lang.startswith("hungar"):
                preload_prompt = "Szia! Üdvözölj meg a PyCoderAiban!"
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

            self.preload_thread.start()
        else:
            self.status_label.setText("Non-Ollama model - no preload needed")
            debug_print(f"[INFO] {raw_model} is a Claude model, no preload needed")

    def _on_preload_progress(self, value):
        """Update progress bar during preload (simple mode)."""
        debug_print(f"[DEBUG] Preload progress: {value}%")
        if value > self.preload_progress.value():
            self.preload_progress.setValue(min(100, value))

    def _on_preload_ready(self, result, _=None):
        """Handle preload completion from thread."""
        # Guard: if preload UI is no longer active (user cancelled or another action),
        # ignore late completion from a previous/cancelled thread to avoid UI flicker
        # or operating on a cleaned-up thread object.
        if not getattr(self, 'preload_progress', None) or not self.preload_progress.isVisible():
            self._cleanup_preload_thread()
            return

        self.preload_progress.setValue(100)
        # Small delay so user sees 100% before hiding (back to the original simple 10->100 behavior)
        QtCore.QTimer.singleShot(300, lambda: self.preload_progress.setVisible(False))
        self.cancel_btn.setEnabled(False)
        self.preload_btn.setEnabled(True)
        self.status_label.setText("Model preloaded successfully")
        debug_print(f"[INFO] Preload complete: {result}")
        self._cleanup_preload_thread()
        self._update_preload_button_state()  # now loaded -> green, disabled

    def _on_preload_error(self, error):
        """Handle preload error."""
        if not getattr(self, 'preload_progress', None) or not self.preload_progress.isVisible():
            self._cleanup_preload_thread()
            return
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.cancel_btn.setEnabled(False)
        self.preload_btn.setEnabled(True)
        self.status_label.setText(f"Preload failed: {error}")
        debug_print(f"[ERROR] Preload failed: {error}")
        self._cleanup_preload_thread()

    def load_models(self):
        """Load available AI models with their sizes.
        Robust to both our ollama_wrapper (dicts) and the official 'ollama' pip package
        (which returns ListResponse / Model objects with attribute access).
        This fixes the long-standing "modellméretek nem látszanak" issue.
        """
        models = self.ai_assistant.get_available_models()
        if models:
            self.model_combo.clear()
            # Get model sizes from Ollama if available
            model_sizes = {}
            if self.ai_assistant.use_ollama and ollama:
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
            default_model = "claude-3-5-sonnet-20241022"
            for i in range(self.model_combo.count()):
                if self.model_combo.itemText(i).startswith(default_model):
                    self.model_combo.setCurrentIndex(i)
                    break

            # Enable preload button if an Ollama model is selected
            self._update_preload_button_state()
        else:
            self.model_combo.clear()
            self.model_combo.addItem("claude-3-5-sonnet-20241022")

        # Load persisted context window setting (checkbox + dropdown).
        # The "bekapcsolása" (enabling) must work immediately.
        self._load_context_window_setting()

    def _update_preload_button_state(self):
        """Update Preload button state and color based on whether the selected
        Ollama model is currently resident in memory (according to ollama ps).

        - Green background + disabled when loaded (keep-alive active).
        - Pale red / attention color + enabled when not loaded (user should preload
          to avoid slow first response).
        - The button becomes active again automatically when the model unloads
          due to keep-alive expiration.
        """
        model = self.model_combo.currentText()
        raw_model = model.split(" (")[0]

        if not raw_model.startswith("ollama:"):
            self.preload_btn.setEnabled(False)
            self.preload_btn.setStyleSheet("")
            self.preload_btn.setToolTip("Preload is only for Ollama models")
            return

        model_name = raw_model[7:]
        is_loaded = self._is_ollama_model_loaded(model_name)

        if is_loaded:
            self.preload_btn.setEnabled(False)
            self.preload_btn.setStyleSheet(
                "background-color: #2e7d32; color: white; border: 1px solid #1b5e20;"
            )
            self.preload_btn.setToolTip("Model is currently loaded in memory")
        else:
            self.preload_btn.setEnabled(True)
            self.preload_btn.setStyleSheet(
                "background-color: #c62828; color: white; border: 1px solid #b71c1c;"
            )
            self.preload_btn.setToolTip("Click to preload model (avoids slow first response)")

    def _on_model_changed(self, index):
        """Called when a new model is selected from the combo box.
        Updates the AI assistant's model and enables/disables the preload button.
        """
        model = self.model_combo.itemText(index)
        # Strip size info if present (e.g., "ollama:model (4.2 GB)")
        raw_model = model.split(" (")[0]
        debug_print(f"[DEBUG] Model changed to: {model} (raw: {raw_model})")
        self.ai_assistant.selected_model = raw_model
        self._update_preload_button_state()

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

    def _check_for_preloaded_model(self):
        """Check if any Ollama model is already loaded and populate the dropdown accordingly."""
        if not self.ai_assistant.use_ollama:
            return

        try:
            # Use ps endpoint to check which models are actually loaded in memory
            # The /api/ps endpoint returns loaded models, not just available ones
            import requests
            response = requests.get("http://localhost:11434/api/ps", timeout=5)
            if response.status_code == 200:
                loaded_data = response.json()
                models_loaded = loaded_data.get('models', [])
                if models_loaded:
                    # Get the first loaded model
                    first_model = models_loaded[0]
                    model_name = first_model.get('model', first_model.get('name', ''))
                    if model_name:
                        debug_print(f"[DEBUG] Found preloaded model: {model_name}")
                        # Add the preloaded model to the dropdown if not already present
                        raw_model = f"ollama:{model_name}"
                        found = False
                        for i in range(self.model_combo.count()):
                            if self.model_combo.itemText(i).startswith(raw_model):
                                found = True
                                self.model_combo.setCurrentIndex(i)
                                break
                        if not found:
                            self.model_combo.addItem(raw_model)
                            self.model_combo.setCurrentText(raw_model)
                        # Update the AI assistant's selected model
                        self.ai_assistant.selected_model = raw_model
                        self._update_preload_button_state()
                        debug_print(f"[DEBUG] Set model to preloaded: {raw_model}")
                        # Disable preload button since model is already loaded
                        self.preload_btn.setEnabled(False)
                    else:
                        # No loaded model found, enable preload button
                        self.preload_btn.setEnabled(True)
                else:
                    # No loaded models, enable preload button
                    self.preload_btn.setEnabled(True)
            else:
                self.preload_btn.setEnabled(True)
        except Exception as e:
            debug_print(f"[WARN] Could not check for preloaded models: {e}")
            self.preload_btn.setEnabled(True)

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
        if not getattr(self, 'preload_progress', None) or not self.preload_progress.isVisible():
            self._cleanup_preload_thread()
            return
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
        The QThread object must only ever be deleted via the
        `finished.connect(self.preload_thread.deleteLater)` connection that was
        established at creation time. Disconnecting that or calling deleteLater
        from here is what triggers the 'Destroyed while thread is still running' crash.
        """
        th = getattr(self, 'preload_thread', None)
        if not th:
            return

        self.preload_thread = None  # drop reference first

        # Only disconnect the signals that point to our UI handlers.
        # IMPORTANT: do NOT touch the finished -> deleteLater connection.
        for signal, slot in (
            (th.result_ready, self._on_preload_ready),
            (th.error_occurred, self._on_preload_error),
            (th.progress_update, self._on_preload_progress),
            # deliberately not including finished here
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
        parent = getattr(self, "parent", None)
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
                    break  # found editor host

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
            parent = getattr(parent, "parent", None) or getattr(parent, "projects", None) or getattr(parent, "window", None)

        return code, file_path, project_root

    def _smart_truncate_for_context(self, code: str, file_path: str = "", safety_note: bool = True) -> str:
        """Intelligent truncation when custom context window is enabled.
        Goal: never let the code part blow up the model's context window.
        Strategy:
        - If not enabled or code is small → return as-is.
        - Rough token estimate (code is ~3.5-4 chars per token).
        - Keep head (imports, class/function signatures, top of file) + tail (recent logic).
        - Add a clear note so the model knows it was truncated (transparency).
        This is the "okos + intelligens" part on top of the safety dropdown.
        """
        if not getattr(self.ai_assistant, 'context_window_enabled', False):
            return code

        size = getattr(self.ai_assistant, 'context_window_size', 0) or 8192
        # Budget for the code part: leave room for system instructions, user question,
        # history, and the model's output (num_predict).
        # Conservative: ~50% of context for the code payload.
        max_code_tokens = max(1024, int(size * 0.50))
        max_chars = int(max_code_tokens * 3.8)

        if len(code) <= max_chars:
            return code

        lines = code.splitlines(keepends=True)
        n = len(lines)
        if n <= 8:
            truncated = code[:max_chars]
        else:
            head = lines[: max(3, n // 3)]
            tail = lines[-max(3, n // 4):]
            truncated = ''.join(head) + "\n\n# ... [code truncated to fit context window] ...\n\n" + ''.join(tail)

        if safety_note:
            truncated += f"\n\n# [Note: file was automatically truncated because custom context window ({size} tokens) is enabled]"

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
            elif action == "explain":
                return "Magyarázd el részletesen a megnyitott kódot"
            elif action == "fix":
                return "Javítsd ki a hibákat a megnyitott kódban"
        elif lang.startswith("german"):
            if action == "suggest":
                return "Schlage Verbesserungen für den geöffneten Code vor"
            elif action == "explain":
                return "Erkläre den geöffneten Code detailliert"
            elif action == "fix":
                return "Behebe Fehler im geöffneten Code"
        elif lang.startswith("slovak"):
            if action == "suggest":
                return "Navrhni vylepšenia pre otvorený kód"
            elif action == "explain":
                return "Vysvetli podrobne otvorený kód"
            elif action == "fix":
                return "Oprav chyby v otvorenom kóde"
        else:
            # English fallback
            if action == "suggest":
                return "Suggest improvements for the open code"
            elif action == "explain":
                return "Explain the open code in detail"
            elif action == "fix":
                return "Fix errors in the open code"
        return action

    def configure_ai_assistant(self, settings):
        """Configure AI assistant with settings"""
        api_provider = settings.get("ai_api_provider", "Demo Mode")
        api_key = settings.get("ai_api_key", "freecc")
        api_url = settings.get("ai_api_url", "http://localhost:8082")
        default_model = settings.get("ai_default_model", "claude-3-5-sonnet-20241022")
        timeout = int(settings.get("ai_timeout", 15))
        cache_enabled = settings.get("ai_cache_enabled", "True") == "True"

        # Configure the AI assistant
        self.ai_assistant.set_api_config(api_url, api_key, default_model, timeout, cache_enabled)

        print(f"DEBUG: AI Assistant configured - Provider: {api_provider}, Model: {default_model}, Timeout: {timeout}s, Cache: {cache_enabled}")

    def on_suggest_clicked(self):
        """Handle suggest improvements button click"""
        # Defensive full reset of any previous busy state before starting a new action.
        # This helps recover from corrupted state after previous cancel/preload issues
        # (progress bar left animating, buttons disabled, timers running).
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
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to analyze!")
            # re-enable in case they were disabled
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            return

        # Smart truncation when user enabled a limited context window (safety feature).
        code = self._smart_truncate_for_context(code, file_path)

        # Make the implicit button action visible in chat (like a user prompt).
        # This addresses "nem is megy látható utasítás a modellnek".
        # The label is now localized to the currently selected AI language (dropdown).
        self._add_chat_item("user", self._localized_action("suggest"))
        self.start_ai_request("suggestion", code)

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
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            return

        code = self._smart_truncate_for_context(code, file_path)
        self._add_chat_item("user", self._localized_action("explain"))
        self.start_ai_request("explanation", code)

    def update_icon_theme(self):
        """Update icon theme based on system theme"""
        # For now, use color icons that work on both light and dark themes
        # In future, could detect system theme and switch icons accordingly
        pass

    def on_send_clicked(self):
        """Handle send button click - send custom prompt to AI.
        Uses robust resolver so the model always sees the open code + project/file
        context, even if the user only typed a free-text request like "nézd át a kódot".
        The language directive is front-loaded inside generate_custom_prompt.
        """
        debug_print(f"[DEBUG] Send button clicked")

        # Get custom prompt first (we allow sending even without editor for pure questions)
        prompt_text = self.prompt_input.toPlainText()
        debug_print(f"[DEBUG] User prompt: {prompt_text[:100]}{'...' if len(prompt_text) > 100 else ''}")
        if not prompt_text.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "Please enter a prompt!")
            return

        # ROBUST resolve (fixes the "nem látja a projektet és a kódot" issue)
        code, file_path, project_root = self._get_active_code_and_context()

        # Build rich context header so the model knows what project/file it's looking at.
        context_lines = []
        if project_root:
            context_lines.append(f"Project root: {project_root}")
        if file_path:
            context_lines.append(f"Current file: {file_path}")
        context_header = ("\n".join(context_lines) + "\n\n") if context_lines else ""

        if not code or not code.strip():
            full_prompt = f"{context_header}User question:\n{prompt_text}" if context_header else prompt_text
            debug_print("[DEBUG] No code in editor; sending plain question")
        else:
            # Smart truncation when the safety context window is enabled by the user.
            # This is the "intelligens" part: we never send more code than the chosen window can reasonably hold.
            truncated_code = self._smart_truncate_for_context(code, file_path)

            # For free-text custom prompts, provide the open code as optional reference only.
            # Do NOT force "review the code" – this makes simple questions (like language test)
            # fast, without unnecessary huge context processing. The model can use the code
            # if the question refers to it.
            # (The Suggest/Explain/Fix buttons are the ones that explicitly ask for code analysis.)
            full_prompt = (
                f"{context_header}"
                f"Current open editor file (reference only if relevant to the question):\n{truncated_code}\n\n"
                f"User question: {prompt_text}"
            )
            debug_print("[DEBUG] Sending project/file context header + (optionally truncated) code for custom prompt")

        # Store prompt for history and add to chat display
        self._pending_prompt = prompt_text
        self.history_count += 1
        # Preserve prompt history for Up/Down navigation (new paragraph ready after send)
        if prompt_text.strip():
            self.prompt_history.append(prompt_text)
            self.history_index = len(self.prompt_history)
        # Use helper to add chat item with proper role and collapse support
        self._add_chat_item("user", prompt_text)

        self.start_ai_request("custom", full_prompt)

    def start_ai_request(self, request_type, code):
        """Start an AI request"""
        debug_print(f"[DEBUG] start_ai_request: type={request_type}")
        # Update UI
        self.suggest_btn.setEnabled(False)
        self.explain_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.busy_indicator.setVisible(True)
        self.status_label.setText("Processing...")
        self.status_label.setStyleSheet("color: #0066cc;")

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
            if request_type == "suggestion":
                debug_print("[DEBUG] Calling generate_code_suggestions")
                self.ai_assistant.generate_code_suggestions(code)
            elif request_type == "explanation":
                debug_print("[DEBUG] Calling explain_code")
                self.ai_assistant.explain_code(code)
            elif request_type == "fix":
                debug_print("[DEBUG] Calling fix_code_errors")
                self.ai_assistant.fix_code_errors(code)
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
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            return

        code = self._smart_truncate_for_context(code, file_path)
        self._add_chat_item("user", self._localized_action("fix"))
        self.start_ai_request("fix", code)

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
                "\n\n[... A válasz nagyon hosszú vagy ismétlődő volt, a megjelenítés csonkítva. "
                "A Copy / Quote gombokkal próbálkozhatsz a teljesebb változattal ...]"
            )

        self.message_count += 1
        num = self.message_count
        if add_to_history:
            # Persist only the (capped) version to avoid blowing up QSettings / load time
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
        root_layout.setContentsMargins(4, 2, 4, 2)
        root_layout.setSpacing(0)

        # Early item so all mousePress and toggle closures can safely capture it
        item = QtWidgets.QListWidgetItem()

        ts = datetime.datetime.now().strftime("%H:%M")

        if role == "user":
            bg = "#1f3a1f"
            role_text = "You"
            align = Qt.AlignmentFlag.AlignRight
            text_color = "#e8f5e9"
        elif role == "error":
            bg = "#3a1f1f"
            role_text = "Error"
            align = Qt.AlignmentFlag.AlignLeft
            text_color = "#ffcccc"
        else:
            bg = "#2a2a2e"
            role_text = "AI"
            align = Qt.AlignmentFlag.AlignLeft
            text_color = "#e0e0e0"

        # The bubble itself - one rounded frame containing everything
        bubble = QtWidgets.QFrame()
        bubble.setStyleSheet(
            f"background-color:{bg}; "
            "border-radius:9px; "
            "padding:6px 8px;"
        )
        # No hard max width — the bubble content should adapt to the available/free
        # horizontal space in the chat (as requested). Only height and fixed vertical
        # spacings/margins/padding are controlled. The HBox + stretch gives side
        # alignment (left for AI, right for user) while letting the bubble expand.
        bubble.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum
        )

        bubble_layout = QtWidgets.QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(2, 2, 2, 2)
        bubble_layout.setSpacing(3)
        # Force the inner layout to stay tightly packed to its content.
        # This prevents the bubble from getting extra internal height that
        # would create empty space between the text/meta and the action buttons
        # (the red area in the screenshot).
        bubble_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)

        # --- Text content (or preview for long messages) ---
        lines = text.splitlines()
        is_long = (len(text) > 600) or (len(lines) > 5)

        if is_long:
            preview = "\n".join(lines[:3]) + "\n..."
            lbl = QtWidgets.QLabel(preview)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setAlignment(align)
            lbl.setFont(QtGui.QFont("Courier New", self.font_size))
            lbl.setStyleSheet(f"color:{text_color}; background:transparent;")
            lbl.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Minimum
            )
            def _quote_preview(ev, it=item):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self.on_history_item_clicked(it)
            lbl.mousePressEvent = _quote_preview
            bubble_layout.addWidget(lbl)

            toggle = QtWidgets.QPushButton("▼ show more")
            toggle.setStyleSheet("font-size:8pt; color:#888; padding:1px 3px; border:none; background:transparent;")
            toggle.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

            toggle._full_text = text
            toggle._bubble_layout = bubble_layout
            toggle._preview_lbl = lbl
            toggle._full_lbl = None

            def _toggle(_=False):
                if toggle._full_lbl is None:
                    full = QtWidgets.QLabel(toggle._full_text)
                    full.setWordWrap(True)
                    full.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    full.setAlignment(align)
                    full.setFont(QtGui.QFont("Courier New", self.font_size))
                    full.setStyleSheet(f"color:{text_color}; background:transparent;")
                    full.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Minimum
                    )
                    def _quote_full(ev, it=item):
                        if ev.button() == Qt.MouseButton.LeftButton:
                            self.on_history_item_clicked(it)
                    full.mousePressEvent = _quote_full
                    toggle._full_lbl = full
                    idx = toggle._bubble_layout.indexOf(toggle)
                    toggle._bubble_layout.insertWidget(idx, full)
                    full.setVisible(True)
                    toggle._preview_lbl.setVisible(False)
                    toggle.setText("▲ show less")
                else:
                    f = toggle._full_lbl
                    if f.isVisible():
                        f.setVisible(False)
                        toggle._preview_lbl.setVisible(True)
                        toggle.setText("▼ show more")
                    else:
                        f.setVisible(True)
                        toggle._preview_lbl.setVisible(False)
                        toggle.setText("▲ show less")
                if hasattr(toggle, '_widget') and hasattr(toggle, '_item'):
                    w = toggle._widget
                    it = toggle._item
                    it.setSizeHint(w.sizeHint())
                    if hasattr(toggle, '_chat'):
                        toggle._chat.updateGeometry()
                        toggle._chat.scrollToBottom()

            toggle.clicked.connect(_toggle)
            bubble_layout.addWidget(toggle, alignment=align)
        else:
            lbl = QtWidgets.QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setAlignment(align)
            if role == "user":
                lbl.setFont(QtGui.QFont("Courier New", self.font_size, QtGui.QFont.Weight.Medium))
            else:
                lbl.setFont(QtGui.QFont("Courier New", self.font_size))
            lbl.setStyleSheet(f"color:{text_color}; background:transparent;")
            lbl.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Minimum
            )
            def _quote_lbl(ev, it=item):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self.on_history_item_clicked(it)
            lbl.mousePressEvent = _quote_lbl
            bubble_layout.addWidget(lbl)

        # --- Meta (timestamp + role + count) inside the bubble, bottom of text area ---
        meta = QtWidgets.QLabel(f"{ts} · {role_text} [{num}]")
        meta.setStyleSheet("color:#888; font-size:7pt; background:transparent;")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight)
        meta.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Minimum
        )
        bubble_layout.addWidget(meta)

        # --- Action buttons inside the bubble at the very bottom ---
        act = QtWidgets.QHBoxLayout()
        act.setContentsMargins(0, 3, 0, 0)
        act.setSpacing(3)

        def make_btn(txt, tip):
            b = QtWidgets.QPushButton(txt)
            b.setToolTip(tip)
            b.setStyleSheet(
                "font-size:8pt; color:#ccc; padding:1px 5px; border:1px solid #555; "
                "border-radius:3px; background:#222;"
            )
            b.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(17)
            return b

        btn_copy = make_btn("Copy", "Másolás a vágólapra")
        btn_quote = make_btn("Quote", "Idézés a promptba (follow-up)")
        btn_apply = make_btn("Apply", "Alkalmazás a szerkesztőbe (hamarosan)")

        full_text = original_for_actions

        def do_copy():
            QtWidgets.QApplication.clipboard().setText(full_text)
            self.status_label.setText("Másolva ✓")
            QtCore.QTimer.singleShot(1200, lambda: self.status_label.setText("Kész"))

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
            QtWidgets.QSizePolicy.Policy.Minimum
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

        # For long messages: attach so "show more" can update the item height later
        if is_long and 'toggle' in locals():
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
        sep_line.setStyleSheet("background-color:#444; max-height:1px;")
        sep_layout.addWidget(sep_line)
        sep_item.setSizeHint(sep_widget.sizeHint())
        self.chat_display.addItem(sep_item)
        self.chat_display.setItemWidget(sep_item, sep_widget)

    def on_cancel_clicked(self):
        """Handle cancel button click"""
        self.ai_assistant.cancel_request()

        cancelled_preload = False
        # Properly cancel a running preload thread (separate from normal AI worker_thread)
        if getattr(self, 'preload_thread', None) and self.preload_thread.isRunning():
            cancelled_preload = True
            th = self.preload_thread
            try:
                th.cancel()
                th.quit()
                # Very short wait — do not block UI. Deletion owned by finished->deleteLater.
                th.wait(100)
            except Exception:
                pass
            self.preload_thread = None

        # Reset preload progress bar to the simple original behavior (0 and hide on cancel).
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.preload_btn.setEnabled(True)
        if cancelled_preload:
            self.status_label.setText("Preload cancelled")
            self.status_label.setStyleSheet("color: #cc0000;")

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)

        # Safe cleanup: do not force-delete a still-running thread (prevents "Destroyed while running")
        self._cleanup_preload_thread()

        # Mark any pending result from the cancelled request to be ignored.
        # This stops partial AI responses from appearing after the user pressed Cancel.
        self._ignore_next_ai_result = True

        # ALWAYS fully reset normal AI busy/processing state on cancel.
        # Also stop any leftover preload ramp timer (even though we reverted the display logic,
        # the timer object may still exist from previous code).
        self._is_processing = False
        if hasattr(self, '_busy_timer') and self._busy_timer.isActive():
            self._busy_timer.stop()
        if hasattr(self, '_preload_ramp_timer') and self._preload_ramp_timer.isActive():
            self._preload_ramp_timer.stop()
        if hasattr(self, '_preload_ramp_active'):
            self._preload_ramp_active = False
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)

    def on_clear_clicked(self):
        """Clear the current prompt input and reset any temporary state."""
        if hasattr(self, "prompt_input") and self.prompt_input is not None:
            self.prompt_input.clear()
        self.status_label.setText("Kész")
        self.status_label.setStyleSheet("color: #666;")

    def on_clear_chat_clicked(self):
        """Clear the entire chat conversation history (modern chat UX)."""
        self.chat_display.clear()
        self.prompt_history.clear()
        self.history_index = -1
        self.message_count = 0
        self.status_label.setText("Chat előzmények törölve")
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
        # Replay without re-adding to history list (to avoid dup on load)
        # count will be set correctly by the _add calls
        for role, text in self.chat_history:
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
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return

        # Add suggestion to chat display (clean content, role styling handles "AI")
        self._add_chat_item("ai", suggestion)

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Javaslat kész")
        self.status_label.setStyleSheet("color: #009900;")

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
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return

        # Add explanation to chat display (clean content)
        self._add_chat_item("ai", explanation)

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Magyarázat kész")
        self.status_label.setStyleSheet("color: #009900;")

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
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return

        # Use the modern bubble chat item (consistent with user messages and PLAN chat layout)
        self._add_chat_item("ai", content)

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Válasz érkezett")
        self.status_label.setStyleSheet("color: #009900;")
        debug_print("[DEBUG] Custom response received and UI reset")
        self._update_preload_button_state()  # response likely loaded/warmed the model

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
            self.busy_indicator.setVisible(False)
            self.suggest_btn.setEnabled(True)
            self.explain_btn.setEnabled(True)
            self.fix_btn.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return

        # Add fix to chat display (clean content)
        self._add_chat_item("ai", fix)

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Hibajavítás kész")
        self.status_label.setStyleSheet("color: #009900;")

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
        """Handle error signal"""
        self._ignore_next_ai_result = False
        # Use modern error bubble (consistent design)
        self._add_chat_item("error", error_message)

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText(f"Hiba: {error_message}")
        self.status_label.setStyleSheet("color: #cc0000;")
        debug_print(f"[DEBUG] Error handled: {error_message}")
