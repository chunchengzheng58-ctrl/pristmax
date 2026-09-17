"""
M5 Web Module: Dashboard and UI Components

M5 核心模块: Web 界面组件。

功能:
- 仪表盘
- 任务管理
- 存储概览
- 策略配置
- 实时监控
"""
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class DashboardStats:
    """仪表盘统计"""
    # 存储
    total_storage_gb: float = 0
    used_storage_gb: float = 0
    available_storage_gb: float = 0
    storage_usage_percent: float = 0

    # 任务
    total_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # 去重
    total_chunks: int = 0
    unique_chunks: int = 0
    dedup_ratio: float = 0
    saved_gb: float = 0

    # 策略
    active_strategies: int = 0
    total_strategies: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    strategy_name: str
    input_path: str
    status: str
    progress: float = 0

    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # 结果
    original_size: int = 0
    compressed_size: int = 0
    psnr: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StorageVolume:
    """存储卷"""
    name: str
    mount_point: str
    storage_type: str  # local, nas, cloud
    total_gb: float = 0
    used_gb: float = 0
    available_gb: float = 0

    # 性能
    read_speed_mbps: float = 0
    write_speed_mbps: float = 0

    # 状态
    status: str = "healthy"  # healthy, warning, error
    health_percent: float = 100

    @property
    def usage_percent(self) -> float:
        if self.total_gb == 0:
            return 0
        return (self.used_gb / self.total_gb) * 100

    def to_dict(self) -> dict:
        return asdict(self)


class DashboardData:
    """仪表盘数据生成器"""

    def __init__(self, api_base_url: str = "http://localhost:5001"):
        self.api_base_url = api_base_url

    def get_stats(self) -> DashboardStats:
        """获取统计"""
        # 从 API 获取
        try:
            import requests
            resp = requests.get(f"{self.api_base_url}/api/stats", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return DashboardStats(**data)
        except Exception:
            pass

        # 返回模拟数据
        return DashboardStats(
            total_storage_gb=1000,
            used_storage_gb=350,
            available_storage_gb=650,
            storage_usage_percent=35,
            total_tasks=100,
            pending_tasks=5,
            running_tasks=2,
            completed_tasks=90,
            failed_tasks=3,
            total_chunks=10000,
            unique_chunks=7500,
            dedup_ratio=0.25,
            saved_gb=50,
            active_strategies=2,
            total_strategies=4
        )

    def get_recent_tasks(self, limit: int = 10) -> List[TaskInfo]:
        """获取最近任务"""
        return [
            TaskInfo(
                task_id=f"task-{i:04d}",
                strategy_name="ROI + 背景模糊",
                input_path=f"/videos/camera_{i}.mp4",
                status="completed" if i % 5 != 0 else "failed",
                progress=100 if i % 5 != 0 else 0,
                original_size=100 * 1024 * 1024,
                compressed_size=70 * 1024 * 1024,
                psnr=35.0,
                created_at=datetime.now().isoformat()
            )
            for i in range(limit)
        ]

    def get_storage_volumes(self) -> List[StorageVolume]:
        """获取存储卷"""
        return [
            StorageVolume(
                name="主存储",
                mount_point="/mnt/storage",
                storage_type="local",
                total_gb=500,
                used_gb=200,
                available_gb=300,
                read_speed_mbps=550,
                write_speed_mbps=300,
                status="healthy"
            ),
            StorageVolume(
                name="NAS备份",
                mount_point="/mnt/nas",
                storage_type="nas",
                total_gb=2000,
                used_gb=800,
                available_gb=1200,
                read_speed_mbps=100,
                write_speed_mbps=80,
                status="healthy"
            ),
            StorageVolume(
                name="云存储",
                mount_point="s3://bucket",
                storage_type="cloud",
                total_gb=10000,
                used_gb=2500,
                available_gb=7500,
                read_speed_mbps=50,
                write_speed_mbps=30,
                status="warning",
                health_percent=95
            )
        ]

    def get_dedup_chart(self) -> Dict[str, Any]:
        """获取去重图表数据"""
        return {
            'labels': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
            'datasets': [
                {
                    'label': '去重节省 (GB)',
                    'data': [10, 15, 12, 18, 20, 25, 22]
                },
                {
                    'label': '新数据 (GB)',
                    'data': [50, 45, 55, 48, 52, 58, 60]
                }
            ]
        }

    def get_compression_chart(self) -> Dict[str, Any]:
        """获取压缩效果图表"""
        return {
            'labels': ['ROI模糊', 'ASVC', 'BLUE', 'H.265基线'],
            'datasets': [
                {
                    'label': '压缩率 (%)',
                    'data': [45, 38, 42, 30]
                }
            ]
        }


def generate_dashboard_html() -> str:
    """生成仪表盘 HTML"""
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pristmax - 智能存储优化平台</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20120%20120%22%20style%3D%22color%3A%23173D58%22%3E%3Cpath%20fill%3D%22currentColor%22%20d%3D%22M60%2012C84%2012%20104%2029%20108%2051C94%2040%2081%2036%2066%2040L47%2045C38%2047%2031%2042%2032%2034C34%2023%2047%2012%2060%2012Z%22%20transform%3D%22rotate%280%2060%2060%29%22%2F%3E%3Cpath%20fill%3D%22currentColor%22%20d%3D%22M60%2012C84%2012%20104%2029%20108%2051C94%2040%2081%2036%2066%2040L47%2045C38%2047%2031%2042%2032%2034C34%2023%2047%2012%2060%2012Z%22%20transform%3D%22rotate%28120%2060%2060%29%22%2F%3E%3Cpath%20fill%3D%22currentColor%22%20d%3D%22M60%2012C84%2012%20104%2029%20108%2051C94%2040%2081%2036%2066%2040L47%2045C38%2047%2031%2042%2032%2034C34%2023%2047%2012%2060%2012Z%22%20transform%3D%22rotate%28240%2060%2060%29%22%2F%3E%3C%2Fsvg%3E">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a1520;
            color: #e0e6ed;
        }

        .dashboard {
            display: grid;
            grid-template-columns: 280px 1fr;
            min-height: 100vh;
        }

        .sidebar {
            background: #121414;
            border-right: 1px solid rgba(255,255,255,0.1);
            padding: 24px;
        }

        .logo {
            font-size: 24px;
            font-weight: 700;
            color: #7ec8e3;
            margin-bottom: 40px;
        }

        .nav-item {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .nav-item:hover, .nav-item.active {
            background: rgba(126,200,227,0.15);
            color: #7ec8e3;
        }

        .main {
            padding: 32px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
        }

        .header h1 {
            font-size: 28px;
            font-weight: 600;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 32px;
        }

        .stat-card {
            background: rgba(18,20,20,0.8);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 12px;
            padding: 24px;
        }

        .stat-label {
            color: #8899a6;
            font-size: 14px;
            margin-bottom: 8px;
        }

        .stat-value {
            font-size: 32px;
            font-weight: 600;
            color: #7ec8e3;
        }

        .stat-sub {
            font-size: 12px;
            color: #8899a6;
            margin-top: 4px;
        }

        .card {
            background: rgba(18,20,20,0.8);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }

        .card-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 20px;
        }

        .volume-list {
            display: grid;
            gap: 16px;
        }

        .volume-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
        }

        .volume-name {
            font-weight: 500;
        }

        .volume-type {
            font-size: 12px;
            color: #8899a6;
            background: rgba(255,255,255,0.1);
            padding: 2px 8px;
            border-radius: 4px;
            margin-left: 8px;
        }

        .volume-stats {
            text-align: right;
        }

        .progress-bar {
            width: 200px;
            height: 6px;
            background: rgba(255,255,255,0.1);
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #7ec8e3, #5ba3c6);
            border-radius: 3px;
        }

        .task-list {
            display: grid;
            gap: 12px;
        }

        .task-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
        }

        .task-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .task-name {
            font-weight: 500;
        }

        .task-path {
            font-size: 12px;
            color: #8899a6;
        }

        .task-status {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }

        .status-completed { background: rgba(76,175,80,0.2); color: #4caf50; }
        .status-running { background: rgba(33,150,243,0.2); color: #2196f3; }
        .status-failed { background: rgba(244,67,54,0.2); color: #f44336; }
        .status-pending { background: rgba(255,193,7,0.2); color: #ffc107; }
    </style>
<style>
/* Pristmax identity: ink blue / glacier / white. */
:root{--bg-dark:#f2f7fb;--bg-card:#fff;--border:#cfdee8;--text-primary:#173d58;--text-secondary:#587185;--accent:#285775;--accent-dim:#1b405b;--success:#287054;--warning:#8a6214;--error:#b13a46}
body{color:#173d58;background:#f2f7fb}
.header{background:#ffffff;border-color:#cfdee8;padding:18px 30px;box-shadow:none}
.logo{color:#173d58;font-weight:650;letter-spacing:-.5px}
.sidebar{background:#eaf2f8;border-color:#cfdee8;padding-top:32px}
.sidebar-title{font-size:10px;letter-spacing:2px;color:#627e92}
.sidebar-item,.nav-item{border-radius:3px}
.sidebar-item.active,.nav-item.active{background:#dcebf5;color:#173d58}
.main{padding:36px;min-width:0}
.page-title{font-weight:500;font-size:28px;letter-spacing:-.5px}
.stat-card,.card{background:white;border-color:#cfdee8;border-radius:5px;box-shadow:none}
.stat-card:hover{transform:none}
.stat-card{border-top:2px solid #8ab1ca}
.stat-value{font-family:'Segoe UI',Arial,sans-serif;font-size:36px;font-weight:400;line-height:1.3;font-variant-numeric:lining-nums tabular-nums;letter-spacing:0;color:#173d58}
.table{font-variant-numeric:lining-nums tabular-nums}
.card-title{font-size:17px;font-weight:600}
.btn{border-radius:3px;min-height:38px}
.btn-primary{background:#173d58;color:#fff;border-color:#173d58}
.btn-primary:hover{background:#2a5875}
.progress{background:#e4eef5}
.progress-fill,.chart-bar{background:#689dbc}
.modal-content{background:#fff;max-width:calc(100vw - 32px);max-height:90vh;overflow:auto;border-radius:6px;box-shadow:0 24px 90px #0e293d35}
.form-input{background:#f5f9fc;color:#173d58;border-color:#bfd2e0}
.form-input:focus{outline:2px solid #91b8d0;outline-offset:2px}
.badge-info{background:#e1eff8;color:#245779}
.brand-context{display:flex;justify-content:space-between;gap:12px;margin-bottom:28px;padding-bottom:16px;border-bottom:1px solid #ccdde8;font:10px/1.7 Consolas,monospace;letter-spacing:1.3px;color:#56758a}
.brand-context span:last-child{font-family:'Segoe UI',sans-serif;letter-spacing:0}
@media(max-width:1000px){.layout{grid-template-columns:190px minmax(0,1fr)}.stats-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.main{padding:24px}.header{flex-wrap:wrap;gap:16px}.nav{flex-wrap:wrap}.card{overflow-x:auto}}
@media(max-width:650px){.layout{display:block}.sidebar{display:none}.main{padding:20px 14px}.header{padding:16px}.header .nav{order:3;width:100%;overflow-x:auto;flex-wrap:nowrap}.nav-item{white-space:nowrap;padding:7px 12px}.stats-grid{gap:10px}.stat-card{padding:16px}.stat-value{font-size:29px}.brand-context{flex-direction:column}.card{padding:18px}.table{min-width:550px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

</style>
</head>
<body>
    <div class="dashboard">
        <div class="sidebar">
            <div class="logo" style="display:flex;align-items:center;gap:10px"><svg class="logo-icon" width="34" height="34" viewBox="0 0 120 120" aria-hidden="true"><path fill="currentColor" d="M60 12C84 12 104 29 108 51C94 40 81 36 66 40L47 45C38 47 31 42 32 34C34 23 47 12 60 12Z" transform="rotate(0 60 60)"/><path fill="currentColor" d="M60 12C84 12 104 29 108 51C94 40 81 36 66 40L47 45C38 47 31 42 32 34C34 23 47 12 60 12Z" transform="rotate(120 60 60)"/><path fill="currentColor" d="M60 12C84 12 104 29 108 51C94 40 81 36 66 40L47 45C38 47 31 42 32 34C34 23 47 12 60 12Z" transform="rotate(240 60 60)"/></svg><span>Pristmax</span></div>
            <nav>
                <div class="nav-item active">仪表盘</div>
                <div class="nav-item">任务管理</div>
                <div class="nav-item">存储卷</div>
                <div class="nav-item">策略配置</div>
                <div class="nav-item">监控告警</div>
                <div class="nav-item">系统设置</div>
            </nav>
        </div>
        <div class="main">
            <div class="header">
                <h1>仪表盘</h1>
                <button onclick="location.reload()">刷新</button>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">存储使用</div>
                    <div class="stat-value">35%</div>
                    <div class="stat-sub">350 GB / 1000 GB</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">去重节省</div>
                    <div class="stat-value">50 GB</div>
                    <div class="stat-sub">25% 重复率</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">活跃任务</div>
                    <div class="stat-value">7</div>
                    <div class="stat-sub">2 运行中, 5 等待</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">策略状态</div>
                    <div class="stat-value">2/4</div>
                    <div class="stat-sub">ROI模糊 + H.265基线</div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">存储卷</div>
                <div class="volume-list">
                    <div class="volume-item">
                        <div>
                            <span class="volume-name">主存储</span>
                            <span class="volume-type">本地</span>
                        </div>
                        <div class="volume-stats">
                            <div>200 GB / 500 GB</div>
                            <div class="progress-bar"><div class="progress-fill" style="width:40%"></div></div>
                        </div>
                    </div>
                    <div class="volume-item">
                        <div>
                            <span class="volume-name">NAS备份</span>
                            <span class="volume-type">NAS</span>
                        </div>
                        <div class="volume-stats">
                            <div>800 GB / 2000 GB</div>
                            <div class="progress-bar"><div class="progress-fill" style="width:40%"></div></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">最近任务</div>
                <div class="task-list">
                    <div class="task-item">
                        <div class="task-info">
                            <div class="task-name">ROI + 背景模糊</div>
                            <div class="task-path">/videos/camera_01.mp4</div>
                        </div>
                        <span class="task-status status-completed">已完成</span>
                    </div>
                    <div class="task-item">
                        <div class="task-info">
                            <div class="task-name">H.265 基线</div>
                            <div class="task-path">/videos/camera_02.mp4</div>
                        </div>
                        <span class="task-status status-running">运行中</span>
                    </div>
                    <div class="task-item">
                        <div class="task-info">
                            <div class="task-name">ASVC</div>
                            <div class="task-path">/videos/camera_03.mp4</div>
                        </div>
                        <span class="task-status status-failed">失败</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""


def main():
    """生成仪表盘 HTML"""
    html = generate_dashboard_html()
    with open('./dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("[Web] Dashboard generated: ./dashboard.html")


if __name__ == '__main__':
    main()
