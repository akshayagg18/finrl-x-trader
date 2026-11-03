# LLM trading research

## Evidence reviewed

Research and source code were inspected on 3 November 2026.

| Source | What it actually provides | Applicability / limitation |
|---|---|---|
| [TradingAgents paper](https://arxiv.org/abs/2412.20138) and repository commit `c454491` | Multi-agent analyst, debate, trader and risk roles; provider abstraction; dated-data guards; structured proposals | Its `backtest.py` explicitly scores independent decisions rather than a cash portfolio and says text feeds are not archived, so headline performance is not transferable to this $500 execution model. Its free-text fallback is unsuitable for orders. |
| [AI-Trader paper](https://arxiv.org/abs/2512.10971) and repository commit `d03ff6c` | Agent registration, signal exchange, challenges, simulated accounts and research exports | Primarily platform and simulated execution infrastructure; not proof that an LLM creates alpha. Its documented default simulated capital is far above $500. |
| [FinGPT paper](https://arxiv.org/abs/2306.06031) and repository commit `ac5c544` | Financial instruction tuning, sentiment and forecasting components | Most defensible here as a feature extractor. Large local models are operationally excessive for a $500 portfolio, and sentiment accuracy is not trading profitability. |
| [FinBERT paper](https://arxiv.org/abs/1908.10063) and [ProsusAI implementation](https://github.com/ProsusAI/finBERT) | Three-way financial sentiment probabilities using a finance-domain BERT | A strong zero-API-cost baseline when the model is already installed locally; still requires timestamp-safe text and profitability validation. |
| [Sentiment trading with LLMs](https://discovery.ucl.ac.uk/id/eprint/10190583/) | Large news sample, model comparisons and a costed long-short study | Evidence that text features can matter, but a broad U.S. equity long-short design does not transfer to long-only $500 BTC trading. |
| [Expected Returns and Large Language Models](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687) | LLM embeddings and cross-sectional return prediction after stated costs | Encouraging institutional evidence; depends on broad universes and proprietary-quality point-in-time news. |
| [AI's predictable memory in financial analysis](https://doi.org/10.1016/j.econlet.2025.112602) | Direct measurement of LLM historical-return memorization | Supports avoiding retrospective identifiable-event prompts as clean evidence. |
| [Financial LLM bias review](https://arxiv.org/abs/2602.14233) | Review of look-ahead, survivorship, narrative, objective and cost biases | Reinforces structural-validity gates before any deployment claim. |
| [The Price of Thought](https://arxiv.org/abs/2609.30705) | Controlled comparison of reasoning levels and economic outcomes | More reasoning changes decisions without reliably improving after-cost value; multi-agent token spend needs evidence. |

## Engineering conclusion

The plausible use is an event-driven veto or timestamp-safe feature extractor, not an unconstrained agent queried every tick. LLM output is untrusted data. The implementation therefore:

- uses strict Pydantic/JSON schemas and rejects unknown fields;
- sends no tools and exposes no broker object;
- wraps retrieved text as untrusted data and tells the model to ignore embedded instructions;
- records source IDs and availability timestamps;
- caches identical requests and caps requests and spend;
- defaults disabled and requires explicit paid-research authorization;
- falls back to the unchanged baseline on failure;
- records prospective shadow decisions without submitting orders.

Official OpenAI documentation recommends server-side API keys and Structured Outputs with strict JSON Schema; the adapter uses the Responses API shape, checks/validates the response again locally, and records usage. See [API authentication](https://developers.openai.com/api/reference/overview) and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## Historical-data decision

The repository has no archived, licensed point-in-time news corpus with demonstrable availability timestamps. Current web searches cannot recreate what the bot could have seen at an old decision time, and an LLM may remember later outcomes. Consequently, no historical LLM trading return is manufactured. The correct next experiment is prospective shadow collection using newly ingested timestamped events.
