"""``infer_modality`` — the guess Coffer makes when nobody has said yet.

Only two callers may guess: the one-shot migration that converted the old
bare-id sets, and endpoint introspection, which pre-fills a kind the user then
corrects from the connection's model table. Everywhere else the STORED modality
is the truth, so these pin the guess itself, not any behaviour downstream of it.

The bar the rule is written to: a wrong guess on a chat model is the expensive
one — it drops the model out of every chat picker — so an ambiguous name must
fall back to ``text`` rather than reach for a cleverer answer.
"""

from __future__ import annotations

import pytest

from coffer.domain.provider.modality import Modality, infer_modality


@pytest.mark.parametrize(
    "model_id",
    [
        "text-embedding-3-large",
        "text-embedding-ada-002",
        "embed-english-v3.0",
        "multilingual-e5-embed",
    ],
)
def test_embedding_ids(model_id: str) -> None:
    assert infer_modality(model_id) is Modality.EMBEDDING


@pytest.mark.parametrize(
    "model_id",
    ["dall-e-3", "imagen-3.0-generate-002", "flux-pro", "sdxl", "sd3-large", "gpt-image-1"],
)
def test_image_ids(model_id: str) -> None:
    assert infer_modality(model_id) is Modality.IMAGE


@pytest.mark.parametrize("model_id", ["veo-3", "veo3", "sora-2", "video-01"])
def test_video_ids(model_id: str) -> None:
    assert infer_modality(model_id) is Modality.VIDEO


@pytest.mark.parametrize(
    "model_id", ["tts-1", "tts-1-hd", "whisper-1", "gpt-4o-audio-preview", "gpt-4o-mini-tts"]
)
def test_audio_ids(model_id: str) -> None:
    assert infer_modality(model_id) is Modality.AUDIO


@pytest.mark.parametrize(
    "model_id",
    [
        "gpt-5",
        "claude-opus-4-6",
        "qwen3:8b",  # ollama's tag syntax, not a word boundary the rule may trip on
        "gemini-2.5-flash",
        "o3",
        "deepseek-r1",
        "mistral-large-latest",
    ],
)
def test_ordinary_chat_ids_stay_text(model_id: str) -> None:
    assert infer_modality(model_id) is Modality.TEXT


@pytest.mark.parametrize("model_id", ["voyage-3", "bge-m3", "nomic-1.5"])
def test_an_embedding_model_that_does_not_say_so_guesses_text(model_id: str) -> None:
    # Embedding houses that spell it nowhere in the id are NOT special-cased:
    # the guess reaches only for evidence in the name, and ``text`` is the
    # fallback the user corrects from the connection's model table. Widening the
    # table here would also have to be matched in migration 0063, which is
    # frozen — so a missing house is a correction to make, never a bug to fix.
    assert infer_modality(model_id) is Modality.TEXT


@pytest.mark.parametrize("model_id", ["sd-turbo", "sd", "sd3", "sdxl-lightning"])
def test_a_bare_sd_token_is_stable_diffusion(model_id: str) -> None:
    assert infer_modality(model_id) is Modality.IMAGE


@pytest.mark.parametrize(
    "model_id",
    [
        "gpt-4o-sdk",  # "sd" only as a prefix of a longer token
        "sdo-chat-1",
        "wisdom-7b",  # … and in the middle of a word
        "ttsx-1",  # "tts" with a letter glued on is not the speech stem
        "veolia-1",
    ],
)
def test_a_short_stem_inside_a_longer_word_does_not_match(model_id: str) -> None:
    # The short stems are matched as whole tokens precisely so an unrelated chat
    # model is not quietly dropped from every picker that asks for text.
    assert infer_modality(model_id) is Modality.TEXT


def test_the_guess_is_case_and_whitespace_insensitive() -> None:
    # Ids arrive from endpoint listings and from a user's typing alike.
    assert infer_modality("  Text-Embedding-3-Large  ") is Modality.EMBEDDING
    assert infer_modality("DALL-E-3") is Modality.IMAGE


def test_an_empty_id_falls_back_to_text() -> None:
    # Nothing to read; ``text`` is the answer that keeps a chat picker working.
    assert infer_modality("") is Modality.TEXT


def test_an_earlier_rule_wins_over_a_later_one() -> None:
    # Names collide (an "embedding" that also says "image"); the table's order
    # is the tiebreak, and it is fixed so the same id always guesses the same.
    assert infer_modality("image-embed-1") is Modality.EMBEDDING
