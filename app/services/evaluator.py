import json
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.observability import add_trace_metadata, traceable, wrap_openai_client
from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import ProjectReviewReport


PROMPT_PATH = Path("prompts/review_prompt.txt")

FALLBACK_REVIEW_PROMPT = """
You are an expert code reviewer for student vibe-coded projects at FutureX.

Your job is to compare what the student planned to build in Idea Lab with what their GitHub project appears to implement from the Graphify knowledge graph.

Review principles:
- Be concrete and useful for a student builder.
- Judge alignment with the Idea Lab report, not only code quality.
- Do not invent features that are not supported by the graph summary.
- If call relationships are unavailable, explicitly state that implementation confidence is limited. Do not automatically give a low Idea Alignment score when files, functions, classes, routes, domain terms, or modules visibly match the Idea Lab plan.
- If the graph summary is sparse, say so in the JSON fields and lower feature completeness or confidence where appropriate, but do not punish alignment when the available evidence strongly matches the planned idea.
- Reward working structure, clear separation of concerns, and implemented core workflows.
- Penalize missing core features, unclear architecture, dead-end code, and projects that do not match the planned idea.
- If the GitHub project appears unrelated to the Idea Lab plan, it is valid to assign 0 for scores.alignment_with_idea and 0 for alignment.alignment_percentage. Do not give partial alignment credit just because the code is functional.

Idea Alignment scoring rubric:
- 90-100 alignment_percentage and 9-10 scores.alignment_with_idea: the repo's apparent domain, user workflows, models, routes/components, or feature names strongly match the Idea Lab plan, even if tests, polish, or some implementation details are missing.
- 70-89 alignment_percentage and 7-8.9 scores.alignment_with_idea: the main idea is clearly represented, but one or two planned workflows are incomplete, shallow, or uncertain from the graph.
- 40-69 alignment_percentage and 4-6.9 scores.alignment_with_idea: the repo is in a related domain but misses important promised workflows or only implements supporting pieces.
- 1-39 alignment_percentage and 0.1-3.9 scores.alignment_with_idea: there are only weak or accidental overlaps with the Idea Lab plan.
- 0 alignment_percentage and 0 scores.alignment_with_idea: the repo appears unrelated to the Idea Lab plan.
- Do not use architecture quality, code organization, test coverage, or sparse call edges as the main reason for a low Idea Alignment score. Put those concerns in architecture_quality, feature_completeness, code_organization, gaps, and improvements instead.

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

Response depth:
- Give enough detail for the student to understand what was observed, why it matters, and what to do next.
- Prefer 3-5 specific items in strengths, weaknesses, implemented_features, missing_features, gaps, and improvements when the graph summary supports them.
- Write each feature, gap, and improvement as a complete, specific sentence, not a short label.
- For every gap and improvement, mention the likely impact on the product or user experience.
- If evidence is limited, still explain what can be concluded and what remains uncertain.
- Keep the response JSON valid, but do not make the text terse.

Severity and priority calibration:
- For gaps, use "critical" only when a core promised workflow appears missing or blocked.
- Use "major" when the project can work but an important feature, architecture boundary, or safety requirement is incomplete.
- Use "minor" only for polish, clarity, small organization issues, or low-risk missing details.
- For improvements, use "high" for the next change that most improves product usefulness or alignment.
- Use "medium" for important follow-up work after the highest-impact fixes.
- Use "low" for polish or optional enhancements.
- Keep gap "area" and improvement "title" short and title-like, without repeating severity or priority words.

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
    "description": "<3-5 sentences explaining the apparent architecture, the main modules involved, and confidence level>",
    "strengths": ["<specific strength with evidence from files/functions/classes>", "..."],
    "weaknesses": ["<specific weakness, why it matters, and what evidence suggests it>", "..."]
  }},
  "alignment": {{
    "alignment_percentage": <0-100>,
    "implemented_features": ["<complete sentence naming the feature and the graph evidence that supports it>", "..."],
    "missing_features": ["<complete sentence naming the planned feature that appears absent or incomplete and why>", "..."],
    "extra_features": ["<complete sentence naming extra implementation found beyond the Idea Lab plan, or [] if none>", "..."]
  }},
  "gaps": [
    {{
      "area": "<short title-case area, without severity text>",
      "description": "<2-3 sentences explaining what is missing or wrong, the evidence, and the likely impact>",
      "severity": "<critical | major | minor>"
    }}
  ],
  "improvements": [
    {{
      "title": "<short title-case action, without priority text>",
      "description": "<2-3 sentences with an actionable next step, expected benefit, and where in the project it likely applies>",
      "priority": "<high | medium | low>"
    }}
  ],
  "summary": "<8-10 sentence overall assessment for the student, including what works, what is missing, confidence limits, and the best next step>"
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


def _graph_summary_counts(graph_summary: dict[str, Any]) -> dict[str, int]:
    return {
        "files": len(graph_summary.get("files", [])),
        "functions": len(graph_summary.get("functions", [])),
        "classes": len(graph_summary.get("classes", [])),
        "call_edges": len(graph_summary.get("call_edges", [])),
        "import_edges": len(graph_summary.get("import_edges", [])),
        "communities": len(graph_summary.get("communities", [])),
    }


def _trace_prompt_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    idea_lab_report = inputs.get("idea_lab_report")
    graph_summary = inputs.get("graph_summary", {})
    return {
        "conversation_id": getattr(idea_lab_report, "conversation_id", None),
        "graph_summary_counts": _graph_summary_counts(graph_summary) if isinstance(graph_summary, dict) else {},
    }


def _trace_prompt_output(output: str) -> dict[str, Any]:
    return {"prompt_chars": len(output)}


def _trace_evaluation_output(output: ProjectReviewReport) -> dict[str, Any]:
    return {
        "overall_score": output.scores.overall,
        "alignment_percentage": output.alignment.alignment_percentage,
        "gap_count": len(output.gaps),
        "improvement_count": len(output.improvements),
        "summary": output.summary,
    }


@traceable(
    name="review.build_prompt",
    run_type="prompt",
    tags=["review", "prompt"],
    process_inputs=_trace_prompt_inputs,
    process_outputs=_trace_prompt_output,
)
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


@traceable(
    name="review.evaluate_project",
    run_type="chain",
    tags=["review", "openai"],
    process_inputs=_trace_prompt_inputs,
    process_outputs=_trace_evaluation_output,
)
async def evaluate_project(
    idea_lab_report: IdeaLabReport,
    graph_summary: dict[str, Any],
) -> ProjectReviewReport:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to evaluate project reviews")

    client = wrap_openai_client(AsyncOpenAI(api_key=settings.openai_api_key))
    prompt = build_review_prompt(idea_lab_report, graph_summary)
    add_trace_metadata(
        {
            "conversation_id": idea_lab_report.conversation_id,
            "openai_model": settings.openai_model,
            "prompt_chars": len(prompt),
            "graph_summary_counts": _graph_summary_counts(graph_summary),
        }
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON that matches the requested schema.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    text = response.choices[0].message.content or ""
    report = ProjectReviewReport.model_validate(_json_from_text(text))
    add_trace_metadata(
        {
            "openai_response_chars": len(text),
            "overall_score": report.scores.overall,
            "alignment_percentage": report.alignment.alignment_percentage,
        }
    )
    return report
