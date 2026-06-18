import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import add_trace_metadata, traceable
from app.utils.file_handler import clone_or_update_repository


def _tail(value: str, limit: int = 2_000) -> str:
    return value[-limit:] if len(value) > limit else value


def _graph_overview(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    communities = graph.get("communities", [])
    hyperedges = graph.get("graph", {}).get("hyperedges", [])
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "communities": len(communities),
        "hyperedges": len(hyperedges),
    }


def _summary_overview(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "functions": len(summary.get("functions", [])),
        "classes": len(summary.get("classes", [])),
        "files": len(summary.get("files", [])),
        "call_edges": len(summary.get("call_edges", [])),
        "import_edges": len(summary.get("import_edges", [])),
        "communities": len(summary.get("communities", [])),
        "sample_functions": summary.get("functions", [])[:10],
        "sample_classes": summary.get("classes", [])[:10],
        "sample_files": summary.get("files", [])[:10],
    }


def _trace_graph_input(inputs: dict[str, Any]) -> dict[str, Any]:
    graph = inputs.get("graph")
    if isinstance(graph, dict):
        return {"graph": _graph_overview(graph)}
    return inputs


def _trace_graph_output(output: dict[str, Any]) -> dict[str, Any]:
    return _graph_overview(output) if isinstance(output, dict) else {"output": str(type(output))}


def _trace_summary_output(output: dict[str, Any]) -> dict[str, Any]:
    return _summary_overview(output) if isinstance(output, dict) else {"output": str(type(output))}


def _trace_github_output(output: tuple[Path, dict[str, Any]]) -> dict[str, Any]:
    project_path, graph = output
    return {"project_path": str(project_path), "graph": _graph_overview(graph)}


@traceable(
    name="graphify.run_extract",
    run_type="tool",
    tags=["graphify", "extract"],
    process_outputs=_trace_graph_output,
)
def run_graphify(project_path: str | Path) -> dict[str, Any]:
    path = Path(project_path).expanduser().resolve()
    graph_json = path / "graphify-out" / "graph.json"

    command = [settings.graphify_command, "extract", str(path), "--no-cluster"]
    started_at = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    add_trace_metadata(
        {
            "graphify_command": command,
            "graphify_project_path": str(path),
            "graphify_graph_json": str(graph_json),
            "graphify_returncode": result.returncode,
            "graphify_duration_ms": duration_ms,
            "graphify_stdout_tail": _tail(result.stdout),
            "graphify_stderr_tail": _tail(result.stderr),
        }
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "graphify extraction failed")

    add_trace_metadata({"graphify_graph_json_exists": graph_json.exists()})
    if not graph_json.exists():
        raise FileNotFoundError(f"graphify did not create {graph_json}")

    graph = json.loads(graph_json.read_text(encoding="utf-8"))
    add_trace_metadata({"graph_overview": _graph_overview(graph)})
    return graph


@traceable(
    name="graphify.run_for_github",
    run_type="chain",
    tags=["graphify", "github"],
    process_outputs=_trace_github_output,
)
def run_graphify_for_github(github_url: str, access_token: str | None = None) -> tuple[Path, dict[str, Any]]:
    project_path = clone_or_update_repository(github_url, settings.projects_dir, access_token=access_token)
    add_trace_metadata({"github_url": github_url, "project_path": str(project_path)})
    return project_path, run_graphify(project_path)


@traceable(
    name="graphify.extract_summary",
    run_type="tool",
    tags=["graphify", "summary"],
    process_inputs=_trace_graph_input,
    process_outputs=_trace_summary_output,
)
def extract_graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    hyperedges = graph.get("graph", {}).get("hyperedges", [])

    functions: set[str] = set()
    classes: set[str] = set()
    files: set[str] = set()
    schema_counts = {
        "legacy_function_nodes": 0,
        "legacy_class_nodes": 0,
        "current_function_nodes": 0,
        "current_code_label_nodes": 0,
        "source_file_nodes": 0,
    }

    for node in nodes:
        node_type = str(node.get("type") or node.get("kind") or "").lower()
        node_name = node.get("name") or node.get("id") or node.get("label")

        # Legacy Graphify schema: {"name": "foo", "type": "function", "file": "x.py"}.
        if node_type == "function" and node_name:
            schema_counts["legacy_function_nodes"] += 1
            functions.add(str(node_name))

        elif node_type == "class" and node_name:
            schema_counts["legacy_class_nodes"] += 1
            classes.add(str(node_name))

        for file_key in ("file", "path"):
            if node.get(file_key):
                files.add(str(node[file_key]))

        # Current Graphify schema: {"label": "foo()", "file_type": "code", "source_file": "x.py"}.
        label = str(node.get("label", "")).strip()

        if label.endswith("()"):
            schema_counts["current_function_nodes"] += 1
            functions.add(label[:-2])

        elif (
            label
            and not label.endswith(".py")
            and node.get("file_type") == "code"
        ):
            schema_counts["current_code_label_nodes"] += 1
            classes.add(label)

        if node.get("source_file"):
            schema_counts["source_file_nodes"] += 1
            files.add(str(node["source_file"]))

    functions_list = sorted(functions)
    classes_list = sorted(classes)
    files_list = sorted(files)

    # COMMUNITIES
    communities_raw = graph.get("communities", [])
    if communities_raw:
        # OLD FORMAT
        communities = [
            {
                "name": community.get("label") or community.get("name") or f"Cluster {index}",
                "members": list(community.get("members", []))[:10],
            }
            for index, community in enumerate(communities_raw)
            if isinstance(community, dict)
        ]
    else:
        # NEW FORMAT
        communities = []
        community_map: dict[int, list[str]] = {}

        for node in nodes:
            community = node.get("community")
            if community is None:
                continue
            label = node.get("label") or node.get("name")
            if not label:
                continue
            try:
                community_id = int(community)
            except (TypeError, ValueError):
                continue
            community_map.setdefault(community_id, []).append(str(label))

        for community_id, members in sorted(community_map.items()):
            communities.append(
                {
                    "name": f"Cluster {community_id}",
                    "members": members[:10],
                }
            )

    # EDGES
    def edge_text(edge: dict[str, Any]) -> str:
        return f"{edge.get('source')} -> {edge.get('target')}"

    call_edges = [
        edge_text(edge)
        for edge in edges
        if str(edge.get("type") or edge.get("relation") or "").lower() in {"calls", "call"}
    ]

    import_edges = [
        edge_text(edge)
        for edge in edges
        if str(edge.get("type") or edge.get("relation") or "").lower() in {"imports", "import", "depends_on"}
    ]

    for edge in hyperedges:
        relation = str(edge.get("relation", "")).lower()
        if relation != "participate_in":
            continue
        label = edge.get("label", edge.get("id"))
        nodes_in_edge = edge.get("nodes", [])
        import_edges.append(f"{label}: {', '.join(str(node) for node in nodes_in_edge)}")

    summary = {
        "functions": functions_list[:200],
        "classes": classes_list[:200],
        "files": files_list[:300],
        "call_edges": call_edges[:50],
        "import_edges": import_edges[:50],
        "communities": communities[:30],
    }
    add_trace_metadata(
        {
            "graph_overview": _graph_overview(graph),
            "graph_schema_counts": schema_counts,
            "graph_summary_overview": _summary_overview(summary),
        }
    )
    return summary
