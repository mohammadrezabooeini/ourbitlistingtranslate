"""Spot-only description translator. Futures must never call this module.

Default backend is Groq (free AI). If Groq is unavailable, Google Translate
and MyMemory are used as fallback. The bot never crashes on translation errors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Protocol, Sequence

from .utils import to_persian_digits

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_MODEL_FALLBACKS = (
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
)
DEPRECATED_GROQ_MODELS = {
    "qwen/qwen3.6-27b": "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile": "qwen/qwen3.8-27b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
}
USER_AGENT = "Mozilla/5.0 (compatible; OurbitSelfBot/1.0)"
TICKER_LEAD_RE = re.compile(r"^(?:\$?[A-Za-z0-9]{1,20})\s*(?:--+|[-–—:])\s*")
CASHTAG_RE = re.compile(r"(?<!\*)(\$[A-Za-z0-9]+)(?!\*)")
PERSIAN_LETTER_RE = re.compile(
    r"[\u0621-\u063A\u0641-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CC]"
)
META_LABEL_NAMES = (
    "Literal",
    "Crypto Channel Vibe",
    "Analyze User Input",
    "Thinking Process",
    "Here's a thinking process",
    "Source Text",
    "Task",
    "Constraints",
    "Output",
    "Translation",
    "Final answer",
    "Final",
    "Reasoning",
    "Notes",
    "Note",
    "Explanation",
)
META_LABEL_PATTERN = "|".join(
    re.escape(name) for name in sorted(META_LABEL_NAMES, key=len, reverse=True)
)
LABEL_SPLIT_RE = re.compile(
    rf"(?:^|\n|\s*[-*]\s+)({META_LABEL_PATTERN})\s*:\s*",
    re.IGNORECASE,
)
GLOSSARY_LINE_RE = re.compile(
    r'^\s*[-*]?\s*(?:["“].+["”]|[A-Za-z][A-Za-z0-9 \-]{1,40})\s*(?:->|→)'
)
QUOTED_ENGLISH_LEFTOVER_RE = re.compile(r'^\s*[-*]?\s*["“][A-Za-z].*')
TRAILING_ENGLISH_QUOTE_RE = re.compile(r'\s*[-–—*]*\s*["“][A-Za-z].*$')
QWEN_EXTRA_KEYS = ("reasoning_effort", "reasoning_format", "presence_penalty", "top_p")
REASONING_MARKERS = (
    "analyze user input",
    "thinking process",
    "source text",
    "constraints",
    "i must keep",
    "chain-of-thought",
    "here's a thinking",
    "the user wants",
    "the user asked",
    "the task is",
)


class TranslatorBackend(Protocol):
    async def translate(self, text: str, preserve_terms: Sequence[str]) -> str:
        ...


def strip_ticker_lead(text: str) -> str:
    """Drop a leading 'FLORK --' / '$ORBIO:' so only the description is translated."""
    return TICKER_LEAD_RE.sub("", text.strip(), count=1).strip()


def protect_terms(text: str, terms: Sequence[str]) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    protected = text
    unique = sorted({term for term in terms if term}, key=len, reverse=True)
    for index, term in enumerate(unique):
        if term not in protected:
            continue
        token = f"XKEEP{index}X"
        protected = protected.replace(term, token)
        mapping[token] = term
    return protected, mapping


def restore_terms(text: str, mapping: dict[str, str]) -> str:
    restored = text
    for token, term in mapping.items():
        restored = re.sub(re.escape(token), term, restored, flags=re.IGNORECASE)
    return restored


def emphasize_translated(text: str) -> str:
    with_persian_digits = to_persian_digits(text)
    return CASHTAG_RE.sub(r"**\1**", with_persian_digits).strip()


def _visible_preserve_terms(text: str, preserve_terms: Sequence[str]) -> list[str]:
    return [term for term in preserve_terms if term and term in text]


def _spot_prompt(text: str, preserve_terms: Sequence[str]) -> list[dict[str, str]]:
    visible_terms = _visible_preserve_terms(text, preserve_terms)
    user = (
        "Translate this token description into natural Iranian Persian "
        "for a Farsi crypto channel. Do not translate word-for-word.\n"
    )
    if visible_terms:
        user += "Keep these names exactly as written: " + ", ".join(sorted(set(visible_terms))) + "\n"
    user += (
        "Reply with only the final Persian translation. "
        "No thinking, labels, analysis, alternatives, or leftover English.\n\n"
        f"{text}"
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a Persian crypto-channel translator. "
                "You receive only the English description field. "
                "Reply with the final Persian translation and nothing else."
            ),
        },
        {"role": "user", "content": user},
    ]


def _is_qwen_model(model: str) -> bool:
    return "qwen" in model.lower()


def _groq_chat_payload(model: str, text: str, preserve_terms: Sequence[str]) -> dict:
    messages = _spot_prompt(text, preserve_terms)
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": 300,
    }
    if _is_qwen_model(model):
        messages[-1]["content"] += "\n/no_think"
        payload.update(
            {
                "temperature": 0.7,
                "top_p": 0.80,
                "presence_penalty": 1.5,
                "reasoning_effort": "none",
                "reasoning_format": "hidden",
            }
        )
    else:
        payload.update(
            {
                "temperature": 0.3,
                "reasoning_format": "hidden",
            }
        )
    return payload


def _persian_letter_count(text: str) -> int:
    return len(PERSIAN_LETTER_RE.findall(text))


def _is_mostly_persian(text: str) -> bool:
    letters = _persian_letter_count(text)
    latin = len(re.findall(r"[A-Za-z]", text))
    return letters >= 4 and letters >= latin


def _is_analysis_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REASONING_MARKERS)


def _persian_slice(text: str) -> str:
    matches = list(PERSIAN_LETTER_RE.finditer(text))
    if not matches:
        return ""
    start = matches[0].start()
    end = matches[-1].end()
    tail = text[end:]
    extra = re.match(
        r"(?:[\s$#!@/.\-]*[A-Za-z0-9]{1,20}){0,6}[\s.؟!؛,،]*",
        tail,
    )
    if extra and not re.search(r"\b[a-z]{4,}\b", extra.group(0)):
        end += extra.end()
    return text[start:end].strip(" \t-–—*")


def _usable_persian(text: str) -> str:
    stripped = TRAILING_ENGLISH_QUOTE_RE.sub("", text).strip().strip('"').strip("'")
    if GLOSSARY_LINE_RE.match(stripped) or QUOTED_ENGLISH_LEFTOVER_RE.match(stripped):
        return ""
    if _is_analysis_text(stripped) and not _is_mostly_persian(stripped):
        return ""
    if _is_mostly_persian(stripped):
        return stripped
    sliced = _persian_slice(stripped)
    if sliced and _is_mostly_persian(sliced):
        return sliced
    return ""


def _split_labeled_segments(text: str) -> list[tuple[str | None, str]]:
    parts: list[tuple[str | None, str]] = []
    last = 0
    current_label: str | None = None
    for match in LABEL_SPLIT_RE.finditer(text):
        chunk = text[last:match.start()].strip()
        if chunk:
            parts.append((current_label, chunk))
        current_label = match.group(1)
        last = match.end()
    tail = text[last:].strip()
    if tail:
        parts.append((current_label, tail))
    elif not parts:
        parts.append((None, text.strip()))
    return parts


def _clean_llm_translation(content: str) -> str:
    """Keep only the final Persian translation; drop Qwen reasoning/labels."""
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)

    vibe_parts: list[str] = []
    literal_parts: list[str] = []
    other_parts: list[str] = []

    for label, chunk in _split_labeled_segments(cleaned):
        for raw_line in chunk.splitlines():
            body = _usable_persian(raw_line)
            if not body:
                continue
            label_key = (label or "").lower()
            if "vibe" in label_key:
                vibe_parts.append(body)
            elif "literal" in label_key:
                literal_parts.append(body)
            else:
                other_parts.append(body)

    chosen = vibe_parts or other_parts or literal_parts
    result = " ".join(chosen).strip()
    result = re.sub(r"\s+", " ", result).strip()
    if len(result) > 700:
        result = result[:700].rsplit(" ", 1)[0].rstrip("،,;:") + "…"
    return result


class PassthroughBackend:
    """Keeps English text. Used when translation is explicitly turned off."""

    async def translate(self, text: str, preserve_terms: Sequence[str]) -> str:
        logger.info("Translation is disabled; using original Spot description.")
        return text


class FreeBackend:
    """No API key. Tries Google Translate, then MyMemory. Both are free."""

    def __init__(self, providers: Sequence[Callable[[str], str]] | None = None) -> None:
        self.providers = list(providers) if providers is not None else [
            _google_translate,
            _mymemory_translate,
        ]

    async def translate(self, text: str, preserve_terms: Sequence[str]) -> str:
        prepared = strip_ticker_lead(text)
        protected, mapping = protect_terms(prepared, preserve_terms)
        try:
            translated = await asyncio.to_thread(self._translate_with_fallback, protected)
        except Exception:
            logger.exception("Free translation failed; using original Spot description.")
            return text
        if not translated:
            logger.error("Free translator returned empty text; using original description.")
            return text
        restored = restore_terms(translated, mapping)
        return emphasize_translated(restored)

    def _translate_with_fallback(self, text: str) -> str:
        errors: list[str] = []
        for provider in self.providers:
            try:
                result = provider(text).strip()
                if result:
                    logger.info("Spot description translated with %s.", provider.__name__)
                    return result
                errors.append(f"{provider.__name__}: empty response")
            except Exception as exc:
                errors.append(f"{provider.__name__}: {exc}")
                logger.warning("Free provider %s failed: %s", provider.__name__, exc)
        raise RuntimeError("All free translators failed: " + "; ".join(errors))


def groq_models_to_try(preferred: str) -> list[str]:
    mapped = DEPRECATED_GROQ_MODELS.get(preferred, preferred)
    ordered = [mapped, *GROQ_MODEL_FALLBACKS]
    seen: set[str] = set()
    unique: list[str] = []
    for model in ordered:
        if model not in seen:
            unique.append(model)
            seen.add(model)
    return unique


def _is_missing_model_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "model_not_found" in text or "does not exist" in text or "http 404" in text


class GroqBackend:
    """Free Groq LLM. Falls back to another backend if the request fails."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GROQ_MODEL,
        fallback: TranslatorBackend | None = None,
        complete: Callable[[dict], dict] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.fallback = fallback
        self._complete = complete or self._post

    async def translate(self, text: str, preserve_terms: Sequence[str]) -> str:
        prepared = strip_ticker_lead(text)
        last_error: Exception | None = None
        for model in groq_models_to_try(self.model):
            payload = _groq_chat_payload(model, prepared, preserve_terms)
            try:
                try:
                    data = await asyncio.to_thread(self._complete, payload)
                except Exception as exc:
                    if "400" in str(exc) and any(key in payload for key in QWEN_EXTRA_KEYS):
                        for key in QWEN_EXTRA_KEYS:
                            payload.pop(key, None)
                        logger.warning(
                            "Groq rejected extra params for %s; retrying a simpler request.",
                            model,
                        )
                        data = await asyncio.to_thread(self._complete, payload)
                    else:
                        raise
                raw = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    or ""
                )
                content = _clean_llm_translation(raw)
                if not content:
                    raise RuntimeError("Groq returned reasoning instead of a translation")
                logger.info("Spot description translated with Groq (%s).", model)
                return emphasize_translated(content)
            except Exception as exc:
                last_error = exc
                retryable = (
                    _is_missing_model_error(exc)
                    or "reasoning instead" in str(exc).lower()
                    or "http 400" in str(exc).lower()
                )
                if retryable:
                    logger.warning(
                        "Groq model %s unusable (%s); trying the next model.", model, exc
                    )
                    continue
                logger.warning("Groq model %s failed: %s", model, exc)
                break

        logger.error("Groq translation failed (%s); trying fallback.", last_error)
        if self.fallback is not None:
            return await self.fallback.translate(text, preserve_terms)
        return text

    def _post(self, payload: dict) -> dict:
        return _chat_complete(GROQ_URL, self.api_key, payload)


class OpenAIBackend:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    async def translate(self, text: str, preserve_terms: Sequence[str]) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": _spot_prompt(text, preserve_terms),
        }
        try:
            data = await asyncio.to_thread(_chat_complete, OPENAI_URL, self.api_key, payload)
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not content:
                logger.error("Translator returned an empty response; using original text.")
                return text
            return content
        except Exception:
            logger.exception("Spot description translation failed; using original text.")
            return text


class Translator:
    def __init__(self, backend: TranslatorBackend) -> None:
        self.backend = backend

    @classmethod
    def from_config(cls, config) -> Translator:
        engine = str(getattr(config, "translator", "groq") or "groq").strip().lower()
        if engine in {"off", "none", "passthrough"}:
            logger.info("Spot translation is turned off.")
            return cls(PassthroughBackend())

        groq_key = getattr(config, "groq_api_key", None)
        groq_model = getattr(config, "groq_model", None) or DEFAULT_GROQ_MODEL
        openai_key = getattr(config, "openai_api_key", None)
        openai_model = getattr(config, "openai_model", "gpt-4o-mini")

        if engine == "openai":
            if openai_key:
                logger.info("Using paid OpenAI translator (%s).", openai_model)
                return cls(OpenAIBackend(api_key=openai_key, model=openai_model))
            logger.warning("TRANSLATOR=openai but OPENAI_API_KEY is empty; using Groq/free fallback.")

        if engine == "free":
            logger.info("Using free machine-translation fallback (no Groq).")
            return cls(FreeBackend())

        if groq_key:
            logger.info("Using Groq translator (%s).", groq_model)
            return cls(GroqBackend(api_key=groq_key, model=groq_model, fallback=FreeBackend()))

        logger.warning(
            "GROQ_API_KEY is not set; using free Google/MyMemory translator. "
            "Add GROQ_API_KEY to .env for AI translation."
        )
        return cls(FreeBackend())

    @classmethod
    def from_keys(cls, api_key: str | None, model: str = "gpt-4o-mini") -> Translator:
        if api_key:
            return cls(OpenAIBackend(api_key=api_key, model=model))
        return cls(FreeBackend())

    async def translate_spot_description(
        self,
        text: str,
        preserve_terms: Sequence[str] | None = None,
    ) -> str:
        if not text or not text.strip():
            return text
        return await self.backend.translate(text, preserve_terms or [])


def _chat_complete(url: str, api_key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {body}") from exc


def _http_get_json(url: str, timeout: int = 20) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _google_translate(text: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "en",
            "tl": "fa",
            "dt": "t",
            "q": text,
        }
    )
    data = _http_get_json(f"{GOOGLE_URL}?{query}")
    if not isinstance(data, list) or not data or not data[0]:
        raise RuntimeError("Unexpected Google Translate response")
    parts = [item[0] for item in data[0] if item and item[0]]
    return "".join(parts).strip()


def _mymemory_translate(text: str) -> str:
    query = urllib.parse.urlencode({"q": text, "langpair": "en|fa"})
    data = _http_get_json(f"{MYMEMORY_URL}?{query}")
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected MyMemory response")
    translated = (data.get("responseData") or {}).get("translatedText") or ""
    if not str(translated).strip():
        raise RuntimeError("MyMemory returned empty text")
    return str(translated).strip()


_default_translator: Translator | None = None


def _default() -> Translator:
    global _default_translator
    if _default_translator is None:
        try:
            from .config import load_config

            _default_translator = Translator.from_config(load_config())
        except Exception:
            _default_translator = Translator(FreeBackend())
    return _default_translator


async def translate_spot_description(text: str) -> str:
    """Public API. Uses Groq when configured, otherwise the free fallback."""
    return await _default().translate_spot_description(text)
