import json
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.utils.file_handler import clone_or_update_repository


def run_graphify(project_path: str | Path) -> dict[str, Any]:
    path = Path(project_path).expanduser().resolve()
    graph_json = path / "graphify-out" / "graph.json"

    command = [settings.graphify_command, "extract", str(path), "--no-cluster"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "graphify extraction failed")

    if not graph_json.exists():
        raise FileNotFoundError(f"graphify did not create {graph_json}")

    return json.loads(graph_json.read_text(encoding="utf-8"))


def run_graphify_for_github(github_url: str) -> tuple[Path, dict[str, Any]]:
    project_path = clone_or_update_repository(github_url, settings.projects_dir)
    return project_path, run_graphify(project_path)


def _node_name(node: dict[str, Any]) -> str | None:
    value = node.get("name") or node.get("id") or node.get("label")
    return str(value) if value else None


def _node_type(node: dict[str, Any]) -> str:
    return str(node.get("type") or node.get("kind") or "").lower()


def extract_graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    functions = sorted(
        {name for node in nodes if _node_type(node) == "function" and (name := _node_name(node))}
    )
    classes = sorted({name for node in nodes if _node_type(node) == "class" and (name := _node_name(node))})
    files = sorted({str(node.get("file") or node.get("path")) for node in nodes if node.get("file") or node.get("path")})

    def edge_text(edge: dict[str, Any]) -> str:
        return f"{edge.get('source')} -> {edge.get('target')}"

    call_edges = [
        edge_text(edge)
        for edge in edges
        if str(edge.get("type") or edge.get("relation") or "").lower() in {"calls", "call"}
    ][:50]
    import_edges = [
        edge_text(edge)
        for edge in edges
        if str(edge.get("type") or edge.get("relation") or "").lower() in {"imports", "import", "depends_on"}
    ][:30]

    communities = [
        {
            "name": community.get("label") or community.get("name") or f"Cluster {index}",
            "members": list(community.get("members", []))[:10],
        }
        for index, community in enumerate(graph.get("communities", []))
        if isinstance(community, dict)
    ]

    return {
        "functions": functions[:200],
        "classes": classes[:200],
        "files": files[:300],
        "call_edges": call_edges,
        "import_edges": import_edges,
        "communities": communities[:30],
    }
