#!/usr/bin/env python3
"""
Topic-level analyzer for the Bilibili keyword heat checker.

This module builds on the keyword collector in ``bilibili_keyword_probe.py``:
it extracts important terms from a topic/title, collects public Bilibili data
for those terms, scores the whole topic, and proposes optimized topic variants.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from bilibili_keyword_probe import (
    FetchConfig,
    clean_text,
    clamp,
    collect_for_keyword,
    collect_suggestions,
    recommendation_for_score,
    summarize_keyword,
)


TOPIC_SUMMARY_FIELDS = [
    "platform",
    "topic",
    "topic_score",
    "recommendation",
    "selected_keywords",
    "avg_opportunity_score",
    "avg_demand_score",
    "avg_growth_score",
    "avg_competition_score",
    "intent_score",
    "clarity_score",
    "differentiation_score",
    "confidence_score",
    "risk_penalty",
    "reason",
]


TOPIC_KEYWORD_FIELDS = [
    "platform",
    "topic",
    "keyword",
    "importance_score",
    "source",
    "reason",
    "collected_videos",
    "demand_score",
    "growth_score",
    "competition_score",
    "opportunity_score",
    "recommendation",
]


OPTIMIZED_TOPIC_FIELDS = [
    "platform",
    "original_topic",
    "rank",
    "optimized_topic",
    "score",
    "recommendation",
    "based_keyword",
    "reason",
]


AUDIENCE_WORDS = [
    "普通人",
    "新手",
    "小白",
    "学生",
    "宝妈",
    "上班族",
    "打工人",
    "年轻人",
    "中年人",
    "女生",
    "男生",
]


INTENT_WORDS = [
    "如何",
    "怎么",
    "为什么",
    "能不能",
    "可不可以",
    "到底",
    "真的",
    "值不值得",
    "还有机会",
    "教程",
    "方法",
    "避坑",
    "复盘",
    "解说",
    "测评",
    "推荐",
    "清单",
    "入门",
    "攻略",
]


ACTION_WORDS = [
    "赚钱",
    "副业",
    "涨粉",
    "变现",
    "学习",
    "入门",
    "做",
    "用",
    "看懂",
    "讲清楚",
    "复盘",
    "拆解",
]


FILM_DOMAIN_WORDS = [
    "影视",
    "电影",
    "电视剧",
    "剧集",
    "国产剧",
    "韩剧",
    "日剧",
    "美剧",
    "泰剧",
    "港剧",
    "英剧",
    "网剧",
    "综艺",
    "动漫",
    "动画",
    "番剧",
    "纪录片",
    "演员",
    "导演",
    "主演",
    "角色",
    "人物",
    "剧情",
    "结局",
    "伏笔",
    "反转",
    "名场面",
    "解说",
    "影评",
    "剧评",
    "烂尾",
    "开播",
    "上映",
    "更新",
    "一口气看完",
]


FILM_INTENT_WORDS = [
    "解说",
    "解析",
    "剧情",
    "结局",
    "伏笔",
    "细节",
    "反转",
    "人物",
    "角色",
    "关系",
    "名场面",
    "看懂",
    "剧评",
    "影评",
    "值得看",
    "烂尾",
    "封神",
    "高能",
    "一口气",
    "全梳理",
]


NOISE_WORDS = [
    "一个",
    "一种",
    "哪些",
    "什么",
    "多少",
    "可以",
    "不能",
    "是不是",
    "有没有",
    "还有",
    "机会",
    "真的",
    "到底",
    "如何",
    "怎么",
    "为什么",
    "吗",
    "呢",
    "啊",
    "的",
    "了",
    "和",
    "与",
    "及",
    "以及",
    "还是",
]


SPLIT_WORDS = [
    "如何",
    "怎么",
    "为什么",
    "是不是",
    "到底",
    "真的",
    "能不能",
    "可不可以",
    "还有机会吗",
    "还有机会",
    "值不值得",
    "有哪些",
    "推荐",
    "教程",
    "方法",
    "攻略",
    "入门",
    "避坑",
    "复盘",
    "测评",
    "解说",
    "清单",
    "普通人",
    "新手",
    "小白",
    "学生",
    "宝妈",
    "上班族",
    "打工人",
    "做",
    "用",
    "靠",
    "通过",
    "能",
    "可以",
]


ProgressCallback = Callable[[Dict[str, Any]], None]


def analyze_topic(
    topic: str,
    config: FetchConfig,
    pages: int,
    order: str,
    enrich: bool,
    max_results: Optional[int],
    suggestions_limit: int,
    keyword_limit: int = 5,
    optimized_limit: int = 8,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    clean_topic = normalize_topic(topic)
    if not clean_topic:
        raise ValueError("请先输入一个选题")

    notify(
        progress_callback,
        message="正在采集整题联想词",
        current_keyword=clean_topic,
        completed_keywords=0,
        total_keywords=1,
    )
    topic_suggestions = safe_collect_suggestions(clean_topic, config, suggestions_limit)
    candidates = extract_keyword_candidates(clean_topic, topic_suggestions, limit=keyword_limit)
    selected_keywords = [row["keyword"] for row in candidates]

    total = len(selected_keywords)
    all_rows: List[Dict[str, Any]] = []
    all_suggestions = list(topic_suggestions)
    keyword_summaries: List[Dict[str, Any]] = []

    for index, keyword in enumerate(selected_keywords, start=1):
        notify(
            progress_callback,
            message=f"正在采集关键词：{keyword}",
            current_keyword=keyword,
            completed_keywords=index - 1,
            total_keywords=total,
            topic_keywords=candidates,
        )

        suggestions = safe_collect_suggestions(keyword, config, suggestions_limit)
        all_suggestions.extend(suggestions)

        try:
            rows = collect_for_keyword(
                keyword,
                pages,
                config,
                order,
                enrich=enrich,
                max_results=max_results,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            rows = []
            summary = empty_topic_keyword_summary(keyword, str(exc))
        else:
            summary = summarize_keyword(keyword, rows)

        keyword_summaries.append(summary)
        all_rows.extend(rows)
        notify(
            progress_callback,
            message=f"已完成关键词：{keyword}",
            current_keyword=keyword,
            completed_keywords=index,
            total_keywords=total,
            topic_keywords=merge_candidate_scores(candidates, keyword_summaries),
            summary=keyword_summaries,
            suggestions=all_suggestions,
            details_preview=all_rows[:100],
        )

    merged_keywords = merge_candidate_scores(candidates, keyword_summaries)
    topic_summary = score_topic(clean_topic, merged_keywords, all_suggestions)
    optimized_topics = generate_optimized_topics(
        clean_topic,
        merged_keywords,
        all_suggestions,
        topic_summary,
        all_rows,
        limit=optimized_limit,
    )

    result = {
        "topic": clean_topic,
        "topic_summary": topic_summary,
        "topic_keywords": merged_keywords,
        "optimized_topics": optimized_topics,
        "summary": keyword_summaries,
        "suggestions": all_suggestions,
        "details": all_rows,
        "details_preview": all_rows[:100],
    }
    notify(
        progress_callback,
        message="选题分析完成",
        current_keyword="",
        completed_keywords=total,
        total_keywords=total,
        topic_result=result,
    )
    return result


def normalize_topic(topic: str) -> str:
    text = clean_text(topic)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def safe_collect_suggestions(keyword: str, config: FetchConfig, limit: int) -> List[Dict[str, Any]]:
    try:
        return collect_suggestions(keyword, config, limit=max(0, limit))
    except Exception as exc:  # pragma: no cover - network dependent
        return [
            {
                "platform": "bilibili",
                "keyword": keyword,
                "suggestion_rank": 0,
                "suggestion": "",
                "highlighted": f"采集失败：{exc}",
                "source": "search_box",
            }
        ]


def extract_keyword_candidates(
    topic: str,
    suggestions: Sequence[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    scored: Dict[str, Dict[str, Any]] = {}

    def add(keyword: str, points: float, source: str, reason: str) -> None:
        cleaned = normalize_candidate(keyword)
        if not cleaned or is_noise_candidate(cleaned):
            return
        if cleaned not in scored:
            scored[cleaned] = {
                "platform": "bilibili",
                "topic": topic,
                "keyword": cleaned,
                "importance_score": 0.0,
                "source": source,
                "reason": reason,
            }
        scored[cleaned]["importance_score"] += points
        if source not in scored[cleaned]["source"]:
            scored[cleaned]["source"] += f"、{source}"
        if reason not in scored[cleaned]["reason"]:
            scored[cleaned]["reason"] += f"；{reason}"

    add(topic, 42, "选题原句", "保留整题搜索，用于判断完整表达的搜索需求")
    core = strip_noise_words(topic)
    add(core, 58, "结构拆解", "去掉人群词和问题词后得到的核心主题")

    for phrase in split_topic_phrases(topic):
        add(phrase, 44 + min(len(phrase) * 2, 12), "结构拆解", "从选题结构中拆出的候选主题")

    for rank, row in enumerate(suggestions, start=1):
        suggestion = row.get("suggestion") or ""
        if not suggestion:
            continue
        points = max(18, 52 - rank * 3)
        add(suggestion, points, "B站联想", f"来自B站搜索框联想词第{rank}位")
        compact = strip_noise_words(suggestion)
        if compact != suggestion:
            add(compact, points * 0.62, "B站联想", "联想词去除修饰后得到的核心表达")

    rows = sorted(
        scored.values(),
        key=lambda row: (row["importance_score"], suitable_keyword_bonus(row["keyword"])),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    for row in rows:
        keyword = row["keyword"]
        if any(is_similar_keyword(keyword, chosen["keyword"]) for chosen in selected):
            continue
        row["importance_score"] = round(clamp(row["importance_score"]), 1)
        selected.append(row)
        if len(selected) >= max(1, limit):
            break
    return selected


def normalize_candidate(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"[\s《》“”\"'【】\[\]（）()]+", "", text)
    text = re.sub(r"[?？!！。；;：:,，、]+$", "", text)
    return text.strip()


def strip_noise_words(value: str) -> str:
    text = normalize_candidate(value)
    for word in AUDIENCE_WORDS + SPLIT_WORDS + NOISE_WORDS:
        text = text.replace(word, "")
    return normalize_candidate(text)


def split_topic_phrases(topic: str) -> List[str]:
    parts: List[str] = []
    punct_parts = re.split(r"[，,。！？!?.、：:；;《》“”\"'（）()【】\[\]\s]+", topic)
    for part in punct_parts:
        part = normalize_candidate(part)
        if part:
            parts.append(part)

    split_pattern = "|".join(re.escape(word) for word in sorted(SPLIT_WORDS, key=len, reverse=True))
    for part in re.split(split_pattern, topic):
        part = normalize_candidate(part)
        if part:
            parts.append(part)

    latin_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#.\-]*", topic)
    parts.extend(latin_terms)
    return unique_preserve_order(parts)


def is_noise_candidate(keyword: str) -> bool:
    if len(keyword) < 2:
        return True
    if re.fullmatch(r"[A-Za-z0-9+#.\-]{1,2}", keyword):
        return True
    if keyword in NOISE_WORDS or keyword in AUDIENCE_WORDS:
        return True
    if len(keyword) > 26:
        return True
    return False


def suitable_keyword_bonus(keyword: str) -> float:
    length = len(keyword)
    if 3 <= length <= 12:
        return 12
    if 2 <= length <= 18:
        return 6
    return 0


def is_similar_keyword(left: str, right: str) -> bool:
    if left == right:
        return True
    shorter, longer = sorted([left, right], key=len)
    if len(shorter) >= 3 and shorter in longer and len(shorter) / len(longer) >= 0.80:
        return True
    return False


def merge_candidate_scores(
    candidates: Sequence[Dict[str, Any]],
    summaries: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    summary_by_keyword = {row.get("keyword"): row for row in summaries}
    merged: List[Dict[str, Any]] = []
    for row in candidates:
        summary = summary_by_keyword.get(row["keyword"], {})
        merged_row = dict(row)
        merged_row.update(
            {
                "collected_videos": summary.get("collected_videos", 0),
                "demand_score": summary.get("demand_score", 0),
                "growth_score": summary.get("growth_score", 0),
                "competition_score": summary.get("competition_score", 0),
                "opportunity_score": summary.get("opportunity_score", 0),
                "recommendation": summary.get("recommendation", "暂不建议"),
            }
        )
        merged.append(merged_row)
    return merged


def score_topic(
    topic: str,
    keyword_rows: Sequence[Dict[str, Any]],
    suggestions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    weighted = weighted_keyword_scores(keyword_rows)
    intent_score = score_search_intent(topic, suggestions)
    clarity_score = score_title_clarity(topic)
    differentiation_score = score_differentiation(topic, keyword_rows)
    confidence_score = score_confidence(keyword_rows, suggestions)
    risk_penalty = score_risk_penalty(keyword_rows, confidence_score)

    topic_score = clamp(
        weighted["opportunity"] * 0.45
        + intent_score * 0.20
        + clarity_score * 0.15
        + differentiation_score * 0.10
        + confidence_score * 0.10
        - risk_penalty
    )
    recommendation = recommendation_for_score(topic_score)
    reason = build_topic_reason(
        weighted,
        intent_score,
        clarity_score,
        differentiation_score,
        confidence_score,
        risk_penalty,
    )
    selected_keywords = "、".join(row["keyword"] for row in keyword_rows)
    return {
        "platform": "bilibili",
        "topic": topic,
        "topic_score": round(topic_score, 1),
        "recommendation": recommendation,
        "selected_keywords": selected_keywords,
        "avg_opportunity_score": round(weighted["opportunity"], 1),
        "avg_demand_score": round(weighted["demand"], 1),
        "avg_growth_score": round(weighted["growth"], 1),
        "avg_competition_score": round(weighted["competition"], 1),
        "intent_score": round(intent_score, 1),
        "clarity_score": round(clarity_score, 1),
        "differentiation_score": round(differentiation_score, 1),
        "confidence_score": round(confidence_score, 1),
        "risk_penalty": round(risk_penalty, 1),
        "reason": reason,
    }


def weighted_keyword_scores(keyword_rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    if not keyword_rows:
        return {"opportunity": 0.0, "demand": 0.0, "growth": 0.0, "competition": 0.0}

    total_weight = 0.0
    sums = {"opportunity": 0.0, "demand": 0.0, "growth": 0.0, "competition": 0.0}
    for row in keyword_rows:
        weight = 0.5 + safe_float(row.get("importance_score")) / 100
        total_weight += weight
        sums["opportunity"] += safe_float(row.get("opportunity_score")) * weight
        sums["demand"] += safe_float(row.get("demand_score")) * weight
        sums["growth"] += safe_float(row.get("growth_score")) * weight
        sums["competition"] += safe_float(row.get("competition_score")) * weight
    return {key: value / total_weight if total_weight else 0.0 for key, value in sums.items()}


def score_search_intent(topic: str, suggestions: Sequence[Dict[str, Any]]) -> float:
    valid_suggestions = [row for row in suggestions if row.get("suggestion")]
    distinct_count = len({row["suggestion"] for row in valid_suggestions})
    suggestion_score = clamp(distinct_count / 30 * 70)
    intent_bonus = 0
    if any(word in topic for word in INTENT_WORDS):
        intent_bonus += 18
    if any(word in topic for word in ACTION_WORDS):
        intent_bonus += 12
    return clamp(suggestion_score + intent_bonus)


def score_title_clarity(topic: str) -> float:
    score = 42.0
    length = len(topic)
    if 10 <= length <= 30:
        score += 18
    elif 6 <= length <= 38:
        score += 10
    else:
        score -= 8

    if any(word in topic for word in AUDIENCE_WORDS):
        score += 14
    if any(word in topic for word in INTENT_WORDS):
        score += 14
    if any(word in topic for word in ACTION_WORDS):
        score += 10
    if re.search(r"[？?：:]", topic):
        score += 5
    return clamp(score)


def score_differentiation(topic: str, keyword_rows: Sequence[Dict[str, Any]]) -> float:
    score = 46.0
    niche_words = AUDIENCE_WORDS + ["避坑", "真实", "复盘", "对比", "成本", "案例", "低成本", "从0到1"]
    score += min(28, sum(1 for word in niche_words if word in topic) * 7)

    weighted = weighted_keyword_scores(keyword_rows)
    competition = weighted["competition"]
    if competition <= 35:
        score += 16
    elif competition <= 55:
        score += 8
    elif competition >= 75:
        score -= 14

    if len(strip_noise_words(topic)) <= 2:
        score -= 14
    return clamp(score)


def score_confidence(keyword_rows: Sequence[Dict[str, Any]], suggestions: Sequence[Dict[str, Any]]) -> float:
    video_count = sum(int(safe_float(row.get("collected_videos"))) for row in keyword_rows)
    success_count = len([row for row in keyword_rows if safe_float(row.get("collected_videos")) > 0])
    suggestion_count = len({row.get("suggestion") for row in suggestions if row.get("suggestion")})
    return clamp(video_count / 40 * 45 + success_count / max(1, len(keyword_rows)) * 35 + suggestion_count / 30 * 20)


def score_risk_penalty(keyword_rows: Sequence[Dict[str, Any]], confidence_score: float) -> float:
    weighted = weighted_keyword_scores(keyword_rows)
    penalty = 0.0
    if confidence_score < 35:
        penalty += 18
    if weighted["competition"] >= 75:
        penalty += 14
    if weighted["demand"] < 25:
        penalty += 10
    if not any(safe_float(row.get("collected_videos")) > 0 for row in keyword_rows):
        penalty += 20
    return clamp(penalty, 0, 42)


def build_topic_reason(
    weighted: Dict[str, float],
    intent_score: float,
    clarity_score: float,
    differentiation_score: float,
    confidence_score: float,
    risk_penalty: float,
) -> str:
    reasons: List[str] = []
    if weighted["opportunity"] >= 70:
        reasons.append("关键词机会分较高")
    elif weighted["opportunity"] >= 45:
        reasons.append("关键词机会分中等")
    else:
        reasons.append("关键词机会分偏弱")

    if intent_score >= 70:
        reasons.append("搜索意图明确")
    elif intent_score < 40:
        reasons.append("搜索意图证据不足")

    if clarity_score >= 75:
        reasons.append("选题表达清晰")
    elif clarity_score < 55:
        reasons.append("选题表达需要收窄")

    if differentiation_score >= 70:
        reasons.append("具备差异化切入点")
    elif weighted["competition"] >= 70:
        reasons.append("竞争压力偏高")

    if confidence_score < 45:
        reasons.append("数据样本偏少")
    if risk_penalty >= 20:
        reasons.append("执行风险需要控制")
    return "；".join(reasons)


def generate_optimized_topics(
    topic: str,
    keyword_rows: Sequence[Dict[str, Any]],
    suggestions: Sequence[Dict[str, Any]],
    topic_summary: Dict[str, Any],
    source_rows: Sequence[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    keywords = [row["keyword"] for row in keyword_rows if row.get("keyword")]
    primary = best_core_keyword(topic, keywords)
    secondary = next((kw for kw in keywords if kw != primary and kw != topic and len(kw) <= 14), "")
    suggestion_terms = [
        row["suggestion"]
        for row in suggestions
        if row.get("suggestion") and 3 <= len(row["suggestion"]) <= 18 and row["suggestion"] != topic
    ]

    domain = infer_topic_domain(topic, keyword_rows, suggestions, source_rows)
    if domain == "film":
        candidates = film_topic_candidates(topic, primary, secondary, suggestion_terms)
    else:
        candidates = general_topic_candidates(primary, secondary, suggestion_terms)

    rows: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        title = normalize_candidate(candidate)
        if not title or title in seen or title == topic:
            continue
        seen.add(title)
        score, based_keyword, reason = score_optimized_topic(title, keyword_rows, topic_summary, domain)
        rows.append(
            {
                "platform": "bilibili",
                "original_topic": topic,
                "rank": 0,
                "optimized_topic": title,
                "score": round(score, 1),
                "recommendation": recommendation_for_score(score),
                "based_keyword": based_keyword,
                "reason": reason,
            }
        )

    rows.sort(key=lambda row: row["score"], reverse=True)
    for index, row in enumerate(rows[:limit], start=1):
        row["rank"] = index
    return rows[:limit]


def infer_topic_domain(
    topic: str,
    keyword_rows: Sequence[Dict[str, Any]],
    suggestions: Sequence[Dict[str, Any]],
    source_rows: Sequence[Dict[str, Any]],
) -> str:
    parts: List[str] = [topic]
    parts.extend(str(row.get("keyword", "")) for row in keyword_rows)
    parts.extend(str(row.get("suggestion", "")) for row in suggestions)
    for row in source_rows[:20]:
        parts.extend(
            [
                str(row.get("title", "")),
                str(row.get("category", "")),
                str(row.get("tags", "")),
                str(row.get("description", "")),
            ]
        )

    text = " ".join(parts)
    film_hits = sum(1 for word in FILM_DOMAIN_WORDS if word and word in text)
    if film_hits >= 1:
        return "film"
    return "general"


def film_topic_candidates(
    topic: str,
    primary: str,
    secondary: str,
    suggestion_terms: Sequence[str],
) -> List[str]:
    title = strip_film_question_words(primary) if primary and primary != topic else ""
    if not title:
        title = strip_film_question_words(topic)
    if not title:
        title = primary or topic
    secondary_title = strip_film_question_words(secondary)

    candidates = [
        f"{title}一口气看懂：剧情和人物关系全梳理",
        f"{title}结局解析：这几个伏笔很多人没看懂",
        f"{title}为什么能火？爽点和反转拆解",
        f"{title}值不值得看？无剧透剧评",
        f"{title}高能名场面盘点：最狠的反转在哪",
        f"{title}人物关系解析：谁才是真正的关键角色",
        f"{title}细节伏笔复盘：二刷才看懂的地方",
        f"{title}被低估了吗？优点和争议一次说清",
    ]
    if secondary_title and secondary_title != title:
        candidates.append(f"{title}和{secondary_title}对比：谁的剧情更有看点")
    for term in suggestion_terms[:5]:
        compact = strip_film_question_words(term)
        if compact and compact != title:
            candidates.append(f"{compact}剧情解析")
            candidates.append(f"{compact}结局和伏笔全梳理")
    return candidates


def general_topic_candidates(
    primary: str,
    secondary: str,
    suggestion_terms: Sequence[str],
) -> List[str]:
    candidates = [
        f"{primary}到底还值不值得做？",
        f"普通人做{primary}，先看这几个坑",
        f"{primary}新手入门：从0到1怎么做",
        f"我测试了{primary}，真实结果怎么样",
        f"一口气讲清楚{primary}的机会和风险",
    ]
    if secondary:
        candidates.append(f"{primary}和{secondary}怎么选？")
    for term in suggestion_terms[:6]:
        candidates.append(f"{term}避坑指南")
        candidates.append(f"{term}真实数据复盘")
    return candidates


def strip_film_question_words(value: str) -> str:
    text = normalize_candidate(value)
    for word in [
        "为什么",
        "怎么",
        "如何",
        "到底",
        "真的",
        "值不值得看",
        "值不值得",
        "好看吗",
        "好不好看",
        "结局解析",
        "剧情解析",
        "解说",
        "影评",
        "剧评",
    ]:
        text = text.replace(word, "")
    return normalize_candidate(text)


def best_core_keyword(topic: str, keywords: Sequence[str]) -> str:
    for keyword in keywords:
        if keyword != topic and 2 <= len(keyword) <= 14:
            return keyword
    if keywords:
        return keywords[0]
    return topic


def score_optimized_topic(
    title: str,
    keyword_rows: Sequence[Dict[str, Any]],
    topic_summary: Dict[str, Any],
    domain: str = "general",
) -> Tuple[float, str, str]:
    matched_rows = [row for row in keyword_rows if row.get("keyword") and row["keyword"] in title]
    if matched_rows:
        base = max(safe_float(row.get("opportunity_score")) for row in matched_rows)
        based_keyword = max(matched_rows, key=lambda row: safe_float(row.get("opportunity_score")))["keyword"]
    else:
        base = safe_float(topic_summary.get("avg_opportunity_score"))
        based_keyword = keyword_rows[0]["keyword"] if keyword_rows else ""

    clarity = score_title_clarity(title)
    differentiation = score_differentiation(title, keyword_rows)
    intent = score_search_intent(title, [])
    length_bonus = 5 if 10 <= len(title) <= 28 else -5
    domain_bonus = score_domain_fit(title, domain)
    score = clamp(base * 0.50 + clarity * 0.22 + differentiation * 0.10 + intent * 0.06 + domain_bonus * 0.12 + length_bonus)

    reasons = []
    if domain == "film":
        reasons.append("匹配影视内容结构")
        if any(word in title for word in ["剧情", "结局", "伏笔", "人物", "反转", "名场面"]):
            reasons.append("强化解说/解析角度")
        if any(word in title for word in ["值得看", "剧评", "影评", "争议"]):
            reasons.append("适合影视区评测表达")
    else:
        if any(word in title for word in AUDIENCE_WORDS):
            reasons.append("增加人群限定")
        if any(word in title for word in ["避坑", "真实", "复盘", "风险"]):
            reasons.append("强化差异化角度")
        if any(word in title for word in ["怎么", "入门", "讲清楚", "值不值得"]):
            reasons.append("搜索意图更明确")
    if not reasons:
        reasons.append("基于高相关关键词优化表达")
    return score, based_keyword, "；".join(reasons)


def score_domain_fit(title: str, domain: str) -> float:
    if domain == "film":
        hits = sum(1 for word in FILM_INTENT_WORDS if word in title)
        return clamp(42 + hits * 12)
    return 60


def empty_topic_keyword_summary(keyword: str, error: str) -> Dict[str, Any]:
    return {
        "platform": "bilibili",
        "keyword": keyword,
        "collected_videos": 0,
        "demand_score": 0,
        "growth_score": 0,
        "competition_score": 0,
        "opportunity_score": 0,
        "recommendation": "暂不建议",
        "reason": f"采集失败：{error}",
    }


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def unique_preserve_order(values: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def notify(callback: Optional[ProgressCallback], **updates: Any) -> None:
    if callback:
        callback(updates)
