"""
M5 Monitor Module: System Monitoring and Dashboard

系统监控模块:
- 系统指标收集 (CPU/内存/磁盘/网络)
- 告警管理
- Prometheus 格式导出
- 监控面板 API
"""
import os
import sys
import psutil
import time
import threading
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import deque
from enum import Enum


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alert:
    """告警"""
    def __init__(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        metric: str = "",
        value: float = 0,
        threshold: float = 0
    ):
        self.alert_id = f"alert-{int(time.time() * 1000)}"
        self.level = level
        self.title = title
        self.message = message
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.timestamp = datetime.now().isoformat()
        self.acknowledged = False

    def to_dict(self) -> dict:
        return {
            'alert_id': self.alert_id,
            'level': self.level.value,
            'title': self.title,
            'message': self.message,
            'metric': self.metric,
            'value': self.value,
            'threshold': self.threshold,
            'timestamp': self.timestamp,
            'acknowledged': self.acknowledged
        }


@dataclass
class SystemMetrics:
    """系统指标"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    network_sent_mb: float = 0
    network_recv_mb: float = 0

    def to_dict(self) -> dict:
        return asdict(self)


class SystemMonitor:
    """
    系统监控器

    功能:
    - CPU/内存/磁盘/网络监控
    - 历史数据保留
    - 告警检测
    - Prometheus 格式导出
    """

    def __init__(
        self,
        history_size: int = 3600  # 保留 1 小时数据
    ):
        self.history_size = history_size
        self.metrics_history: deque = deque(maxlen=history_size)
        self.alerts: List[Alert] = []

        # 告警阈值
        self.thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0
        }

        # 回调
        self.alert_callbacks: List[callable] = []

        # 运行状态
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.collection_interval = 10  # 10 秒

    def set_threshold(self, metric: str, threshold: float):
        """设置告警阈值"""
        self.thresholds[metric] = threshold

    def add_alert_callback(self, callback: callable):
        """添加告警回调"""
        self.alert_callbacks.append(callback)

    def start(self):
        """启动监控"""
        if self.running:
            return
        self.running = True
        self.monitor_thread = threading.Thread(target=self._collect_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """停止监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

    def _collect_loop(self):
        """收集循环"""
        while self.running:
            try:
                self.collect_metrics()
            except Exception as e:
                print(f"[Monitor] Collection error: {e}")
            time.sleep(self.collection_interval)

    def collect_metrics(self) -> SystemMetrics:
        """收集系统指标"""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)

        # 内存
        mem = psutil.virtual_memory()
        memory_percent = mem.percent
        memory_used_gb = mem.used / 1024**3
        memory_total_gb = mem.total / 1024**3

        # 磁盘
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = disk.used / 1024**3
        disk_total_gb = disk.total / 1024**3

        # 网络
        net = psutil.net_io_counters()
        network_sent_mb = net.bytes_sent / 1024**2
        network_recv_mb = net.bytes_recv / 1024**2

        metrics = SystemMetrics(
            timestamp=datetime.now().isoformat(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            disk_percent=disk_percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            network_sent_mb=network_sent_mb,
            network_recv_mb=network_recv_mb
        )

        # 存储历史
        self.metrics_history.append(metrics)

        # 检查告警
        self._check_alerts(metrics)

        return metrics

    def _check_alerts(self, metrics: SystemMetrics):
        """检查告警"""
        alert_conditions = [
            ('cpu_percent', metrics.cpu_percent, self.thresholds['cpu_percent'], 'CPU 使用率过高'),
            ('memory_percent', metrics.memory_percent, self.thresholds['memory_percent'], '内存使用率过高'),
            ('disk_percent', metrics.disk_percent, self.thresholds['disk_percent'], '磁盘使用率过高')
        ]

        for metric, value, threshold, title in alert_conditions:
            if value > threshold:
                level = AlertLevel.WARNING if value < threshold * 1.1 else AlertLevel.CRITICAL
                alert = Alert(
                    level=level,
                    title=title,
                    message=f"{title} {value:.1f}% (阈值: {threshold}%)",
                    metric=metric,
                    value=value,
                    threshold=threshold
                )
                self.add_alert(alert)

    def add_alert(self, alert: Alert):
        """添加告警"""
        self.alerts.append(alert)
        self._persist_alert(alert)
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"[Monitor] Alert callback error: {e}")

    def _persist_alert(self, alert: Alert):
        """持久化告警到数据库"""
        import sqlite3, os
        try:
            db_path = os.environ.get('PRISTMAX_DB') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'tasks.db')
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute('''
                INSERT OR IGNORE INTO alert_history (alert_id,level,title,message,metric,value,threshold,timestamp)
                VALUES (?,?,?,?,?,?,?,?)
            ''', (alert.alert_id, alert.level.value, alert.title, alert.message,
                  alert.metric, alert.value, alert.threshold, alert.timestamp))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Monitor] Failed to persist alert: {e}")

    def acknowledge_alert(self, alert_id: str):
        """确认告警"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                self._persist_acknowledge(alert_id)

    def _persist_acknowledge(self, alert_id: str):
        """持久化告警确认"""
        import sqlite3, os
        try:
            from datetime import datetime
            db_path = os.environ.get('PRISTMAX_DB') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'tasks.db')
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute('''
                UPDATE alert_history SET acknowledged=1, acknowledged_at=? WHERE alert_id=?
            ''', (datetime.now().isoformat(), alert_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Monitor] Failed to persist ack: {e}")

    def load_alert_history(self, limit: int = 100):
        """从数据库加载历史告警"""
        import sqlite3, os
        try:
            db_path = os.environ.get('PRISTMAX_DB') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'tasks.db')
            conn = sqlite3.connect(db_path, check_same_thread=False)
            rows = conn.execute('''
                SELECT alert_id,level,title,message,metric,value,threshold,timestamp,acknowledged
                FROM alert_history ORDER BY timestamp DESC LIMIT ?
            ''', (limit,)).fetchall()
            conn.close()
            for row in rows:
                alert = Alert(
                    level=AlertLevel(row[1]),
                    title=row[2],
                    message=row[3] or '',
                    metric=row[4] or '',
                    value=row[5] or 0,
                    threshold=row[6] or 0
                )
                alert.alert_id = row[0]
                alert.timestamp = row[7]
                alert.acknowledged = bool(row[8])
                # 避免重复
                if not any(a.alert_id == alert.alert_id for a in self.alerts):
                    self.alerts.append(alert)
        except Exception as e:
            print(f"[Monitor] Failed to load alert history: {e}")

    def acknowledge_alert(self, alert_id: str):
        """确认告警"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True

    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """获取当前指标"""
        return self.metrics_history[-1] if self.metrics_history else None

    def get_metrics_history(self, minutes: int = 60) -> List[SystemMetrics]:
        """获取历史指标"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [
            m for m in self.metrics_history
            if datetime.fromisoformat(m.timestamp) > cutoff
        ]

    def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        return [a for a in self.alerts if not a.acknowledged]

    def export_prometheus(self) -> str:
        """导出 Prometheus 格式"""
        metrics = self.get_current_metrics()
        if not metrics:
            return ""

        lines = [
            "# HELP pristmax_cpu_usage CPU 使用率",
            "# TYPE pristmax_cpu_usage gauge",
            f"pristmax_cpu_usage {metrics.cpu_percent}",
            "",
            "# HELP pristmax_memory_usage 内存使用率",
            "# TYPE pristmax_memory_usage gauge",
            f"pristmax_memory_usage {metrics.memory_percent}",
            "",
            "# HELP pristmax_disk_usage 磁盘使用率",
            "# TYPE pristmax_disk_usage gauge",
            f"pristmax_disk_usage {metrics.disk_percent}",
            "",
            "# HELP pristmax_disk_bytes 磁盘字节",
            "# TYPE pristmax_disk_bytes gauge",
            f"pristmax_disk_used_bytes {int(metrics.disk_used_gb * 1024**3)}",
            f"pristmax_disk_total_bytes {int(metrics.disk_total_gb * 1024**3)}",
        ]
        return "\n".join(lines)

    def get_dashboard_data(self) -> Dict:
        """获取监控面板数据"""
        metrics = self.get_current_metrics()
        history = self.get_metrics_history(minutes=60)

        # 计算平均值
        avg_cpu = sum(m.cpu_percent for m in history) / len(history) if history else 0
        avg_memory = sum(m.memory_percent for m in history) / len(history) if history else 0
        avg_disk = sum(m.disk_percent for m in history) / len(history) if history else 0

        return {
            'current': metrics.to_dict() if metrics else {},
            'averages': {
                'cpu_percent': round(avg_cpu, 1),
                'memory_percent': round(avg_memory, 1),
                'disk_percent': round(avg_disk, 1)
            },
            'history': [m.to_dict() for m in history[-60:]],  # 最近 60 个点
            'alerts': [a.to_dict() for a in self.get_active_alerts()],
            'thresholds': self.thresholds
        }


# 全局监控器实例
_monitor: Optional[SystemMonitor] = None


def get_monitor() -> SystemMonitor:
    """获取全局监控器"""
    global _monitor
    if _monitor is None:
        _monitor = SystemMonitor()
        _monitor.load_alert_history()
    return _monitor


def main():
    """演示"""
    monitor = get_monitor()
    monitor.start()

    try:
        # 收集一次
        metrics = monitor.collect_metrics()
        print(f"[Monitor] CPU: {metrics.cpu_percent}%, Memory: {metrics.memory_percent}%, Disk: {metrics.disk_percent}%")

        # 获取面板数据
        dashboard = monitor.get_dashboard_data()
        print(f"[Monitor] Alerts: {len(dashboard['alerts'])}")

        # Prometheus 格式
        print(f"\n[Monitor] Prometheus:\n{monitor.export_prometheus()}")

    finally:
        monitor.stop()


if __name__ == '__main__':
    main()
