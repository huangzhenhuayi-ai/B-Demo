#!/usr/bin/env python3
"""
Local web UI for the Bilibili keyword heat checker.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import posixpath
import threading
import traceback
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from bilibili_keyword_probe import (
    DETAIL_FIELDS,
    SUMMARY_FIELDS,
    SUGGESTION_FIELDS,
    FetchConfig,
    collect_suggestions,
    collect_for_keyword,
    summarize_keyword,
    write_csv,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "outputs"

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def parse_keywords(raw: str) -> List[str]:
    keywords: List[str] = []
    for line in raw.replace("，", "\n").replace(",", "\n").splitlines():
        keyword = line.strip()
        if keyword:
            keywords.append(keyword)

    seen = set()
    result = []
    for keyword in keywords:
        if keyword not in seen:
            result.append(keyword)
            seen.add(keyword)
    return result


def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "id",
        "status",
        "message",
        "keywords",
        "created_at",
        "started_at",
        "finished_at",
        "current_keyword",
        "completed_keywords",
        "total_keywords",
        "summary",
        "suggestions",
        "details_preview",
        "files",
        "error",
    }
    return {key: job.get(key) for key in allowed if key in job}


def update_job(job_id: str, **updates: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def run_job(job_id: str, options: Dict[str, Any]) -> None:
    keywords = options["keywords"]
    pages = options["pages"]
    max_results = options.get("max_results")
    order = options["order"]
    enrich = options["enrich"]
    suggestions_limit = options["suggestions_limit"]
    config = FetchConfig(
        timeout=options["timeout"],
        retries=options["retries"],
        sleep_seconds=options["sleep"],
        force_ipv4=options["force_ipv4"],
    )

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / f"web_run_{timestamp}_{job_id[:8]}"
    detail_path = run_dir / "bilibili_videos.csv"
    summary_path = run_dir / "bilibili_keyword_summary.csv"
    suggestions_path = run_dir / "bilibili_keyword_suggestions.csv"

    all_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []
    suggestion_rows: List[Dict[str, Any]] = []

    update_job(
        job_id,
        status="running",
        started_at=dt.datetime.now().isoformat(timespec="seconds"),
        message="开始采集",
        completed_keywords=0,
        total_keywords=len(keywords),
    )

    try:
        for index, keyword in enumerate(keywords, start=1):
            update_job(
                job_id,
                current_keyword=keyword,
                message=f"正在采集联想词：{keyword}",
                completed_keywords=index - 1,
            )
            try:
                suggestions = collect_suggestions(keyword, config, limit=suggestions_limit)
            except Exception as exc:  # pragma: no cover - network dependent
                suggestions = [
                    {
                        "platform": "bilibili",
                        "keyword": keyword,
                        "suggestion_rank": 0,
                        "suggestion": "",
                        "highlighted": f"采集失败：{exc}",
                        "source": "search_box",
                    }
                ]
            suggestion_rows.extend(suggestions)
            update_job(
                job_id,
                suggestions=suggestion_rows,
                message=f"正在采集视频：{keyword}",
            )

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
                summary_rows.append(empty_summary(keyword, str(exc)))
            else:
                all_rows.extend(rows)
                summary_rows.append(summarize_keyword(keyword, rows))

            update_job(
                job_id,
                completed_keywords=index,
                summary=summary_rows,
                suggestions=suggestion_rows,
                details_preview=all_rows[:100],
            )

        write_csv(str(detail_path), all_rows, DETAIL_FIELDS)
        write_csv(str(summary_path), summary_rows, SUMMARY_FIELDS)
        write_csv(str(suggestions_path), suggestion_rows, SUGGESTION_FIELDS)
        update_job(
            job_id,
            status="done",
            message="采集完成",
            finished_at=dt.datetime.now().isoformat(timespec="seconds"),
            current_keyword="",
            summary=summary_rows,
            suggestions=suggestion_rows,
            details_preview=all_rows[:100],
            files={
                "detail": f"/api/download/{job_id}/detail",
                "summary": f"/api/download/{job_id}/summary",
                "suggestions": f"/api/download/{job_id}/suggestions",
                "detail_path": str(detail_path),
                "summary_path": str(summary_path),
                "suggestions_path": str(suggestions_path),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        update_job(
            job_id,
            status="error",
            message="采集失败",
            error=f"{exc}\n{traceback.format_exc()}",
            finished_at=dt.datetime.now().isoformat(timespec="seconds"),
        )


def empty_summary(keyword: str, error: str) -> Dict[str, Any]:
    row = {field: 0 for field in SUMMARY_FIELDS}
    row.update(
        {
            "platform": "bilibili",
            "keyword": keyword,
            "recommendation": "暂不建议",
            "reason": f"采集失败：{error}",
        }
    )
    return row


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "BilibiliKeywordProbe/1.0"

    def do_GET(self) -> None:
        if self.path.startswith("/api/runs/"):
            self.handle_job_status()
            return
        if self.path.startswith("/api/download/"):
            self.handle_download()
            return
        self.serve_static()

    def do_POST(self) -> None:
        if self.path == "/api/runs":
            self.handle_create_job()
            return
        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def handle_create_job(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            keywords = parse_keywords(str(payload.get("keywords", "")))
            if not keywords:
                self.send_json({"error": "请至少输入一个关键词"}, HTTPStatus.BAD_REQUEST)
                return

            options = {
                "keywords": keywords,
                "pages": clamp_int(payload.get("pages"), 1, 5, default=1),
                "max_results": optional_int(payload.get("max_results"), 1, 200),
                "order": payload.get("order") if payload.get("order") in {"totalrank", "click", "pubdate", "dm", "stow"} else "totalrank",
                "sleep": clamp_float(payload.get("sleep"), 0.1, 10.0, default=1.0),
                "timeout": clamp_float(payload.get("timeout"), 3.0, 60.0, default=15.0),
                "retries": clamp_int(payload.get("retries"), 1, 5, default=2),
                "suggestions_limit": clamp_int(payload.get("suggestions_limit"), 0, 20, default=10),
                "enrich": bool(payload.get("enrich", True)),
                "force_ipv4": bool(payload.get("force_ipv4", True)),
            }
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "status": "queued",
                "message": "等待开始",
                "keywords": keywords,
                "created_at": dt.datetime.now().isoformat(timespec="seconds"),
                "completed_keywords": 0,
                "total_keywords": len(keywords),
                "summary": [],
                "suggestions": [],
                "details_preview": [],
            }
            with JOBS_LOCK:
                JOBS[job_id] = job

            thread = threading.Thread(target=run_job, args=(job_id, options), daemon=True)
            thread.start()
            self.send_json(public_job(job), HTTPStatus.CREATED)
        except json.JSONDecodeError:
            self.send_json({"error": "请求体不是有效 JSON"}, HTTPStatus.BAD_REQUEST)

    def handle_job_status(self) -> None:
        job_id = self.path.rsplit("/", 1)[-1]
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            data = public_job(job) if job else None
        if not data:
            self.send_json({"error": "任务不存在"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(data)

    def handle_download(self) -> None:
        parts = self.path.split("/")
        if len(parts) < 5:
            self.send_json({"error": "下载地址无效"}, HTTPStatus.BAD_REQUEST)
            return
        job_id = parts[3]
        kind = parts[4]
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if not job or job.get("status") != "done":
            self.send_json({"error": "文件还未生成"}, HTTPStatus.NOT_FOUND)
            return
        files = job.get("files") or {}
        if kind == "summary":
            path_key = "summary_path"
        elif kind == "suggestions":
            path_key = "suggestions_path"
        else:
            path_key = "detail_path"
        path = Path(files.get(path_key, ""))
        if not path.exists() or not path.is_file():
            self.send_json({"error": "文件不存在"}, HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as file:
            self.wfile.write(file.read())

    def serve_static(self) -> None:
        path = urllib_unquote_path(self.path.split("?", 1)[0])
        if path == "/":
            path = "/index.html"
        safe_path = posixpath.normpath(path).lstrip("/")
        target = (STATIC_DIR / safe_path).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = guess_content_type(target)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as file:
            self.wfile.write(file.read())

    def send_json(self, data: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def optional_int(value: Any, low: int, high: int) -> Optional[int]:
    if value in (None, "", 0, "0"):
        return None
    return clamp_int(value, low, high, default=low)


def clamp_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def urllib_unquote_path(path: str) -> str:
    from urllib.parse import unquote

    return unquote(path)


def guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 B站关键词热度排查工具 Web 界面。")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1。")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765。")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"可视化界面已启动：http://{args.host}:{args.port}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
