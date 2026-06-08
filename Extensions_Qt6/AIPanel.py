#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Panel for PyCoderAi
Provides a user interface for AI assistant features
"""

import sys
import os
import datetime

# Debug logger – appends all DEBUG_* prints to DEBUG_LOG.md
def debug_print(message):
    """Append a debug line to DEBUG_LOG.md with a timestamp."""
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
from Extensions_Qt6.AIAssistant import AIAssistant, AIWorkerThread, ollama
# Import the ollama module/variable from AIAssistant's scope
from Extensions_Qt6 import AIAssistant as _ai_assistant_module
ollama = getattr(_ai_assistant_module, 'ollama', None), ollama


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
        prompt_label = QtWidgets.QLabel("Prompt:")
        prompt_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(prompt_label)

        self.prompt_input = QtWidgets.QTextEdit()
        self.prompt_input.setPlaceholderText("Enter your question or request for the AI...")
        self.prompt_input.setStyleSheet("background-color: #252526; color: #ffffff; font-family: 'Courier New', monospace;")
        self.prompt_input.setMaximumHeight(80)
        self.prompt_input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.prompt_input)

        # Send button and font controls
        send_layout = QtWidgets.QHBoxLayout()
        send_layout.setContentsMargins(0, 0, 0, 0)

        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/flag-green.png")))
        self.send_btn.setToolTip("Send prompt to AI")
        self.send_btn.setFixedWidth(100)
        send_layout.addWidget(self.send_btn)

        # Clear button
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setToolTip("Clear prompt input")
        self.clear_btn.setFixedWidth(80)
        send_layout.addWidget(self.clear_btn)

        # Font size controls
        self.fontSize = 12  # Default font size
        self.decrease_font_btn = QtWidgets.QPushButton("-A")
        self.decrease_font_btn.setToolTip("Decrease font size")
        self.decrease_font_btn.setFixedWidth(40)
        send_layout.addWidget(self.decrease_font_btn)

        self.increase_font_btn = QtWidgets.QPushButton("+A")
        self.increase_font_btn.setToolTip("Increase font size")
        self.increase_font_btn.setFixedWidth(40)
        send_layout.addWidget(self.increase_font_btn)

        send_layout.addStretch()
        main_layout.addLayout(send_layout)

        # Response area – modern chat display with collapsible messages
        self.chat_display = QtWidgets.QListWidget()
        self.chat_display.setStyleSheet("background-color: #2d2d30; color: #ffffff; border:none;")
        self.chat_display.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.chat_display.itemClicked.connect(self.on_history_item_clicked)
        main_layout.addWidget(self.chat_display)

        # Status bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #666;")
        main_layout.addWidget(self.status_label)

    def setup_connections(self):
        """Setup signal connections"""
        self.suggest_btn.clicked.connect(self.on_suggest_clicked)
        self.explain_btn.clicked.connect(self.on_explain_clicked)
        self.fix_btn.clicked.connect(self.on_fix_clicked)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        self.send_btn.clicked.connect(self.on_send_clicked)
        self.clear_btn.clicked.connect(self.on_clear_clicked)
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
        """Add a chat item with collapsible support for long messages.
        role: "user" or "ai" or "error"
        text: full message string
        """
        # Create container widget
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Determine colors and alignment
        if role == "user":
            bg_color = "#2a3b2a"  # Dark green for user
            align = Qt.AlignmentFlag.AlignRight
        elif role == "error":
            bg_color = "#4a2222"  # Dark red for errors
            align = Qt.AlignmentFlag.AlignLeft
        else:
            bg_color = "#333333"  # Dark gray for AI
            align = Qt.AlignmentFlag.AlignLeft

        # Timestamp label
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        ts_label = QtWidgets.QLabel(timestamp)
        ts_label.setStyleSheet(f"color:#888; font-size:8pt;")
        ts_label.setAlignment(align)
        layout.addWidget(ts_label)

        # Count lines for collapse decision
        lines = text.splitlines()

        if len(lines) > 3:
            # Long message – preview with toggle
            preview_text = "\n".join(lines[:3]) + "\n..."
            preview_label = QtWidgets.QLabel(preview_text)
            preview_label.setWordWrap(True)
            preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            preview_label.setStyleSheet(f"background-color:{bg_color}; padding:6px; border-radius:6px;")
            preview_label.setAlignment(align)
            preview_label.setFont(QtGui.QFont("", self.font_size))

            full_label = QtWidgets.QLabel(text)
            full_label.setWordWrap(True)
            full_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            full_label.setStyleSheet(f"background-color:{bg_color}; padding:6px; border-radius:6px;")
            full_label.setAlignment(align)
            full_label.setVisible(False)
            full_label.setFont(QtGui.QFont("", self.font_size))  # Font size updated immediately

            toggle_btn = QtWidgets.QPushButton("Show more")
            toggle_btn.setStyleSheet("font-size:8pt; color:#888;")
            toggle_btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

            def toggle(checked=False):
                if full_label.isVisible():
                    full_label.setVisible(False)
                    preview_label.setVisible(True)
                    toggle_btn.setText("Show more")
                else:
                    full_label.setVisible(True)
                    preview_label.setVisible(False)
                    toggle_btn.setText("Show less")

            toggle_btn.clicked.connect(toggle)

            layout.addWidget(preview_label)
            layout.addWidget(full_label)
            layout.addWidget(toggle_btn, alignment=align)
        else:
            # Short message – possibly bold for plain user text
            is_plain_user = role == "user" and not text.strip().startswith("```") and not text.strip().startswith("`")
            label = QtWidgets.QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            style = f"background-color:{bg_color}; padding:6px; border-radius:6px;"
            if is_plain_user:
                style += " font-weight: bold;"
            label.setStyleSheet(style)
            label.setAlignment(align)
            label.setFont(QtGui.QFont("", self.font_size))
            layout.addWidget(label)

        # Insert into list
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        self.chat_display.addItem(item)
        self.chat_display.setItemWidget(item, widget)
        # Add a visual separator after each message
        self._add_separator()
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
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #666;")

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

        # Add suggestion to chat display
        self._add_chat_item("ai", f"Suggestion: {suggestion}")

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

        # Add explanation to chat display
        self._add_chat_item("ai", f"Explanation: {explanation}")

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

        # Add custom response to chat display
        item = QtWidgets.QListWidgetItem(f"AI: {content}")
        item.setData(32, content)  # Store with UserRole flag
        self.chat_display.addItem(item)
        self.chat_display.scrollToBottom()

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
        """Handle history item click - quote/reply functionality."""
        # Check if item has stored data (new format)
        if item.data(32) is not None:  # UserRole = 32
            text = item.data(32)
            # Determine if it's a user or AI message by the prefix in display text
            display_text = item.text()
            if display_text.startswith("You:"):
                self.prompt_input.setPlainText(text)
            elif display_text.startswith("AI:"):
                # For AI responses, we might want to reply or quote
                self.prompt_input.insertPlainText(f"\n\n{text}")
        else:
            # Fallback for old format items (should not happen after update)
            text = item.text()
            if text.startswith("[+]"):  # Prompt entry - quote it
                num = text[3:].split("]")[0]
                prompt_text = text.split("] Prompt:")[1]
                self.prompt_input.setPlainText(f"[+] {num} {prompt_text}")
            elif "]" in text and "Prompt:" in text:  # Old format prompt entry
                num = text.split("]")[0][3:]
                prompt_text = text.split("] Prompt:")[1]
                self.prompt_input.setPlainText(f"[+] {num} {prompt_text}")
            elif "Response:" in text:  # Response entry - allow reply
                response_text = text.split("Response:")[1]
                self.prompt_input.insertPlainText(f"\n\nREPLY: {response_text}")

    def on_error(self, error_message):
        """Handle error signal"""
        # Add error to chat display
        item = QtWidgets.QListWidgetItem(f"Error: {error_message}")
        item.setData(32, error_message)  # Store with UserRole flag
        self.chat_display.addItem(item)
        self.chat_display.scrollToBottom()

        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setStyleSheet("color: #cc0000;")
        debug_print(f"[DEBUG] Error handled: {error_message}")
