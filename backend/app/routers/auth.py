# -*- coding: utf-8 -*-
"""认证接口：登录 / 注销 / 当前用户"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import auth as auth_mod
from app.db import User, get_db
from app.schemas import LoginRequest, LoginResponse, UserInfo, ok

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _user_info(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role,
            "display_name": u.display_name}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """账号密码登录：校验 PBKDF2 哈希，签发 12 小时有效令牌"""
    user = db.query(User).filter_by(username=body.username).first()
    if not user or not auth_mod.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth_mod.create_token(db, user)
    return ok({"token": token, "user": _user_info(user)})


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """注销：删除服务端令牌记录"""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        auth_mod.revoke_token(db, header[len("Bearer "):])
    return ok()


@router.get("/me")
def me(user: User = Depends(auth_mod.get_current_user)):
    """当前登录用户信息"""
    return ok(_user_info(user))
