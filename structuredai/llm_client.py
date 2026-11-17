"""Stateless OpenAI-compatible HTTP client with GBNF, thinking strip & speed guard."""

from dataclasses import dataclass
import json
import re
import time
import urllib.error
import urllib.request

from structuredai.config import Config
from structuredai.gbnf_schemas import GBNF_GRAMMARS, SCHEMAS

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class LLMResponse:
    data: dict
    raw_text: str
    prompt_tokens: int
    completion_tokens: int
    duration_sec: float
    tokens_per_sec: float


def strip_and_parse_json(raw: str) -> dict:
    """Remove stray <think> tags or markdown fences and parse strict JSON."""
    cleaned = _THINK_RE.sub("", raw).strip()
    if not cleaned.startswith("{"):
        m = _JSON_FENCE_RE.search(cleaned)
        if m:
            cleaned = m.group(1)
        elif "{" in cleaned and "}" in cleaned:
            cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
    obj = json.loads(cleaned)
    if not isinstance(obj, dict):
        raise ValueError("LLM response JSON root must be an object")
    return obj


class LLMClient:
    """Stateless client targeting llama-server, Ollama, or OpenAI-compatible APIs."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.consecutive_anomalies = 0
        self.avg_tps = 0.0

    def _build_payload(self, role: str, sys_p: str, usr_p: str, temp: float | None) -> dict:
        model = self.cfg.llm_critique_model if (role == "3_CRITIQUE" and self.cfg.llm_critique_model) else self.cfg.llm_model
        payload: dict = {
            "model": model,
            "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
            "temperature": self.cfg.llm_temperature if temp is None else temp,
            "max_tokens": self.cfg.llm_max_output_tokens,
            "stream": False,
        }
        if self.cfg.llm_disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        mode = self.cfg.llm_structured_mode
        if mode == "gbnf" and self.cfg.llm_provider == "llama_cpp" and role in GBNF_GRAMMARS:
            payload["grammar"] = GBNF_GRAMMARS[role]
        elif mode in {"gbnf", "json_schema"} and role in SCHEMAS:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": role, "strict": True, "schema": SCHEMAS[role]}}
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload

    def complete(self, role: str, sys_p: str, usr_p: str, temp: float | None = None) -> LLMResponse:
        """Execute a single stateless completion call and validate structured JSON."""
        url = self.cfg.llm_base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(self._build_payload(role, sys_p, usr_p, temp)).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.llm_api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout_sec) as resp:
                raw_body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.consecutive_anomalies += 1
            raise RuntimeError(f"LLM HTTP error: {exc}") from exc
        dt = max(0.01, time.monotonic() - t0)
        content = raw_body["choices"][0]["message"]["content"] or ""
        usage = raw_body.get("usage", {})
        ptok = int(usage.get("prompt_tokens", len(sys_p + usr_p) // 3))
        ctok = int(usage.get("completion_tokens", max(1, len(content) // 3)))
        tps = ctok / dt
        self.avg_tps = tps if self.avg_tps == 0.0 else (0.7 * self.avg_tps + 0.3 * tps)
        if not content.strip() or (self.cfg.llm_provider == "llama_cpp" and ctok >= 10 and tps < self.cfg.min_tokens_per_sec):
            self.consecutive_anomalies += 1
        else:
            self.consecutive_anomalies = 0
        data = strip_and_parse_json(content)
        return LLMResponse(data=data, raw_text=content, prompt_tokens=ptok, completion_tokens=ctok, duration_sec=dt, tokens_per_sec=tps)
