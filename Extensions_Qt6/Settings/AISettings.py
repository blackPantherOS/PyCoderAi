#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Settings Module for PyCoderAi
Provides configuration for AI assistant features including cloud providers,
local models, and free/demo tiers.

Settings are persisted via the ``settings`` dict (useData.settings), which
gets saved to ``settings.conf`` by the caller.
"""

import json
import os

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    import requests as _requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False


# ── Known model catalog ───────────────────────────────────────────────
# Static fallback lists when the live API can't be reached.
CLAUDE_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "claude-4-5-sonnet-20260422",
]

OPENROUTER_FALLBACK = [
    "openrouter/anthropic/claude-3.5-sonnet",
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/meta-llama/llama-3.1-8b-instruct",
    "openrouter/mistralai/mistral-7b-instruct",
    "openrouter/qwen/qwen-2.5-7b-instruct",
]

OPENCODE_FALLBACK = [
    "anthropic/claude-3.5-sonnet",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
]

# ── Provider metadata ─────────────────────────────────────────────────
PROVIDER_URLS = {
    "ollama":       "http://localhost:11434",
    "anthropic":    "https://api.anthropic.com",
    "openrouter":   "https://openrouter.ai/api/v1",
    "opencode":     "https://api.opencode.ai/v1",
    "custom":       "http://localhost:8080",
    "demo":         "",
}

PROVIDER_LABELS = [
    "Ollama (local)",
    "Anthropic API",
    "OpenRouter",
    "OpenCode",
    "Custom OpenAI-compatible",
    "(Demo) Claude 3.5 Sonnet — free, limited",
]

# Internal keys (without UI label spaces / parens)
PROVIDER_KEYS = {
    "Ollama (local)": "ollama",
    "Anthropic API": "anthropic",
    "OpenRouter": "openrouter",
    "OpenCode": "opencode",
    "Custom OpenAI-compatible": "custom",
    "(Demo) Claude 3.5 Sonnet — free, limited": "demo",
}
_KEY_TO_LABEL = {v: k for k, v in PROVIDER_KEYS.items()}


class AISettings(QtWidgets.QWidget):
    """
    AI Settings widget for configuring AI assistant.

    Writes directly to the ``settings`` dict on every change (matching the
    pattern used by ``GeneralSettings``), so values are always in sync.
    The ``SettingsWidget`` dialog also calls ``save_settings()`` on accept
    to ensure nothing is lost.
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._ignore_save = False  # prevent cascading saves during setup

        self.init_ui()
        self._ignore_save = True
        self.load_settings()
        self._ignore_save = False

    # ── UI construction ───────────────────────────────────────────────

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # ── Connection group ──────────────────────────────────────
        conn_group = QtWidgets.QGroupBox("Connection")
        conn_group.setStyleSheet("font-weight: bold;")
        conn_layout = QtWidgets.QFormLayout(conn_group)
        conn_layout.setSpacing(6)

        # Provider
        prov_row = QtWidgets.QHBoxLayout()
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.addItems(PROVIDER_LABELS)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        prov_row.addWidget(self.provider_combo)

        self.refresh_btn = QtWidgets.QPushButton("Refresh Models")
        self.refresh_btn.setToolTip("Fetch available models from the selected provider")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        prov_row.addWidget(self.refresh_btn)
        prov_row.addStretch()
        conn_layout.addRow("API Provider:", prov_row)

        # API Key
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter your API key…")
        self.api_key_edit.textChanged.connect(self._mark_dirty)
        self.api_key_label = QtWidgets.QLabel("API Key:")
        conn_layout.addRow(self.api_key_label, self.api_key_edit)

        # API Base URL
        self.api_url_edit = QtWidgets.QLineEdit()
        self.api_url_edit.setPlaceholderText("http://localhost:8080")
        self.api_url_edit.textChanged.connect(self._mark_dirty)
        self.api_url_label = QtWidgets.QLabel("API Base URL:")
        conn_layout.addRow(self.api_url_label, self.api_url_edit)

        layout.addWidget(conn_group)

        # ── Model group ───────────────────────────────────────────
        model_group = QtWidgets.QGroupBox("Default Model")
        model_group.setStyleSheet("font-weight: bold;")
        model_layout = QtWidgets.QVBoxLayout(model_group)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)  # allow typing custom names
        self.model_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.model_combo.currentTextChanged.connect(self._mark_dirty)
        model_layout.addWidget(self.model_combo)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 9pt;")
        model_layout.addWidget(self.status_label)

        layout.addWidget(model_group)

        # ── Advanced group ────────────────────────────────────────
        adv_group = QtWidgets.QGroupBox("Advanced")
        adv_group.setStyleSheet("font-weight: bold;")
        adv_layout = QtWidgets.QFormLayout(adv_group)
        adv_layout.setSpacing(6)

        # Timeout
        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSuffix(" sec")
        self.timeout_spin.setValue(120)
        self.timeout_spin.setToolTip("Request timeout in seconds (increase if using USB storage)")
        self.timeout_spin.valueChanged.connect(self._mark_dirty)
        adv_layout.addRow("Timeout:", self.timeout_spin)

        # Cache
        self.cache_check = QtWidgets.QCheckBox("Enable response caching")
        self.cache_check.setToolTip("Cache responses to avoid duplicate requests")
        self.cache_check.toggled.connect(self._mark_dirty)
        adv_layout.addRow("", self.cache_check)

        # Auto-preload (Ollama only)
        self.auto_preload_check = QtWidgets.QCheckBox("Auto-preload model on startup")
        self.auto_preload_check.setToolTip(
            "Automatically load the last selected Ollama model into memory on startup"
        )
        self.auto_preload_check.toggled.connect(self._mark_dirty)
        adv_layout.addRow("", self.auto_preload_check)

        layout.addWidget(adv_group)
        layout.addStretch()

    # ── Event handlers ────────────────────────────────────────────────

    def _on_provider_changed(self, idx):
        """Update field visibility and URL default when provider changes."""
        label = self.provider_combo.currentText()
        provider = PROVIDER_KEYS.get(label, "ollama")

        # Hide all rows first, then selectively show
        self.api_key_label.setVisible(False)
        self.api_key_edit.setVisible(False)
        self.api_url_label.setVisible(False)
        self.api_url_edit.setVisible(False)

        if provider == "custom":
            self.api_key_label.setVisible(True)
            self.api_key_edit.setVisible(True)
            self.api_url_label.setVisible(True)
            self.api_url_edit.setVisible(True)
            # Restore saved URL or fallback to default
            saved = self.settings.get("ai_api_url", PROVIDER_URLS["custom"])
            self.api_url_edit.setText(saved)

        elif provider in ("anthropic", "openrouter", "opencode"):
            self.api_key_label.setVisible(True)
            self.api_key_edit.setVisible(True)
            # Set default URL (but don't show the URL field)
            if provider in PROVIDER_URLS:
                saved = self.settings.get("ai_api_url", PROVIDER_URLS[provider])
                self.api_url_edit.setText(saved)

        # Auto-preload is only meaningful for Ollama
        self.auto_preload_check.setVisible(provider == "ollama")

        self._mark_dirty()

    def _on_refresh_clicked(self):
        """Fetch available models from the selected provider."""
        label = self.provider_combo.currentText()
        provider = PROVIDER_KEYS.get(label, "ollama")

        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Fetching models...")
        QtWidgets.QApplication.processEvents()

        try:
            models = self._fetch_models(provider)
            if models:
                self._populate_model_combo(models)
                self.status_label.setText(f"Loaded {len(models)} models")
            else:
                self.status_label.setText("No models found — check connection / API key")
        except Exception as exc:
            self.status_label.setText(f"Error: {exc}")
        finally:
            self.refresh_btn.setEnabled(True)

    def _fetch_models(self, provider):
        """Return a list of model name strings for *provider*."""
        if provider == "ollama":
            return self._fetch_ollama_models()
        elif provider == "anthropic":
            return list(CLAUDE_MODELS)
        elif provider == "openrouter":
            return self._fetch_openai_compat_models(
                "https://openrouter.ai/api/v1/models",
                "openrouter",
                OPENROUTER_FALLBACK,
            )
        elif provider == "opencode":
            return self._fetch_openai_compat_models(
                "https://api.opencode.ai/v1/models",
                "opencode",
                OPENCODE_FALLBACK,
            )
        elif provider == "demo":
            return ["claude-3-5-sonnet-20241022"]
        else:
            return []

    def _fetch_ollama_models(self):
        """Query local Ollama for installed models."""
        try:
            import ollama
            result = ollama.list()
            # Support both official ollama (ListResponse) and ollama_wrapper (dict)
            if hasattr(result, "models"):
                models = [m.model for m in result.models]
            elif isinstance(result, dict):
                models = [m["name"] for m in result.get("models", [])]
            else:
                return []
            return sorted(models)
        except Exception:
            # Try the HTTP API directly as fallback
            return self._fetch_ollama_http()

    def _fetch_ollama_http(self):
        """Fallback: query Ollama via its HTTP API."""
        if not HAVE_REQUESTS:
            return []
        try:
            resp = _requests.get("http://localhost:11434/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return sorted(m["name"] for m in data.get("models", []))
        except Exception:
            return []

    def _fetch_openai_compat_models(self, url, provider, fallback):
        """Query an OpenAI-compatible models endpoint."""
        if not HAVE_REQUESTS:
            return list(fallback)
        api_key = self.settings.get("ai_api_key", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            resp = _requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Standard OpenAI format: { data: [ { id: "..." }, ... ] }
            items = data.get("data", [])
            if items and isinstance(items, list):
                return sorted(m["id"] for m in items if "id" in m)
            return list(fallback)
        except Exception:
            return list(fallback)

    def _populate_model_combo(self, models):
        """Replace model combo items, preserving current selection if possible."""
        current = self.model_combo.currentText()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models)
        # Restore selection if still available
        idx = self.model_combo.findText(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        elif models:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _mark_dirty(self):
        """Save settings on every change (unless suppressed during init)."""
        if not self._ignore_save:
            self.save_settings()

    # ── Persistence ───────────────────────────────────────────────────

    def load_settings(self):
        """Populate UI from the settings dict."""
        self._ignore_save = True

        # Provider
        raw_provider = self.settings.get("ai_api_provider", "ollama")
        label = _KEY_TO_LABEL.get(raw_provider, _KEY_TO_LABEL.get("ollama"))
        idx = self.provider_combo.findText(label)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self._on_provider_changed(idx)  # sync visibility

        # API key & URL
        self.api_key_edit.setText(self.settings.get("ai_api_key", ""))
        saved_url = self.settings.get("ai_api_url", "")
        if saved_url:
            self.api_url_edit.setText(saved_url)

        # Model
        saved_model = self.settings.get("ai_default_model", "")
        known_raw = self.settings.get("ai_known_models", "[]")
        try:
            known = json.loads(known_raw) if isinstance(known_raw, str) else known_raw
        except Exception:
            known = []
        if known:
            self._populate_model_combo(known)
        else:
            # Try a quick fetch (non-blocking for local Ollama)
            QtCore.QTimer.singleShot(100, self._on_refresh_clicked)

        if saved_model:
            idx = self.model_combo.findText(saved_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                # Custom model name — add it
                if self.model_combo.findText(saved_model) < 0:
                    self.model_combo.addItem(saved_model)
                self.model_combo.setCurrentText(saved_model)

        # Performance
        self.timeout_spin.setValue(int(self.settings.get("ai_timeout", 120)))
        self.cache_check.setChecked(self.settings.get("ai_cache_enabled", "True") == "True")
        self.auto_preload_check.setChecked(
            self.settings.get("ai_auto_preload", "False") == "True"
        )

        self._ignore_save = False

    def save_settings(self):
        """Write current UI state to the settings dict."""
        label = self.provider_combo.currentText()
        provider = PROVIDER_KEYS.get(label, "ollama")
        self.settings["ai_api_provider"] = provider
        self.settings["ai_api_key"] = self.api_key_edit.text().strip()
        self.settings["ai_api_url"] = self.api_url_edit.text().strip()
        self.settings["ai_default_model"] = self.model_combo.currentText().strip()
        self.settings["ai_timeout"] = str(self.timeout_spin.value())
        self.settings["ai_cache_enabled"] = str(self.cache_check.isChecked())
        self.settings["ai_auto_preload"] = str(self.auto_preload_check.isChecked())

        # Persist the current model list so we don't need to re-fetch next time
        known = [self.model_combo.itemText(i) for i in range(self.model_combo.count())]
        self.settings["ai_known_models"] = json.dumps(known)
