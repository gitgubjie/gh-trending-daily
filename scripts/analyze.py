#!/usr/bin/env python3
"""
为每个 trending repo 生成 AI 分析（中文）：

  - brief:        1-2 句简要介绍（解决什么问题）
  - advantages:   3-4 条核心优势 / 特点（精炼短语）
  - scenarios:    1-2 个典型应用场景
  - category:     项目分类（标签），用于分组展示

设计：所有分析在一次 LLM 调用里完成（17 个 repo 一次性给），降低延迟和 token 浪费。
输出：在每个 repo dict 上新增 `analysis` 字段；分析失败时降级为基于描述的启发式结果。
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any


# --- LLM 调用配置（OpenAI 兼容协议） ---
LLM_BASE_URL = os.environ.get("HERMES_LLM_BASE_URL", "https://api.minimaxi.com/v1")
# 顺序：显式 > MINIMAX_CN > MINIMAX > OPENAI
LLM_API_KEY=(
    os.environ.get("HERMES_LLM_API_KEY")
    or os.environ.get("MINIMAX_CN_API_KEY")
    or os.environ.get("MINIMAX_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
)
LLM_MODEL = os.environ.get("HERMES_LLM_MODEL", "MiniMax-M3")


# --- 项目分类标签（用于统计 + 分组展示） ---
CATEGORY_RULES = [
    ("AI Agent / LLM 工具",        r"\b(agent|llm|gpt|claude|copilot|rag|chatgpt|gemini|llama|mcp|assistant|openai|anthropic)\b"),
    ("AI 基础设施",                  r"\b(diffusion|embedding|transformer|finetun|vector|prompt|model|train|infer|serving|vllm|sglang)\b"),
    ("前端 / Web UI",                r"\b(ui|web|react|vue|frontend|nextjs|tailwind|dashboard|component|design)\b"),
    ("CLI / 终端",                   r"\b(cli|terminal|tui|shell|bash|command[- ]line|console|REPL)\b"),
    ("DevOps / 部署",                r"\b(docker|kubernetes|k8s|deploy|ci|cd|devops|helm|terraform|ansible)\b"),
    ("数据库 / 存储",                 r"\b(database|sql|postgres|mysql|sqlite|redis|vector|storage|orm|prisma|duckdb)\b"),
    ("浏览器 / 扩展",                 r"\b(browser|chrome|firefox|extension|bookmark|tab)\b"),
    ("安全 / 渗透",                   r"\b(security|hack|exploit|vulnerab|pentest|cve|crypto|auth|pwn|redteam)\b"),
    ("学习 / 教程",                   r"\b(tutorial|course|learn|book|curriculum|roadmap|study|interview)\b"),
    ("效率 / 工具",                   r"\b(productiv|tool|notion|obsidian|markdown|todo|task|note|workflow|automation)\b"),
    ("媒体 / 音视频",                 r"\b(video|audio|image|music|ffmpeg|whisper|tts|speech|transcri|mp4|stream)\b"),
    ("游戏开发",                     r"\b(game|godot|unity|unreal|bevy|gamedev)\b"),
    ("编程语言 / 框架",                r"\b(framework|library|compiler|interpreter|parser|runtime|kernel)\b"),
    ("机器人 / 嵌入式",                r"\b(robot|drone|iot|embedded|firmware|arduino|esp32)\b"),
    ("金融 / 量化",                   r"\b(finance|trading|quant|crypto|wallet|blockchain|btc|eth|defi)\b"),
]


def heuristic_category(repo: dict) -> str:
    """基于 description + name 的正则分类。LLM 失败时降级。"""
    text = f"{repo.get('name','')} {repo.get('description','')}".lower()
    for label, pat in CATEGORY_RULES:
        if re.search(pat, text, re.I):
            return label
    return "其他"


def _heuristic_analysis(repo: dict) -> dict:
    """无 LLM 时的降级方案：只给一个简单的 brief 和基于描述的卖点。"""
    desc = repo.get("description") or "（无描述）"
    return {
        "brief": desc,
        "advantages": [],
        "scenarios": [],
        "category": heuristic_category(repo),
    }


def _extract_json_block(text: str) -> str:
    """从模型返回中抠出 JSON 块（兼容 ```json ... ``` 围栏、<think>...</think> 包裹、或裸 JSON）。"""
    text = text.strip()
    # 去掉 <think>...</think> 块
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    if fence:
        return fence.group(1)
    # 第一个 [ 到最后一个 ]  （数组形式）
    if "[" in text and "]" in text:
        return text[text.index("["): text.rindex("]") + 1]
    # 第一个 { 到最后一个 }
    if "{" in text and "}" in text:
        return text[text.index("{"): text.rindex("}") + 1]
    return text


def _call_llm(repos: list[dict]) -> list[dict]:
    """一次调用，分析所有 repo。返回 list[dict]，长度与 repos 相同。"""
    minimal = [
        {
            "i": i,
            "full_name": r["full_name"],
            "description": r.get("description", ""),
            "language": r.get("language", ""),
            "stars_today": r.get("stars_today", 0),
            "total_stars": r.get("stars", 0),
        }
        for i, r in enumerate(repos)
    ]

    system = (
        "你是一个 GitHub 项目分析专家，擅长用精炼的中文总结开源项目的核心价值。"
        "不要思考、不要解释、不要任何前后缀文字。"
        "你的回复必须且只能是一个合法 JSON 数组，不要 markdown 围栏，不要换行说明。"
    )
    user = (
        "下面是 GitHub 今日 trending 列表。请为每个项目生成简明分析。"
        "直接以 [ 开始、以 ] 结束，数组每个对象字段：\n"
        "  i: 整数（与输入对应）\n"
        "  brief: 1-2 句中文简介（不超过 60 字）\n"
        "  advantages: 3 条核心优势（数组，每条不超过 18 字，短语）\n"
        "  scenarios: 1-2 个典型使用场景（数组，每条不超过 18 字）\n"
        "  category: 分类标签（从列表中选一个）"
        + " | ".join(label for label, _ in CATEGORY_RULES) + " | 其他"
        + "\n\n输入：\n" + json.dumps(minimal, ensure_ascii=False)
    )

    url = f"{LLM_BASE_URL}/chat/completions"
    if not LLM_API_KEY:
        print("  [analyze] no LLM API key in env; falling back to heuristic", file=sys.stderr)
        return []

    try:
        import requests
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": 8000,
            },
            timeout=180,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [analyze] LLM call failed: {e}", file=sys.stderr)
        return []  # 触发降级

    raw = _extract_json_block(content)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [analyze] JSON parse failed: {e}; raw head: {raw[:200]}", file=sys.stderr)
        return []

    if not isinstance(result, list):
        if isinstance(result, dict) and "data" in result:
            result = result["data"]
        else:
            print("  [analyze] unexpected JSON shape, expected list", file=sys.stderr)
            return []
    return result


def analyze_repos(repos: list[dict]) -> list[dict]:
    """入口：给每个 repo 加上 `analysis` 字段。失败时降级为启发式。"""
    print(f"  [analyze] {len(repos)} repos, calling LLM ({LLM_MODEL})...", file=sys.stderr)
    raw = _call_llm(repos)
    by_index = {item.get("i"): item for item in raw if isinstance(item, dict)}
    print(f"  [analyze] LLM returned {len(raw)} entries", file=sys.stderr)

    for i, r in enumerate(repos):
        item = by_index.get(i)
        if not item:
            r["analysis"] = _heuristic_analysis(r)
            continue
        adv = item.get("advantages") or []
        if isinstance(adv, str):
            adv = [adv]
        scen = item.get("scenarios") or []
        if isinstance(scen, str):
            scen = [scen]
        r["analysis"] = {
            "brief": (item.get("brief") or r.get("description") or "")[:200],
            "advantages": [str(x)[:60] for x in adv[:5]],
            "scenarios": [str(x)[:60] for x in scen[:3]],
            "category": item.get("category") or heuristic_category(r),
        }
    print(f"  [analyze] done", file=sys.stderr)
    return repos


if __name__ == "__main__":
    sample = json.loads(sys.stdin.read())
    out = analyze_repos(sample)
    print(json.dumps(out, ensure_ascii=False, indent=2))
