"""Minimal fashion search webapp powered by Flask + Word2Vec retrieval."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import Flask, abort, render_template, request, session

from myapp.analytics.analytics_data import AnalyticsData, ClickedDoc
from myapp.generation.rag import RAGAssistant
from myapp.search.algorithms import get_retrieval_engine
from myapp.search.load_corpus import load_corpus
from myapp.search.objects import StatsDocument

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_PATH = BASE_DIR / "data" / "products.json"
CATALOG_CSV_PATH = BASE_DIR / "data" / "productos_preprocesados.csv"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fashion-search-dev-secret")

# Load resources once at startup
corpus = load_corpus(PRODUCTS_PATH)
retrieval_engine = get_retrieval_engine(
    catalog_csv_path=CATALOG_CSV_PATH,
    metadata_path=PRODUCTS_PATH,
)
rag_assistant = RAGAssistant()
analytics = AnalyticsData()
def _get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def _finalize_pending_click() -> None:
    pending = session.pop("pending_click", None)
    if not pending:
        return
    try:
        started = datetime.fromisoformat(pending["timestamp"])
        dwell = max((datetime.utcnow() - started).total_seconds(), 0)
        analytics.register_dwell(pending["click_id"], dwell)
    except (ValueError, KeyError):
        pass


@app.before_request
def track_request() -> None:
    session_id = _get_session_id()
    analytics.log_session(request, session_id)
    analytics.log_request(request, session_id)


def _format_currency(value: Any) -> str | None:
    if value in (None, "", "nan"):
        return None
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return None


def _format_percentage(value: Any) -> str | None:
    if value in (None, "", "nan"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"{number:.0f}% OFF"


app.jinja_env.filters["currency"] = _format_currency
app.jinja_env.filters["percentage"] = _format_percentage


@app.context_processor
def inject_globals() -> Dict[str, str]:
    return {"app_name": "Maison IRWA"}


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/search", methods=["GET", "POST"])
def search():
    session_id = _get_session_id()
    _finalize_pending_click()
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if not query:
            return render_template("index.html", error="Por favor ingresa una búsqueda.")
        results = retrieval_engine.search(query, top_n=20)
        analytics.log_query(session_id, query, results)
        session["last_query"] = query
        session["last_rank_map"] = {item["pid"]: item.get("rank") for item in results}
        summary = rag_assistant.summarize(query, results)
        return render_template("results.html", query=query, results=results, summary=summary)

    query = request.args.get("q", "").strip()
    if not query:
        return render_template("index.html")
    results = retrieval_engine.search(query, top_n=20)
    analytics.log_query(session_id, query, results)
    session["last_query"] = query
    session["last_rank_map"] = {item["pid"]: item.get("rank") for item in results}
    summary = rag_assistant.summarize(query, results)
    return render_template("results.html", query=query, results=results, summary=summary)


@app.route("/product/<pid>", methods=["GET"])
def product_detail(pid: str):
    session_id = _get_session_id()
    product = corpus.get(pid)
    if not product:
        abort(404)
    rank_map = session.get("last_rank_map", {}) or {}
    click_id = analytics.log_click(
        session_id=session_id,
        pid=pid,
        query=session.get("last_query"),
        rank=rank_map.get(pid),
    )
    session["pending_click"] = {"click_id": click_id, "timestamp": datetime.utcnow().isoformat()}
    product_dict = product.model_dump()
    product_details = product_dict.get("product_details") or {}
    if isinstance(product_details, list):
        # Safety net: convert list of dicts to a merged dict
        merged: Dict[str, Any] = {}
        for entry in product_details:
            if isinstance(entry, dict):
                merged.update(entry)
        product_details = merged
    product_dict["product_details"] = product_details
    return render_template("product.html", product=product_dict)


@app.route("/health", methods=["GET"])
def healthcheck():
    return {"status": "ok", "documents": len(corpus)}


@app.route("/stats", methods=["GET"])
def stats():
    docs = []
    for doc_id, count in analytics.fact_clicks.items():
        row = corpus.get(doc_id)
        if not row:
            continue
        doc = StatsDocument(
            pid=row.pid,
            title=row.title,
            description=row.description,
            url=row.url,
            count=count,
        )
        docs.append(doc)
    docs.sort(key=lambda doc: doc.count or 0, reverse=True)
    summary = analytics.get_summary()
    recent_queries = analytics.get_recent_queries()
    device_mix = analytics.get_device_mix()
    clicks_by_hour = analytics.get_clicks_by_hour()
    return render_template(
        "stats.html",
        clicks_data=docs,
        summary=summary,
        recent_queries=recent_queries,
        device_mix=device_mix,
        clicks_by_hour=clicks_by_hour,
    )


@app.route("/dashboard", methods=["GET"])
def dashboard():
    visited_docs = []
    for doc_id, count in analytics.fact_clicks.items():
        row = corpus.get(doc_id)
        if not row:
            continue
        visited_docs.append(ClickedDoc(doc_id=row.pid, description=row.description or "", counter=count))
    visited_docs.sort(key=lambda doc: doc.counter, reverse=True)
    top_queries = analytics.get_recent_queries()
    device_mix = analytics.get_device_mix()
    return render_template(
        "dashboard.html",
        visited_docs=visited_docs,
        top_queries=top_queries,
        device_mix=device_mix,
    )


@app.route("/plot_number_of_views", methods=["GET"])
def plot_number_of_views():
    return analytics.plot_number_of_views()


def create_app() -> Flask:
    """Flask factory compatible with `flask run`."""
    return app


if __name__ == "__main__":
    app.run(debug=True)

