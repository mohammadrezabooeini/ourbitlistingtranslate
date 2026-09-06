import pytest

from ourbit_selfbot.translator import (
    FreeBackend,
    GroqBackend,
    Translator,
    emphasize_translated,
    protect_terms,
    restore_terms,
    strip_ticker_lead,
)


def test_strip_ticker_lead():
    assert strip_ticker_lead("FLORK -- The versatile OG meme.") == "The versatile OG meme."
    assert strip_ticker_lead("$ORBIO: Earn credits.") == "Earn credits."
    assert strip_ticker_lead("Earn OpenRouter credits by holding $ORBIO.") == (
        "Earn OpenRouter credits by holding $ORBIO."
    )


def test_protect_and_restore_keeps_cashtag_and_brand():
    text = "Earn OpenRouter credits by holding $ORBIO."
    protected, mapping = protect_terms(text, ["$ORBIO", "ORBIO", "OpenRouter", "USDT"])
    assert "$ORBIO" not in protected
    assert "OpenRouter" not in protected
    assert "XKEEP" in protected
    restored = restore_terms(protected, mapping)
    assert restored == text


def test_emphasize_bolds_cashtag_and_persian_digits():
    assert emphasize_translated("hold $ORBIO for 10 years") == "hold **$ORBIO** for ۱۰ years"


@pytest.mark.asyncio
async def test_free_backend_uses_injected_provider_and_preserves_terms():
    def fake_provider(text: str) -> str:
        assert "XKEEP" in text
        assert "$ORBIO" not in text
        return text.replace("Earn", "دریافت کنید")

    translator = Translator(FreeBackend(providers=[fake_provider]))
    result = await translator.translate_spot_description(
        "Earn OpenRouter credits by holding $ORBIO.",
        preserve_terms=["$ORBIO", "OpenRouter"],
    )
    assert "$ORBIO" in result
    assert "OpenRouter" in result
    assert "**$ORBIO**" in result
    assert "دریافت کنید" in result


@pytest.mark.asyncio
async def test_free_backend_falls_back_when_first_provider_fails():
    def boom(_text: str) -> str:
        raise RuntimeError("blocked")

    def ok(text: str) -> str:
        return "یک میم قدیمی با ۱۰ سال سابقه"

    translator = Translator(FreeBackend(providers=[boom, ok]))
    result = await translator.translate_spot_description(
        "FLORK -- The versatile OG meme with over 10 years of history."
    )
    assert "میم" in result
    assert "FLORK --" not in result


@pytest.mark.asyncio
async def test_free_backend_returns_original_when_all_providers_fail():
    def boom(_text: str) -> str:
        raise RuntimeError("down")

    original = "The versatile OG meme."
    translator = Translator(FreeBackend(providers=[boom]))
    result = await translator.translate_spot_description(original)
    assert result == original


def test_from_config_uses_groq_when_key_is_set():
    class FakeConfig:
        translator = "groq"
        groq_api_key = "gsk_test"
        groq_model = "qwen/qwen3.6-27b"
        openai_api_key = None
        openai_model = "gpt-4o-mini"

    translator = Translator.from_config(FakeConfig())
    assert isinstance(translator.backend, GroqBackend)
    assert isinstance(translator.backend.fallback, FreeBackend)


def test_from_config_falls_back_to_free_without_groq_key():
    class FakeConfig:
        translator = "groq"
        groq_api_key = None
        groq_model = "qwen/qwen3.6-27b"
        openai_api_key = None
        openai_model = "gpt-4o-mini"

    translator = Translator.from_config(FakeConfig())
    assert isinstance(translator.backend, FreeBackend)


@pytest.mark.asyncio
async def test_groq_backend_translates_with_injected_complete():
    def fake_complete(_payload: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": "با نگهداری **$ORBIO** می‌توانید اعتبار OpenRouter دریافت کنید."
                    }
                }
            ]
        }

    translator = Translator(GroqBackend("gsk_test", complete=fake_complete))
    result = await translator.translate_spot_description(
        "Earn OpenRouter credits by holding $ORBIO.",
        preserve_terms=["$ORBIO", "OpenRouter", "Ourbit", "USDT"],
    )
    assert "$ORBIO" in result
    assert "OpenRouter" in result
    assert "**$ORBIO**" in result


def test_spot_prompt_sends_only_description_and_visible_terms():
    from ourbit_selfbot.translator import _spot_prompt

    prompt = _spot_prompt(
        "The theater was a front. It was A Meme Coin all along. MEME Paired with AMC.",
        ["MEME", "AMC", "Ourbit", "USDT", "OpenRouter"],
    )
    user = prompt[1]["content"]
    assert "The theater was a front." in user
    assert "MEME" in user
    assert "AMC" in user
    assert "Ourbit" not in user
    assert "OpenRouter" not in user
    assert "USDT" not in user
    assert "New Listing" not in user


def test_groq_qwen_payload_disables_thinking():
    from ourbit_selfbot.translator import _groq_chat_payload

    payload = _groq_chat_payload(
        "qwen/qwen3.6-27b",
        "The theater was a front.",
        ["MEME"],
    )
    assert payload["reasoning_effort"] == "none"
    assert payload["reasoning_format"] == "hidden"
    assert payload["temperature"] == 0.7
    assert payload["presence_penalty"] == 1.5
    assert payload["messages"][-1]["content"].endswith("/no_think")


def test_clean_llm_translation_keeps_only_final_persian():
    from ourbit_selfbot.translator import _clean_llm_translation

    cleaned = _clean_llm_translation(
        "این تئاتر فقط یک پوشش بود؛ در واقع از ابتدا یک میم‌کوین بود. MEME با AMC جفت شده است."
    )
    assert cleaned == (
        "این تئاتر فقط یک پوشش بود؛ در واقع از ابتدا یک میم‌کوین بود. MEME با AMC جفت شده است."
    )
    assert "Literal" not in cleaned
    assert "Task" not in cleaned


def test_clean_llm_translation_drops_qwen_reasoning_dump():
    from ourbit_selfbot.translator import _clean_llm_translation

    raw = (
        "Analyze User Input:\n"
        "Thinking Process:\n"
        "Source Text: The theater was a front.\n"
        "Task: translate\n"
        "Constraints: keep tickers\n"
        "- Literal: این تئاتر یک پوشش بود. MEME با AMC جفت شده است.\n"
        "- Crypto Channel Vibe: این تئاتر فقط یک پوشش بود؛ در واقع از ابتدا یک میم‌کوین بود. MEME با AMC جفت شده است.\n"
    )
    cleaned = _clean_llm_translation(raw)
    assert cleaned == (
        "این تئاتر فقط یک پوشش بود؛ در واقع از ابتدا یک میم‌کوین بود. MEME با AMC جفت شده است."
    )
    assert "Literal" not in cleaned
    assert "Crypto Channel Vibe" not in cleaned
    assert "Analyze" not in cleaned
    assert "Task:" not in cleaned


def test_clean_llm_translation_drops_leftover_english_and_glossary():
    from ourbit_selfbot.translator import _clean_llm_translation

    leftover = (
        "اولین لانچ‌پاد چنداستخری روی روبین‌هود هست\n"
        '   - "that enables users to deploy tokens paired to a'
    )
    cleaned = _clean_llm_translation(leftover)
    assert "لانچ‌پاد" in cleaned
    assert "that enables users" not in cleaned

    vibe = (
        "- Literal: STONKS یک میم‌کوین است که روی شبکه BSC زده شده. "
        "- Crypto Channel Vibe: $STONKS یه میم‌کوینه که روی شبکه BSC لیست شده"
    )
    cleaned_vibe = _clean_llm_translation(vibe)
    assert "$STONKS" in cleaned_vibe
    assert "میم‌کوین" in cleaned_vibe
    assert "Literal" not in cleaned_vibe
    assert "Crypto Channel Vibe" not in cleaned_vibe
    assert "زده شده" not in cleaned_vibe

    glossary = '- "lending protocol" -> پروتکل وام‌دهی / پلتفرم وام‌دهی'
    assert _clean_llm_translation(glossary) == ""


@pytest.mark.asyncio
async def test_groq_retries_when_qwen_returns_reasoning():
    calls: list[str] = []

    def complete(payload: dict) -> dict:
        calls.append(payload["model"])
        if payload["model"].startswith("qwen"):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Analyze User Input:\nThinking Process:\n"
                                "Source Text: foo\nTask: translate\nConstraints: none"
                            )
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": "این تئاتر فقط یک پوشش بود. MEME با AMC جفت شده است."
                    }
                }
            ]
        }

    translator = Translator(GroqBackend("gsk_test", complete=complete))
    result = await translator.translate_spot_description(
        "The theater was a front. It was A Meme Coin all along. MEME Paired with AMC."
    )
    assert "این تئاتر" in result
    assert "Analyze" not in result
    assert "Thinking" not in result
    assert calls[0] == "qwen/qwen3.6-27b"
    assert "openai/gpt-oss-120b" in calls


@pytest.mark.asyncio
async def test_groq_retries_next_model_after_404():
    calls: list[str] = []

    def complete(payload: dict) -> dict:
        calls.append(payload["model"])
        if payload["model"] != "openai/gpt-oss-20b":
            raise RuntimeError(
                'LLM HTTP 404: {"error":{"message":"The model does not exist","code":"model_not_found"}}'
            )
        return {"choices": [{"message": {"content": "یک میم قدیمی"}}]}

    translator = Translator(
        GroqBackend("gsk_test", model="llama-3.3-70b-versatile", complete=complete)
    )
    result = await translator.translate_spot_description("The versatile OG meme.")
    assert "میم" in result
    assert calls[0] == "qwen/qwen3.6-27b"
    assert "openai/gpt-oss-120b" in calls
    assert "openai/gpt-oss-20b" in calls


@pytest.mark.asyncio
async def test_groq_backend_uses_fallback_when_groq_fails():
    def boom(_payload: dict) -> dict:
        raise RuntimeError("groq down")

    fallback = FreeBackend(providers=[lambda _text: "ترجمه پشتیبان"])
    translator = Translator(GroqBackend("gsk_test", complete=boom, fallback=fallback))
    result = await translator.translate_spot_description("The versatile OG meme.")
    assert result == "ترجمه پشتیبان"
