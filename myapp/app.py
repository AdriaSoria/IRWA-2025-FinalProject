"""Minimal fashion search webapp powered by Flask + Word2Vec retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from flask import Flask, abort, render_template, request

from myapp.generation.rag import RAGAssistant
from myapp.search.algorithms import get_retrieval_engine
from myapp.search.load_corpus import load_corpus

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
PRODUCTS_PATH = BASE_DIR / "products.json"
CATALOG_CSV_PATH = PROJECT_ROOT / "data" / "productos_preprocesados.csv"

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)

# Load resources once at startup
corpus = load_corpus(PRODUCTS_PATH)
retrieval_engine = get_retrieval_engine(
    catalog_csv_path=CATALOG_CSV_PATH,
    metadata_path=PRODUCTS_PATH,
)
rag_assistant = RAGAssistant()


def _format_currency(value: Any) -> str | None:
    if value in (None, "", "nan"):
        return None
    try:
        return f"€{float(value):,.2f}"
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
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if not query:
            return render_template("index.html", error="Por favor ingresa una búsqueda.")
        results = retrieval_engine.search(query, top_n=20)
        summary = rag_assistant.summarize(query, results)
        return render_template("results.html", query=query, results=results, summary=summary)

    query = request.args.get("q", "").strip()
    if not query:
        return render_template("index.html")
    results = retrieval_engine.search(query, top_n=20)
    summary = rag_assistant.summarize(query, results)
    return render_template("results.html", query=query, results=results, summary=summary)


@app.route("/product/<pid>", methods=["GET"])
def product_detail(pid: str):
    product = corpus.get(pid)
    if not product:
        abort(404)
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


def create_app() -> Flask:
    """Flask factory compatible with `flask run`."""
    return app


if __name__ == "__main__":
    app.run(debug=True)

