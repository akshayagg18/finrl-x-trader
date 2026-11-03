# LLM research configuration

LLM analysis is optional, server-side, and research-only. The application works unchanged with no keys.

## Providers

- `openai`: Responses API with strict structured output; key from `OPENAI_API_KEY`.
- `anthropic`: Messages API with a forced schema tool; key from `ANTHROPIC_API_KEY`.
- `openai_compatible`: configurable Chat Completions endpoint; optional key environment variable.
- `ollama`: default `http://127.0.0.1:11434/v1/chat/completions`; no key.

Open Research & backtests → LLM Research to set the provider, exact model and endpoint. Credentials are never accepted by or returned to the browser. Configure input/output prices from the provider's current pricing page before authorizing paid research; the application does not hard-code prices that can become stale.

Paid requests require: `enabled=true`, a present server environment key, and `research_budget_authorized=true`. The default caps are $0.25/day and $5/month. Cache hits cost zero and do not count as provider requests.

## Data integrity

POST timestamped events to `/api/llm/news`. Every event requires publication, earliest demonstrable availability and retrieval times. `/api/llm/news?decision_time=...` returns only events available by that time. Do not import current search results into historical simulations.

Variants are available under `/api/llm/analyze/{baseline|features|agent}` and `/api/llm/veto`. All reject paper/live mode. `/api/llm/shadow` records prospective decisions without orders. The deterministic non-LLM control is `/api/llm/sentiment/non-llm`.

## Safety boundary

- No broker imports exist in `trader/llm`.
- No provider receives tools.
- External text is wrapped as untrusted data.
- Unknown JSON fields and invalid enums are rejected.
- A veto only changes `buy` to `hold`.
- Agent proposals are validated and returned with `order_submitted=false`.
- Provider errors fall back to the original quantitative action.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests\test_llm_research.py -q --basetemp=runtime\pytest-llm
.venv\Scripts\python.exe -m pytest tests\test_core.py tests\test_configuration_search.py tests\test_profitability.py tests\test_llm_research.py -q --basetemp=runtime\pytest-compatible
```
