#!/usr/bin/env python3
"""
Bilibili keyword heat checker.

This script collects public Bilibili video search results for one or more
keywords, enriches each result with public video stats, then writes a detail CSV
and a keyword-level summary CSV.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import math
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional


SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
SUGGEST_URL = "https://s.search.bilibili.com/main/suggest"


DETAIL_FIELDS = [
    "platform",
    "keyword",
    "rank",
    "bvid",
    "aid",
    "title",
    "url",
    "author",
    "author_mid",
    "category",
    "publish_date",
    "age_days",
    "duration_seconds",
    "views",
    "danmaku",
    "comments",
    "likes",
    "coins",
    "favorites",
    "shares",
    "search_order",
    "search_page",
    "description",
    "tags",
]


SUMMARY_FIELDS = [
    "platform",
    "keyword",
    "collected_videos",
    "median_views",
    "avg_views",
    "p75_views",
    "max_views",
    "median_engagement",
    "avg_engagement",
    "recent_30d_ratio",
    "recent_90d_ratio",
    "top3_view_share",
    "high_view_ratio",
    "demand_score",
    "growth_score",
    "competition_score",
    "opportunity_score",
    "recommendation",
    "reason",
]


SUGGESTION_FIELDS = [
    "platform",
    "keyword",
    "suggestion_rank",
    "suggestion",
    "highlighted",
    "source",
]


@dataclass
class FetchConfig:
    timeout: float = 12.0
    retries: int = 3
    sleep_seconds: float = 0.8
    jitter_seconds: float = 0.4
    force_ipv4: bool = True
    prefer_curl: bool = True
    cookie_file: Optional[str] = None


_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_IPV4_ONLY_ENABLED = False


def enable_ipv4_only() -> None:
    global _IPV4_ONLY_ENABLED
    if _IPV4_ONLY_ENABLED:
        return

    def ipv4_getaddrinfo(host: str, port: Any, family: int = 0, type: int = 0, proto: int = 0, flags: int = 0):
        results = _ORIGINAL_GETADDRINFO(host, port, socket.AF_INET, type, proto, flags)
        return [item for item in results if item[0] == socket.AF_INET]

    socket.getaddrinfo = ipv4_getaddrinfo
    _IPV4_ONLY_ENABLED = True


def find_curl() -> Optional[str]:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidates = [
        os.path.join(system_root, "System32", "curl.exe"),
        os.path.join(system_root, "Sysnative", "curl.exe"),
        shutil.which("curl.exe"),
        shutil.which("curl"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def default_cookie_file() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "runtime", "bilibili_cookies.txt")


def ensure_bilibili_cookie_file(headers: Dict[str, str], config: FetchConfig) -> str:
    curl = find_curl()
    if not curl:
        raise RuntimeError("curl is not available")

    cookie_file = config.cookie_file or default_cookie_file()
    os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
    if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
        return cookie_file

    command = [
        curl,
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(max(3, int(config.timeout))),
        "--cookie-jar",
        cookie_file,
    ]
    if config.force_ipv4:
        command.append("--ipv4")
    for key, value in headers.items():
        command.extend(["--header", f"{key}: {value}"])
    command.append("https://www.bilibili.com")

    completed = subprocess.run(command, capture_output=True, timeout=config.timeout + 8, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl cookie warmup failed with exit code {completed.returncode}: {stderr}")
    return cookie_file


def reset_bilibili_cookie(config: FetchConfig) -> None:
    cookie_file = config.cookie_file or default_cookie_file()
    try:
        if os.path.exists(cookie_file):
            os.remove(cookie_file)
    except OSError:
        pass


def request_json_with_curl(full_url: str, headers: Dict[str, str], config: FetchConfig) -> Dict[str, Any]:
    curl = find_curl()
    if not curl:
        raise RuntimeError("curl is not available")

    command = [
        curl,
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(max(3, int(config.timeout))),
    ]
    cookie_file = ensure_bilibili_cookie_file(headers, config)
    command.extend(["--cookie", cookie_file, "--cookie-jar", cookie_file])
    if config.force_ipv4:
        command.append("--ipv4")
    for key, value in headers.items():
        command.extend(["--header", f"{key}: {value}"])
    command.append(full_url)

    completed = subprocess.run(
        command,
        capture_output=True,
        timeout=config.timeout + 8,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl failed with exit code {completed.returncode}: {stderr}")

    raw = completed.stdout.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = clean_text(raw)[:300]
        raise RuntimeError(f"curl returned non-JSON response: {preview}") from exc
    if data.get("code") not in (0, None):
        message = data.get("message") or data.get("msg") or "unknown API error"
        raise RuntimeError(f"Bilibili API error {data.get('code')}: {message}")
    return data


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--"}:
        return 0

    multiplier = 1
    if text.endswith("万"):
        multiplier = 10_000
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100_000_000
        text = text[:-1]

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0
    return max(0, int(float(match.group(0)) * multiplier))


def parse_duration(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    parts = str(value).strip().split(":")
    try:
        nums = [int(part) for part in parts]
    except ValueError:
        return 0
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return 0


def format_date(timestamp: Any) -> str:
    ts = parse_count(timestamp)
    if ts <= 0:
        return ""
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def age_days(timestamp: Any) -> int:
    ts = parse_count(timestamp)
    if ts <= 0:
        return 0
    published = dt.datetime.fromtimestamp(ts)
    return max(0, (dt.datetime.now() - published).days)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def log_score(value: float, low_power: float, high_power: float) -> float:
    if value <= 0:
        return 0.0
    score = (math.log10(value) - low_power) / (high_power - low_power) * 100
    return clamp(score)


def percentile(values: List[int], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * pct
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[int(position)])
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def sleep_between_requests(config: FetchConfig) -> None:
    delay = config.sleep_seconds + random.random() * config.jitter_seconds
    if delay > 0:
        time.sleep(delay)


def request_json(
    url: str,
    params: Dict[str, Any],
    config: FetchConfig,
    referer_keyword: Optional[str] = None,
) -> Dict[str, Any]:
    if config.force_ipv4:
        enable_ipv4_only()

    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    referer = "https://www.bilibili.com/"
    if referer_keyword:
        encoded = urllib.parse.quote(referer_keyword)
        referer = f"https://search.bilibili.com/all?keyword={encoded}"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, config.retries + 1):
        if config.prefer_curl:
            try:
                return request_json_with_curl(full_url, headers, config)
            except (subprocess.TimeoutExpired, RuntimeError) as exc:
                last_error = exc
                if "-412" in str(exc) or "request was banned" in str(exc):
                    reset_bilibili_cookie(config)
                if attempt < config.retries:
                    time.sleep(min(8, attempt * 1.5))
                    continue
                raise RuntimeError(f"Request failed via curl: {full_url}\n{last_error}") from exc

        request = urllib.request.Request(full_url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                raw = response.read().decode(charset, errors="replace")
                data = json.loads(raw)
                if data.get("code") not in (0, None):
                    message = data.get("message") or data.get("msg") or "unknown API error"
                    raise RuntimeError(f"Bilibili API error {data.get('code')}: {message}")
                return data
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < config.retries:
                time.sleep(min(8, attempt * 1.5))

    raise RuntimeError(f"Request failed: {full_url}\n{last_error}")


def collect_suggestions(keyword: str, config: FetchConfig, limit: int = 10) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []

    params = {"term": keyword}
    data = request_json(SUGGEST_URL, params, config, referer_keyword=keyword)
    tags = data.get("result", {}).get("tag") or []

    rows: List[Dict[str, Any]] = []
    seen = set()
    for item in tags:
        suggestion = clean_text(item.get("value") or item.get("term") or item.get("name"))
        if not suggestion or suggestion in seen:
            continue
        seen.add(suggestion)
        rows.append(
            {
                "platform": "bilibili",
                "keyword": keyword,
                "suggestion_rank": len(rows) + 1,
                "suggestion": suggestion,
                "highlighted": clean_text(item.get("name")),
                "source": "search_box",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def search_videos(keyword: str, pages: int, config: FetchConfig, order: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for page in range(1, pages + 1):
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "order": order,
        }
        data = request_json(SEARCH_URL, params, config, referer_keyword=keyword)
        result = data.get("data", {}).get("result") or []
        if not result:
            break

        for index, item in enumerate(result, start=1):
            rank = len(rows) + 1
            rows.append(normalize_search_item(keyword, page, index, rank, item))

        sleep_between_requests(config)

    return rows


def normalize_search_item(
    keyword: str,
    page: int,
    index: int,
    rank: int,
    item: Dict[str, Any],
) -> Dict[str, Any]:
    bvid = item.get("bvid") or ""
    url = item.get("arcurl") or (f"https://www.bilibili.com/video/{bvid}" if bvid else "")
    pubdate = item.get("pubdate")

    return {
        "platform": "bilibili",
        "keyword": keyword,
        "rank": rank,
        "bvid": bvid,
        "aid": item.get("aid") or item.get("id") or "",
        "title": clean_text(item.get("title")),
        "url": url,
        "author": clean_text(item.get("author")),
        "author_mid": item.get("mid") or "",
        "category": clean_text(item.get("typename")),
        "publish_date": format_date(pubdate),
        "age_days": age_days(pubdate),
        "duration_seconds": parse_duration(item.get("duration")),
        "views": parse_count(item.get("play")),
        "danmaku": parse_count(item.get("video_review")),
        "comments": parse_count(item.get("review")),
        "likes": 0,
        "coins": 0,
        "favorites": parse_count(item.get("favorites")),
        "shares": 0,
        "search_order": index,
        "search_page": page,
        "description": clean_text(item.get("description")),
        "tags": clean_text(item.get("tag")),
    }


def enrich_video(row: Dict[str, Any], config: FetchConfig) -> Dict[str, Any]:
    bvid = row.get("bvid")
    if not bvid:
        return row

    data = request_json(VIEW_URL, {"bvid": bvid}, config, referer_keyword=row.get("keyword"))
    video = data.get("data") or {}
    stat = video.get("stat") or {}
    owner = video.get("owner") or {}

    row["title"] = clean_text(video.get("title") or row.get("title"))
    row["author"] = clean_text(owner.get("name") or row.get("author"))
    row["author_mid"] = owner.get("mid") or row.get("author_mid")
    row["category"] = clean_text(video.get("tname") or row.get("category"))
    row["publish_date"] = format_date(video.get("pubdate")) or row.get("publish_date")
    row["age_days"] = age_days(video.get("pubdate")) or row.get("age_days")
    row["duration_seconds"] = parse_duration(video.get("duration")) or row.get("duration_seconds")
    row["views"] = parse_count(stat.get("view")) or row.get("views")
    row["danmaku"] = parse_count(stat.get("danmaku")) or row.get("danmaku")
    row["comments"] = parse_count(stat.get("reply")) or row.get("comments")
    row["likes"] = parse_count(stat.get("like"))
    row["coins"] = parse_count(stat.get("coin"))
    row["favorites"] = parse_count(stat.get("favorite")) or row.get("favorites")
    row["shares"] = parse_count(stat.get("share"))
    row["description"] = clean_text(video.get("desc") or row.get("description"))
    row["url"] = f"https://www.bilibili.com/video/{bvid}"
    return row


def engagement(row: Dict[str, Any]) -> int:
    return (
        parse_count(row.get("likes"))
        + parse_count(row.get("coins"))
        + parse_count(row.get("favorites"))
        + parse_count(row.get("comments"))
        + parse_count(row.get("danmaku"))
    )


def summarize_keyword(keyword: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "platform": "bilibili",
            "keyword": keyword,
            "collected_videos": 0,
            "median_views": 0,
            "avg_views": 0,
            "p75_views": 0,
            "max_views": 0,
            "median_engagement": 0,
            "avg_engagement": 0,
            "recent_30d_ratio": 0,
            "recent_90d_ratio": 0,
            "top3_view_share": 0,
            "high_view_ratio": 0,
            "demand_score": 0,
            "growth_score": 0,
            "competition_score": 0,
            "opportunity_score": 0,
            "recommendation": "暂不建议",
            "reason": "没有采集到可用结果",
        }

    views = [parse_count(row.get("views")) for row in rows]
    ages = [parse_count(row.get("age_days")) for row in rows if parse_count(row.get("age_days")) > 0]
    engagements = [engagement(row) for row in rows]
    total_views = sum(views)
    top3_views = sum(sorted(views, reverse=True)[:3])
    top3_share = top3_views / total_views if total_views else 0
    high_view_ratio = len([value for value in views if value >= 100_000]) / len(views)
    recent_30_ratio = len([age for age in ages if age <= 30]) / len(rows) if rows else 0
    recent_90_ratio = len([age for age in ages if age <= 90]) / len(rows) if rows else 0

    median_views = median(views)
    avg_views = mean(views)
    p75_views = percentile(views, 0.75)
    median_engagement = median(engagements)
    avg_engagement = mean(engagements)

    view_score = log_score(median_views, 2, 6)
    engagement_score = log_score(median_engagement, 1, 5)
    result_depth_score = clamp(len(rows) / 50 * 100)
    demand_score = clamp(view_score * 0.55 + engagement_score * 0.35 + result_depth_score * 0.10)

    freshness_score = clamp(recent_30_ratio * 70 + recent_90_ratio * 30)
    evergreen_bonus = 15 if median_views >= 50_000 and recent_90_ratio >= 0.10 else 0
    growth_score = clamp(freshness_score + evergreen_bonus)

    p75_view_score = log_score(p75_views, 3, 6)
    competition_score = clamp(top3_share * 45 + high_view_ratio * 35 + p75_view_score * 0.20)

    opportunity_score = clamp(demand_score * 0.55 + growth_score * 0.25 + result_depth_score * 0.20 - competition_score * 0.25 + 10)
    recommendation = recommendation_for_score(opportunity_score)
    reason = build_reason(demand_score, growth_score, competition_score, top3_share, high_view_ratio, recent_90_ratio)

    return {
        "platform": "bilibili",
        "keyword": keyword,
        "collected_videos": len(rows),
        "median_views": round(median_views),
        "avg_views": round(avg_views),
        "p75_views": round(p75_views),
        "max_views": max(views),
        "median_engagement": round(median_engagement),
        "avg_engagement": round(avg_engagement),
        "recent_30d_ratio": round(recent_30_ratio, 4),
        "recent_90d_ratio": round(recent_90_ratio, 4),
        "top3_view_share": round(top3_share, 4),
        "high_view_ratio": round(high_view_ratio, 4),
        "demand_score": round(demand_score, 1),
        "growth_score": round(growth_score, 1),
        "competition_score": round(competition_score, 1),
        "opportunity_score": round(opportunity_score, 1),
        "recommendation": recommendation,
        "reason": reason,
    }


def recommendation_for_score(score: float) -> str:
    if score >= 75:
        return "可执行"
    if score >= 55:
        return "小样本测试"
    return "暂不建议"


def build_reason(
    demand_score: float,
    growth_score: float,
    competition_score: float,
    top3_share: float,
    high_view_ratio: float,
    recent_90_ratio: float,
) -> str:
    reasons: List[str] = []
    if demand_score >= 70:
        reasons.append("需求强")
    elif demand_score >= 45:
        reasons.append("需求中等")
    else:
        reasons.append("需求偏弱")

    if growth_score >= 60 or recent_90_ratio >= 0.30:
        reasons.append("近期供给活跃")
    elif recent_90_ratio < 0.10:
        reasons.append("近期新增偏少")

    if competition_score >= 70 or top3_share >= 0.55:
        reasons.append("头部集中明显")
    elif high_view_ratio >= 0.30:
        reasons.append("爆款门槛较高")
    else:
        reasons.append("竞争可切入")

    return "；".join(reasons)


def load_keywords(args: argparse.Namespace) -> List[str]:
    keywords: List[str] = []
    for value in args.keyword or []:
        keywords.extend(part.strip() for part in re.split(r"[,，]", value) if part.strip())

    if args.keywords_file:
        with open(args.keywords_file, "r", encoding="utf-8-sig") as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    keywords.append(line)

    seen = set()
    unique_keywords = []
    for keyword in keywords:
        if keyword not in seen:
            unique_keywords.append(keyword)
            seen.add(keyword)
    return unique_keywords


def write_csv(path: str, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def collect_for_keyword(
    keyword: str,
    pages: int,
    config: FetchConfig,
    order: str,
    enrich: bool,
    max_results: Optional[int],
) -> List[Dict[str, Any]]:
    print(f"[B站] 采集关键词：{keyword}")
    rows = search_videos(keyword, pages, config, order)
    if max_results:
        rows = rows[:max_results]
    print(f"  搜索结果：{len(rows)} 条")

    if enrich:
        enriched_rows = []
        for index, row in enumerate(rows, start=1):
            try:
                enriched_rows.append(enrich_video(row, config))
            except RuntimeError as exc:
                print(f"  警告：补全 {row.get('bvid') or row.get('title')} 失败：{exc}", file=sys.stderr)
                enriched_rows.append(row)
            if index < len(rows):
                sleep_between_requests(config)
        rows = enriched_rows

    return rows


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="采集 B站关键词搜索结果，并输出热度排查 CSV。"
    )
    parser.add_argument("-k", "--keyword", action="append", help="关键词。可重复传入，也可用逗号分隔。")
    parser.add_argument("-f", "--keywords-file", help="关键词文件，每行一个关键词。")
    parser.add_argument("-p", "--pages", type=int, default=1, help="每个关键词采集搜索页数，默认 1。")
    parser.add_argument("--max-results", type=int, help="每个关键词最多保留多少条结果，适合小样本测试。")
    parser.add_argument("--suggestions-limit", type=int, default=10, help="每个关键词采集多少条搜索框联想词，默认 10。")
    parser.add_argument(
        "--order",
        default="totalrank",
        choices=["totalrank", "click", "pubdate", "dm", "stow"],
        help="B站搜索排序：综合 totalrank、播放 click、最新 pubdate、弹幕 dm、收藏 stow。",
    )
    parser.add_argument("-o", "--output-dir", default="outputs", help="输出目录，默认 outputs。")
    parser.add_argument("--sleep", type=float, default=0.8, help="请求间隔秒数，默认 0.8。")
    parser.add_argument("--timeout", type=float, default=12.0, help="单次请求超时秒数，默认 12。")
    parser.add_argument("--retries", type=int, default=3, help="失败重试次数，默认 3。")
    parser.add_argument("--allow-ipv6", action="store_true", help="允许 IPv6。默认强制 IPv4，以避免部分网络下 B站 TLS 握手超时。")
    parser.add_argument("--no-curl", action="store_true", help="不使用 curl 作为请求传输层，改用 Python urllib。")
    parser.add_argument("--no-enrich", action="store_true", help="只保存搜索页数据，不逐条补全视频统计。")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    keywords = load_keywords(args)

    if not keywords:
        parser.error("请通过 --keyword 或 --keywords-file 提供至少一个关键词。")

    pages = max(1, args.pages)
    config = FetchConfig(
        timeout=args.timeout,
        retries=max(1, args.retries),
        sleep_seconds=max(0, args.sleep),
        force_ipv4=not args.allow_ipv6,
        prefer_curl=not args.no_curl,
    )
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    all_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []
    suggestion_rows: List[Dict[str, Any]] = []
    failed_keywords: List[str] = []

    for keyword in keywords:
        try:
            suggestions = collect_suggestions(keyword, config, limit=max(0, args.suggestions_limit))
            suggestion_rows.extend(suggestions)
            if suggestions:
                print(f"  联想词：{', '.join(row['suggestion'] for row in suggestions)}")
        except RuntimeError as exc:
            print(f"  警告：采集 {keyword} 联想词失败：{exc}", file=sys.stderr)

        try:
            rows = collect_for_keyword(
                keyword,
                pages,
                config,
                args.order,
                enrich=not args.no_enrich,
                max_results=args.max_results,
            )
        except RuntimeError as exc:
            print(f"[失败] {keyword}: {exc}", file=sys.stderr)
            rows = []
            failed_keywords.append(keyword)

        all_rows.extend(rows)
        summary_rows.append(summarize_keyword(keyword, rows))

    detail_path = os.path.join(args.output_dir, f"bilibili_videos_{timestamp}.csv")
    summary_path = os.path.join(args.output_dir, f"bilibili_keyword_summary_{timestamp}.csv")
    suggestions_path = os.path.join(args.output_dir, f"bilibili_keyword_suggestions_{timestamp}.csv")
    write_csv(detail_path, all_rows, DETAIL_FIELDS)
    write_csv(summary_path, summary_rows, SUMMARY_FIELDS)
    write_csv(suggestions_path, suggestion_rows, SUGGESTION_FIELDS)

    print("")
    print("完成。")
    print(f"明细表：{detail_path}")
    print(f"汇总表：{summary_path}")
    print(f"联想词表：{suggestions_path}")
    if failed_keywords:
        print(f"失败关键词：{', '.join(failed_keywords)}")
    return 1 if failed_keywords and not all_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
