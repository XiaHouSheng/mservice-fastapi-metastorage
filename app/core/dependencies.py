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


def is_superuser(user: CurrentUser) -> bool:
    """判定是否为超级用户（三重 AND 校验，缺一不可）。

    必须同时满足：
    1. JWT payload 的 role == "superuser"；
    2. username（sub）在 SUPERUSER_USERNAMES 白名单中；
    3. user_id 在 SUPERUSER_USER_IDS 白名单中。

    无兜底：任意一项不满足即返回 False，管理接口返回 403。
    """
    if user.role != "superuser":
        return False
    if user.sub not in settings.SUPERUSER_USERNAMES:
        return False
    if user.user_id not in settings.SUPERUSER_USER_IDS:
        return False
    return True


async def get_superuser_flag(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> bool:
    """返回当前用户是否为 superuser（非强制依赖，用于需要跨服务权限判断的接口）。"""
    return is_superuser(current_user)


async def require_superuser(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """管理接口依赖：仅 superuser 可调用，否则返回 403。"""
    if not is_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级用户可执行此操作",
        )
    return current_user
