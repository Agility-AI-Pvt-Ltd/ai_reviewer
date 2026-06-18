from app.schemas.report import ProjectReviewReport


def test_project_review_report_defaults_missing_architecture_lists():
    report = ProjectReviewReport.model_validate(
        {
            "scores": {
                "overall": 7,
                "alignment_with_idea": 8,
                "architecture_quality": 6,
                "feature_completeness": 7,
                "code_organization": 6,
            },
            "architecture": {
                "pattern": "Monolithic",
                "description": "The project appears to keep most behavior in a small number of modules.",
            },
            "alignment": {
                "alignment_percentage": 75,
                "implemented_features": ["The core workflow appears to be present."],
                "missing_features": ["Automated tests are not visible in the graph summary."],
                "extra_features": [],
            },
            "gaps": [
                {
                    "area": "Testing",
                    "description": "The graph summary does not show test files, which limits confidence in changes.",
                    "severity": "major",
                }
            ],
            "improvements": [
                {
                    "title": "Add Coverage",
                    "description": "Add focused tests around the primary user workflow.",
                    "priority": "high",
                }
            ],
            "summary": "The implementation is reviewable even when architecture detail is sparse.",
        }
    )

    assert report.architecture.strengths == []
    assert report.architecture.weaknesses == []
