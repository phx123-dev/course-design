# -*- coding: utf-8 -*-
"""
LLM 客户端 —— DeepSeek（OpenAI 兼容协议）httpx 直调 + 离线降级
==============================================================
- 无 API Key 时 is_available()=False，编排器自动切换离线模式；
- 单次调用超时/失败重试 1 次，仍失败则抛 LLMError（编排器逐节点降级）；
- JSON 输出四级校验降级链（extract_json）：
    L1 json.loads 直接解析 → L2 正则提取首个 {...} 块 → L3 截断修复（补全括号/引号）
    → L4 返回 None（调用方回退离线模板）
- 流式接口 stream_chat 逐 token 产出（最终回复打字机效果）。
"""
import json
import re

import httpx

from app.config import settings


class LLMError(Exception):
    pass


def is_available() -> bool:
    """LLM 模式可用性：配置了 API Key 即视为可用（调用失败时逐节点降级）"""
    return bool(settings.deepseek_api_key.strip())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }


def chat(messages: list, temperature: float = 0.3, max_tokens: int = 1024,
         json_mode: bool = False) -> str:
    """非流式对话补全，返回文本。超时/异常重试 1 次。"""
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(2):
        try:
            resp = httpx.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers=_headers(), json=payload, timeout=settings.llm_timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:      # 网络/限流/欠费统一处理
            last_err = e
    raise LLMError(f"LLM 调用失败: {last_err}")


def stream_chat(messages: list, temperature: float = 0.5, max_tokens: int = 800):
    """流式对话补全：逐 token 产出（生成器）"""
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    with httpx.stream(
        "POST", f"{settings.deepseek_base_url}/chat/completions",
        headers=_headers(), json=payload, timeout=settings.llm_timeout,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0].get("delta", {})
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            token = delta.get("content")
            if token:
                yield token


def extract_json(text: str):
    """JSON 四级校验降级链。返回 (obj, 实际级别 1-4)，彻底失败返回 (None, 4)"""
    if not text:
        return None, 4
    # L1：直接解析
    try:
        return json.loads(text), 1
    except (json.JSONDecodeError, ValueError):
        pass
    # L2：提取首个 {...} 块（兼容模型输出的前后缀说明文字）
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0)), 2
        except (json.JSONDecodeError, ValueError):
            pass
    # L3：截断修复——补全缺失的右括号/引号（长输出被截断的常见情况）
    repaired = _repair_truncated_json(text)
    if repaired:
        try:
            return json.loads(repaired), 3
        except (json.JSONDecodeError, ValueError):
            pass
    return None, 4


def _repair_truncated_json(text: str):
    """按栈匹配补齐缺失的右括号与尾部引号（尽力而为）"""
    s = text.strip().lstrip("`").rstrip("`")
    if "{" not in s:
        return None
    s = s[s.index("{"):]
    stack = []
    in_str = False
    for ch in s:
        if ch == '"':
            in_str = not in_str
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    if in_str:
        s += '"'
    # 按栈的逆序补右括号：{"a":["b" 的栈为 ['{','['] → 应补 ']}'
    close_map = {"{": "}", "[": "]"}
    while stack:
        s += close_map[stack.pop()]
    return s
