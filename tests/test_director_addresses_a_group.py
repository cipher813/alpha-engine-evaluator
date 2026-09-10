"""The Director's plan call must put a MODEL GROUP on the wire.

alpha-engine-config-I10399. A fallback chain is declared ON A GROUP, so a
request naming a concrete deployment gets no chain — LiteLLM answers
`Available Model Group Fallbacks=[]` and the primary's error is final.

Measured live 2026-09-09 through the running router, back to back:

    model="ultra"                -> OK, served deepseek-v4-pro (fell back)
    model="ultra-glm-5.2-direct" -> 429  Available Model Group Fallbacks=[]

Zhipu, the provider behind `ultra`'s primary, returns `Insufficient balance`
on every call. So `alpha-engine-config-I8165`'s whole deliverable — a second
arm so an unavailable Zhipu is not a full outage — was defeated at the wire,
and the next weekly Director run would have failed outright.

The property was asserted in a COMMENT in `director/agent.py`, in the repo
that does not own the resolver, and nothing tested it. This is the consumer
half: it lives with the consumer that depends on the property, and it
exercises the REAL `krepis.router` against a real registry file rather than a
fake, because a fake resolver would have agreed with the comment.
"""
from __future__ import annotations

import pytest
import yaml

from director import agent

#: An `ultra`-shaped registry: a Zhipu primary that declares streaming and
#: tool_choice, and a DeepSeek second arm that declares streaming only.
_REGISTRY = {
    "schema_version": 1,
    "model_groups": {"ultra": ["glm-5.2-direct", "deepseek-v4-pro"]},
    "models": [
        {
            "id": "glm-5.2-direct", "name": "GLM 5.2", "provider": "zhipu",
            "route": "egress_proxy", "api_base": "http://127.0.0.1:8981/v1",
            "upstream_host": "api.z.ai", "model": "glm-5.2", "status": "active",
            "reachable_from": ["laptop", "ec2"],
            "endpoints": {"openai": "http://127.0.0.1:8981/v1"},
            "params": {"max_tokens": 8192},
            "capabilities": {"streaming": True, "tool_choice": True, "batches": False},
        },
        {
            "id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "deepseek",
            "route": "egress_proxy", "api_base": "http://127.0.0.1:8972/v1",
            "upstream_host": "api.deepseek.com", "model": "deepseek-v4-pro",
            "status": "active", "reachable_from": ["laptop", "ec2"],
            "endpoints": {"openai": "http://127.0.0.1:8972/v1"},
            "params": {"max_tokens": 8192},
            "capabilities": {"streaming": True, "tool_choice": False, "batches": False},
        },
    ],
}


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    router = pytest.importorskip("krepis.router")
    if not hasattr(router, "group_wire_model"):
        import krepis

        pytest.skip(
            f"installed krepis {krepis.__version__} predates the I10399 "
            "resolver (krepis.router.group_wire_model); this check arms "
            "itself the moment requirements.txt pins a krepis that has it"
        )
    reg = tmp_path / "LLM_MODEL_REGISTRY.yaml"
    reg.write_text(yaml.safe_dump(_REGISTRY, sort_keys=False))
    monkeypatch.setenv("LLM_MODEL_REGISTRY_PATH", str(reg))
    monkeypatch.setattr(
        router, "_litellm_edge_admission",
        lambda: (True, "https://router.example.invalid:8443", []),
    )
    return router


def _resolve(router):
    """Exactly the resolution `director/agent.py::_default_llm` performs —
    same group, same execution context, same wire, same declared `requires`.
    Reading the constants off the module is what keeps the two in step."""
    return router.resolve_group_spec(
        agent.DIRECTOR_GROUP,
        exec_context="ec2",
        wire="openai",
        requires=("streaming",),
    )


def test_the_plan_call_addresses_a_group_not_a_deployment(resolver):
    spec, route = _resolve(resolver)
    primary = route["primary_registry_id"]
    assert spec.model != f"{agent.DIRECTOR_GROUP}-{primary}", (
        "the Director is addressing the primary DEPLOYMENT name, which LiteLLM "
        "applies no fallback chain to (alpha-engine-config-I10399)"
    )
    assert spec.model == resolver.group_wire_model(
        agent.DIRECTOR_GROUP, ("streaming",)
    )
    assert route["wire_addressing"] == "capability_group"


def test_the_resolution_still_names_the_primary_it_expects(resolver):
    """Group addressing does not give up knowing which entry should serve —
    that is what `_stamp_route_degradation` compares `result.model` against."""
    _spec, route = _resolve(resolver)
    assert route["primary_registry_id"] == "glm-5.2-direct"
    assert route["primary_model"] == "glm-5.2"


def test_the_spec_carries_the_primary_so_a_healthy_call_is_priceable(resolver):
    """LiteLLM restamps the requested model onto every response that did NOT
    fall back, so a healthy group-addressed call reports the GROUP as its
    served model. `group_primary_model` is what makes that billable — without
    it the group name reaches the price-card lookup, which is the failure
    I6543 exists to prevent."""
    spec, _route = _resolve(resolver)
    assert spec.group_primary_model == "glm-5.2"
