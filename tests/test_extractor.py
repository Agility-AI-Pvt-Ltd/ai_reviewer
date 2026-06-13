import subprocess

from app.services.graphify import extractor
from app.services.graphify.extractor import extract_graph_summary, run_graphify


def test_run_graphify_records_subprocess_trace_metadata(tmp_path, monkeypatch):
    graph_json = tmp_path / "graphify-out" / "graph.json"
    graph_json.parent.mkdir()
    graph_json.write_text(
        '{"nodes": [{"id": "main"}], "edges": [{"source": "main", "target": "db"}], "communities": []}',
        encoding="utf-8",
    )
    metadata: list[dict] = []

    def fake_run(command, capture_output, text):
        assert command == ["graphify-test", "extract", str(tmp_path), "--no-cluster"]
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(command, 0, stdout="created graph", stderr="")

    monkeypatch.setattr(extractor.settings, "graphify_command", "graphify-test")
    monkeypatch.setattr(extractor.subprocess, "run", fake_run)
    monkeypatch.setattr(extractor, "add_trace_metadata", metadata.append)

    graph = run_graphify(tmp_path)

    assert graph["nodes"] == [{"id": "main"}]
    assert metadata[0]["graphify_command"] == ["graphify-test", "extract", str(tmp_path), "--no-cluster"]
    assert metadata[0]["graphify_returncode"] == 0
    assert metadata[0]["graphify_stdout_tail"] == "created graph"
    assert metadata[1] == {"graphify_graph_json_exists": True}
    assert metadata[2] == {"graph_overview": {"nodes": 1, "edges": 1, "communities": 0, "hyperedges": 0}}


def test_extract_graph_summary_caps_and_groups_graphify_shapes():
    graph = {
        "nodes": [
            {"id": "f1", "name": "main", "type": "function", "file": "app/main.py"},
            {"id": "c1", "name": "Reviewer", "type": "class", "file": "app/reviewer.py"},
            {"id": "x", "label": "misc", "kind": "module", "path": "app/misc.py"},
        ],
        "edges": [
            {"source": "main", "target": "Reviewer", "type": "calls"},
            {"source": "main", "target": "app.reviewer", "relation": "imports"},
        ],
        "communities": [{"label": "API", "members": ["main", "Reviewer", "misc"]}],
    }

    summary = extract_graph_summary(graph)

    assert summary["functions"] == ["main"]
    assert summary["classes"] == ["Reviewer"]
    assert summary["files"] == ["app/main.py", "app/misc.py", "app/reviewer.py"]
    assert summary["call_edges"] == ["main -> Reviewer"]
    assert summary["import_edges"] == ["main -> app.reviewer"]
    assert summary["communities"] == [{"name": "API", "members": ["main", "Reviewer", "misc"]}]


def test_extract_graph_summary_supports_current_graphify_schema():
    graph = {
        "nodes": [
            {
                "id": "app_main",
                "label": "main.py",
                "file_type": "code",
                "source_file": "app/main.py",
                "community": 2,
            },
            {
                "id": "app_main_review_project",
                "label": "review_project()",
                "file_type": "code",
                "source_file": "app/main.py",
                "community": 2,
            },
            {
                "id": "reviewer",
                "label": "Reviewer",
                "file_type": "code",
                "source_file": "app/reviewer.py",
                "community": 3,
            },
            {
                "id": "reviewer_note",
                "label": "The review flow persists stage snapshots.",
                "file_type": "rationale",
                "source_file": "app/reviewer.py",
                "community": 3,
            },
        ],
        "edges": [
            {"source": "app_main_review_project", "target": "reviewer", "relation": "call"},
            {"source": "app_main", "target": "reviewer", "relation": "depends_on"},
        ],
        "graph": {
            "hyperedges": [
                {
                    "id": "review-flow",
                    "label": "Review flow",
                    "relation": "participate_in",
                    "nodes": ["app_main_review_project", "reviewer"],
                }
            ]
        },
    }

    summary = extract_graph_summary(graph)

    assert summary["functions"] == ["review_project"]
    assert summary["classes"] == ["Reviewer"]
    assert summary["files"] == ["app/main.py", "app/reviewer.py"]
    assert summary["call_edges"] == ["app_main_review_project -> reviewer"]
    assert summary["import_edges"] == [
        "app_main -> reviewer",
        "Review flow: app_main_review_project, reviewer",
    ]
    assert summary["communities"] == [
        {"name": "Cluster 2", "members": ["main.py", "review_project()"]},
        {"name": "Cluster 3", "members": ["Reviewer", "The review flow persists stage snapshots."]},
    ]
