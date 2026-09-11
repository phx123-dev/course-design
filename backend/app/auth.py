# -*- coding: utf-8 -*-
"""
认证鉴权 —— 自研轻量实现（不引入第三方认证库）
==============================================
密码存储：PBKDF2-HMAC-SHA256 加盐哈希（hashlib 标准库，10 万次迭代），
          格式：pbkdf2$<iterations>$<salt_hex>$<hash_hex>，校验时逐字段比对。
会话令牌：secrets 生成 48 字节随机串发给前端，数据库只存其 SHA256 摘要
          （即使数据库泄露也无法伪造令牌），有效期 12 小时。
鉴权链路：请求头 Authorization: Bearer <token> → 查摘要 → 校验有效期 → 返回用户。
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import AuthToken, User, get_db

PBKDF2_ITERATIONS = 100_000
TOKEN_TTL_HOURS = 12


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iterations, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(calc, digest)   # 常量时间比较，防时序攻击
    except (ValueError, AttributeError):
        return False


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(db: Session, user: User) -> str:
    """签发令牌：返回原始令牌给前端，数据库存摘要"""
    raw = secrets.token_urlsafe(48)
    db.add(AuthToken(user_id=user.id, token=_token_digest(raw),
                     expires_at=datetime.now() + timedelta(hours=TOKEN_TTL_HOURS)))
    db.commit()
    return raw


def revoke_token(db: Session, token: str) -> None:
    row = db.query(AuthToken).filter_by(token=_token_digest(token)).first()
    if row:
        db.delete(row)
        db.commit()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI 依赖：从 Authorization 头解析当前用户，失败抛 401"""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或缺少令牌")
    token = header[len("Bearer "):].strip()
    row = (db.query(AuthToken).filter_by(token=_token_digest(token)).first())
    if not row or row.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    user = db.query(User).filter_by(id=row.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_role(*roles: str):
    """依赖工厂：限定接口可访问角色。用法：Depends(require_role('admin','engineer'))"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"需要角色 {roles} 之一，当前为 {user.role}")
        return user
    return checker
