# -*- coding: utf-8 -*-
"""
Semantic Reduction System - Production Version

A system that intelligently classifies and reduces data based on semantic value
instead of blindly storing all bits.

Core Architecture:
- DataClassifier: Rule-based and ML-based classification
- VideoAnalyzer: Surveillance video semantic analysis
- LogAnalyzer: Server log value analysis
- SemanticReducer: Main processing engine
- AuditLogger: Immutable audit trail
"""

__version__ = "1.0.0"
__semantic_reduction__ = True

from semantic_reduction.semantic_reducer import SemanticReducer
from semantic_reduction.utils.config import Config
from semantic_reduction.utils.logger import setup_logger

__all__ = [
    "SemanticReducer",
    "Config",
    "setup_logger",
]
