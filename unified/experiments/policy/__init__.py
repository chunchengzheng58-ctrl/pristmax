"""
M3 Policy Module: Enterprise Policy Integration

M3 核心模块:
- PolicyEngine: 策略插件系统
- FileStateMachine: 文件状态机
- TaskQueue: 任务队列与资源管理

状态机:
discovered → encoded → validated → published → retirement_eligible → retired

策略类型:
- ROI_BLUR: M1 ROI + 背景模糊
- ASVC: M2 ASVC 背景差分
- BLUE: M2 BLUE 背景冻结
- BASELINE: H.265 基线
"""

from .policy.engine import (
    PolicyEngine,
    Strategy,
    StrategyType,
    TaskResult,
    TaskStatus,
    create_default_strategies
)

from .policy.state_machine import (
    FileStateMachine,
    FileState,
    FileRecord,
    StateTransition,
    VALID_TRANSITIONS
)

from .policy.task_queue import (
    TaskQueue,
    QueuedTask,
    TaskPriority,
    TaskState,
    ResourceLimit
)

__all__ = [
    # Policy Engine
    'PolicyEngine',
    'Strategy',
    'StrategyType',
    'TaskResult',
    'TaskStatus',
    'create_default_strategies',

    # State Machine
    'FileStateMachine',
    'FileState',
    'FileRecord',
    'StateTransition',
    'VALID_TRANSITIONS',

    # Task Queue
    'TaskQueue',
    'QueuedTask',
    'TaskPriority',
    'TaskState',
    'ResourceLimit',
]
