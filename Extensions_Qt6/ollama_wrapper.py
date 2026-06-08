#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embedded Ollama wrapper for PyCoderAi
Provides Ollama functionality without requiring pip installation
"""

import sys
import os
import json
import requests
from typing import Any, Dict, List, Optional


class OllamaWrapper:
    """Wrapper for Ollama API that can work without the official ollama package.
    Includes model preloading and simple keep‑alive ping to avoid cold‑start delays.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.loaded_models = set()  # Track which models have been preloaded

    def list(self) -> Dict[str, Any]:
        """List available models. Also double‑checks that the server is responsive."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return {"models": response.json()["models"]}
        except Exception as e:
            # Return empty list if server is not available
            return {"models": []}

    def preload_model(self, model: str) -> bool:
        """Load the model into memory with a tiny prompt to avoid long first‑request latency.
        Returns True on success, False otherwise."""
        print(f"[OLLAMA] PreloadModel called for: {model}")
        if model in self.loaded_models:
            print(f"[OLLAMA] Model {model} already loaded")
            return True
        try:
            print(f"[OLLAMA] Sending preload request for {model}")
            data = {
                "model": model,
                "prompt": "Hello",
                "stream": False,
                "options": {"num_predict": 1}
            }
            response = requests.post(f"{self.base_url}/api/generate", json=data, timeout=30)
            response.raise_for_status()
            self.loaded_models.add(model)
            print(f"[OLLAMA] Model {model} preloaded successfully")
            return True
        except Exception as e:
            print(f"[OLLAMA] Preload failed for {model}: {e}")
            return False

    def keepalive(self, model: str) -> bool:
        """Send a lightweight ping to keep the model loaded (useful if USB drive spins down)."""
        if model not in self.loaded_models:
            return self.preload_model(model)
        try:
            data = {"model": model, "prompt": "", "stream": False, "options": {"num_predict": 0}}
            response = requests.post(f"{self.base_url}/api/generate", json=data, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def generate(self, model: str, prompt: str, options: Optional[Dict] = None, stream: bool = False) -> Dict[str, Any]:
        """Generate text using Ollama. Supports streaming for faster first token."""
        try:
            data = {
                "model": model,
                "prompt": prompt,
                "stream": stream
            }
            if options:
                data["options"] = options

            response = requests.post(f"{self.base_url}/api/generate", json=data, timeout=120)
            response.raise_for_status()
            if stream:
                # For streaming we return the raw response so the caller can iterate lines
                return response
            return response.json()
        except Exception as e:
            return {
                "response": f"Error calling Ollama: {str(e)}",
                "error": str(e)
            }


# Create a module-level instance
_ollama_instance = OllamaWrapper()

# Module functions that mimic the official ollama package
def list() -> Dict[str, Any]:
    """List available models"""
    return _ollama_instance.list()

def generate(model: str, prompt: str, options: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate text using Ollama"""
    return _ollama_instance.generate(model, prompt, options)
