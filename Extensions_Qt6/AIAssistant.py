#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Assistant Module for PyCoderAi
Integrates with Claude API for code suggestions, explanations, and improvements
"""

import requests
import json
import gettext
import os
import time

# Internationalisation (gettext) support
# By default we just return the message unchanged; translators can bind this
# with a .mo file later if they want real translations.
def _(message: str) -> str:
    """Simple translation wrapper used throughout the project."""
    return message

# Debug logger – important events always written; verbose only when PYCODER_DEBUG_AI=1.
# This mirrors the copy in AIPanel.py so both files can log independently.
import datetime
DEBUG_AI = os.getenv("PYCODER_DEBUG_AI", "0") == "1"

def debug_print(message):
    """Append a debug line to DEBUG_LOG.md.
    Always writes messages containing ERROR, WARN, CHAIN, or FAIL.
    Other DEBUG messages only when PYCODER_DEBUG_AI=1."""
    is_critical = any(tag in message for tag in ["[ERROR", "[WARN", "[CHAIN", "[RESPONSE", "[USER", "FAIL", "ERROR SIGNAL"])
    if not DEBUG_AI and not is_critical:
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    try:
        with open("DEBUG_LOG.md", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception:
        print(message)

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import QToolTip

try:
    from anthropic import Anthropic, AnthropicError
except ImportError:
    Anthropic = None
    AnthropicError = Exception

try:
    # Try to import system ollama first
    import ollama
    # Test if Ollama server is running
    try:
        ollama.list()
    except Exception:
        ollama = None
except ImportError:
    try:
        # Fall back to embedded ollama wrapper
        from Extensions_Qt6.ollama_wrapper import OllamaWrapper
        ollama = OllamaWrapper()
        # Test if Ollama server is running
        try:
            ollama.list()
        except Exception:
            ollama = None
    except ImportError:
        ollama = None


# ── HardwareDetector: assess system resources for safe multi-model orchestration ──

class HardwareDetector:
    """Detect system hardware resources (RAM, VRAM) and select models
    that can safely run without causing out-of-memory crashes.

    Uses /proc/meminfo for RAM, optional nvidia-smi for GPU VRAM,
    and a hardcoded model-size table (sourced from ollama show / common knowledge)
    with fallback to ollama.list() for dynamic size discovery.
    """

    # Hardcoded size table for common Ollama models (in GB, approximate loaded RAM usage).
    # These are the actual size as reported by ollama list (quantized model),
    # NOT the parameter count — RAM usage at load time is ~1.2x this value.
    KNOWN_MODEL_SIZES = {
        # Code-focused models
        "codeqwen:7b": 3.9, "codeqwen:7b-code": 3.9,
        "codeqwen:14b": 7.5, "codeqwen:14b-code": 7.5,
        "codeqwen:34b": 18.5,
        "codellama:7b": 3.8, "codellama:7b-code": 3.8,
        "codellama:13b": 7.3, "codellama:13b-code": 7.3,
        "codellama:34b": 18.0,
        "qwen2.5-coder:1.5b": 1.1,
        "qwen2.5-coder:7b": 4.5,
        "qwen2.5-coder:14b": 8.2,
        "qwen2.5-coder:32b": 19.0,
        "deepseek-coder:6.7b": 4.2,
        "deepseek-coder:33b": 19.5,
        "stable-code:3b": 1.8,
        # General-purpose small models
        "gemma:2b": 1.6, "gemma2:2b": 1.6,
        "gemma:7b": 4.5, "gemma2:9b": 5.2,
        "phi:2.7b": 1.6, "phi3:3.8b": 2.2,
        "phi3:14b": 7.8,
        "mistral:7b": 4.1,
        "mixtral:8x7b": 25.0,
        "llama3:8b": 4.7,
        "llama3:70b": 38.0,
        "llama3.2:1b": 0.8,
        "llama3.2:3b": 2.0,
        "llama3.2:11b": 6.5,
        "tinyllama:1.1b": 0.7,
        "orca-mini:3b": 1.8,
        "orca-mini:7b": 4.0,
    }

    # Load overhead factor — at runtime a model uses ~1.2x its disk size in RAM
    LOAD_OVERHEAD = 1.2

    def __init__(self):
        self._total_ram = 0.0
        self._available_ram = 0.0
        self._gpu_vram = 0.0
        self._refresh_ram()
        self._refresh_gpu()

    def _refresh_ram(self):
        """Read /proc/meminfo for total and available RAM."""
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        self._total_ram = float(line.split()[1]) / (1024 * 1024)  # kB → GB
                    elif line.startswith("MemAvailable:"):
                        self._available_ram = float(line.split()[1]) / (1024 * 1024)
        except (FileNotFoundError, PermissionError, IndexError, ValueError):
            # Fallback: os.sysconf
            try:
                import os
                self._total_ram = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024**3)
                self._available_ram = self._total_ram * 0.4  # rough estimate
            except Exception:
                self._total_ram = 4.0
                self._available_ram = 2.0

    def _refresh_gpu(self):
        """Try to read GPU VRAM via nvidia-smi (best effort)."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # Take the first GPU's total VRAM in MiB, convert to GB
                first_line = result.stdout.strip().split("\n")[0].strip()
                self._gpu_vram = float(first_line) / 1024
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            self._gpu_vram = 0.0

    def get_total_ram_gb(self) -> float:
        return self._total_ram

    def get_available_ram_gb(self) -> float:
        return self._available_ram

    def get_gpu_vram_gb(self) -> float:
        return self._gpu_vram

    def get_model_size_gb(self, model_name: str) -> float:
        """Return estimated RAM usage for a model in GB.
        Looks up hardcoded table first, then tries ollama.list() for dynamic info.
        """
        # Strip 'ollama:' prefix if present
        name = model_name[7:] if model_name.startswith("ollama:") else model_name

        # 1. Check hardcoded table (lowercased key)
        key = name.lower().strip()
        if key in self.KNOWN_MODEL_SIZES:
            return self.KNOWN_MODEL_SIZES[key] * self.LOAD_OVERHEAD

        # 2. Try to get from ollama.list()
        if ollama is not None:
            try:
                result = ollama.list()
                if hasattr(result, 'models') and not isinstance(result, dict):
                    models_list = result.models or []
                elif isinstance(result, dict):
                    models_list = result.get('models', []) or []
                else:
                    models_list = list(result) if result else []
                for m in models_list:
                    if isinstance(m, dict):
                        m_name = m.get('model') or m.get('name') or ''
                        m_size = m.get('size', 0)
                    else:
                        m_name = getattr(m, 'model', None) or getattr(m, 'name', None) or ''
                        m_size = getattr(m, 'size', 0) or 0
                    if m_name == name and m_size:
                        disk_gb = m_size / (1024**3)
                        return disk_gb * self.LOAD_OVERHEAD
            except Exception:
                pass

        # 3. Fallback: rough estimate based on parameter count in name
        try:
            import re
            m = re.search(r'(\d+)b', name, re.IGNORECASE)
            if m:
                params_b = int(m.group(1))
                # Rough: N billion params * 2 bytes (fp16) + overhead
                return params_b * 2.2 * 0.7  # typical Q4 quant is ~0.7x fp16
        except Exception:
            pass

        return 3.0  # safe unknown default

    def can_load_model(self, model_name: str) -> bool:
        """Check if the model fits in available RAM (with safety margin)."""
        needed = self.get_model_size_gb(model_name)
        # Safety: leave at least 1 GB for the OS + PyCoder6
        safe_available = self._available_ram - 1.0
        result = needed <= safe_available
        if not result:
            print(f"[HardwareDetector] REJECTED {model_name}: need {needed:.1f} GB, "
                  f"only {safe_available:.1f} GB safely available")
        return result

    def model_exists_locally(self, model_name: str) -> bool:
        """Check if the model is actually pulled in the local Ollama install.
        Returns True if the model exists locally, False if unknown/not found."""
        name = model_name[7:] if model_name.startswith("ollama:") else model_name
        if ollama is None:
            return False
        try:
            result = ollama.list()
            if hasattr(result, 'models') and not isinstance(result, dict):
                models_list = result.models or []
            elif isinstance(result, dict):
                models_list = result.get('models', []) or []
            else:
                return False
            local_names = set()
            for m in models_list:
                if isinstance(m, dict):
                    m_name = m.get('model') or m.get('name') or ''
                else:
                    m_name = getattr(m, 'model', None) or getattr(m, 'name', None) or ''
                # Strip tag to get base name — ollama may return "qwen2.5-coder:1.5b" or "qwen2.5-coder:1.5b-q4_K_M"
                local_names.add(m_name)
            return name in local_names
        except Exception:
            return False

    def unload_model(self, model_name: str):
        """Tell Ollama to unload a model from memory.
        Sets keepalive=0 so the model process exits immediately.
        """
        name = model_name[7:] if model_name.startswith("ollama:") else model_name
        if ollama is not None and hasattr(ollama, 'keepalive'):
            try:
                ollama.keepalive(name, "0")
                print(f"[HardwareDetector] Unloaded model: {name}")
            except Exception as e:
                print(f"[HardwareDetector] Failed to unload {name}: {e}")

    def select_models_for_pipeline(self, preferred_coder: str = "",
                                   available_models: list = None) -> dict | None:
        """Select models for interpreter → coder → reviewer pipeline.
        Returns {interpreter: str, coder: str, reviewer: str} or None if insufficient resources.

        Strategy:
        - Find the smallest available model for interpreter (≤ 3 GB)
        - Use preferred_coder or next-smallest for coder
        - Use the same model for reviewer (avoids extra load)
        """
        if not available_models:
            return None

        # Parse models: keep only ollama models with size info
        ollama_models = []
        for m in available_models:
            is_ollama = m.startswith("ollama:")
            size = self.get_model_size_gb(m)
            ollama_models.append((m, size, is_ollama))

        if not ollama_models:
            return None

        # Sort by size
        ollama_models.sort(key=lambda x: x[1])

        # Find interpreter: smallest model ≤ 3 GB
        interpreter = None
        for m, size, _ in ollama_models:
            if size <= 3.0 and self.can_load_model(m):
                interpreter = m
                break
        if not interpreter and ollama_models:
            # Fallback: use the absolute smallest
            smallest = ollama_models[0]
            if self.can_load_model(smallest[0]):
                interpreter = smallest[0]

        if not interpreter:
            return None  # can't even run one small model

        # Determine coder: preferred_coder if available and fits, else next after interpreter
        coder = None
        if preferred_coder:
            pref_size = self.get_model_size_gb(preferred_coder)
            if self.can_load_model(preferred_coder):
                coder = preferred_coder

        if not coder:
            for m, size, _ in ollama_models:
                if m != interpreter and size >= 3.0 and self.can_load_model(m):
                    coder = m
                    break

        if not coder:
            # Use interpreter as coder (single-model fallback)
            coder = interpreter

        # Reviewer: same as interpreter (avoids extra memory load, and small models
        # are fine for checking import completeness and syntax)
        reviewer = interpreter

        return {
            "interpreter": interpreter,
            "coder": coder,
            "reviewer": reviewer,
        }

    def describe(self) -> str:
        """Human-readable hardware summary (for debug logging)."""
        parts = [f"RAM: {self._total_ram:.1f} GB total, {self._available_ram:.1f} GB available"]
        if self._gpu_vram > 0:
            parts.append(f"GPU VRAM: {self._gpu_vram:.1f} GB")
        else:
            parts.append("GPU: N/A (CPU only)")
        return " | ".join(parts)


class AIAssistant(QtCore.QObject):
    """
    AI Assistant class for interacting with Claude API
    """

    suggestion_ready = pyqtSignal(str)
    explanation_ready = pyqtSignal(str)
    preload_ready = pyqtSignal(str)
    custom_ready = pyqtSignal(str)  # New signal for custom prompts
    fix_ready = pyqtSignal(str)
    chain_ready = pyqtSignal(str)   # Final result from 3-model chain
    chain_status = pyqtSignal(str)  # Phase label for status bar
    error_occurred = pyqtSignal(str)
    stream_token = pyqtSignal(str)  # Relayed from worker thread for streaming

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_key = "freecc"  # Default key, can be changed via settings
        self.selected_model = "claude-3-5-sonnet-20241022"
        self.worker_thread = None
        self.use_anthropic_api = Anthropic is not None
        self.use_ollama = ollama is not None
        self.timeout = 120  # Default timeout in seconds (increased for USB storage latency)
        self.cache = {}  # Simple cache for responses
        self.cache_enabled = False  # Cache disabled by default
        self.api_base = "http://localhost:8082"  # Default API base URL
        self.api_provider = "ollama"  # Provider: ollama, anthropic, openrouter, opencode, custom, demo

        # Context window settings (Ollama num_ctx). Disabled by default = use model default.
        # When enabled, we pass num_ctx to Ollama + do smart truncation on our side.
        self.context_window_enabled = False
        self.context_window_size = 0   # 0 or "model default" means do not override num_ctx

    def set_api_config(self, base_url, api_key, model, timeout=120, cache_enabled=True, provider="ollama"):
        """Configure API settings"""
        self.api_base = base_url
        self.api_key = api_key
        self.selected_model = model
        self.timeout = timeout
        self.cache_enabled = cache_enabled
        self.api_provider = provider

    def set_language(self, lang_code):
        """Set the language for AI responses"""
        self.language = lang_code  # e.g. "Hungarian"

    def get_language(self):
        """Get user's preferred language for AI responses"""
        return getattr(self, 'language', 'Hungarian')

    def set_context_window(self, enabled: bool, size: int):
        """Enable/disable custom context window and set the size in tokens.
        size=0 or negative means "model default" (do not send num_ctx).
        """
        self.context_window_enabled = bool(enabled)
        self.context_window_size = int(size) if size and size > 0 else 0

    def _get_lang_instruction(self):
        """Return an output-language directive.
        The model prompt itself is always in English (for reliability across
        all models). Only the output language is controlled here.
        Uses a gentle tone — small models degrade if forced into a weak language.
        """
        lang = self.get_language()
        if lang and lang.lower() != "english":
            return (
                f"\n\nPlease respond in {lang}.\n"
                f"Code comments and variable names can stay in English.\n"
            )
        return ""

    def get_available_models(self, provider=None):
        """Fetch available models from the configured provider.
        If *provider* is None, uses ``self.api_provider``.
        Returns a list of model name strings (with provider prefix where applicable).
        """
        models = []
        provider = provider or self.api_provider

        if provider == "ollama":
            return self._get_ollama_models()
        elif provider == "anthropic":
            return [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
                "claude-4-5-sonnet-20260422",
            ]
        elif provider == "openrouter":
            return self._get_openai_compat_models(
                "https://openrouter.ai/api/v1/models",
                "openrouter:",
                [
                    "openrouter:anthropic/claude-3.5-sonnet",
                    "openrouter:anthropic/claude-3.5-haiku",
                    "openrouter:meta-llama/llama-3.1-8b-instruct",
                    "openrouter:mistralai/mistral-7b-instruct",
                    "openrouter:qwen/qwen-2.5-7b-instruct",
                ],
            )
        elif provider == "opencode":
            return self._get_openai_compat_models(
                "https://api.opencode.ai/v1/models",
                "opencode:",
                [
                    "opencode:anthropic/claude-3.5-sonnet",
                    "opencode:meta-llama/llama-3.1-8b-instruct",
                    "opencode:mistralai/mistral-7b-instruct",
                ],
            )
        elif provider == "custom":
            # Custom — editable combo; return saved list if available
            return []
        else:
            # Demo / fallback
            return [
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-haiku-20240307",
                "claude-3-sonnet-20240229"
            ]

    def _get_ollama_models(self):
        """Query local Ollama for installed models."""
        models = []
        if not self.use_ollama:
            return models
        try:
            print(f"[DEBUG] Fetching Ollama models...")
            result = ollama.list()
            # Support BOTH: official 'ollama' pip pkg (ListResponse with .models of Model objs)
            # and our ollama_wrapper (returns dict with 'models' list of dicts from /api/tags).
            if hasattr(result, 'models') and not isinstance(result, dict):
                ollama_models = result.models or []
            elif isinstance(result, dict):
                ollama_models = result.get('models', []) or []
            else:
                ollama_models = list(result) if result else []
            for model in ollama_models:
                if isinstance(model, dict):
                    model_name = model.get('model') or model.get('name') or str(model)
                    size = model.get('size', 0) or 0
                else:
                    # Official ollama.Model objects expose .model (and sometimes .name)
                    model_name = getattr(model, 'model', None) or getattr(model, 'name', None) or str(model)
                    size = getattr(model, 'size', 0) or 0
                if model_name:
                    entry = f"ollama:{model_name}"
                    if size:
                        try:
                            entry += f" ({size / (1024**3):.1f} GB)"
                        except Exception:
                            pass
                    models.append(entry)
                    print(f"[DEBUG] Found Ollama model: {model_name} (size attached: {bool(size)})")
        except Exception as e:
            print(f"[ERROR] Could not fetch Ollama models: {e}")
            import traceback
            traceback.print_exc()
        return models

    def _get_openai_compat_models(self, url, prefix, fallback):
        """Fetch models from an OpenAI-compatible API endpoint."""
        if not self.api_key:
            return list(fallback)
        try:
            import requests as _req
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = _req.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            if items and isinstance(items, list):
                return sorted(f"{prefix}{m['id']}" for m in items if "id" in m)
        except Exception:
            pass
        return list(fallback)

    def preload_model(self, model_name: str) -> bool:
        """Preload a model into memory to avoid cold start delays."""
        print(f"[DEBUG] PreloadModel called for: {model_name}")
        if self.worker_thread and self.worker_thread.isRunning():
            print("[DEBUG] Cancelling previous request")
            self.worker_thread.quit()
            self.worker_thread.wait()

        try:
            if model_name.startswith("ollama:"):
                model = model_name[7:]
                if self.use_ollama:
                    return ollama.preload_model(model)
            return False
        except Exception as e:
            print(f"[ERROR] Preload failed: {e}")
            return False

    def generate_code_suggestions(self, code, prompt=""):
        """Generate code suggestions using AI.
        Note: prompt already includes lang_inst from the caller (on_suggest_clicked).
        Do NOT append lang_inst here — that would duplicate it.
        """
        if not prompt:
            task = ("Analyze the code below. If there is a traceback, find the bug that causes it. "
                    "Otherwise suggest improvements. Quote the relevant lines. Be brief.\n\n")
            prompt = f"{task}=== CODE ===\n{code}\n=== END ==="

        # Check cache first
        cache_key = f"suggestion:{self.selected_model}:{hash(prompt)}"
        if getattr(self, 'cache_enabled', False) and cache_key in self.cache:
            # Return cached result immediately
            QtCore.QTimer.singleShot(0, lambda: self.suggestion_ready.emit(self.cache[cache_key]))
            return

        self._start_worker_thread("suggestion", code, prompt)

    def explain_code(self, code, prompt=""):
        """Explain what the code does.
        Note: prompt already includes lang_inst from the caller (on_explain_clicked).
        Do NOT append lang_inst here — that would duplicate it.
        """
        if not prompt:
            task = ("Explain the code below in detail — what it does, how it works, "
                    "key parts, data flow, and any non-obvious behavior.\n\n")
            prompt = f"{task}=== CODE ===\n{code}\n=== END ==="

        # Check cache first
        cache_key = f"explanation:{self.selected_model}:{hash(prompt)}"
        if getattr(self, 'cache_enabled', False) and cache_key in self.cache:
            # Return cached result immediately
            import PyQt6.QtCore as QtCore
            QtCore.QTimer.singleShot(0, lambda: self.explanation_ready.emit(self.cache[cache_key]))
            return

        self._start_worker_thread("explanation", code, prompt)

    def generate_custom_prompt(self, prompt):
        """Send custom prompt to AI.
        The incoming 'prompt' is a pre-built context string from AIPanel
        that already includes the language instruction. Do NOT append
        lang_inst here — that would duplicate it.
        """
        prompt = prompt.strip()
        if not prompt:
            self.error_occurred.emit("Empty prompt")
            return
        self._start_worker_thread("custom", "", prompt)

    def fix_code_errors(self, code, prompt=""):
        """Fix errors in the code using AI"""
        if not prompt:
            task = ("Find and fix bugs in the code below. If a traceback is present, "
                    "the error is in this code. Quote the problematic line, explain the "
                    "root cause, and show the minimal fix. Be brief.\n\n")
            prompt = f"{task}=== CODE ===\n{code}\n=== END ==="
        # Note: prompt already includes lang_inst from the caller (on_fix_clicked).
        # Do NOT append lang_inst here — that would duplicate it.

        # Check cache first
        cache_key = f"fix:{self.selected_model}:{hash(prompt)}"
        if getattr(self, 'cache_enabled', False) and cache_key in self.cache:
            # Return cached result immediately
            import PyQt6.QtCore as QtCore
            QtCore.QTimer.singleShot(0, lambda: self.fix_ready.emit(self.cache[cache_key]))
            return

        self._start_worker_thread("fix", code, prompt)

    def _start_worker_thread(self, request_type, code, prompt):
        """Start a worker thread for API calls"""
        # Cancel previous request if still running.
        # Use short wait + cancel flag (non-blocking) to avoid freezing the UI
        # when the previous worker is stuck in a long ollama.generate (e.g. large model first load
        # after a previous Suggest or preload that was cancelled).
        # This was a major source of "UI freezes on second Suggest after cancel".
        if self.worker_thread and self.worker_thread.isRunning():
            try:
                self.worker_thread.cancel()
            except Exception:
                pass
            self.worker_thread.quit()
            self.worker_thread.wait(100)  # short grace; let it finish in background if needed

        # Create and start new worker thread
        self.worker_thread = AIWorkerThread(
            self.api_key,
            self.selected_model,
            prompt,
            request_type,
            self.use_anthropic_api,
            self.use_ollama,
            self.timeout,
            context_window_enabled=getattr(self, 'context_window_enabled', False),
            context_window_size=getattr(self, 'context_window_size', 0),
            api_provider=self.api_provider,
            api_base=self.api_base,
        )
        self.worker_thread.result_ready.connect(self._handle_result)
        self.worker_thread.error_occurred.connect(self.error_occurred)
        self.worker_thread.stream_token.connect(self.stream_token)
        self.worker_thread.start()

    def _handle_result(self, result, request_type):
        """Handle the result from the worker thread"""
        print(f"[DEBUG] _handle_result called with request_type={request_type}, result_len={len(result) if result else 0}")
        # Cache the result if caching is enabled
        if getattr(self, 'cache_enabled', False):
            cache_key = f"{request_type}:{self.selected_model}:{hash(self.worker_thread.prompt)}"
            self.cache[cache_key] = result

        if request_type == "suggestion":
            print("[DEBUG] Emitting suggestion_ready")
            self.suggestion_ready.emit(result)
        elif request_type == "debug":
            print("[DEBUG] Emitting suggestion_ready (from debug)")
            self.suggestion_ready.emit(result)
        elif request_type == "explanation":
            print("[DEBUG] Emitting explanation_ready")
            self.explanation_ready.emit(result)
        elif request_type == "preload":
            print("[DEBUG] Emitting preload_ready")
            self.preload_ready.emit(result)
        elif request_type == "custom":
            print("[DEBUG] Emitting custom_ready")
            self.custom_ready.emit(result)  # ← NEW: emit signal for custom requests
        elif request_type == "fix":
            print("[DEBUG] Emitting fix_ready")
            self.fix_ready.emit(result)

    def cancel_request(self):
        """Cancel the current AI request (non-blocking for UI)."""
        if self.worker_thread and self.worker_thread.isRunning():
            try:
                self.worker_thread.cancel()  # set the _cancelled flag for early exit where possible
            except Exception:
                pass
            self.worker_thread.quit()
            # Do NOT do long blocking wait here — it freezes the main GUI thread
            # when the worker is stuck in a long ollama.generate / HTTP request.
            # Give a tiny grace period; the thread will exit when its current blocking
            # call returns (or on next check of _cancelled).
            self.worker_thread.wait(50)

    def _generate_demo_response(self, prompt):
        """Generate a demo response when API is not available"""
        if "improvements" in prompt.lower() or "suggest" in prompt.lower():
            return """Here are some suggestions for improving your code:

1. Add type hints for better code clarity
2. Consider adding input validation
3. Add docstring to explain the function
4. Consider handling edge cases (negative numbers)

Example with improvements:

```python
def factorial(n: int) -> int:
    \"\"\Calculate the factorial of a non-negative integer n.\"\"\n    if not isinstance(n, int) or n < 0:
        raise ValueError("n must be a non-negative integer")
    if n == 0:
        return 1
    else:
        return n * factorial(n-1)
```"""
        elif "explain" in prompt.lower():
            return """This code defines a recursive function to calculate the factorial of a number.

The factorial of a non-negative integer n is the product of all positive integers less than or equal to n.

Key points:
- Base case: factorial(0) = 1
- Recursive case: factorial(n) = n * factorial(n-1)
- The function calls itself with a smaller value until it reaches the base case

Example: factorial(5) = 5 * 4 * 3 * 2 * 1 = 120"""
        elif "fix" in prompt.lower() or "error" in prompt.lower():
            return """Common issues and fixes for factorial function:

1. No input validation: Add check for negative numbers
2. Stack overflow: For large n, consider iterative approach
3. Type error: Ensure input is integer

Fixed version:

```python
def factorial(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError("Input must be non-negative integer")
    result = 1
    for i in range(1, n+1):
        result *= i
    return result
```"""
        else:
            return _("AI response: This is a demo response. The actual AI API is not available at the moment.")

    def _orchestrate(self, task: str, code_context: str,
                     preferred_coder: str = "",
                     language: str = "English"):  # returns OrchestrationManager (defined below)
        """Start a multi-model pipeline for complex tasks.
        Called from AIPanel when the model uses TOOL: orchestrate.

        Returns the OrchestrationManager instance so AIPanel can connect signals.
        """
        hw = HardwareDetector()
        models = hw.select_models_for_pipeline(preferred_coder=preferred_coder)
        if models is None:
            print("[AIAssistant] Not enough RAM for pipeline, falling back to single model")
            return None

        mgr = OrchestrationManager()
        mgr.run(task, code_context, models, hw, self.use_ollama, language)
        return mgr

    def _start_chain(self, task: str, code: str, lang: str = "English",
                     model_interpreter: str = "", model_coder: str = "",
                     model_reviewer: str = "", num_models: int = 3):
        """Start the sequential model chain.
        num_models=2 → interpreter + coder (no reviewer).
        num_models=3 → interpreter + coder + reviewer.
        """
        # Cancel previous chain if running
        if hasattr(self, '_chain_worker') and self._chain_worker and self._chain_worker.isRunning():
            self._chain_worker.cancel()
            self._chain_worker.wait(200)

        # Auto-select models if not specified (prefer small→large→small)
        hw = HardwareDetector()
        current = self.selected_model

        if not model_interpreter:
            # Try to pick a tiny model for interpreter (≤2GB) that EXISTS locally
            if self.use_ollama:
                for tiny in ["qwen2.5-coder:1.5b", "llama3.2:3b", "gemma:2b"]:
                    if hw.can_load_model(tiny) and hw.model_exists_locally(tiny):
                        model_interpreter = f"ollama:{tiny}"
                        break
            if not model_interpreter:
                model_interpreter = current  # fallback: same as current model

        if not model_coder:
            model_coder = current  # main model for coding

        if num_models >= 3:
            if not model_reviewer:
                model_reviewer = model_interpreter  # reuse interpreter (already loaded)
            # model_reviewer is explicitly passed from AIPanel — if user selected one, use it
        else:
            model_reviewer = ""  # 2-model chain has no reviewer

        print(f"[AIAssistant] Chain: I={model_interpreter}, C={model_coder}"
              f"{', R=' + model_reviewer if model_reviewer else ''}")

        worker = ChainWorker(task, code, lang,
                             model_interpreter, model_coder,
                             model_reviewer if num_models >= 3 else "")
        worker.result_ready.connect(lambda r: self.chain_ready.emit(r))
        worker.status_update.connect(lambda s: self.chain_status.emit(s))
        worker.error_occurred.connect(lambda e: self.error_occurred.emit(e))
        self._chain_worker = worker
        worker.start()

    def cancel_chain(self) -> bool:
        """Cancel the running chain worker. Returns True if a chain was actually cancelled."""
        if hasattr(self, '_chain_worker') and self._chain_worker and self._chain_worker.isRunning():
            self._chain_worker.cancel()
            self._chain_worker.wait(200)
            self._chain_worker = None
            return True
        return False


class AIWorkerThread(QThread):
    """Worker thread for making API calls"""

    result_ready = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    stream_token = pyqtSignal(str)  # emitted per-token during streaming

    def __init__(self, api_key, model, prompt, request_type, use_anthropic_api, use_ollama, timeout=30,
                 context_window_enabled=False, context_window_size=0,
                 api_provider="ollama", api_base="http://localhost:11434"):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.request_type = request_type
        self.use_anthropic_api = use_anthropic_api
        self.use_ollama = use_ollama
        self.timeout = timeout
        self.context_window_enabled = context_window_enabled
        self.context_window_size = context_window_size
        self.api_provider = api_provider
        self.api_base = api_base
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the current operation"""
        print(f"[DEBUG] AIWorkerThread.cancel() called")
        self._cancelled = True

    def run(self):
        """Make the API call in a separate thread"""
        print(f"[DEBUG] AIWorkerThread.run() started for model={self.model}, type={self.request_type}")
        try:
            if self._cancelled:
                print("[DEBUG] Cancelled before start")
                return

            # Determine the provider from model prefix + self.api_provider
            provider = self._detect_provider()

            if provider == "ollama":
                self._call_ollama()
            elif provider in ("openrouter", "opencode", "custom"):
                self._call_openai_compat(provider)
            elif provider == "anthropic":
                self._call_anthropic()
            else:
                # Fallback: free-claude-code / demo
                self._call_free_claude_api()

        except AnthropicError as e:
            self.error_occurred.emit(f"Anthropic API Error: {str(e)}")
        except Exception as e:
            print(f"[DEBUG] AIWorkerThread error: {e}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"Error calling AI API: {str(e)}")
        finally:
            print(f"[DEBUG] AIWorkerThread.run() finished")

    # ── Provider helpers ──────────────────────────────────────────────────

    def _detect_provider(self):
        """Determine which provider to use based on model prefix and
        ``self.api_provider``."""
        if self.model.startswith("ollama:"):
            return "ollama"
        elif self.model.startswith("openrouter:"):
            return "openrouter"
        elif self.model.startswith("opencode:"):
            return "opencode"
        # Fall back to the configured provider
        return self.api_provider

    def _get_system_message(self):
        """Standard system message used across all providers."""
        return (
            "You are a Python coding assistant integrated into the PyCoder IDE.\n"
            "You help the user understand, analyze, and improve their code.\n"
            "Base your answers strictly on the provided code and context.\n"
            "If details are missing, say so instead of inventing answers.\n"
            "When suggesting fixes, output the corrected code inside ```python blocks "
            "so it can be automatically written into the editor."
        )

    def _make_options(self, provider, model_name):
        """Build the options dict for the request."""
        if provider == "ollama":
            # NOTE: "Assistant:" was earlier removed because some quantized models
            # output "Assistant:" as their very first token after a short prompt,
            # matching the stop token before any content.  However, with LONG prompts
            # (12000+ chars) the model sometimes generates 8192 invisible special-
            # tokens (done_reason=length, eval_count=8192, 0 content tokens) when
            # "Assistant:" is absent from the stop list and only "[SYSTEM]", "</s>"
            # are present.  Having "Assistant:" in the stop list prevents this loop
            # and lets the model generate real content.  The FIRST token latency is
            # higher (80+ s cold) but content arrives reliably.
            options = {
                "temperature": 0.15,
                "num_predict": 8192,
                "repeat_penalty": 1.8,          # increased from 1.5 to prevent repetition loops
                "frequency_penalty": 0.5,       # increased from 0.3
                "presence_penalty": 0.3,        # increased from 0.2
                "top_p": 0.85,
                "top_k": 40,
                "stop": ["Assistant:", "</s>"],
            }
            if self.request_type in ("suggestion", "fix", "debug"):
                # Suggestion, fix & debug need some creativity to avoid repetition loops.
                # temperature=0.0 causes the model to get stuck in a repeating pattern
                # because the single most-likely token is always the same continuation.
                # NOTE: repeat_penalty=2.0 was tried but caused 0-token failures on
                # the hadad/qwen3-4bd:Q8_0 model (the model couldn't recover from the
                # aggressive penalty). Using the base default (1.8) works reliably.
                options["temperature"] = 0.2
                options["num_predict"] = 2048  # shorter limit reduces garbage from loops
                # repeat_penalty left at base default (1.8) — 2.0 caused 0-token failures
                options["frequency_penalty"] = 0.6
                options["presence_penalty"] = 0.4
            if self.context_window_enabled and self.context_window_size > 0:
                options["num_ctx"] = self.context_window_size
            return options
        # OpenAI-compatible (openrouter, opencode, custom) — temperature only
        return {"temperature": 0.3}

    def _call_ollama(self):
        """Make a streaming request to local Ollama, with automatic retry on 0-token failures."""
        model_name = self.model[7:]  # Remove "ollama:" prefix
        try:
            if hasattr(ollama, 'keepalive'):
                ollama.keepalive(model_name)
        except Exception:
            pass
        print(f"[DEBUG] Calling Ollama generate for {model_name}, prompt_len={len(self.prompt)}")
        if self._cancelled:
            return

        options = self._make_options("ollama", model_name)
        print(f"[DEBUG] Options: temp={options.get('temperature')}, stop={options.get('stop')}, num_predict={options.get('num_predict')}")

        # Retry up to 2 times on 0-token failures (intermittent model issue)
        max_retries = 2
        import json as _json
        for attempt in range(max_retries + 1):
            if self._cancelled:
                return
            if attempt > 0:
                import time as _time
                print(f"[DEBUG] Retry attempt {attempt}/{max_retries} after 0-token failure")
                _time.sleep(1)
                # Re-run keepalive before retry
                try:
                    if hasattr(ollama, 'keepalive'):
                        ollama.keepalive(model_name)
                except Exception:
                    pass

            # IMPORTANT: always send keep_alive with the /api/chat request.
            # The separate keepalive() call pings /api/generate, but that doesn't
            # set keep_alive for /api/chat sessions. Without this, Ollama's default
            # (5 min) is used and the model may be unloaded between slow requests.
            chat_payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": self._get_system_message()},
                    {"role": "user", "content": self.prompt},
                ],
                "options": options,
                "stream": True,
                "keep_alive": "10m",
            }
            try:
                stream_response = requests.post(
                    "http://localhost:11434/api/chat",
                    json=chat_payload,
                    stream=True,
                    # Connect timeout scales with user setting, read timeout is generous
                    # to handle slow USB storage responses between streaming tokens.
                    timeout=(max(10, self.timeout // 2), max(180, self.timeout * 2)),
                )
                stream_response.raise_for_status()
            except Exception as e:
                if attempt < max_retries:
                    print(f"[DEBUG] Request failed (attempt {attempt+1}): {e} — retrying")
                    try:
                        stream_response.close()
                    except Exception:
                        pass
                    continue
                print(f"[DEBUG] Request failed after all retries: {e}")
                self.error_occurred.emit(f"Ollama request failed: {str(e)}")
                return

            if self._cancelled:
                stream_response.close()
                return

            _request_start_time = time.time()
            full_content = ""
            _idle_timeout = max(self.timeout * 2, 300)
            _first_token_timeout = max(self.timeout * 3, 600)  # generous first-token wait (USB, reasoning models)
            _last_token_time = None  # set on first token, not stream start
            token_count = 0
            empty_done_reason = "N/A"
            for line in stream_response.iter_lines():
                if self._cancelled:
                    stream_response.close()
                    return
                if not line:
                    continue
                chunk = _json.loads(line)
                # Check for Ollama error response
                if "error" in chunk:
                    print(f"[DEBUG] Ollama error in stream: {chunk['error']}")
                    if attempt < max_retries:
                        print(f"[DEBUG] Will retry after error")
                        stream_response.close()
                        break  # break out to retry
                    self.error_occurred.emit(f"Ollama error: {chunk['error']}")
                    stream_response.close()
                    return
                if chunk.get("done"):
                    elapsed = time.time() - _request_start_time
                    done_reason = chunk.get("done_reason", "N/A")
                    empty_done_reason = done_reason
                    eval_count = chunk.get("eval_count", 0)
                    prompt_eval_count = chunk.get("prompt_eval_count", 0)
                    total_duration_ns = chunk.get("total_duration", 0)
                    total_duration_s = total_duration_ns / 1e9 if total_duration_ns else 0
                    print(f"[DEBUG] Stream done after {token_count} tokens, {elapsed:.1f}s")
                    print(f"[DEBUG]   done_reason={done_reason}, eval_count={eval_count}, prompt_eval_count={prompt_eval_count}, total_duration={total_duration_s:.1f}s")
                    break
                token = chunk.get("message", {}).get("content", "")
                # Idle timeout: only check between tokens (not before first token)
                if _last_token_time is not None:
                    idle = time.time() - _last_token_time
                    if idle > _idle_timeout:
                        print(f"[DEBUG] Idle timeout after {token_count} tokens, idle={idle:.0f}s")
                        if attempt < max_retries:
                            print(f"[DEBUG] Will retry after idle timeout")
                            stream_response.close()
                            break  # break out to retry
                        self.error_occurred.emit(
                            f"Timeout: no response from {model_name} in {_idle_timeout:.0f}s"
                        )
                        stream_response.close()
                        return
                if token:
                    if _last_token_time is None:
                        # First token — check against a generous first-token timeout
                        elapsed = time.time() - _request_start_time
                        if elapsed > _first_token_timeout:
                            print(f"[DEBUG] First token timeout at {elapsed:.0f}s")
                            if attempt < max_retries:
                                print(f"[DEBUG] Will retry after first-token timeout")
                                stream_response.close()
                                break  # break out to retry
                            self.error_occurred.emit(
                                f"Timeout: {model_name} did not start generating in {_first_token_timeout:.0f}s"
                            )
                            stream_response.close()
                            return
                    full_content += token
                    self.stream_token.emit(token)
                    _last_token_time = time.time()
                    token_count += 1

            if self._cancelled:
                stream_response.close()
                return
            elapsed = time.time() - _request_start_time
            if full_content:
                print(f"[DEBUG] Ollama OK: {token_count} tokens in {elapsed:.1f}s (attempt {attempt+1})")
                self.result_ready.emit(full_content, self.request_type)
                return  # success — exit retry loop
            else:
                print(f"[DEBUG] Ollama empty response after {elapsed:.1f}s (attempt {attempt+1}) — no tokens generated")
                print(f"[DEBUG]   done_reason={empty_done_reason}")
                if attempt >= max_retries:
                    self.error_occurred.emit("No response from Ollama (model generated 0 tokens)")
                    return
                # Continue retry loop
                print(f"[DEBUG] Retrying...")
                continue

    def _call_openai_compat(self, provider):
        """Make a streaming request to an OpenAI-compatible chat completions
        endpoint (OpenRouter, OpenCode, or custom)."""
        # Strip prefix if present
        if provider == "openrouter":
            model_name = self.model[len("openrouter:"):]
            url = "https://openrouter.ai/api/v1/chat/completions"
        elif provider == "opencode":
            model_name = self.model[len("opencode:"):]
            url = "https://api.opencode.ai/v1/chat/completions"
        else:
            model_name = self.model
            url = f"{self.api_base.rstrip('/')}/chat/completions"

        print(f"[DEBUG] Calling {provider} for model={model_name}")

        # temperature=0.0 causes repetition loops — use 0.3 as minimum
        temperature = 0.3 if self.request_type in ("suggestion", "fix", "debug") else 0.25
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://pycoder6.local"
            headers["X-Title"] = "PyCoder6"

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": self._get_system_message()},
                {"role": "user", "content": self.prompt},
            ],
            "temperature": temperature,
            "max_tokens": 2048,
            "stream": True,
        }

        try:
            stream_response = requests.post(
                url, headers=headers, json=payload,
                stream=True, timeout=(max(10, self.timeout // 2), max(180, self.timeout * 2)),
            )
            stream_response.raise_for_status()
        except requests.RequestException as e:
            self.error_occurred.emit(f"{provider} request failed: {e}")
            return

        if self._cancelled:
            stream_response.close()
            return

        import json as _json
        full_content = ""
        _idle_timeout = max(self.timeout * 2, 120)
        _last_token_time = time.time()
        for line in stream_response.iter_lines():
            if self._cancelled:
                stream_response.close()
                return
            if not line:
                continue
            # OpenAI SSE format: "data: {...}"
            text = line.decode("utf-8", errors="replace").strip()
            if text == "data: [DONE]":
                break
            if not text.startswith("data: "):
                continue
            try:
                chunk = _json.loads(text[6:])
            except Exception:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            token = delta.get("content", "")
            idle = time.time() - _last_token_time
            if idle > _idle_timeout:
                self.error_occurred.emit(
                    f"Timeout: no response from {provider} in {_idle_timeout:.0f}s"
                )
                stream_response.close()
                return
            if token:
                full_content += token
                self.stream_token.emit(token)
                _last_token_time = time.time()

        if self._cancelled:
            return
        if full_content:
            self.result_ready.emit(full_content, self.request_type)
        else:
            self.error_occurred.emit(f"No response from {provider}")

    def _call_anthropic(self):
        """Make a request to the Anthropic API."""
        print(f"[DEBUG] Calling Anthropic API for {self.model}")
        client = Anthropic(api_key=self.api_key)
        messages = [{"role": "user", "content": self.prompt}]
        if self.request_type == "explanation":
            messages = [{"role": "system", "content": "Explain the following in detail:"}] + messages

        # Note: Anthropic SDK does not support streaming by default in simple mode,
        # but we still check _cancelled before/after the call.
        if self._cancelled:
            return
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=messages,
            )
        except Exception as e:
            self.error_occurred.emit(f"Anthropic API error: {e}")
            return

        if self._cancelled:
            return
        if response and response.content:
            content = "\n".join([block.text for block in response.content])
            self.result_ready.emit(content, self.request_type)
        else:
            self.error_occurred.emit("No response from AI")

    def _call_free_claude_api(self):
        """Fallback: free-claude-code proxy or demo."""
        print(f"[DEBUG] Calling free-claude-code API for {self.model}")
        try:
            params = {
                "model": self.model,
                "message": self.prompt,
                "max_tokens": "2048",
            }
            response = requests.get(
                "http://localhost:8082/",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params=params,
                timeout=self.timeout,
            )

            if self._cancelled:
                return

            if response.status_code == 200:
                result = response.json()
                if "response" in result:
                    content = result["response"]
                    self.result_ready.emit(content, self.request_type)
                else:
                    content = self._generate_demo_response(self.prompt)
                    self.result_ready.emit(content, self.request_type)
            else:
                content = self._generate_demo_response(self.prompt)
                self.result_ready.emit(content, self.request_type)
        except Exception as e:
            print(f"[DEBUG] free-claude-code API error: {e}")
            content = self._generate_demo_response(self.prompt)
            self.result_ready.emit(content, self.request_type)


class PipelineWorker(QThread):
    """Worker thread that runs the full pipeline synchronously.
    Uses ollama.chat() directly (blocking calls inside the thread)
    so phases run sequentially without complex signal chains.
    """
    phase_changed = pyqtSignal(str, str)     # (phase_name, message)
    phase_result = pyqtSignal(str, str)       # (phase_name, result_text)
    pipeline_complete = pyqtSignal(str)       # final code content
    pipeline_error = pyqtSignal(str)          # error message

    INTERPRETER_PROMPT = """You are a code task interpreter. Analyse the following user request and code, and produce a structured plan.

User request: {task}

Code:
{code}

Output format (use EXACTLY this):
PROBLEM: <one-line summary>
ROOT CAUSE: <what causes the bug or needs change>
FIX PLAN:
1. <step>
2. <step>
AFFECTED: <which lines or sections>
IMPORTS NEEDED: <any missing imports, or "none">"""

    CODER_PROMPT = """You are a code generator. Implement the fix plan below precisely.
Output ONLY the changed code sections inside ```python blocks.

Fix plan:
{interpretation}

Relevant code:
{code}

Rules:
- Output only the changed code inside ```python blocks
- Include ALL necessary imports at the top of the ```python block
- Do NOT change unrelated code
- The user's language is: {lang}"""

    REVIEWER_PROMPT = """You are a code reviewer. Check this fix for errors.

Original task: {task}
Original code:
{code}

Fixed code:
{fixed_code}

Check:
1. Missing imports (compare with original)
2. Syntax errors
3. API misuse (e.g. PySide6 vs PyQt5)
4. Incomplete changes

Output:
ERRORS: <list each error or "none">
FIX: <how to fix each error or "none">
VERDICT: PASS or FAIL"""

    def __init__(self, task: str, code_context: str,
                 models: dict, hw: HardwareDetector,
                 use_ollama: bool, language: str = "English"):
        super().__init__()
        self.task = task
        self.code_context = code_context
        self.models = models          # {interpreter, coder, reviewer}
        self.hw = hw
        self.use_ollama = use_ollama
        self.language = language

    def _call_model(self, model_name: str, prompt: str, timeout_s: int = None) -> str:
        """Synchronous Ollama model call via direct HTTP (runs in this thread, blocks)."""
        name = model_name[7:] if model_name.startswith("ollama:") else model_name
        if not self.use_ollama:
            return f"[ERROR] Ollama not available for model {model_name}"
        if timeout_s is None:
            timeout_s = 300  # default for reasoning models (was 120)

        url = "http://localhost:11434/api/chat"
        payload = {
            "model": name,
            "messages": [{"role": "user", "content": prompt}],
            "options": {
                "temperature": 0.15,
                "num_predict": 8192,
                "repeat_penalty": 1.5,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.2,
                "top_p": 0.85,
                "top_k": 40,
            },
            "stream": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            return f"[ERROR] Ollama call failed on {name}: {e}"

        if isinstance(data, dict) and "message" in data:
            return data["message"].get("content", "")
        return str(data)

    def run(self):
        try:
            print(f"[PipelineWorker] Starting pipeline: I={self.models['interpreter']} "
                  f"C={self.models['coder']} R={self.models['reviewer']}")

            # ── Phase 1: Interpreter ──
            self.phase_changed.emit("interpreter", "Elemzés...")
            interp_prompt = self.INTERPRETER_PROMPT.format(
                task=self.task,
                code=self.code_context
            )
            interpretation = self._call_model(self.models["interpreter"], interp_prompt)
            self.phase_result.emit("interpreter", interpretation)

            # Unload interpreter if it's not the reviewer (saves memory)
            if self.models["interpreter"] != self.models["reviewer"]:
                self.hw.unload_model(self.models["interpreter"])

            # ── Phase 2: Coder ──
            self.phase_changed.emit("coder", "Kód generálása...")
            lang_inst = ""
            if self.language and self.language.lower() != "english":
                lang_inst = self.language
            coder_prompt = self.CODER_PROMPT.format(
                interpretation=interpretation,
                code=self.code_context,
                lang=lang_inst
            )
            code_result = self._call_model(self.models["coder"], coder_prompt)
            self.phase_result.emit("coder", code_result)

            # Unload coder if it's not the reviewer
            if self.models["coder"] != self.models["reviewer"]:
                self.hw.unload_model(self.models["coder"])

            # ── Phase 3: Reviewer (with fix loop) ──
            max_loops = 2
            loop_count = 0
            final_code = code_result

            while loop_count < max_loops:
                self.phase_changed.emit("reviewer", f"Áttekintés ({loop_count + 1}/{max_loops})...")
                review_prompt = self.REVIEWER_PROMPT.format(
                    task=self.task,
                    code=self.code_context,
                    fixed_code=final_code
                )
                review = self._call_model(self.models["reviewer"], review_prompt)
                self.phase_result.emit("reviewer", review)

                if "VERDICT: PASS" in review.upper():
                    print(f"[PipelineWorker] Review PASSED (loop {loop_count + 1})")
                    break

                if loop_count < max_loops - 1:
                    self.phase_changed.emit("coder", f"Javítás ({loop_count + 1}/{max_loops})...")
                    fix_prompt = (
                        f"The reviewer found issues:\n{review}\n\n"
                        f"Fix the code below and output the corrected version in ```python blocks.\n\n"
                        f"Previous code:\n{final_code}"
                    )
                    final_code = self._call_model(self.models["coder"], fix_prompt)
                    self.phase_result.emit("coder", final_code)
                loop_count += 1

            # Done
            self.pipeline_complete.emit(final_code)
            print(f"[PipelineWorker] Pipeline complete")

        except Exception as e:
            print(f"[PipelineWorker] Error: {e}")
            import traceback
            traceback.print_exc()
            self.pipeline_error.emit(f"Pipeline error: {str(e)}")


class OrchestrationManager(QtCore.QObject):
    """High-level orchestration API for AIPanel.
    Creates a PipelineWorker thread and relays its signals.
    """
    pipeline_progress = pyqtSignal(str, str)   # (phase, message) for chat bubbles
    pipeline_result = pyqtSignal(str)           # final code to write to editor
    pipeline_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

    def run(self, task: str, code_context: str,
            models: dict, hw: HardwareDetector,
            use_ollama: bool, language: str = "English"):
        """Start the multi-model pipeline in a background thread."""
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(200)

        self._worker = PipelineWorker(task, code_context, models, hw, use_ollama, language)
        self._worker.phase_changed.connect(lambda p, m: self.pipeline_progress.emit(p, m))
        self._worker.pipeline_complete.connect(lambda r: self.pipeline_result.emit(r))
        self._worker.pipeline_error.connect(lambda e: self.pipeline_error.emit(e))
        self._worker.start()

    def cancel(self):
        """Cancel the running pipeline."""
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(200)


class ChainWorker(QThread):
    """Ultra-simple sequential chain: 3 model runs in one thread.
    Exactly matches the user's shell-script approach:
      1) Interpreter  (small model)  — analyse the task
      2) Coder        (large model)  — produce code
      3) Reviewer     (small model)  — validate & fix
    Each model is loaded, runs once, then the next loads.
    ONE final result is emitted — no streaming, no intermediate tabs.
    """
    result_ready = pyqtSignal(str)     # final code/text
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)    # short phase label for status bar

    # ── Prompt templates ──────────────────────────────────────────
    INTERPRETER_TEMPLATE = (
        "You are a senior code reviewer. Analyze the following request and code.\n"
        "Be specific: which lines, what is wrong, what needs to change.\n\n"
        "Request: {task}\n\n"
        "Code:\n{code}\n\n"
        "Output ONLY a clear description of the problem and the minimal fix plan."
    )

    CODER_TEMPLATE = (
        "You are a Python developer. Implement the fix plan below.\n"
        "You MUST output the COMPLETE fixed file in a single ```python block.\n"
        "DO NOT output only the changed parts — include EVERY line of the file\n"
        "from the first import to the last line. The output will REPLACE the\n"
        "entire file, so nothing must be left out.\n"
        "Include ALL necessary imports.\n"
        "{framework_inst}\n"
        "Fix plan:\n{analysis}\n\n"
        "Original code:\n{code}\n\n"
        "Language: {lang}"
    )

    REVIEWER_TEMPLATE = (
        "You are a QA code reviewer. Check this code for errors, missing imports,\n"
        "syntax mistakes.\n"
        "{framework_inst}\n"
        "If you find issues, output the CORRECTED full code in ```python blocks.\n"
        "If the code is correct, just say VERDICT: PASS.\n"
        "IMPORTANT: Always output code in ```python blocks, never just text.\n\n"
        "Task: {task}\n\n"
        "Code:\n{code}"
    )

    @staticmethod
    def _detect_framework_inst(code: str) -> str:
        """Detect Qt framework from code and return an appropriate instruction."""
        lower = code.lower()
        if "pyside6" in lower:
            return "IMPORTANT: This code uses PySide6. Only use 'from PySide6 import ...' (NOT PyQt5 or PyQt6)."
        elif "pyqt6" in lower:
            return "IMPORTANT: This code uses PyQt6. Only use 'from PyQt6 import ...' (NOT PyQt5 or PySide6)."
        elif "pyqt5" in lower:
            return "IMPORTANT: This code uses PyQt5. Only use 'from PyQt5 import ...'."
        else:
            return "Use whatever imports the original code already uses (keep the same Qt framework)."

    def __init__(self, task: str, code: str, lang: str,
                 model_interpreter: str, model_coder: str, model_reviewer: str = ""):
        super().__init__()
        self.task = task
        self.code = code
        self.lang = lang
        self.model_interpreter = model_interpreter
        self.model_coder = model_coder
        self.model_reviewer = model_reviewer
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _ollama_call(self, model: str, prompt: str) -> str:
        """Single blocking ollama call via direct HTTP. Returns content string or raises.
        Uses requests.post instead of the ollama library to avoid httpx default 30s timeout
        — full-file generation (8192 tokens) can take 90+ seconds."""
        name = model[7:] if model.startswith("ollama:") else model
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": name,
            "messages": [{"role": "user", "content": prompt}],
            "options": {
                "temperature": 0.15,
                "num_predict": 8192,
                "repeat_penalty": 1.5,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.2,
                "num_ctx": 8192,
            },
            "stream": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout:
            raise RuntimeError(f"Ollama call timed out (300s) on {name}")
        except requests.ConnectionError:
            raise RuntimeError(f"Cannot connect to Ollama (is it running?) on {name}")
        except requests.RequestException as e:
            raise RuntimeError(f"Ollama call failed on {name}: {e}")

        if self._cancelled:
            raise RuntimeError("Cancelled")

        if isinstance(data, dict) and "message" in data:
            return data["message"].get("content", "")
        return str(data)

    def run(self):
        try:
            # ── Step 1: Interpreter ──
            self.status_update.emit("🔍 Interpreter")
            interp_prompt = self.INTERPRETER_TEMPLATE.format(
                task=self.task, code=self.code
            )
            analysis = self._ollama_call(self.model_interpreter, interp_prompt)
            if self._cancelled:
                return

            # ── Step 2: Coder ──
            self.status_update.emit("✏️ Coder")
            coder_prompt = self.CODER_TEMPLATE.format(
                analysis=analysis,
                code=self.code,
                lang=self.lang if self.lang.lower() != "english" else "English (keep code in English)",
                framework_inst=self._detect_framework_inst(self.code),
            )
            code_out = self._ollama_call(self.model_coder, coder_prompt)
            if self._cancelled:
                return

            # ── Step 3: Reviewer (only for 3-model chain) ──
            if self.model_reviewer:
                self.status_update.emit("✅ Reviewer")
                review_prompt = self.REVIEWER_TEMPLATE.format(
                    task=self.task, code=code_out,
                    framework_inst=self._detect_framework_inst(code_out),
                )
                final = self._ollama_call(self.model_reviewer, review_prompt)
                if self._cancelled:
                    return

                # Decide which to return: if reviewer gave a corrected version, use that
                if "VERDICT: PASS" in final.upper() or "```" not in final:
                    # Reviewer approved the coder's output — return original
                    self.result_ready.emit(code_out)
                else:
                    # Reviewer produced a corrected version — return that
                    self.result_ready.emit(final)
            else:
                # 2-model chain: no reviewer, emit coder output directly
                self.result_ready.emit(code_out)

            # DEBUG: Log chain completion
            debug_print(f"[CHAIN] Completed, emitted result ({len(code_out)} chars from coder)")

        except RuntimeError as e:
            if "Cancelled" in str(e):
                return
            self.error_occurred.emit(str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
        finally:
            self.status_update.emit("")
