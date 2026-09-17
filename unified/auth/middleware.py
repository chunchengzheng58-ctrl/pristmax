"""
Auth Middleware: Authentication Middleware for Flask

认证中间件:
- JWT Token 验证
- API Key 验证
- 角色权限检查
"""
from functools import wraps
from flask import request, jsonify, g
from typing import Optional, Callable
import os

# 全局 AuthManager 实例
_auth_manager = None


def get_auth_manager():
    """获取认证管理器"""
    global _auth_manager
    if _auth_manager is None:
        from auth.models import AuthManager
        db_path = os.environ.get('PRISTMAX_AUTH_DB', os.environ.get('PRISTINE_AUTH_DB', './auth.db'))
        jwt_secret = os.environ.get('PRISTMAX_JWT_SECRET', os.environ.get('PRISTINE_JWT_SECRET'))
        _auth_manager = AuthManager(db_path=db_path, jwt_secret=jwt_secret)
    return _auth_manager


def extract_token_from_header() -> Optional[str]:
    """从请求头提取 Token"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def extract_api_key_from_header() -> Optional[str]:
    """从请求头提取 API Key"""
    # 从 X-API-Key 头提取
    api_key = request.headers.get('X-API-Key', '')
    if api_key:
        return api_key

    # 从 Authorization 头提取 (ApiKey scheme)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('ApiKey '):
        return auth_header[7:]

    return None


def require_auth(f: Callable) -> Callable:
    """
    要求认证装饰器

    使用方式:
    @app.route('/api/protected')
    @require_auth
    def protected_endpoint():
        user = g.current_user
        return jsonify({'user': user.username})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = extract_token_from_header()
        api_key = None

        # 尝试 Token 认证
        if token:
            auth = get_auth_manager()
            payload = auth.verify_token(token)
            if payload:
                user = auth.get_user(payload.get('user_id'))
                if user:
                    g.current_user = user
                    g.auth_type = 'token'
                    return f(*args, **kwargs)

        # 尝试 API Key 认证
        api_key = extract_api_key_from_header()
        if api_key:
            auth = get_auth_manager()
            user = auth.db.authenticate_api_key(api_key)
            if user:
                g.current_user = user
                g.auth_type = 'api_key'
                return f(*args, **kwargs)

        return jsonify({
            'error': 'Authentication required',
            'message': 'Please provide a valid token or API key'
        }), 401

    return decorated


def require_role(required_role: str) -> Callable:
    """
    要求特定角色装饰器

    使用方式:
    @app.route('/api/admin')
    @require_auth
    @require_role('admin')
    def admin_endpoint():
        return jsonify({'message': 'Admin access granted'})
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            # 先检查认证
            token = extract_token_from_header()
            api_key = None

            user = None
            auth = get_auth_manager()

            if token:
                payload = auth.verify_token(token)
                if payload:
                    user = auth.get_user(payload.get('user_id'))

            if not user:
                api_key = extract_api_key_from_header()
                if api_key:
                    user = auth.db.authenticate_api_key(api_key)

            if not user:
                return jsonify({
                    'error': 'Authentication required'
                }), 401

            # 检查角色权限
            role_hierarchy = {
                'admin': 3,
                'operator': 2,
                'viewer': 1
            }

            user_level = role_hierarchy.get(user.role.value, 0)
            required_level = role_hierarchy.get(required_role, 0)

            if user_level < required_level:
                return jsonify({
                    'error': 'Insufficient permissions',
                    'required_role': required_role,
                    'your_role': user.role.value
                }), 403

            g.current_user = user
            return f(*args, **kwargs)

        return decorated
    return decorator


def optional_auth(f: Callable) -> Callable:
    """
    可选认证装饰器

    如果提供了有效的认证信息，则设置 g.current_user
    否则继续执行，但不设置 g.current_user
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_user = None

        token = extract_token_from_header()
        if token:
            auth = get_auth_manager()
            payload = auth.verify_token(token)
            if payload:
                user = auth.get_user(payload.get('user_id'))
                if user:
                    g.current_user = user
                    g.auth_type = 'token'

        if not g.current_user:
            api_key = extract_api_key_from_header()
            if api_key:
                auth = get_auth_manager()
                user = auth.db.authenticate_api_key(api_key)
                if user:
                    g.current_user = user
                    g.auth_type = 'api_key'

        return f(*args, **kwargs)

    return decorated


def get_current_user():
    """获取当前用户"""
    return getattr(g, 'current_user', None)


def is_authenticated() -> bool:
    """检查是否已认证"""
    return get_current_user() is not None
