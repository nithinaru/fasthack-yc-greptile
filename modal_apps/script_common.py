"""Pure helpers for the Repo Radio script writer.

No modal / vllm / GPU dependencies here — importable anywhere (used by the
local unit test and by script.py inside the Modal container).
"""
from __future__ import annotations

import json
import os
from typing import Any

VALID_VERDICTS = ("HYPE", "REAL", "MIXED")

# JSON schema for the frozen /script response contract. Also fed to vLLM
# guided decoding so the model cannot emit anything else.
SCRIPT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "verdict": {"type": "string", "enum": list(VALID_VERDICTS)},
        "segments": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citation": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "object",
                                "properties": {
                                    "file": {"type": "string"},
                                    "start_line": {"type": "integer"},
                                    "end_line": {"type": "integer"},
                                },
                                "required": ["file", "start_line", "end_line"],
                                "additionalProperties": False,
                            },
                        ]
                    },
                },
                "required": ["text", "citation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "verdict", "segments"],
    "additionalProperties": False,
}


def validate_script_response(obj: Any) -> list[str]:
    """Validate against the frozen contract. Returns a list of error strings
    (empty list == valid)."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["response is not a JSON object"]
    if not isinstance(obj.get("title"), str) or not obj.get("title"):
        errors.append("title must be a non-empty string")
    if obj.get("verdict") not in VALID_VERDICTS:
        errors.append(f"verdict must be one of {VALID_VERDICTS}")
    segments = obj.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("segments must be a non-empty list")
        return errors
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            errors.append(f"segments[{i}] is not an object")
            continue
        if not isinstance(seg.get("text"), str) or not seg.get("text"):
            errors.append(f"segments[{i}].text must be a non-empty string")
        if "citation" not in seg:
            errors.append(f"segments[{i}] is missing the citation key")
            continue
        cit = seg["citation"]
        if cit is None:
            continue
        if not isinstance(cit, dict):
            errors.append(f"segments[{i}].citation must be an object or null")
            continue
        if not isinstance(cit.get("file"), str) or not cit.get("file"):
            errors.append(f"segments[{i}].citation.file must be a non-empty string")
        for key in ("start_line", "end_line"):
            if not isinstance(cit.get(key), int) or isinstance(cit.get(key), bool):
                errors.append(f"segments[{i}].citation.{key} must be an integer")
    return errors


def _normalize_finding(f: dict) -> dict:
    """Accept both the PRD body shape (question/answer/file/start_line/end_line)
    and the raw Greptile fixture shape (query/message/filepath/linestart/lineend)."""
    sources = []
    for s in f.get("sources", []) or []:
        sources.append(
            {
                "file": s.get("file") or s.get("filepath") or "",
                "start_line": s.get("start_line", s.get("linestart", 0)),
                "end_line": s.get("end_line", s.get("lineend", 0)),
                "summary": s.get("summary", ""),
            }
        )
    return {
        "question": f.get("question") or f.get("query") or "",
        "answer": f.get("answer") or f.get("message") or "",
        "sources": sources,
    }


def _findings_block(findings: list[dict]) -> str:
    lines = []
    for i, raw in enumerate(findings or [], 1):
        f = _normalize_finding(raw)
        lines.append(f"FINDING {i}")
        lines.append(f"Q: {f['question']}")
        lines.append(f"A: {f['answer']}")
        for s in f["sources"]:
            summary = f" — {s['summary']}" if s["summary"] else ""
            lines.append(
                f"  source: {s['file']} lines {s['start_line']}-{s['end_line']}{summary}"
            )
        lines.append("")
    return "\n".join(lines).strip()


def build_messages(body: dict, host_prompt: str) -> list[dict]:
    """Build chat messages for either episode mode (default) or answer mode
    (body["mode"] == "answer")."""
    repo_meta = body.get("repo_meta") or {}
    findings = body.get("greptile_findings") or []
    memory_digest = (body.get("memory_digest") or "").strip()

    parts = [
        "REPO METADATA:",
        json.dumps(repo_meta, indent=2),
        "",
        "GREPTILE FINDINGS (your only source of facts):",
        _findings_block(findings),
        "",
    ]

    if body.get("mode") == "answer":
        question = body.get("question") or ""
        verdict = body.get("verdict") if body.get("verdict") in VALID_VERDICTS else "MIXED"
        parts += [
            f"MODE: answer. A listener asked on air: \"{question}\"",
            "Write a 15-25 second spoken answer (1-3 segments, ~40-70 words total).",
            f'Set "title" to the listener\'s question verbatim and "verdict" to "{verdict}".',
            "Cite the specific files you discuss using the findings' sources.",
        ]
    else:
        parts += [
            "MODE: episode. Write tonight's full episode script per your structure rules:",
            "6-10 segments, 450-700 words total, hook open, verdict close.",
        ]
        if memory_digest:
            parts += [
                "",
                "HOST MEMORY DIGEST — MANDATORY: your SECOND segment must open with the",
                "exact words 'Previously on Repo Radio' and reference this digest:",
                memory_digest,
            ]
        else:
            parts += ["", "No host memory for this repo — do NOT include a 'previously on' callback."]

    parts += [
        "",
        "Respond with STRICT JSON only, matching exactly:",
        '{"title": str, "verdict": "HYPE"|"REAL"|"MIXED", "segments": [{"text": str, "citation": {"file": str, "start_line": int, "end_line": int} | null}]}',
    ]

    return [
        {"role": "system", "content": host_prompt},
        {"role": "user", "content": "\n".join(parts)},
    ]


def load_mock(path: str | None = None) -> dict:
    """Load the bundled canonical mock response (verbatim copy of
    fixtures/script_response.json)."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_script_response.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_script_json(text: str) -> dict:
    """Parse model output into the contract dict, tolerating stray prose or
    code fences around the JSON object. Raises ValueError on failure."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in model output")
        obj = json.loads(text[start : end + 1])
    errors = validate_script_response(obj)
    if errors:
        raise ValueError("; ".join(errors))
    return obj
