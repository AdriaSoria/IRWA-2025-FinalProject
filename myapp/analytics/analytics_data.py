from __future__ import annotations
import random
import uuid
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd


@dataclass
class SessionRecord:
    session_id: str
    user_agent: str
    browser: str
    platform: str
    ip: str
    created_at: datetime
    last_seen: datetime
    request_count: int = 0


@dataclass
class RequestRecord:
    session_id: str
    path: str
    method: str
    timestamp: datetime
    query_params: Dict[str, Any]
    form_params: Dict[str, Any]


@dataclass
class QueryRecord:
    session_id: str
    query: str
    num_terms: int
    terms_order: List[str]
    timestamp: datetime
    results_count: int


@dataclass
class ClickRecord:
    click_id: str
    session_id: str
    pid: str
    query: Optional[str]
    rank: Optional[int]
    timestamp: datetime
    dwell_time: Optional[float] = None


class AnalyticsData:
    """
    In-memory analytics storage for educational purposes.
    Captures sessions, HTTP requests, queries, clicks, and dwell times.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, SessionRecord] = {}
        self.requests: List[RequestRecord] = []
        self.queries: List[QueryRecord] = []
        self.clicks: List[ClickRecord] = []
        self.fact_clicks: Dict[str, int] = defaultdict(int)
        self._click_lookup: Dict[str, ClickRecord] = {}

    # ------------------------------------------------------------------ #
    # Session & request tracking
    # ------------------------------------------------------------------ #
    def log_session(self, request, session_id: str) -> None:
        now = datetime.utcnow()
        ua = request.user_agent
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        record = self.sessions.get(session_id)
        if record:
            record.last_seen = now
            record.request_count += 1
        else:
            self.sessions[session_id] = SessionRecord(
                session_id=session_id,
                user_agent=ua.string,
                browser=ua.browser or "unknown",
                platform=ua.platform or "unknown",
                ip=ip or "unknown",
                created_at=now,
                last_seen=now,
                request_count=1,
            )

    def log_request(self, request, session_id: str) -> None:
        self.requests.append(
            RequestRecord(
                session_id=session_id,
                path=request.path,
                method=request.method,
                timestamp=datetime.utcnow(),
                query_params=request.args.to_dict(flat=True),
                form_params=request.form.to_dict(flat=True),
            )
        )

    # ------------------------------------------------------------------ #
    # Query logging
    # ------------------------------------------------------------------ #
    def log_query(self, session_id: str, query: str, results: List[Dict[str, Any]]) -> None:
        terms = [term for term in query.strip().split() if term]
        self.queries.append(
            QueryRecord(
                session_id=session_id,
                query=query,
                num_terms=len(terms),
                terms_order=terms,
                timestamp=datetime.utcnow(),
                results_count=len(results),
            )
        )

    # ------------------------------------------------------------------ #
    # Click logging + dwell time
    # ------------------------------------------------------------------ #
    def log_click(
        self,
        session_id: str,
        pid: str,
        query: Optional[str],
        rank: Optional[int],
    ) -> str:
        click_id = str(uuid.uuid4())
        record = ClickRecord(
            click_id=click_id,
            session_id=session_id,
            pid=pid,
            query=query,
            rank=rank,
            timestamp=datetime.utcnow(),
        )
        self.clicks.append(record)
        self._click_lookup[click_id] = record
        self.fact_clicks[pid] += 1
        return click_id

    def register_dwell(self, click_id: str, dwell_time: float) -> None:
        record = self._click_lookup.get(click_id)
        if record:
            record.dwell_time = dwell_time

    # ------------------------------------------------------------------ #
    # Convenience helpers for visualisations
    # ------------------------------------------------------------------ #
    def get_summary(self) -> Dict[str, Any]:
        total_sessions = len(self.sessions)
        total_requests = len(self.requests)
        total_queries = len(self.queries)
        total_clicks = len(self.clicks)
        avg_terms = (
            sum(record.num_terms for record in self.queries) / total_queries if total_queries else 0
        )
        avg_dwell = (
            sum(record.dwell_time for record in self.clicks if record.dwell_time)
            / max(len([c for c in self.clicks if c.dwell_time]), 1)
            if self.clicks
            else 0
        )
        return {
            "total_sessions": total_sessions,
            "total_requests": total_requests,
            "total_queries": total_queries,
            "total_clicks": total_clicks,
            "avg_terms": round(avg_terms, 2),
            "avg_dwell": round(avg_dwell, 2),
        }

    def get_recent_queries(self, limit: int = 10) -> List[QueryRecord]:
        return list(sorted(self.queries, key=lambda q: q.timestamp, reverse=True))[:limit]

    def get_top_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        items = sorted(self.fact_clicks.items(), key=lambda item: item[1], reverse=True)
        return [{"pid": pid, "count": count} for pid, count in items[:limit]]

    def get_clicks_by_hour(self) -> List[Dict[str, Any]]:
        counter: Counter[int] = Counter()
        for click in self.clicks:
            counter[click.timestamp.hour] += 1
        return [{"hour": hour, "clicks": counter.get(hour, 0)} for hour in range(24)]

    def get_device_mix(self) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        for record in self.sessions.values():
            counter[record.platform] += 1
        total = sum(counter.values()) or 1
        return [
            {"platform": platform.title(), "percentage": round(count / total * 100, 1)}
            for platform, count in counter.items()
        ]

    def save_query_terms(self, terms: str) -> int:
        return random.randint(0, 100000)

    def plot_number_of_views(self) -> str:
        data = [{"Document ID": pid, "Number of Views": count} for pid, count in self.fact_clicks.items()]
        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame([{"Document ID": "N/A", "Number of Views": 0}])
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x="Document ID", y="Number of Views")
            .properties(title="Number of Views per Document")
        )
        return chart.to_html()


class ClickedDoc:
    def __init__(self, doc_id: str, description: str, counter: int):
        self.doc_id = doc_id
        self.description = description
        self.counter = counter

    def to_json(self) -> Dict[str, Any]:
        return self.__dict__

    def __str__(self) -> str:
        return json.dumps(self.__dict__)
