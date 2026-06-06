#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Settings Module for PyCoderAi
Provides configuration for AI assistant features
"""

from PyQt6 import QtCore, QtGui, QtWidgets


class AISettings(QtWidgets.QWidget):
    """
    AI Settings widget for configuring AI assistant
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # AI Settings Group
        ai_group = QtWidgets.QGroupBox("AI Assistant Settings")
        ai_group.setStyleSheet("font-weight: bold;")
        ai_layout = QtWidgets.QVBoxLayout()
        ai_group.setLayout(ai_layout)

        # API Selection
        api_layout = QtWidgets.QHBoxLayout()
        api_layout.addWidget(QtWidgets.QLabel("API Provider:"))
        self.api_combo = QtWidgets.QComboBox()
        self.api_combo.addItems(["Demo Mode", "Free-Claude-Code", "Anthropic API", "Ollama"])
        self.api_combo.currentIndexChanged.connect(self.on_api_changed)
        api_layout.addWidget(self.api_combo)
        api_layout.addStretch()
        ai_layout.addLayout(api_layout)

        # API Key
        self.api_key_layout = QtWidgets.QHBoxLayout()
        self.api_key_label = QtWidgets.QLabel("API Key:")
        self.api_key_layout.addWidget(self.api_key_label)
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.api_key_layout.addWidget(self.api_key_edit)
        self.api_key_layout.addStretch()
        ai_layout.addLayout(self.api_key_layout)

        # API Base URL
        self.api_url_layout = QtWidgets.QHBoxLayout()
        self.api_url_label = QtWidgets.QLabel("API Base URL:")
        self.api_url_layout.addWidget(self.api_url_label)
        self.api_url_edit = QtWidgets.QLineEdit()
        self.api_url_layout.addWidget(self.api_url_edit)
        self.api_url_layout.addStretch()
        ai_layout.addLayout(self.api_url_layout)

        # Default Model
        model_layout = QtWidgets.QHBoxLayout()
        model_layout.addWidget(QtWidgets.QLabel("Default Model:"))
        self.model_combo = QtWidgets.QComboBox()
        # Add static models first
        self.model_combo.addItems([
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307"
        ])
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        ai_layout.addLayout(model_layout)

        # Performance settings
        perf_group = QtWidgets.QGroupBox("Performance Settings")
        perf_group.setStyleSheet("font-weight: bold;")
        perf_layout = QtWidgets.QVBoxLayout()
        perf_group.setLayout(perf_layout)

        # Timeout
        timeout_layout = QtWidgets.QHBoxLayout()
        timeout_layout.addWidget(QtWidgets.QLabel("Timeout (seconds):"))
        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(5, 60)  # Reduced range for faster responses
        self.timeout_spin.setValue(15)  # Default to 15 seconds for faster responses
        self.timeout_spin.setToolTip("Shorter timeout for faster responses")
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        perf_layout.addLayout(timeout_layout)

        # Enable caching
        cache_layout = QtWidgets.QHBoxLayout()
        self.cache_check = QtWidgets.QCheckBox("Enable response caching")
        self.cache_check.setToolTip("Cache responses to avoid duplicate requests")
        self.cache_check.setChecked(True)
        cache_layout.addWidget(self.cache_check)
        cache_layout.addStretch()
        perf_layout.addLayout(cache_layout)

        main_layout.addWidget(perf_group)

        main_layout.addWidget(ai_group)

        # Enable/disable fields based on API selection
        self.on_api_changed(self.api_combo.currentIndex())

    def on_api_changed(self, index):
        """Handle API provider selection change"""
        api_provider = self.api_combo.itemText(index)

        # Show/hide API key and URL fields
        if api_provider in ["Anthropic API", "Free-Claude-Code"]:
            self.api_key_edit.setVisible(True)
            self.api_key_label.setVisible(True)
            self.api_url_edit.setVisible(api_provider == "Free-Claude-Code")
            self.api_url_label.setVisible(api_provider == "Free-Claude-Code")
        else:
            self.api_key_edit.setVisible(False)
            self.api_key_label.setVisible(False)
            self.api_url_edit.setVisible(False)
            self.api_url_label.setVisible(False)

    def load_settings(self):
        """Load settings from configuration"""
        # Load saved settings or use defaults
        self.api_combo.setCurrentText(self.settings.get("ai_api_provider", "Ollama"))
        self.api_key_edit.setText(self.settings.get("ai_api_key", "freecc"))
        self.api_url_edit.setText(self.settings.get("ai_api_url", "http://localhost:8082"))

        # Set default model
        default_model = self.settings.get("ai_default_model", "ollama:llama3.1:8b")
        if default_model in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
            self.model_combo.setCurrentText(default_model)

        # Load performance settings
        self.timeout_spin.setValue(int(self.settings.get("ai_timeout", 15)))
        self.cache_check.setChecked(self.settings.get("ai_cache_enabled", True) == "True")

    def save_settings(self):
        """Save settings to configuration"""
        self.settings["ai_api_provider"] = self.api_combo.currentText()
        self.settings["ai_api_key"] = self.api_key_edit.text()
        self.settings["ai_api_url"] = self.api_url_edit.text()
        self.settings["ai_default_model"] = self.model_combo.currentText()
        self.settings["ai_timeout"] = str(self.timeout_spin.value())
        self.settings["ai_cache_enabled"] = str(self.cache_check.isChecked())
