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
    """Wrapper for Ollama API that can work without the official ollama package"""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def list(self) -> Dict[str, Any]:
        """List available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return {"models": response.json()["models"]}
        except Exception as e:
            # Return empty list if server is not available
            return {"models": []}

    def generate(self, model: str, prompt: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate text using Ollama"""
        try:
            data = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            if options:
                data["options"] = options

            response = requests.post(f"{self.base_url}/api/generate", json=data)
            response.raise_for_status()
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
