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

        # Font size tracking
        self.font_size = 12  # Default font size for prompt and chat messages

        # Allow the panel to expand and shrink as needed
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        # Setup UI
        self.init_ui()
        self.setup_connections()

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

        # Progress bar for AI processing animation
        self.preload_progress = QtWidgets.QProgressBar()
        self.preload_progress.setMaximum(100)
        self.preload_progress.setValue(0)
        self.preload_progress.setVisible(False)
        self.preload_progress.setFixedWidth(100)
        model_layout.addWidget(self.preload_progress)

        # Language selector
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems(["Hungarian", "English", "Slovak", "German"])
        self.lang_combo.setMinimumWidth(120)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        model_layout.addWidget(self.lang_combo)

        # Add busy timer for progress bar animation during AI processing
        self._busy_timer = QtCore.QTimer(self)
        self._busy_timer.timeout.connect(self._step_progress)
        self._busy_timer.setInterval(50)
        self._busy_progress_value = 0
        self._is_processing = False

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
        self.ai_assistant.error_occurred.connect(self.on_error)

        # Set icon theme based on system theme
        self.update_icon_theme()

        # Load models after connections are set up
        self.load_models()

        # Check for already loaded model after loading all models
        self._check_for_preloaded_model()

    def on_preload_clicked(self):
        """Handle preload button click - manually trigger model preload."""
        model = self.model_combo.currentText()
        raw_model = model.split(" (")[0]
        debug_print(f"[DEBUG] Preload started for: {raw_model}")
        if raw_model.startswith("ollama:"):
            self.preload_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.preload_progress.setVisible(True)
            self.preload_progress.setValue(10)
            # Use Hungarian greeting for preload
            preload_prompt = "Szia! Üdvözölj meg a PyCoderAiban!"
            self.preload_thread = AIWorkerThread(
                None, raw_model, preload_prompt, "preload", False, True, 30
            )
            self.preload_thread.result_ready.connect(self._on_preload_ready)
            self.preload_thread.error_occurred.connect(self._on_preload_error)
            self.preload_thread.progress_update.connect(self._on_preload_progress)
            self.preload_thread.start()
        else:
            self.status_label.setText("Non-Ollama model - no preload needed")
            debug_print(f"[INFO] {raw_model} is a Claude model, no preload needed")

    def _on_preload_progress(self, value):
        """Update progress bar during preload."""
        debug_print(f"[DEBUG] Preload progress: {value}%")
        self.preload_progress.setValue(value)

    def _on_preload_ready(self, result, _=None):
        """Handle preload completion from thread."""
        self.preload_progress.setValue(100)
        self.preload_progress.setVisible(False)
        self.cancel_btn.setEnabled(False)
        self.preload_btn.setEnabled(True)
        self.status_label.setText("Model preloaded successfully")
        debug_print(f"[INFO] Preload complete: {result}")

    def _on_preload_error(self, error):
        """Handle preload error."""
        self.preload_progress.setVisible(False)
        self.preload_progress.setValue(0)
        self.cancel_btn.setEnabled(False)
        self.preload_btn.setEnabled(True)
        self.status_label.setText(f"Preload failed: {error}")
        debug_print(f"[ERROR] Preload error: {error}")

    def load_models(self):
        """Load available AI models with their sizes."""
        models = self.ai_assistant.get_available_models()
        if models:
            self.model_combo.clear()
            # Get model sizes from Ollama if available
            model_sizes = {}
            if self.ai_assistant.use_ollama and ollama:
                try:
                    ollama_result = ollama.list()
                    # Handle different return formats
                    if isinstance(ollama_result, dict):
                        models_list = ollama_result.get('models', [])
                    elif hasattr(ollama_result, '__iter__') and not isinstance(ollama_result, str):
                        models_list = list(ollama_result)
                    else:
                        models_list = []

                    for m in models_list:
                        if isinstance(m, dict):
                            name = m.get('model', m.get('name', ''))
                            size = m.get('size', 0)
                            if size:
                                model_sizes[name] = f" ({size / (1024**3):.1f} GB)"
                except Exception as e:
                    debug_print(f"[WARN] Could not fetch model sizes: {e}")

            for model in models:
                display_name = model
                if model.startswith("ollama:"):
                    pure_name = model[7:]
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

    def _update_preload_button_state(self):
        """Enable/disable preload button based on selected model type."""
        model = self.model_combo.currentText()
        # Strip size info if present (e.g., "ollama:model (4.2 GB)")
        raw_model = model.split(" (")[0]
        is_ollama = raw_model.startswith("ollama:")
        self.preload_btn.setEnabled(is_ollama)

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
        self.ai_assistant.set_language(lang.lower())
        debug_print(f"[DEBUG] Language set to: {lang}")

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

    def set_editor(self, editor):
        """Set the current editor"""
        self.current_editor = editor

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
        if not self.current_editor:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No active editor!")
            return

        # Get code from editor
        try:
            if hasattr(self.current_editor, 'text'):
                code = self.current_editor.text()
            elif hasattr(self.current_editor, 'toPlainText'):
                code = self.current_editor.toPlainText()
            else:
                QtWidgets.QMessageBox.warning(self, "AI Assistant", "Unsupported editor type!")
                return
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", f"Error getting code: {str(e)}")
            return

        if not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to analyze!")
            return

        self.start_ai_request("suggestion", code)

    def on_explain_clicked(self):
        """Handle explain code button click"""
        if not self.current_editor:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No active editor!")
            return

        # Get code from editor
        try:
            if hasattr(self.current_editor, 'text'):
                code = self.current_editor.text()
            elif hasattr(self.current_editor, 'toPlainText'):
                code = self.current_editor.toPlainText()
            else:
                QtWidgets.QMessageBox.warning(self, "AI Assistant", "Unsupported editor type!")
                return
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", f"Error getting code: {str(e)}")
            return

        if not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to explain!")
            return

        self.start_ai_request("explanation", code)

    def update_icon_theme(self):
        """Update icon theme based on system theme"""
        # For now, use color icons that work on both light and dark themes
        # In future, could detect system theme and switch icons accordingly
        pass

    def on_send_clicked(self):
        """Handle send button click - send custom prompt to AI"""
        debug_print(f"[DEBUG] Send button clicked")
        if not self.current_editor:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No active editor!")
            return

        # Get custom prompt
        prompt_text = self.prompt_input.toPlainText()
        debug_print(f"[DEBUG] User prompt: {prompt_text[:100]}{'...' if len(prompt_text) > 100 else ''}")
        if not prompt_text.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "Please enter a prompt!")
            return

        # Get current code
        try:
            if hasattr(self.current_editor, 'text'):
                code = self.current_editor.text()
            elif hasattr(self.current_editor, 'toPlainText'):
                code = self.current_editor.toPlainText()
            else:
                QtWidgets.QMessageBox.warning(self, "AI Assistant", "Unsupported editor type!")
                return
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", f"Error getting code: {str(e)}")
            return

        if not code.strip():
            # If no code, just send the prompt
            full_prompt = prompt_text
            debug_print("[DEBUG] No code in editor, sending only prompt")
        else:
            # Combine code and prompt
            full_prompt = f"Code:\n{code}\n\nPrompt:\n{prompt_text}"
            debug_print("[DEBUG] Sending code with custom prompt")

        # Store prompt for history and add to chat display
        self._pending_prompt = prompt_text
        self.history_count += 1
        # Use helper to add chat item with proper role and collapse support
        self._add_chat_item("user", prompt_text)

        self.start_ai_request("custom", full_prompt)
        #self.start_ai_request("suggestion", full_prompt)

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

        # Start progress bar animation for AI processing
        self._is_processing = True
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
        if not self.current_editor:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No active editor!")
            return

        # Get code from editor
        try:
            if hasattr(self.current_editor, 'text'):
                code = self.current_editor.text()
            elif hasattr(self.current_editor, 'toPlainText'):
                code = self.current_editor.toPlainText()
            else:
                QtWidgets.QMessageBox.warning(self, "AI Assistant", "Unsupported editor type!")
                return
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", f"Error getting code: {str(e)}")
            return

        if not code.strip():
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No code to fix!")
            return

        self.start_ai_request("fix", code)

    def _add_chat_item(self, role, text):
        """Add a modern chat bubble item.
        role: "user", "ai", or "error"
        text: full original message (stored for quoting/copy/apply)
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(3)

        # Colors + alignment
        if role == "user":
            bg = "#1f3a1f"
            header_color = "#8bc34a"
            role_text = "You"
            align = Qt.AlignmentFlag.AlignRight
        elif role == "error":
            bg = "#3a1f1f"
            header_color = "#ff6b6b"
            role_text = "Error"
            align = Qt.AlignmentFlag.AlignLeft
        else:
            bg = "#2a2a2e"
            header_color = "#4fc3f7"
            role_text = "AI"
            align = Qt.AlignmentFlag.AlignLeft

        # Top row: timestamp + role badge
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        ts = datetime.datetime.now().strftime("%H:%M")
        ts_lbl = QtWidgets.QLabel(ts)
        ts_lbl.setStyleSheet("color:#777; font-size:8pt;")
        top.addWidget(ts_lbl)
        top.addStretch()
        role_lbl = QtWidgets.QLabel(role_text)
        role_lbl.setStyleSheet(f"color:{header_color}; font-size:8pt; font-weight: bold;")
        role_lbl.setAlignment(align)
        top.addWidget(role_lbl)
        layout.addLayout(top)

        # Content (with collapse for long messages)
        lines = text.splitlines()
        is_long = len(lines) > 4

        if is_long:
            preview = "\n".join(lines[:3]) + "\n..."
            preview_lbl = QtWidgets.QLabel(preview)
            preview_lbl.setWordWrap(True)
            preview_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            preview_lbl.setStyleSheet(
                f"background-color:{bg}; padding:7px 9px; border-radius:5px; border:1px solid #3a3a3a;"
            )
            preview_lbl.setAlignment(align)
            preview_lbl.setFont(QtGui.QFont("Courier New", self.font_size))

            full_lbl = QtWidgets.QLabel(text)
            full_lbl.setWordWrap(True)
            full_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            full_lbl.setStyleSheet(
                f"background-color:{bg}; padding:7px 9px; border-radius:5px; border:1px solid #3a3a3a;"
            )
            full_lbl.setAlignment(align)
            full_lbl.setVisible(False)
            full_lbl.setFont(QtGui.QFont("Courier New", self.font_size))

            toggle = QtWidgets.QPushButton("▼ show more")
            toggle.setStyleSheet("font-size:8pt; color:#888; padding:1px 4px; border:none;")
            toggle.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

            def _toggle(_=False):
                if full_lbl.isVisible():
                    full_lbl.setVisible(False)
                    preview_lbl.setVisible(True)
                    toggle.setText("▼ show more")
                else:
                    full_lbl.setVisible(True)
                    preview_lbl.setVisible(False)
                    toggle.setText("▲ show less")
            toggle.clicked.connect(_toggle)

            layout.addWidget(preview_lbl)
            layout.addWidget(full_lbl)
            layout.addWidget(toggle, alignment=align)
        else:
            lbl = QtWidgets.QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            style = f"background-color:{bg}; padding:7px 9px; border-radius:5px; border:1px solid #3a3a3a;"
            if role == "user":
                style += " font-weight: 500;"
            lbl.setStyleSheet(style)
            lbl.setAlignment(align)
            lbl.setFont(QtGui.QFont("Courier New", self.font_size))
            layout.addWidget(lbl)

        # === Modern action bar (Copy / Quote / Apply) ===
        actions = QtWidgets.QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(2)

        def make_action_btn(txt, tip):
            b = QtWidgets.QPushButton(txt)
            b.setToolTip(tip)
            b.setStyleSheet(
                "font-size:8pt; color:#aaa; padding:1px 5px; border:1px solid #444; border-radius:3px; background:#222;"
            )
            b.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(18)
            return b

        btn_copy = make_action_btn("Copy", "Másolás a vágólapra")
        btn_quote = make_action_btn("Quote", "Idézés a promptba (follow-up)")
        btn_apply = make_action_btn("Apply", "Alkalmazás a szerkesztőbe (hamarosan)")

        # Capture full text for actions
        full_text = text

        def do_copy():
            QtWidgets.QApplication.clipboard().setText(full_text)
            self.status_label.setText("Másolva ✓")
            QtCore.QTimer.singleShot(1200, lambda: self.status_label.setText("Kész"))

        def do_quote():
            # Put into prompt for easy follow-up / reply
            current = self.prompt_input.toPlainText().strip()
            if current:
                self.prompt_input.setPlainText(current + "\n\n" + full_text)
            else:
                self.prompt_input.setPlainText(full_text)
            self.prompt_input.setFocus()
            self.prompt_input.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        def do_apply():
            # Placeholder per KANBAN "AI model to edit editor content"
            QtWidgets.QMessageBox.information(
                self, "Apply",
                "Apply diff / code insertion coming soon.\n\n"
                "See KANBAN: 'Allow AI model to edit editor content with permission' + diff viewer."
            )
            # Future: self._apply_to_editor(full_text)

        btn_copy.clicked.connect(do_copy)
        btn_quote.clicked.connect(do_quote)
        btn_apply.clicked.connect(do_apply)

        actions.addWidget(btn_copy)
        actions.addWidget(btn_quote)
        actions.addWidget(btn_apply)
        actions.addStretch()
        layout.addLayout(actions)

        # Insert as custom list item
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        item.setData(32, full_text)  # custom role (matches previous code using 32)
        self.chat_display.addItem(item)
        self.chat_display.setItemWidget(item, widget)
        self.chat_display.scrollToBottom()

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
        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Cancelled")
        self.status_label.setStyleSheet("color: #cc0000;")

    def on_clear_clicked(self):
        """Clear the current prompt input and reset any temporary state."""
        if hasattr(self, "prompt_input") and self.prompt_input is not None:
            self.prompt_input.clear()
        self.status_label.setText("Kész")
        self.status_label.setStyleSheet("color: #666;")

    def on_clear_chat_clicked(self):
        """Clear the entire chat conversation history (modern chat UX)."""
        self.chat_display.clear()
        self.status_label.setText("Chat előzmények törölve")
        self.status_label.setStyleSheet("color: #888;")

    def eventFilter(self, obj, event):
        """Handle Enter in prompt_input: Enter = send, Shift+Enter = newline (per PLAN.md)."""
        if obj is getattr(self, "prompt_input", None) and event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    # Allow multiline
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
                # Find all QLabel children and update their font
                labels = widget.findChildren(QtWidgets.QLabel)
                for label in labels:
                    label.setFont(QtGui.QFont("", new_size))

    def on_suggestion_ready(self, suggestion):
        """Handle suggestion ready signal"""
        self._is_processing = False
        self._busy_timer.stop()
        self.preload_progress.setVisible(False)

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
