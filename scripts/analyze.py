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
    """无 LLM 时的降级方案：从 description 切出要点，保证 advantages/scenarios 始终有内容。"""
    desc = (repo.get("description") or "").strip()
    # 把描述按逗号/句号切成短句当卖点
    parts = [p.strip(" .，、;；·") for p in re.split(r"[.,;]|，|；|、", desc) if p.strip()]
    parts = [p for p in parts if 4 <= len(p) <= 40]
    if not parts:
        parts = [desc[:30]] if desc else ["开源项目"]
    advantages = parts[:3] if len(parts) >= 3 else parts + ["实用工具", "值得关注"][: 3 - len(parts)]
    scenarios = ["日常开发使用", "学习参考"] if "工具" in desc or "tool" in desc.lower() else ["日常开发使用"]
    return {
        "brief": desc or "（无描述）",
        "advantages": advantages[:3],
        "scenarios": scenarios[:2],
        "category": heuristic_category(repo),
    }


def _backfill_missing(repos: list[dict]) -> None:
    """LLM 偶尔会漏掉某条 advantages/scenarios；用启发式补齐，保证摘要不空白。"""
    for r in repos:
        a = r.get("analysis") or {}
        adv = a.get("advantages") or []
        scen = a.get("scenarios") or []
        brief = a.get("brief") or ""
        # brief 与 description 完全相同 → 用 heuristic 重新算
        if not brief or brief == (r.get("description") or "").strip():
            fallback = _heuristic_analysis(r)
            if not brief:
                a["brief"] = fallback["brief"]
        if not adv:
            a["advantages"] = _heuristic_analysis(r)["advantages"]
        if not scen:
            a["scenarios"] = _heuristic_analysis(r)["scenarios"]
        r["analysis"] = a


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
        "你是 GitHub 项目分析专家，输出必须严格符合用户给定的 JSON schema。"
        "不要思考、不要解释、不要任何前后缀文字。"
        "回复必须且只能是合法 JSON 数组（以 [ 开头 ] 结尾），无 markdown 围栏。"
    )
    user = (
        "下面是 GitHub 今日 trending 列表。请为每个项目生成简明分析。\n"
        "严格按以下 schema 输出 JSON 数组，**每个字段都必须存在且非空**（除了 i 字段）：\n"
        "[\n"
        "  {\n"
        '    "i": 0,\n'
        '    "brief": "1-2 句中文简介，不超过 60 字，要点出解决什么问题",\n'
        '    "advantages": ["优势短语1", "优势短语2", "优势短语3"],\n'
        '    "scenarios": ["场景短语1", "场景短语2"],\n'
        '    "category": "分类标签"\n'
        "  }\n"
        "]\n"
        "硬性要求：\n"
        "1. advantages **必须恰好 3 条**，每条 4-18 个中文字符\n"
        "2. scenarios **至少 1 条、最多 2 条**，每条 4-18 个中文字符\n"
        "3. brief 不允许与 description 完全相同，必须补充价值信息\n"
        "4. category 必须从以下列表中选一个：" + " | ".join(label for label, _ in CATEGORY_RULES) + " | 其他\n"
        "5. 直接以 [ 开始、] 结束，中间不要任何说明文字\n\n"
        "输入：\n" + json.dumps(minimal, ensure_ascii=False)
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
    _backfill_missing(repos)
    print(f"  [analyze] done", file=sys.stderr)
    return repos


if __name__ == "__main__":
    sample = json.loads(sys.stdin.read())
    out = analyze_repos(sample)
    print(json.dumps(out, ensure_ascii=False, indent=2))
