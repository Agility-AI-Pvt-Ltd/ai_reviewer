from app.services.graphify.extractor import extract_graph_summary


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
