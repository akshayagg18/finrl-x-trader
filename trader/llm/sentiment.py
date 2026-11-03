from __future__ import annotations

import re


class LexiconFinancialSentiment:
    """Zero-cost deterministic NLP control, not branded or reported as FinBERT."""

    positive = {"beat", "growth", "profit", "upgrade", "surge", "approval", "record", "gain"}
    negative = {"miss", "loss", "downgrade", "fraud", "breach", "lawsuit", "decline", "warning"}

    def score(self, text: str) -> dict:
        words = re.findall(r"[a-z]+", text.lower())
        pos = sum(w in self.positive for w in words)
        neg = sum(w in self.negative for w in words)
        total = max(1, pos + neg)
        return {
            "label": "positive" if pos > neg else "negative" if neg > pos else "neutral",
            "score": (pos - neg) / total,
            "model": "deterministic_financial_lexicon_v1",
            "cost_usd": 0.0,
        }


class FinBERTSentiment:
    """Optional local adapter; never downloads a model unless explicitly allowed."""

    def __init__(self, model="ProsusAI/finbert", *, local_files_only=True):
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("Install the optional transformers stack to use FinBERT") from exc
        self.pipe = pipeline(
            "text-classification", model=model, tokenizer=model, local_files_only=local_files_only,
            truncation=True,
        )
        self.model = model

    def score(self, text: str) -> dict:
        result = self.pipe(text[:5000])[0]
        label = result["label"].lower()
        signed = float(result["score"]) * (-1 if "negative" in label else 1 if "positive" in label else 0)
        return {"label": label, "score": signed, "model": self.model, "cost_usd": 0.0}
