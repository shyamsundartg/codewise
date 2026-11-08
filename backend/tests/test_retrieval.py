from app.retrieval.fusion import rrf
from app.retrieval.router import route
from app.retrieval.tokenize import tokenize
from app.retrieval.retriever import search_query


def test_rrf_rewards_agreement_between_rankers():
    fused = rrf([["a", "b", "c"], ["b", "a", "d"]])
    ids = [doc for doc, _ in fused]
    assert ids[:2] in (["a", "b"], ["b", "a"])
    assert ids.index("c") > 1 and ids.index("d") > 1


def test_rrf_item_in_one_list_still_ranked():
    fused = dict(rrf([["a"], ["b"]]))
    assert fused["a"] == fused["b"]


def test_tokenize_splits_identifiers():
    toks = tokenize("def getUserById(user_id): refresh_token")
    assert {"getuserbyid", "get", "user", "id", "refresh_token", "refresh", "token"} <= set(toks)
    assert "def" not in toks


def test_router():
    assert route("List all API endpoints") == "endpoints"
    assert route("What routes does the server expose?") == "endpoints"
    assert route("Which third-party libraries are used?") == "dependencies"
    assert route("Give me an overview of the project") == "overview"
    assert route("How does refresh_token work?") == "code"


def test_short_followups_use_previous_question():
    history = [{"role": "user", "content": "How are tokens refreshed?"},
               {"role": "assistant", "content": "..."}]
    assert search_query("where is it called?", history).startswith("How are tokens refreshed?")
    long_q = "Explain in detail how the order repository stores and cancels orders please"
    assert search_query(long_q, history) == long_q


def test_provider_wiring_defaults():
    from app.config import Settings
    from app.llm.provider import get_provider

    assert get_provider(Settings(llm_provider="fake")).name == "fake+hash"
    p = get_provider(Settings(llm_provider="fake", embedding_provider="hash"))
    assert p.embed(["hello world"]).shape == (1, 512)
