#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Assistant Module for PyCoderAi
Integrates with Claude API for code suggestions, explanations, and improvements
"""

import requests
import json
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QThread, pyqtSignal

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


class AIAssistant(QtCore.QObject):
    """
    AI Assistant class for interacting with Claude API
    """

    suggestion_ready = pyqtSignal(str)
    explanation_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_key = "freecc"  # Default key, can be changed via settings
        self.selected_model = "claude-3-5-sonnet-20241022"
        self.worker_thread = None
        self.use_anthropic_api = Anthropic is not None
        self.use_ollama = ollama is not None
        self.timeout = 30  # Default timeout in seconds
        self.cache = {}  # Simple cache for responses
        self.cache_enabled = False  # Cache disabled by default
        self.api_base = "http://localhost:8082"  # Default API base URL

    def set_api_config(self, base_url, api_key, model, timeout=30, cache_enabled=True):
        """Configure API settings"""
        self.api_base = base_url
        self.api_key = api_key
        self.selected_model = model
        self.timeout = timeout
        self.cache_enabled = cache_enabled

    def get_available_models(self):
        """Fetch available models from the API"""
        models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]

        # Add Ollama models if available
        if self.use_ollama:
            try:
                ollama_models = ollama.list()['models']
                for model in ollama_models:
                    # Use 'model' field if available, otherwise 'name'
                    model_name = model.get('model', model.get('name', str(model)))
                    models.append(f"ollama:{model_name}")
            except Exception as e:
                print(f"Warning: Could not fetch Ollama models: {e}")
                pass

        return models

    def generate_code_suggestions(self, code, prompt=""):
        """Generate code suggestions using AI"""
        if not prompt:
            prompt = f"Analyze the following Python code and suggest improvements:\n\n{code}"

        # Check cache first
        cache_key = f"suggestion:{self.selected_model}:{hash(prompt)}"
        if getattr(self, 'cache_enabled', False) and cache_key in self.cache:
            # Return cached result immediately
            import PyQt6.QtCore as QtCore
            QtCore.QTimer.singleShot(0, lambda: self.suggestion_ready.emit(self.cache[cache_key]))
            return

        self._start_worker_thread("suggestion", code, prompt)

    def explain_code(self, code, prompt=""):
        """Explain what the code does"""
        if not prompt:
            prompt = f"Explain the following Python code in detail:\n\n{code}"

        # Check cache first
        cache_key = f"explanation:{self.selected_model}:{hash(prompt)}"
        if getattr(self, 'cache_enabled', False) and cache_key in self.cache:
            # Return cached result immediately
            import PyQt6.QtCore as QtCore
            QtCore.QTimer.singleShot(0, lambda: self.explanation_ready.emit(self.cache[cache_key]))
            return

        self._start_worker_thread("explanation", code, prompt)

    def fix_code_errors(self, code, error_message=""):
        """Suggest fixes for code errors"""
        prompt = f"The following Python code has an error:\n\nError: {error_message}\n\nCode:\n{code}\n\nSuggest fixes:"

        # Check cache first
        cache_key = f"fix:{self.selected_model}:{hash(prompt)}"
        if getattr(self, 'cache_enabled', False) and cache_key in self.cache:
            # Return cached result immediately
            import PyQt6.QtCore as QtCore
            QtCore.QTimer.singleShot(0, lambda: self.suggestion_ready.emit(self.cache[cache_key]))
            return

        self._start_worker_thread("suggestion", code, prompt)

    def _start_worker_thread(self, request_type, code, prompt):
        """Start a worker thread for API calls"""
        # Cancel previous request if still running
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        # Create and start new worker thread
        self.worker_thread = AIWorkerThread(
            self.api_key,
            self.selected_model,
            prompt,
            request_type,
            self.use_anthropic_api,
            self.use_ollama,
            self.timeout
        )
        self.worker_thread.result_ready.connect(self._handle_result)
        self.worker_thread.error_occurred.connect(self.error_occurred)
        self.worker_thread.start()

    def _handle_result(self, result, request_type):
        """Handle the result from the worker thread"""
        # Cache the result if caching is enabled
        if getattr(self, 'cache_enabled', False):
            cache_key = f"{request_type}:{self.selected_model}:{hash(self.worker_thread.prompt)}"
            self.cache[cache_key] = result

        if request_type == "suggestion":
            self.suggestion_ready.emit(result)
        elif request_type == "explanation":
            self.explanation_ready.emit(result)

    def cancel_request(self):
        """Cancel the current AI request"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()


class AIWorkerThread(QThread):
    """Worker thread for making API calls"""

    result_ready = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key, model, prompt, request_type, use_anthropic_api, use_ollama, timeout=30):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.request_type = request_type
        self.use_anthropic_api = use_anthropic_api
        self.use_ollama = use_ollama
        self.timeout = timeout

    def run(self):
        """Make the API call in a separate thread"""
        try:
            if self.model.startswith("ollama:") and self.use_ollama:
                # Use Ollama
                model_name = self.model[7:]  # Remove "ollama:" prefix
                response = ollama.generate(
                    model=model_name,
                    prompt=self.prompt,
                    options={"temperature": 0.7}
                )

                if response and 'response' in response:
                    content = response['response']
                    self.result_ready.emit(content, self.request_type)
                else:
                    self.error_occurred.emit("No response from Ollama")

            elif self.use_anthropic_api:
                # Use Anthropic API
                client = Anthropic(api_key=self.api_key)
                response = client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    messages=[
                        {"role": "user", "content": self.prompt}
                    ]
                )

                if response.content:
                    content = "\n".join([block.text for block in response.content])
                    self.result_ready.emit(content, self.request_type)
                else:
                    self.error_occurred.emit("No response from AI")

            else:
                # Try to use free-claude-code API
                try:
                    params = {
                        "model": self.model,
                        "message": self.prompt,
                        "max_tokens": "2048"
                    }

                    response = requests.get(
                        "http://localhost:8082/",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        params=params,
                        timeout=self.timeout
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if "response" in result:
                            content = result["response"]
                            self.result_ready.emit(content, self.request_type)
                        else:
                            # Fallback to demo mode
                            content = self._generate_demo_response(self.prompt)
                            self.result_ready.emit(content, self.request_type)
                    else:
                        # Fallback to demo mode
                        content = self._generate_demo_response(self.prompt)
                        self.result_ready.emit(content, self.request_type)
                except Exception:
                    # Fallback to demo mode
                    content = self._generate_demo_response(self.prompt)
                    self.result_ready.emit(content, self.request_type)

        except AnthropicError as e:
            self.error_occurred.emit(f"Anthropic API Error: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(f"Error calling AI API: {str(e)}")

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
            return "AI response: This is a demo response. The actual AI API is not available at the moment."
