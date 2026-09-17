"""
M6 Auth Module: User Authentication and Authorization

用户认证与授权系统:
- 用户注册/登录 (JWT)
- 角色权限管理
- API 密钥认证
- 操作审计

核心原则:
- 密码加密存储 (bcrypt)
- JWT Token 认证
- 角色权限控制 (RBAC)
"""
import os
import sys
import json
import sqlite3
import hashlib
import secrets
import bcrypt
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from pathlib import Path
from enum import Enum
import jwt


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"      # 管理员
    OPERATOR = "operator"  # 操作员
    VIEWER = "viewer"    # 查看者


@dataclass
class User:
    """用户"""
    user_id: str
    username: str
    email: str
    role: UserRole = UserRole.VIEWER
    created_at: str = ""
    last_login: str = ""
    is_active: bool = True
    api_key: str = ""  # API 密钥

    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value,
            'created_at': self.created_at,
            'last_login': self.last_login,
            'is_active': self.is_active,
            # 不暴露密码和完整 API key
        }


@dataclass
class AuthToken:
    """认证令牌"""
    user_id: str
    username: str
    role: str
    token: str
    expires_at: str


class AuthDatabase:
    """认证数据库"""

    def __init__(self, db_path: str = "./auth.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'viewer',
                created_at TEXT,
                last_login TEXT,
                is_active INTEGER DEFAULT 1,
                api_key TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_username ON users(username)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_key ON users(api_key)
        """)
        self.conn.commit()

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.VIEWER
    ) -> Optional[User]:
        """创建用户"""
        import uuid

        # 检查用户名/邮箱是否已存在
        cursor = self.conn.execute(
            "SELECT user_id FROM users WHERE username = ? OR email = ?",
            (username, email)
        )
        if cursor.fetchone():
            return None

        # 密码哈希
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # 生成用户 ID 和 API Key
        user_id = str(uuid.uuid4())
        api_key = f"pk_{secrets.token_urlsafe(32)}"

        now = datetime.now().isoformat()

        self.conn.execute(
            """INSERT INTO users (user_id, username, email, password_hash, role, created_at, api_key)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, email, password_hash, role.value, now, api_key)
        )
        self.conn.commit()

        return User(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            created_at=now,
            api_key=api_key
        )

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """验证用户"""
        cursor = self.conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        # 验证密码
        password_hash = row[3]
        if not bcrypt.checkpw(password.encode(), password_hash.encode()):
            return None

        # 更新最后登录时间
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE users SET last_login = ? WHERE user_id = ?",
            (now, row[0])
        )
        self.conn.commit()

        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            role=UserRole(row[4]),
            created_at=row[5],
            last_login=now,
            is_active=bool(row[7]),
            api_key=row[8]
        )

    def authenticate_api_key(self, api_key: str) -> Optional[User]:
        """API Key 认证"""
        cursor = self.conn.execute(
            "SELECT * FROM users WHERE api_key = ? AND is_active = 1",
            (api_key,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            role=UserRole(row[4]),
            created_at=row[5],
            last_login=row[6],
            is_active=bool(row[7]),
            api_key=row[8]
        )

    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        cursor = self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            role=UserRole(row[4]),
            created_at=row[5],
            last_login=row[6],
            is_active=bool(row[7]),
            api_key=row[8]
        )

    def list_users(self) -> List[User]:
        """列出所有用户"""
        cursor = self.conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        users = []
        for row in cursor.fetchall():
            users.append(User(
                user_id=row[0],
                username=row[1],
                email=row[2],
                role=UserRole(row[4]),
                created_at=row[5],
                last_login=row[6],
                is_active=bool(row[7]),
                api_key=row[8]
            ))
        return users

    def close(self):
        """关闭数据库"""
        self.conn.close()


class JWTAuth:
    """JWT 认证"""

    def __init__(
        self,
        secret_key: str = None,
        algorithm: str = "HS256",
        token_expiry_hours: int = 24
    ):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = algorithm
        self.token_expiry_hours = token_expiry_hours

    def generate_token(self, user: User) -> AuthToken:
        """生成 JWT Token"""
        now = datetime.now()
        expires_at = now + timedelta(hours=self.token_expiry_hours)

        payload = {
            'user_id': user.user_id,
            'username': user.username,
            'role': user.role.value,
            'iat': now.timestamp(),
            'exp': expires_at.timestamp()
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        return AuthToken(
            user_id=user.user_id,
            username=user.username,
            role=user.role.value,
            token=token,
            expires_at=expires_at.isoformat()
        )

    def verify_token(self, token: str) -> Optional[Dict]:
        """验证 JWT Token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None


class AuthManager:
    """
    认证管理器

    整合用户管理、JWT 认证、API Key 认证
    """

    def __init__(
        self,
        db_path: str = "./auth.db",
        jwt_secret: str = None
    ):
        self.db = AuthDatabase(db_path)
        self.jwt_auth = JWTAuth(secret_key=jwt_secret)

    def register(
        self,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.VIEWER
    ) -> Optional[User]:
        """注册用户"""
        return self.db.create_user(username, email, password, role)

    def login(self, username: str, password: str) -> Optional[AuthToken]:
        """登录"""
        user = self.db.authenticate(username, password)
        if not user:
            return None

        return self.jwt_auth.generate_token(user)

    def login_api_key(self, api_key: str) -> Optional[AuthToken]:
        """API Key 登录"""
        user = self.db.authenticate_api_key(api_key)
        if not user:
            return None

        return self.jwt_auth.generate_token(user)

    def verify_token(self, token: str) -> Optional[Dict]:
        """验证 Token"""
        return self.jwt_auth.verify_token(token)

    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return self.db.get_user(user_id)

    def check_permission(self, token: str, required_role: UserRole) -> bool:
        """检查权限"""
        payload = self.verify_token(token)
        if not payload:
            return False

        role_order = {
            UserRole.ADMIN.value: 3,
            UserRole.OPERATOR.value: 2,
            UserRole.VIEWER.value: 1
        }

        user_level = role_order.get(payload.get('role', ''), 0)
        required_level = role_order.get(required_role.value, 0)

        return user_level >= required_level


def main():
    """演示"""
    auth = AuthManager()

    # 注册用户
    print("\n=== Register User ===")
    user = auth.register("admin", "admin@example.com", "password123", UserRole.ADMIN)
    if user:
        print(f"User created: {user.username} ({user.role.value})")
        print(f"API Key: {user.api_key}")
    else:
        print("User already exists")

    # 登录
    print("\n=== Login ===")
    token = auth.login("admin", "password123")
    if token:
        print(f"Token: {token.token[:50]}...")
        print(f"Expires: {token.expires_at}")
    else:
        print("Login failed")

    # 验证 Token
    print("\n=== Verify Token ===")
    payload = auth.verify_token(token.token)
    if payload:
        print(f"User: {payload.get('username')}, Role: {payload.get('role')}")

    # API Key 登录
    print("\n=== API Key Login ===")
    if user:
        api_token = auth.login_api_key(user.api_key)
        if api_token:
            print(f"API Key Login: {api_token.username}")


if __name__ == '__main__':
    main()
