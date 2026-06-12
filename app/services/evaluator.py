import json
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import ProjectReviewReport


PROMPT_PATH = Path("prompts/review_prompt.txt")

FALLBACK_REVIEW_PROMPT = """
You are an expert code reviewer for student vibe-coded projects at FutureX.

IDEA LAB REPORT (what the student planned to build):
<idea_lab>
{idea_lab_report}
</idea_lab>

PROJECT STRUCTURE (extracted via Graphify AST/graph data, no full code sent):
<code_structure>
Files:
{files}

Functions:
{functions}

Classes:
{classes}

Call relationships (A calls B):
{call_edges}

Module dependencies:
{import_edges}

Code clusters:
{communities}
</code_structure>

Return ONLY valid JSON. No explanation. No markdown. No backticks.

{{
  "scores": {{
    "overall": <0-10>,
    "alignment_with_idea": <0-10>,
    "architecture_quality": <0-10>,
    "feature_completeness": <0-10>,
    "code_organization": <0-10>
  }},
  "architecture": {{
    "pattern": "<MVC | Layered | Monolithic | REST API | Component-based | Event-driven | Mixed>",
    "description": "<2-3 sentences>",
    "strengths": ["..."],
    "weaknesses": ["..."]
  }},
  "alignment": {{
    "alignment_percentage": <0-100>,
    "implemented_features": ["..."],
    "missing_features": ["..."],
    "extra_features": ["..."]
  }},
  "gaps": [
    {{
      "area": "<area>",
      "description": "<what is missing or wrong>",
      "severity": "<critical | major | minor>"
    }}
  ],
  "improvements": [
    {{
      "title": "<title>",
      "description": "<actionable suggestion>",
      "priority": "<high | medium | low>"
    }}
  ],
  "summary": "<3-4 sentence overall assessment for the student>"
}}
"""


def load_review_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return FALLBACK_REVIEW_PROMPT


def _json_from_text(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    return json.loads(clean)

def _format_list(values: list[str], empty: str) -> str:
    if not values:
        return empty

    return "\n".join(f"- {v}" for v in values)
def build_review_prompt(
    idea_lab_report: IdeaLabReport,
    graph_summary: dict[str, Any],
) -> str:
    return load_review_prompt().format(
        idea_lab_report=json.dumps(
            idea_lab_report.model_dump(),
            indent=2,
            default=str,
        ),
        files=_format_list(
            graph_summary.get("files", []),
            "Unavailable",
        ),
        functions=_format_list(
            graph_summary.get("functions", []),
            "Unavailable",
        ),
        classes=_format_list(
            graph_summary.get("classes", []),
            "Unavailable",
        ),
        call_edges=_format_list(
            graph_summary.get("call_edges", []),
            "Unavailable",
        ),
        import_edges=_format_list(
            graph_summary.get("import_edges", []),
            "Unavailable",
        ),
        communities=json.dumps(
            graph_summary.get("communities", []),
            indent=2,
        ),
    )

# def build_review_prompt(idea_lab_report: IdeaLabReport, graph_summary: dict[str, Any]) -> str:
#     return load_review_prompt().format(
#         idea_lab_report=json.dumps(idea_lab_report.model_dump(), indent=2, default=str),
#         files="\n".join(graph_summary.get("files", [])),
#         functions="\n".join(graph_summary.get("functions", [])),
#         classes="\n".join(graph_summary.get("classes", [])),
#         call_edges="\n".join(graph_summary.get("call_edges", [])),
#         import_edges="\n".join(graph_summary.get("import_edges", [])),
#         communities=json.dumps(graph_summary.get("communities", []), indent=2),
#     )


async def evaluate_project(
    idea_lab_report: IdeaLabReport,
    graph_summary: dict[str, Any],
) -> ProjectReviewReport:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to evaluate project reviews")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON that matches the requested schema.",
            },
            {
                "role": "user",
                "content": build_review_prompt(idea_lab_report, graph_summary),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    text = response.choices[0].message.content or ""
    return ProjectReviewReport.model_validate(_json_from_text(text))
