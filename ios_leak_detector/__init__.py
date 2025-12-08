"""
iOS Memory Leak Detector - Static Analysis Tool

Detects potential memory leaks and performance issues in Swift/Objective-C code:
- Strong reference cycles
- Missing [weak self] in closures
- Non-weak delegates
- Unremoved observers/timers
- Retain cycles in blocks (Objective-C)
"""

__version__ = "1.0.0"
__author__ = "yoon-k"

from .analyzer import MemoryLeakAnalyzer
from .swift_parser import SwiftParser
from .objc_parser import ObjCParser
from .patterns import LeakPattern, LeakSeverity
from .reporter import Reporter

__all__ = [
    "MemoryLeakAnalyzer",
    "SwiftParser",
    "ObjCParser",
    "LeakPattern",
    "LeakSeverity",
    "Reporter",
]
