"""
M5 Web Module
"""
from .dashboard import (
    DashboardStats,
    TaskInfo,
    StorageVolume,
    DashboardData,
    generate_dashboard_html
)

__all__ = [
    'DashboardStats',
    'TaskInfo',
    'StorageVolume',
    'DashboardData',
    'generate_dashboard_html',
]
