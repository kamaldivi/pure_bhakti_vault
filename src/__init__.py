"""
Main package initialization
"""

__version__ = "0.1.0"
__author__ = "Radha Kanta Dasa"

# Import main modules to make them available at package level
from . import concepts
from . import config
from . import utils

__all__ = [
    "concepts",
    "config", 
    "utils"
]