"""
Semantic-Aware Data Reduction System

A system that intelligently classifies and reduces data based on semantic value
instead of blindly storing all bits.

Core Architecture:
- DataClassifier: Rule-based and ML-based classification
- VideoAnalyzer: Surveillance video semantic analysis
- LogAnalyzer: Server log value analysis
- SemanticReducer: Main processing engine
- AuditLogger: Immutable audit trail

Target Markets:
- Surveillance video storage (primary)
- Server log reduction
- Medical imaging
- UGC content platforms
"""

__version__ = "0.1.0"
__semantic_reduction__ = True

from semantic_reducer import (
    DataValue,
    ReductionAction,
    DataClassifier,
    VideoAnalyzer,
    LogAnalyzer,
    ReductionPolicy,
    AuditRecord,
    AuditLogger,
    SemanticReducer,
    DataValueCalculator,
)

from semantic.video_analyzer import (
    VideoAnalyzer as AdvancedVideoAnalyzer,
    MotionDetector,
    SceneClassifier,
    FrameAnalysis,
    ClipAnalysis,
)

from semantic.surveillance_policy import (
    SurveillancePolicy,
    SurveillancePolicyEngine,
    PreservationPriority,
)

from semantic.log_analyzer import (
    LogAnalyzer,
    LogParser,
    LogLevel,
    LogType,
    LogLine,
    LogBlock,
    KeywordExtractor,
    AnomalyDetector,
)

from semantic.log_policy import (
    LogPolicy,
    LogPolicyEngine,
    LogSamplingStrategy,
)

from semantic.audit_store import (
    AuditStore,
    AuditEntry,
    AuditEventType,
)

from semantic.compliance_reporter import (
    ComplianceReporter,
    ComplianceStandard,
    ComplianceReport,
    ComplianceFinding,
)

from semantic.policy_manager import (
    PolicyManager,
    PolicyVersion,
    PolicyChangeRecord,
    PolicyStatus,
)

__all__ = [
    # Core
    "DataValue",
    "ReductionAction",
    "DataClassifier",
    "VideoAnalyzer",
    "LogAnalyzer",
    "ReductionPolicy",
    "AuditRecord",
    "AuditLogger",
    "SemanticReducer",
    "DataValueCalculator",

    # Video
    "AdvancedVideoAnalyzer",
    "MotionDetector",
    "SceneClassifier",
    "FrameAnalysis",
    "ClipAnalysis",
    "SurveillancePolicy",
    "SurveillancePolicyEngine",
    "PreservationPriority",

    # Log
    "LogParser",
    "LogLevel",
    "LogType",
    "LogLine",
    "LogBlock",
    "KeywordExtractor",
    "AnomalyDetector",
    "LogPolicy",
    "LogPolicyEngine",
    "LogSamplingStrategy",

    # Audit & Compliance
    "AuditStore",
    "AuditEntry",
    "AuditEventType",
    "ComplianceReporter",
    "ComplianceStandard",
    "ComplianceReport",
    "ComplianceFinding",
    "PolicyManager",
    "PolicyVersion",
    "PolicyChangeRecord",
    "PolicyStatus",
]
