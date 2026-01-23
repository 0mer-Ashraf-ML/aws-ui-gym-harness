"""
EnvState dataclass for Gemini Computer Use compatibility
"""
from dataclasses import dataclass


@dataclass
class EnvState:
    """Environment state returned after each action"""
    screenshot: bytes
    url: str
    timestamp: str
