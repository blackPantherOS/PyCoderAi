#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Panel for PyCoderAi
Provides a user interface for AI assistant features
"""

import sys
import os

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from Extensions_Qt6.AIAssistant import AIAssistant


class AIPanel(QtWidgets.QWidget):
    """
    AI Panel widget that provides AI assistant functionality
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.ai_assistant = AIAssistant(self)
        self.current_editor = None

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

        # Action buttons
        actions_layout = QtWidgets.QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self.suggest_btn = QtWidgets.QPushButton("Suggest")
        self.suggest_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/lightbulb.png")))
        self.suggest_btn.setToolTip("Get AI suggestions for code improvements")
        self.suggest_btn.setFixedWidth(120)
        actions_layout.addWidget(self.suggest_btn)

        self.explain_btn = QtWidgets.QPushButton("Explain")
        self.explain_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/about.png")))
        self.explain_btn.setToolTip("Get AI explanation of the code")
        self.explain_btn.setFixedWidth(120)
        actions_layout.addWidget(self.explain_btn)

        self.fix_btn = QtWidgets.QPushButton("Fix")
        self.fix_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/gear.png")))
        self.fix_btn.setToolTip("Get AI suggestions to fix errors")
        self.fix_btn.setFixedWidth(120)
        actions_layout.addWidget(self.fix_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/stop.png")))
        self.cancel_btn.setToolTip("Cancel current AI request")
        self.cancel_btn.setFixedWidth(120)
        self.cancel_btn.setEnabled(False)
        actions_layout.addWidget(self.cancel_btn)

        actions_layout.addStretch()

        main_layout.addLayout(actions_layout)

        # Model selection
        model_layout = QtWidgets.QHBoxLayout()
        model_layout.setContentsMargins(0, 0, 0, 0)

        model_layout.addWidget(QtWidgets.QLabel("Model:"))
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setMinimumWidth(200)
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()

        main_layout.addLayout(model_layout)

        # Prompt input area
        prompt_label = QtWidgets.QLabel("Prompt:")
        prompt_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(prompt_label)

        self.prompt_input = QtWidgets.QTextEdit()
        self.prompt_input.setPlaceholderText("Enter your question or request for the AI...")
        self.prompt_input.setStyleSheet("background-color: #252526; color: #ffffff; font-family: 'Courier New', monospace;")
        self.prompt_input.setMaximumHeight(80)
        self.prompt_input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.prompt_input)

        # Send button
        send_layout = QtWidgets.QHBoxLayout()
        send_layout.setContentsMargins(0, 0, 0, 0)

        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.setIcon(QtGui.QIcon(self._resource_path("Resources/images/flag-green.png")))
        self.send_btn.setToolTip("Send prompt to AI")
        self.send_btn.setFixedWidth(120)
        send_layout.addWidget(self.send_btn)
        send_layout.addStretch()
        main_layout.addLayout(send_layout)

        # Response area
        response_label = QtWidgets.QLabel("AI Response:")
        response_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(response_label)

        self.response_text = QtWidgets.QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setStyleSheet("background-color: #1e1e1e; color: #ffffff; font-family: 'Courier New', monospace;")
        self.response_text.setMinimumHeight(50)
        self.response_text.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.response_text)

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

        self.ai_assistant.suggestion_ready.connect(self.on_suggestion_ready)
        self.ai_assistant.explanation_ready.connect(self.on_explanation_ready)
        self.ai_assistant.error_occurred.connect(self.on_error)

        # Set icon theme based on system theme
        self.update_icon_theme()

        # Load models after connections are set up
        self.load_models()

    def load_models(self):
        """Load available AI models"""
        models = self.ai_assistant.get_available_models()
        if models:
            self.model_combo.clear()
            self.model_combo.addItems(models)
            # Try to select the default model
            default_model = "claude-3-5-sonnet-20241022"
            if default_model in models:
                self.model_combo.setCurrentText(default_model)
            else:
                self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.clear()
            self.model_combo.addItem("claude-3-5-sonnet-20241022")

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
        if not self.current_editor:
            QtWidgets.QMessageBox.warning(self, "AI Assistant", "No active editor!")
            return

        # Get custom prompt
        prompt_text = self.prompt_input.toPlainText()
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
        else:
            # Combine code and prompt
            full_prompt = f"Code:\n{code}\n\nPrompt:\n{prompt_text}"

        self.start_ai_request("custom", full_prompt)

    def start_ai_request(self, request_type, code):
        """Start an AI request"""
        # Update UI
        self.suggest_btn.setEnabled(False)
        self.explain_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.busy_indicator.setVisible(True)
        self.status_label.setText("Processing...")
        self.status_label.setStyleSheet("color: #0066cc;")
        self.response_text.clear()

        # Update model
        current_model = self.model_combo.currentText()
        if current_model:
            self.ai_assistant.selected_model = current_model


        # Make the request
        try:
            if request_type == "suggestion":
                self.ai_assistant.generate_code_suggestions(code)
            elif request_type == "explanation":
                self.ai_assistant.explain_code(code)
            elif request_type == "fix":
                self.ai_assistant.fix_code_errors(code)
            elif request_type == "custom":
                # For custom prompts, use explanation method but with custom prompt
                self.ai_assistant.explain_code(code)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.on_error(f"Error starting AI: {str(e)}")

    def on_suggestion_ready(self, suggestion):
        """Handle suggestion ready signal"""
        self.response_text.setPlainText(suggestion)
        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Suggestion ready")
        self.status_label.setStyleSheet("color: #009900;")

    def on_explanation_ready(self, explanation):
        """Handle explanation ready signal"""
        self.response_text.setPlainText(explanation)
        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Explanation ready")
        self.status_label.setStyleSheet("color: #009900;")

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

    def start_ai_request(self, request_type, code):
        """Start an AI request"""
        # Update UI
        self.suggest_btn.setEnabled(False)
        self.explain_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.busy_indicator.setVisible(True)
        self.status_label.setText("Processing...")
        self.status_label.setStyleSheet("color: #0066cc;")
        self.response_text.clear()

        # Update model
        self.ai_assistant.selected_model = self.model_combo.currentText()

        # Make the request
        if request_type == "suggestion":
            self.ai_assistant.generate_code_suggestions(code)
        elif request_type == "explanation":
            self.ai_assistant.explain_code(code)
        elif request_type == "fix":
            self.ai_assistant.fix_code_errors(code)

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

    def on_suggestion_ready(self, suggestion):
        """Handle suggestion ready signal"""
        self.response_text.setPlainText(suggestion)
        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Suggestion ready")
        self.status_label.setStyleSheet("color: #009900;")

    def on_explanation_ready(self, explanation):
        """Handle explanation ready signal"""
        self.response_text.setPlainText(explanation)
        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText("Explanation ready")
        self.status_label.setStyleSheet("color: #009900;")

    def on_error(self, error_message):
        """Handle error signal"""
        self.response_text.setPlainText(f"Error: {error_message}")
        self.suggest_btn.setEnabled(True)
        self.explain_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.busy_indicator.setVisible(False)
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setStyleSheet("color: #cc0000;")
