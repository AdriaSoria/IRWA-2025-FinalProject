"""Gemini-only RAG helper with inline API key support."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import google.generativeai as genai  # type: ignore

# Note: Storing API keys directly in source code is generally insecure and bad practice.
# However, since this key is free for demo/testing and for simplicity in this project, we place it here.

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


class RAGAssistant:
    PROMPT_TEMPLATE = """
You are an assistant for an e-commerce search engine.

User query:
\"\"\"{query}\"\"\"

Below is a list of products retrieved for this query.
Each product has fields such as title, brand, price, discount, rating and description.

Products:
{product_block}

Your task:

1. Briefly describe what type of products were found.
2. Highlight key trends (e.g., price range, typical discounts, ratings, popular brands).
3. Suggest:
   - A "Best budget" option (if there is at least one clearly cheaper option).
   - A "Best overall" option (if there is at least one with high rating / good value).
4. ONLY use the information given in the product list. Do NOT invent features.
5. Maximum length: 3 sentences.

Return plain text, no bullet points or markdown.
""".strip()

    def __init__(self, model_name: str = "gemini-2.0-flash", max_products: int = 20) -> None:
        if not GEMINI_API_KEY or GEMINI_API_KEY == "PASTE_YOUR_GEMINI_KEY_HERE":
            raise RuntimeError(
                "Set GEMINI_API_KEY in your environment or replace GEMINI_API_KEY constant."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(model_name)
        self.max_products = max_products

    def summarize(self, query: str, results: List[Dict[str, Any]]) -> Optional[str]:
        if not results:
            return None
        product_block = self._format_products(results[: self.max_products])
        prompt = self.PROMPT_TEMPLATE.format(query=query, product_block=product_block)
        try:
            response = self.model.generate_content(prompt)
            text = getattr(response, "text", None)
            return text.strip() if text else None
        except Exception as exc:  # pragma: no cover
            print(f"[RAGAssistant] Gemini generation failed: {exc}")
            return None

    def _format_products(self, products: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for idx, product in enumerate(products, start=1):
            title = product.get("title") or "Untitled"
            brand = product.get("brand")
            price = product.get("selling_price") or product.get("actual_price") or "N/A"
            discount = product.get("discount")
            rating = product.get("average_rating")
            description = product.get("description") or ""
            url = product.get("url") or ""

            block = [f"Product {idx}:", f"  Title: {title}"]
            if brand:
                block.append(f"  Brand: {brand}")
            block.append(f"  Price: {price}")
            if discount not in (None, "", 0, "0%"):
                block.append(f"  Discount: {discount}")
            if rating not in (None, ""):
                block.append(f"  Rating: {rating}")
            if description:
                block.append(f"  Description: {description[:200]}")
            if url:
                block.append(f"  URL: {url}")
            lines.append("\n".join(block))
        return "\n\n".join(lines)
