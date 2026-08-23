"""Local unit tests for the scriptwriter's pure helpers.

Run with:  python3 modal_apps/test_scriptwriter_local.py
No modal / vllm / GPU required.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modal_apps.script_common import (
    build_messages,
    load_mock,
    parse_script_json,
    validate_script_response,
)

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def test_mock_validates():
    mock = load_mock()
    errors = validate_script_response(mock)
    assert errors == [], f"bundled mock failed contract validation: {errors}"
    # The bundled mock must stay byte-identical in content to the frozen fixture.
    fixture_path = os.path.join(FIXTURES, "script_response.json")
    if os.path.exists(fixture_path):
        with open(fixture_path) as fh:
            assert json.load(fh) == mock, "mock_script_response.json drifted from fixtures/script_response.json"


def test_validator_rejects_bad_input():
    good = load_mock()

    bad_verdict = copy.deepcopy(good)
    bad_verdict["verdict"] = "AMAZING"
    errors = validate_script_response(bad_verdict)
    assert any("verdict" in e for e in errors), f"bad verdict not rejected: {errors}"

    missing_citation = copy.deepcopy(good)
    del missing_citation["segments"][0]["citation"]
    errors = validate_script_response(missing_citation)
    assert any("citation" in e for e in errors), f"missing citation key not rejected: {errors}"


def test_prompt_includes_memory_digest():
    with open(os.path.join(FIXTURES, "greptile_response.json")) as fh:
        greptile = json.load(fh)
    body = {
        "repo_meta": {"repository": greptile["repository"], "stars": 4000},
        "greptile_findings": greptile["battery"],
        "memory_digest": "Episode 12 covered author cavemanlabs: verdict HYPE on 'stonetools'.",
    }
    messages = build_messages(body, host_prompt="PERSONA")
    user = messages[1]["content"]
    assert "Episode 12 covered author cavemanlabs" in user, "memory_digest missing from prompt"
    assert "previously on" in user, "prompt does not instruct the callback"
    assert messages[0]["content"] == "PERSONA"

    # Empty digest -> explicitly no callback instruction with digest content.
    body["memory_digest"] = ""
    user_empty = build_messages(body, host_prompt="PERSONA")[1]["content"]
    assert "Episode 12" not in user_empty
    assert "do NOT include a 'previously on'" in user_empty

    # Findings from the raw Greptile fixture shape are normalized into the prompt.
    assert "core/scheduler.py lines 51-88" in user
    # Answer mode sets title/verdict instructions.
    answer_body = {
        "mode": "answer",
        "question": "Is the memory real?",
        "repo_meta": body["repo_meta"],
        "greptile_findings": greptile["battery"],
        "verdict": "MIXED",
    }
    answer_user = build_messages(answer_body, "PERSONA")[1]["content"]
    assert "Is the memory real?" in answer_user
    assert "15-25 second" in answer_user


def test_parse_script_json_tolerates_fences():
    good = load_mock()
    fenced = "```json\n" + json.dumps(good) + "\n```"
    assert parse_script_json(fenced) == good
    try:
        parse_script_json("not json at all")
    except ValueError:
        pass
    else:
        raise AssertionError("parse_script_json accepted garbage")


if __name__ == "__main__":
    tests = [
        test_mock_validates,
        test_validator_rejects_bad_input,
        test_prompt_includes_memory_digest,
        test_parse_script_json_tolerates_fences,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
