"""core 层统一导出入口。"""

from .capabilities import MethodCapability, TaskFamily, validate_compatibility
from .entities import (
    AddResult,
    AnswerResult,
    Conversation,
    Dataset,
    EvaluationResult,
    GoldAnswerInfo,
    ImageRef,
    MetricResult,
    Question,
    RetrievedMemory,
    RetrievalResult,
    Session,
    Turn,
)
from .exceptions import (
    AdapterAlreadyRegisteredError,
    ConfigurationError,
    DataLeakageError,
    DatasetNotFoundError,
    DatasetValidationError,
    JudgeOutputError,
    MemoryBenchmarkError,
    UnknownBenchmarkError,
)
from .interfaces import BaseMemoryRetriever, BaseMemorySystem, BaseResumableMemorySystem
from .results import DryRunSummary

__all__ = [
    "AddResult",
    "AdapterAlreadyRegisteredError",
    "AnswerResult",
    "BaseMemoryRetriever",
    "BaseResumableMemorySystem",
    "BaseMemorySystem",
    "ConfigurationError",
    "Conversation",
    "DataLeakageError",
    "Dataset",
    "DatasetNotFoundError",
    "DatasetValidationError",
    "DryRunSummary",
    "EvaluationResult",
    "GoldAnswerInfo",
    "ImageRef",
    "JudgeOutputError",
    "MethodCapability",
    "MemoryBenchmarkError",
    "MetricResult",
    "Question",
    "RetrievedMemory",
    "RetrievalResult",
    "Session",
    "TaskFamily",
    "Turn",
    "UnknownBenchmarkError",
    "validate_compatibility",
]
