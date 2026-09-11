# -*- coding: utf-8 -*-
"""报告导出接口：单设备诊断报告 / 运维周报（Markdown）"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import User, get_db
from app.services import report_service

router = APIRouter(prefix="/api/reports", tags=["报告导出"])


@router.get("/device/{device_id}")
def device_report(device_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    content = report_service.device_report(db, device_id)
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition":
                                      f"attachment; filename=device_{device_id}_report.md"})


@router.get("/weekly")
def weekly(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    content = report_service.weekly_report(db)
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition":
                                      "attachment; filename=weekly_report.md"})
