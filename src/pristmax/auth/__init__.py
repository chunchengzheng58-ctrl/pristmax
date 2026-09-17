"""
Auth Module: User Authentication and Authorization

用户认证与授权系统:
- 用户注册/登录 (JWT)
- 角色权限管理
- API 密钥认证
- 操作审计

使用方式:
    from auth import AuthManager, require_auth, require_role

    # 初始化
    auth = AuthManager()

    # 注册用户
    user = auth.register("username", "email@example.com", "password", UserRole.ADMIN)

    # 登录
    token = auth.login("username", "password")

    # 在 Flask 中使用
    @app.route('/api/protected')
    @require_auth
    def protected():
        user = g.current_user
        return jsonify({'user': user.username})
"""

from .models import (
    User,
    UserRole,
    AuthToken,
    AuthDatabase,
    AuthManager,
    JWTAuth
)

from .middleware import (
    require_auth,
    require_role,
    optional_auth,
    get_current_user,
    is_authenticated,
    get_auth_manager
)

__all__ = [
    # Models
    'User',
    'UserRole',
    'AuthToken',
    'AuthDatabase',
    'AuthManager',
    'JWTAuth',

    # Middleware
    'require_auth',
    'require_role',
    'optional_auth',
    'get_current_user',
    'is_authenticated',
    'get_auth_manager',
]
