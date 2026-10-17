import httpx
import pytest

from card_generator.clients import TextModel, UpstreamError, _error_text


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_text_model_network_error_is_an_upstream_error():
    def fail(request):
        raise httpx.ConnectError("name resolution failed", request=request)

    model = TextModel("key", "m", client=_client(fail))
    with pytest.raises(UpstreamError, match="unreachable"):
        model.json("system", "user", {}, "x")


def test_text_model_non_json_answer_is_an_upstream_error():
    model = TextModel("key", "m", client=_client(lambda r: httpx.Response(200, text="<html>busy</html>")))
    with pytest.raises(UpstreamError, match="non-JSON"):
        model.json("system", "user", {}, "x")


def test_text_model_error_given_as_a_string():
    model = TextModel("key", "m", client=_client(lambda r: httpx.Response(200, json={"error": "overloaded"})))
    with pytest.raises(UpstreamError, match="overloaded"):
        model.json("system", "user", {}, "x")


def test_error_text_accepts_any_json_shape():
    assert _error_text(httpx.Response(500, json=["a", "b"])) == '["a", "b"]'
    assert _error_text(httpx.Response(500, json={"detail": {"message": "no"}})) == "no"
