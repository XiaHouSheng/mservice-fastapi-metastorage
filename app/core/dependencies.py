"""认证依赖：从 JWT 解析当前用户，提供 superuser 权限判定。

本服务不存储用户表，get_current_user 返回轻量的 CurrentUser 对象（仅含 JWT payload 字段）。
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class CurrentUser(BaseModel):
    """当前登录用户（从 JWT payload 解析，不落库）。"""

    sub: str
    user_id: int
    service_name: str
    role: str
    type: str


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUser:
    """从 JWT 解析当前用户信息。"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = await decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception

    return CurrentUser(
        sub=payload.get("sub", ""),
        user_id=user_id,
        service_name=payload.get("service_name", "default"),
        role=payload.get("role", "user"),
        type=payload.get("type", "access"),
    )


def _is_superuser(user: CurrentUser) -> bool:
    """判定是否为超级用户。

    主路径：JWT payload 携带 role=superuser 即放行。
    兜底路径：JWT 无 role 声明（或 role 非 superuser）时，用 sub/user_id 比对配置白名单。
    """
    if user.role == "superuser":
        return True
    # 兜底：白名单比对
    if user.sub in settings.SUPERUSER_USERNAMES:
        return True
    if user.user_id in settings.SUPERUSER_USER_IDS:
        return True
    return False


async def require_superuser(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """管理接口依赖：仅 superuser 可调用，否则返回 403。"""
    if not _is_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级用户可执行此操作",
        )
    return current_user
