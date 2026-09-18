"""
Notification System: Webhook and Email alerts

支持:
- Webhook HTTP POST 通知
- Email 邮件通知
- 通知历史记录
- 失败重试
"""
import os
import sys
import json
import sqlite3
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor


@dataclass
class NotificationChannel:
    """通知渠道"""
    id: str
    type: str  # webhook, email
    name: str
    config: dict
    enabled: bool = True


class NotificationManager:
    """通知管理器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.environ.get('PRISTMAX_DB', os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'tasks.db'))
        self.db_path = db_path
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._channels: Optional[List[NotificationChannel]] = None

    def _get_db(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def get_channels(self, include_disabled=False) -> List[NotificationChannel]:
        """获取所有通知渠道"""
        conn = self._get_db()
        try:
            if include_disabled:
                rows = conn.execute("SELECT id, type, name, config, enabled FROM notification_channels").fetchall()
            else:
                rows = conn.execute("SELECT id, type, name, config, enabled FROM notification_channels WHERE enabled = 1").fetchall()
            channels = []
            for row in rows:
                try:
                    config = json.loads(row[3]) if row[3] else {}
                except Exception:
                    config = {}
                channels.append(NotificationChannel(
                    id=row[0], type=row[1], name=row[2], config=config, enabled=bool(row[4])))
            return channels
        finally:
            conn.close()

    def add_channel(self, channel_type: str, name: str, config: dict) -> str:
        """添加通知渠道"""
        import uuid
        channel_id = f"{channel_type}-{uuid.uuid4().hex[:8]}"
        conn = self._get_db()
        try:
            from datetime import datetime
            conn.execute('''
                INSERT INTO notification_channels (id, type, name, config, enabled, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
            ''', (channel_id, channel_type, name, json.dumps(config, ensure_ascii=False), datetime.now().isoformat()))
            conn.commit()
            self._channels = None  # invalidate cache
            return channel_id
        finally:
            conn.close()

    def remove_channel(self, channel_id: str) -> bool:
        conn = self._get_db()
        try:
            conn.execute("DELETE FROM notification_channels WHERE id = ?", (channel_id,))
            conn.commit()
            self._channels = None
            return True
        finally:
            conn.close()

    def send_alert(self, alert) -> dict:
        """
        发送告警到所有启用的渠道
        返回: {channel_id: {'status': 'sent'|'failed', 'error': ...}}
        """
        results = {}
        channels = self.get_channels()
        if not channels:
            return results

        for channel in channels:
            future = self.executor.submit(self._send_to_channel, channel, alert)
            results[channel.id] = future

        # 收集结果
        final_results = {}
        for channel_id, future in results.items():
            try:
                final_results[channel_id] = future.result(timeout=10)
            except Exception as e:
                final_results[channel_id] = {'status': 'failed', 'error': str(e)}

        return final_results

    def _send_to_channel(self, channel: NotificationChannel, alert) -> dict:
        """发送到单个渠道"""
        alert_data = {
            'alert_id': alert.alert_id,
            'level': alert.level.value,
            'title': alert.title,
            'message': alert.message,
            'metric': alert.metric,
            'value': alert.value,
            'threshold': alert.threshold,
            'timestamp': alert.timestamp
        }

        try:
            if channel.type == 'webhook':
                self._send_webhook(channel, alert_data)
            elif channel.type == 'email':
                self._send_email(channel, alert_data)
            else:
                raise ValueError(f"Unknown channel type: {channel.type}")

            self._log_notification(channel.id, alert.alert_id, 'sent', level=alert.level.value, title=alert.title)
            return {'status': 'sent'}
        except Exception as e:
            self._log_notification(channel.id, alert.alert_id, 'failed', str(e), level=alert.level.value, title=alert.title)
            return {'status': 'failed', 'error': str(e)}

    def _send_webhook(self, channel: NotificationChannel, alert_data: dict):
        """发送 Webhook"""
        config = channel.config
        url = config.get('url')
        if not url:
            raise ValueError("Webhook URL not configured")

        headers = config.get('headers', {})
        timeout = config.get('timeout', 10)

        body = json.dumps(alert_data, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={**headers, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status < 200 or resp.status >= 300:
                    raise Exception(f"Webhook returned {resp.status}")
        except urllib.error.HTTPError as e:
            raise Exception(f"Webhook HTTP {e.code}: {e.read().decode()[:200]}")
        except urllib.error.URLError as e:
            raise Exception(f"Webhook URL error: {e.reason}")

    def _send_email(self, channel: NotificationChannel, alert_data: dict):
        """发送邮件"""
        config = channel.config
        smtp_host = config.get('smtp_host')
        smtp_port = config.get('smtp_port', 587)
        smtp_user = config.get('smtp_user')
        smtp_password = config.get('smtp_password')
        from_addr = config.get('from', smtp_user)
        to_addrs = config.get('to_addrs', [])

        if not smtp_host or not to_addrs:
            raise ValueError("SMTP or recipients not configured")

        level_colors = {
            'info': '#2196F3',
            'warning': '#ff9800',
            'critical': '#f44336'
        }
        color = level_colors.get(alert_data['level'], '#666')

        html_body = f"""
        <html><body style="font-family: Arial, sans-serif;">
        <div style="border-left: 4px solid {color}; padding: 12px 16px; background: #f9f9f9;">
            <h2 style="margin: 0 0 8px;">{alert_data['title']}</h2>
            <p style="margin: 0; color: #666;">{alert_data['message']}</p>
        </div>
        <table style="margin-top: 16px; font-size: 14px;">
            <tr><td style="padding: 4px 8px;"><b>级别</b></td><td>{alert_data['level'].upper()}</td></tr>
            <tr><td style="padding: 4px 8px;"><b>指标</b></td><td>{alert_data['metric']}</td></tr>
            <tr><td style="padding: 4px 8px;"><b>当前值</b></td><td>{alert_data['value']:.1f}</td></tr>
            <tr><td style="padding: 4px 8px;"><b>阈值</b></td><td>{alert_data['threshold']}</td></tr>
            <tr><td style="padding: 4px 8px;"><b>时间</b></td><td>{alert_data['timestamp']}</td></tr>
        </table>
        </body></html>
        """

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{alert_data['level'].upper()}] {alert_data['title']}"
        msg['From'] = from_addr
        msg['To'] = ', '.join(to_addrs)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, to_addrs, msg.as_string())

    def _log_notification(self, channel_id: str, alert_id: str, status: str, error: str = None, level: str = None, title: str = None):
        """记录发送日志"""
        conn = self._get_db()
        try:
            conn.execute('''
                INSERT INTO notification_log (channel_id, alert_id, status, error, sent_at, level, title)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (channel_id, alert_id, status, error, datetime.now().isoformat(), level, title))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def get_notification_history(self, limit: int = 50) -> List[dict]:
        """获取通知历史"""
        conn = self._get_db()
        try:
            rows = conn.execute('''
                SELECT nl.id, nc.name, nl.alert_id, nl.level, nl.title, nl.status, nl.error, nl.sent_at
                FROM notification_log nl
                LEFT JOIN notification_channels nc ON nl.channel_id = nc.id
                ORDER BY nl.sent_at DESC LIMIT ?
            ''', (limit,)).fetchall()
            return [
                {'id': r[0], 'channel': r[1] or r[2], 'alert_id': r[2], 'level': r[3],
                 'title': r[4], 'status': r[5], 'error': r[6], 'sent_at': r[7]}
                for r in rows
            ]
        finally:
            conn.close()


# 全局实例
_notification_manager: Optional[NotificationManager] = None

def get_notification_manager() -> NotificationManager:
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
