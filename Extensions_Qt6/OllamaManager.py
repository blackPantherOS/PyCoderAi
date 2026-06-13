#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama Manager for PyCoderAi
Monitors Ollama status, manages models, handles installation and service control.
Shows hardware info and recommends suitable models.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time

from PyQt6 import QtCore, QtGui, QtWidgets
try:
    import requests as _requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False


# ── Hardware tier definitions ───────────────────────────────────────────

SMALL_MODELS = [
    {"name": "qwen2.5-coder:1.5b",    "size_gb": 1.0, "desc": "Lightweight code model, good for quick suggestions"},
    {"name": "codegemma:2b",          "size_gb": 1.3, "desc": "Google code model, fast and compact"},
    {"name": "phi3:mini",             "size_gb": 2.2, "desc": "Microsoft Phi-3, strong on logic"},
]

MEDIUM_MODELS = [
    {"name": "deepseek-coder:6.7b",   "size_gb": 3.6, "desc": "Excellent code generation & infilling"},
    {"name": "qwen2.5-coder:7b",      "size_gb": 4.0, "desc": "Qwen code model, good all-rounder"},
    {"name": "codegemma:7b",          "size_gb": 4.1, "desc": "Google mid-size code model"},
    {"name": "llama3.1:8b",           "size_gb": 4.6, "desc": "Meta Llama 3.1, general purpose"},
    {"name": "deepseek-r1:7b",        "size_gb": 4.2, "desc": "DeepSeek R1 with reasoning ability"},
]

LARGE_MODELS = [
    {"name": "deepseek-r1:8b",        "size_gb": 4.9, "desc": "DeepSeek R1 8B with chain-of-thought"},
    {"name": "qwen3:8b",              "size_gb": 4.8, "desc": "Qwen 3, latest generation code model"},
    {"name": "gemma4:9b",             "size_gb": 5.2, "desc": "Google Gemma 4, strong multilingual"},
    {"name": "codellama:13b",         "size_gb": 7.3, "desc": "Meta Code Llama 13B, deep code understanding"},
]


class OllamaManager(QtWidgets.QWidget):
    """
    Manages Ollama installation, service control, model management,
    hardware detection, and model recommendations.
    """

    # Signal emitted when the status changes (for external UI updates)
    status_changed = QtCore.pyqtSignal(str)  # "running" | "stopped" | "not_installed"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ollama_running = False
        self._ollama_installed = False
        self._ollama_version = ""
        self._installed_models = []
        self._hardware = {}  # filled by _detect_hardware()

        # Detection results
        self._detect_hardware()

        # Build UI
        self.init_ui()

        # Start periodic status check
        self._status_timer = QtCore.QTimer(self)
        self._status_timer.timeout.connect(self._check_status)
        self._status_timer.start(30000)  # every 30 seconds

        # Initial check
        QtCore.QTimer.singleShot(100, self._check_status)

    # ── Hardware detection ──────────────────────────────────────────────

    def _detect_hardware(self):
        """Detect RAM, CPU cores, GPU info."""
        ram_gb = 0
        cpu_cores = 0
        gpu_info = []

        # RAM
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_kb = int(line.split()[1])
                        ram_gb = mem_kb / (1024 * 1024)
                        break
        except (OSError, ValueError):
            ram_gb = 0

        # CPU cores
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("processor"):
                        cpu_cores += 1
        except OSError:
            cpu_cores = 0
        if cpu_cores == 0:
            cpu_cores = os.cpu_count() or 2

        # GPU (nvidia)
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        gpu_info.append(f"{parts[0]} ({parts[1]} MB)")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # GPU (AMD via lspci)
        if not gpu_info:
            try:
                result = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "VGA" in line and ("AMD" in line or "ATI" in line or
                                          "Intel" in line or "NVIDIA" in line):
                        name = line.split(":", 2)[-1].strip() if ":" in line else line.strip()
                        gpu_info.append(name)
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

        # Check for Ollama GPU support indicator
        has_cuda = False
        try:
            result = subprocess.run(
                ["nvidia-smi"], capture_output=True, text=True, timeout=5
            )
            has_cuda = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        self._hardware = {
            "ram_gb": round(ram_gb, 1),
            "cpu_cores": cpu_cores,
            "gpu": gpu_info if gpu_info else ["None detected"],
            "has_cuda": has_cuda,
        }

    # ── Status checks ──────────────────────────────────────────────────

    def _check_status(self):
        """Check if Ollama is running and get version/installed models."""
        # Check installed by looking for the ollama binary
        installed = self._find_ollama()
        self._ollama_installed = installed is not None

        if not self._ollama_installed:
            self._ollama_running = False
            self._ollama_version = ""
            self._update_status_ui()
            self.status_changed.emit("not_installed")
            return

        # Get version
        try:
            result = subprocess.run(
                [installed, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                self._ollama_version = result.stdout.strip() or result.stderr.strip()
        except (subprocess.TimeoutExpired, OSError):
            self._ollama_version = ""

        # Check if running by hitting the API
        running = self._is_ollama_running()
        self._ollama_running = running
        self._update_status_ui()
        self.status_changed.emit("running" if running else "stopped")

        # Fetch installed models if running
        if running:
            self._fetch_installed_models()

    def _find_ollama(self):
        """Locate the ollama binary. Returns path or None."""
        common_paths = [
            "/usr/bin/ollama",
            "/usr/local/bin/ollama",
            os.path.expanduser("~/.local/bin/ollama"),
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        # Try PATH
        try:
            result = subprocess.run(["which", "ollama"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    def _is_ollama_running(self):
        """Check if Ollama server responds on the default port."""
        if not HAVE_REQUESTS:
            # Fallback: use subprocess
            try:
                result = subprocess.run(
                    ["pgrep", "-x", "ollama"], capture_output=True, timeout=5
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                return False
        try:
            resp = _requests.get("http://localhost:11434/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def _fetch_installed_models(self):
        """Populate self._installed_models from Ollama API."""
        self._installed_models = []
        if not HAVE_REQUESTS:
            return
        try:
            resp = _requests.get("http://localhost:11434/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            for m in data.get("models", []):
                name = m.get("name", m.get("model", "unknown"))
                size_bytes = m.get("size", 0)
                size_gb = round(size_bytes / (1024**3), 2) if size_bytes else 0
                self._installed_models.append({"name": name, "size_gb": size_gb})
        except Exception:
            pass
        self._update_models_ui()

    # ── Service control (sudo) ─────────────────────────────────────────

    def _run_sudo_command(self, cmd: str, desc: str) -> str:
        """Run a command with sudo and return combined output."""
        full_cmd = f"sudo {cmd}"
        self._append_terminal(f"$ {full_cmd}\n")
        self._settings_terminal.setVisible(True)
        QtWidgets.QApplication.processEvents()
        try:
            result = subprocess.run(
                full_cmd, shell=True, capture_output=True, text=True, timeout=120
            )
            output = result.stdout + result.stderr
            self._append_terminal(output + "\n")
            if result.returncode != 0:
                self._append_terminal(
                    f"[ERROR] Command failed (exit code {result.returncode})\n"
                )
            return output
        except subprocess.TimeoutExpired:
            msg = f"[ERROR] Command timed out: {full_cmd}\n"
            self._append_terminal(msg)
            return msg
        except Exception as e:
            msg = f"[ERROR] {e}\n"
            self._append_terminal(msg)
            return msg

    def _start_ollama(self):
        self._run_sudo_command("systemctl start ollama", "Start Ollama")
        QtCore.QTimer.singleShot(2000, self._check_status)

    def _stop_ollama(self):
        self._run_sudo_command("systemctl stop ollama", "Stop Ollama")
        QtCore.QTimer.singleShot(2000, self._check_status)

    def _restart_ollama(self):
        self._run_sudo_command("systemctl restart ollama", "Restart Ollama")
        QtCore.QTimer.singleShot(3000, self._check_status)

    def _install_ollama(self):
        """Download and install Ollama via official script."""
        script_url = "https://ollama.com/install.sh"
        self._append_terminal(f"$ curl -fsSL {script_url} | sudo sh\n")
        self._settings_terminal.setVisible(True)
        cmd = f"curl -fsSL {script_url} | sudo sh"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300
            )
            output = result.stdout + result.stderr
            self._append_terminal(output + "\n")
            if result.returncode == 0:
                self._append_terminal("[OK] Ollama installed successfully.\n")
            else:
                self._append_terminal(
                    f"[ERROR] Installation failed (exit code {result.returncode})\n"
                )
        except subprocess.TimeoutExpired:
            self._append_terminal("[ERROR] Installation timed out.\n")
        except Exception as e:
            self._append_terminal(f"[ERROR] {e}\n")
        QtCore.QTimer.singleShot(2000, self._check_status)

    # ── Model operations ───────────────────────────────────────────────

    def _pull_model(self, model_name: str):
        """Pull a model with real-time progress."""
        self._set_pull_buttons_enabled(False)
        self._pull_progress.setVisible(True)
        self._pull_progress.setValue(0)
        self._pull_status.setText(f"Pulling {model_name}...")
        QtWidgets.QApplication.processEvents()

        def pull_thread():
            try:
                proc = subprocess.Popen(
                    ["ollama", "pull", model_name],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )
                progress_pat = re.compile(r'(\d+)%')
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    self._append_terminal(line)
                    # Parse streaming progress
                    m = progress_pat.search(line)
                    if m:
                        pct = int(m.group(1))
                        self._pull_progress.setValue(pct)
                proc.wait()
                success = proc.returncode == 0
                if success:
                    self._pull_progress.setValue(100)
                    self._pull_status.setText(f"{model_name} downloaded successfully.")
                else:
                    self._pull_status.setText(f"Failed to pull {model_name}.")
                QtCore.QMetaObject.invokeMethod(
                    self, "_on_pull_finished", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(bool, success)
                )
            except Exception as e:
                self._append_terminal(f"[ERROR] {e}\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_on_pull_finished", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(bool, False)
                )

        threading.Thread(target=pull_thread, daemon=True).start()

    @QtCore.pyqtSlot(bool)
    def _on_pull_finished(self, success: bool):
        """Called after pull completes (in GUI thread)."""
        self._set_pull_buttons_enabled(True)
        if success:
            QtCore.QTimer.singleShot(1000, self._fetch_installed_models)
        QtCore.QTimer.singleShot(5000, lambda: self._pull_progress.setVisible(False))

    def _remove_model(self, model_name: str):
        """Remove a model via ollama rm."""
        self._append_terminal(f"$ ollama rm {model_name}\n")
        try:
            result = subprocess.run(
                ["ollama", "rm", model_name], capture_output=True, text=True, timeout=60
            )
            output = result.stdout + result.stderr
            self._append_terminal(output + "\n")
        except Exception as e:
            self._append_terminal(f"[ERROR] {e}\n")
        self._fetch_installed_models()

    def _set_pull_buttons_enabled(self, enabled: bool):
        """Enable/disable all pull buttons."""
        for btn in self._pull_buttons:
            btn.setEnabled(enabled)

    # ── UI Construction ─────────────────────────────────────────────────

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        tab_widget = QtWidgets.QTabWidget()

        # ── Tab 1: Status ──
        status_widget = self._build_status_tab()
        tab_widget.addTab(status_widget, _("Status"))

        # ── Tab 2: Models ──
        models_widget = self._build_models_tab()
        tab_widget.addTab(models_widget, _("Models"))

        # ── Tab 3: Settings ──
        settings_widget = self._build_settings_tab()
        tab_widget.addTab(settings_widget, _("Settings"))

        layout.addWidget(tab_widget)

    def _build_status_tab(self):
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)
        vbox.setSpacing(8)

        # Status card
        status_group = QtWidgets.QGroupBox(_("Ollama Status"))
        sg = QtWidgets.QFormLayout(status_group)
        sg.setSpacing(6)

        self.status_indicator = QtWidgets.QLabel(_("🔴 Checking..."))
        self.status_indicator.setStyleSheet("font-size: 14pt; font-weight: bold;")
        sg.addRow(_("Status:"), self.status_indicator)

        self.version_label = QtWidgets.QLabel("—")
        sg.addRow(_("Version:"), self.version_label)

        self.model_count_label = QtWidgets.QLabel("—")
        sg.addRow(_("Installed models:"), self.model_count_label)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton(_("Start"))
        self.btn_start.clicked.connect(self._start_ollama)
        btn_row.addWidget(self.btn_start)

        self.btn_stop = QtWidgets.QPushButton(_("Stop"))
        self.btn_stop.clicked.connect(self._stop_ollama)
        btn_row.addWidget(self.btn_stop)

        self.btn_restart = QtWidgets.QPushButton(_("Restart"))
        self.btn_restart.clicked.connect(self._restart_ollama)
        btn_row.addWidget(self.btn_restart)

        self.btn_refresh = QtWidgets.QPushButton(_("Refresh"))
        self.btn_refresh.clicked.connect(self._check_status)
        btn_row.addWidget(self.btn_refresh)

        btn_row.addStretch()
        sg.addRow("", btn_row)
        vbox.addWidget(status_group)

        # Hardware card
        hw_group = QtWidgets.QGroupBox(_("Hardware"))
        hw_form = QtWidgets.QFormLayout(hw_group)
        hw_form.setSpacing(6)

        ram = self._hardware.get("ram_gb", 0)
        hw_form.addRow(_("RAM:"), QtWidgets.QLabel(f"{ram} GB"))

        cores = self._hardware.get("cpu_cores", 0)
        hw_form.addRow(_("CPU Cores:"), QtWidgets.QLabel(str(cores)))

        gpu_list = self._hardware.get("gpu", ["None"])
        hw_form.addRow(_("GPU:"), QtWidgets.QLabel("\n".join(gpu_list)))

        recommended_tier = self._get_recommended_tier()
        tier_label = {
            "small": _("Small models (≤3 GB)"),
            "medium": _("Medium models (3-5 GB)"),
            "large": _("Large models (5+ GB)"),
        }.get(recommended_tier, _("Unknown"))

        self.tier_label = QtWidgets.QLabel(tier_label)
        hw_form.addRow(_("Recommended:"), self.tier_label)

        vbox.addWidget(hw_group)
        vbox.addStretch()
        return widget

    def _build_models_tab(self):
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)
        vbox.setSpacing(8)

        # ── Installed models ──
        installed_group = QtWidgets.QGroupBox(_("Installed Models"))
        ig = QtWidgets.QVBoxLayout(installed_group)
        self.installed_list = QtWidgets.QListWidget()
        ig.addWidget(self.installed_list)
        vbox.addWidget(installed_group)

        # ── Recommended models ──
        rec_group = QtWidgets.QGroupBox(_("Recommended Models"))
        rg = QtWidgets.QVBoxLayout(rec_group)

        self.recommended_table = QtWidgets.QTableWidget()
        self.recommended_table.setColumnCount(4)
        self.recommended_table.setHorizontalHeaderLabels([
            _("Model"), _("Size"), _("Tier"), _("Action")
        ])
        self.recommended_table.horizontalHeader().setStretchLastSection(False)
        self.recommended_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.recommended_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.recommended_table.verticalHeader().setVisible(False)
        rg.addWidget(self.recommended_table)

        # Progress bar for pulls
        self._pull_progress = QtWidgets.QProgressBar()
        self._pull_progress.setVisible(False)
        rg.addWidget(self._pull_progress)

        self._pull_status = QtWidgets.QLabel("")
        self._pull_status.setStyleSheet("color: #888; font-size: 9pt;")
        rg.addWidget(self._pull_status)

        vbox.addWidget(rec_group)

        # Populate recommended models
        self._populate_recommended()
        return widget

    def _build_settings_tab(self):
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)
        vbox.setSpacing(8)

        # Installation
        install_group = QtWidgets.QGroupBox(_("Installation"))
        ig = QtWidgets.QVBoxLayout(install_group)

        install_desc = QtWidgets.QLabel(
            _("Ollama can run fully offline. Install it using the official script below.\n"
              "Requires sudo (root) access. Models are downloaded separately via the Models tab.")
        )
        install_desc.setWordWrap(True)
        ig.addWidget(install_desc)

        install_btn = QtWidgets.QPushButton(_("Install Ollama"))
        install_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "border-radius: 4px; padding: 8px; font-weight: bold; }"
        )
        install_btn.clicked.connect(self._install_ollama)
        ig.addWidget(install_btn)

        vbox.addWidget(install_group)

        # Service control
        svc_group = QtWidgets.QGroupBox(_("Service Control"))
        svg = QtWidgets.QVBoxLayout(svc_group)
        svc_help = QtWidgets.QLabel(
            _("Start/Stop/Restart the Ollama service. Requires sudo access.")
        )
        svc_help.setWordWrap(True)
        svg.addWidget(svc_help)

        svc_btn_row = QtWidgets.QHBoxLayout()
        start_btn = QtWidgets.QPushButton(_("Start"))
        start_btn.clicked.connect(self._start_ollama)
        svc_btn_row.addWidget(start_btn)

        stop_btn = QtWidgets.QPushButton(_("Stop"))
        stop_btn.clicked.connect(self._stop_ollama)
        svc_btn_row.addWidget(stop_btn)

        restart_btn = QtWidgets.QPushButton(_("Restart"))
        restart_btn.clicked.connect(self._restart_ollama)
        svc_btn_row.addWidget(restart_btn)

        svc_btn_row.addStretch()
        svg.addLayout(svc_btn_row)
        vbox.addWidget(svc_group)

        # Terminal output
        terminal_group = QtWidgets.QGroupBox(_("Terminal Output"))
        tg = QtWidgets.QVBoxLayout(terminal_group)
        self._settings_terminal = QtWidgets.QTextEdit()
        self._settings_terminal.setReadOnly(True)
        self._settings_terminal.setStyleSheet(
            "background-color: #1a1a1a; color: #00ff00; font-family: 'Courier New', monospace; font-size: 9pt;"
        )
        self._settings_terminal.setMinimumHeight(120)
        self._settings_terminal.setVisible(False)
        tg.addWidget(self._settings_terminal)

        clear_term_btn = QtWidgets.QPushButton(_("Clear Output"))
        clear_term_btn.clicked.connect(self._settings_terminal.clear)
        tg.addWidget(clear_term_btn)

        vbox.addWidget(terminal_group)
        vbox.addStretch()
        return widget

    # ── UI updates ─────────────────────────────────────────────────────

    def _update_status_ui(self):
        """Update the status tab labels based on current state."""
        if not self._ollama_installed:
            self.status_indicator.setText(_("🟡 Not installed"))
            self.status_indicator.setStyleSheet(
                "font-size: 14pt; font-weight: bold; color: #ffaa00;"
            )
            self.version_label.setText("—")
            self.model_count_label.setText("—")
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_restart.setEnabled(False)
        elif self._ollama_running:
            self.status_indicator.setText(_("🟢 Running"))
            self.status_indicator.setStyleSheet(
                "font-size: 14pt; font-weight: bold; color: #00cc00;"
            )
            self.version_label.setText(self._ollama_version)
            self.model_count_label.setText(str(len(self._installed_models)))
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.btn_restart.setEnabled(True)
        else:
            self.status_indicator.setText(_("🔴 Stopped"))
            self.status_indicator.setStyleSheet(
                "font-size: 14pt; font-weight: bold; color: #cc0000;"
            )
            self.version_label.setText(self._ollama_version or _("Not running"))
            self.model_count_label.setText("—")
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.btn_restart.setEnabled(True)

    def _update_models_ui(self):
        """Update the installed models list."""
        self.installed_list.clear()
        if not self._installed_models:
            self.installed_list.addItem(_("No models installed"))
            return

        for m in self._installed_models:
            size_str = f" ({m['size_gb']} GB)" if m['size_gb'] else ""

            # Add remove button
            btn = QtWidgets.QPushButton(_("Remove"))
            btn.setFixedWidth(80)
            btn.clicked.connect(
                lambda checked, name=m['name']: self._remove_model(name)
            )

            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QtWidgets.QLabel(f"  {m['name']}{size_str}"))
            row_layout.addStretch()
            row_layout.addWidget(btn)

            list_item = QtWidgets.QListWidgetItem()
            list_item.setSizeHint(row_widget.sizeHint())
            self.installed_list.addItem(list_item)
            self.installed_list.setItemWidget(list_item, row_widget)

        self.model_count_label.setText(str(len(self._installed_models)))

    def _populate_recommended(self):
        """Fill the recommended models table based on hardware tier."""
        tier = self._get_recommended_tier()
        if tier == "small":
            models = SMALL_MODELS
        elif tier == "medium":
            models = MEDIUM_MODELS
        else:
            models = LARGE_MODELS

        # Also include the adjacent tier for variety
        if tier == "small":
            models = SMALL_MODELS + MEDIUM_MODELS[:2]
        elif tier == "medium":
            models = MEDIUM_MODELS + SMALL_MODELS[:2] + LARGE_MODELS[:1]
        else:
            models = LARGE_MODELS + MEDIUM_MODELS[:2]

        self.recommended_table.setRowCount(len(models))
        self._pull_buttons = []

        tier_keys = {"small": _("Small"), "medium": _("Medium"), "large": _("Large")}
        for row, m in enumerate(models):
            self.recommended_table.setItem(row, 0, QtWidgets.QTableWidgetItem(m["name"]))
            self.recommended_table.setItem(
                row, 1, QtWidgets.QTableWidgetItem(f"{m['size_gb']} GB")
            )

            # Determine tier label for this model
            if m in SMALL_MODELS:
                tier_label = tier_keys["small"]
            elif m in MEDIUM_MODELS:
                tier_label = tier_keys["medium"]
            else:
                tier_label = tier_keys["large"]
            self.recommended_table.setItem(row, 2, QtWidgets.QTableWidgetItem(tier_label))

            # Pull button
            btn = QtWidgets.QPushButton(_("Pull"))
            btn.setStyleSheet(
                "QPushButton { background-color: #0066cc; color: white; "
                "border-radius: 3px; padding: 4px; }"
            )
            btn.clicked.connect(lambda checked, name=m["name"]: self._pull_model(name))
            self.recommended_table.setCellWidget(row, 3, btn)
            self._pull_buttons.append(btn)

    def _get_recommended_tier(self):
        """Determine the recommended model size tier based on available RAM."""
        ram = self._hardware.get("ram_gb", 0)
        has_gpu = self._hardware.get("has_cuda", False)
        if has_gpu and ram >= 16:
            return "large"
        elif has_gpu and ram >= 8:
            return "medium"
        elif ram >= 12:
            return "medium"
        elif ram >= 6:
            return "small"
        else:
            return "small"

    def _append_terminal(self, text: str):
        """Append text to the terminal output widget."""
        self._settings_terminal.moveCursor(
            QtGui.QTextCursor.MoveOperation.End
        )
        self._settings_terminal.insertPlainText(text)
        self._settings_terminal.verticalScrollBar().setValue(
            self._settings_terminal.verticalScrollBar().maximum()
        )

    # ── Public API ─────────────────────────────────────────────────────

    def is_ollama_running(self) -> bool:
        """Convenience: check if Ollama is currently running."""
        return self._ollama_running

    def get_hardware(self) -> dict:
        """Return detected hardware info dict."""
        return dict(self._hardware)

    def refresh(self):
        """Force a status refresh."""
        self._detect_hardware()
        self._check_status()
