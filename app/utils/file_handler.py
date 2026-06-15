import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def github_slug(github_url: str) -> str:
    parsed = urlparse(github_url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("Only github.com repository URLs are supported")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repository")

    owner = re.sub(r"[^A-Za-z0-9_.-]+", "-", parts[0])
    repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", parts[1].removesuffix(".git"))
    return f"{owner}-{repo}"


def clone_or_update_repository(github_url: str, projects_dir: str) -> Path:
    target = Path(projects_dir).expanduser().resolve() / github_slug(github_url)
    target.parent.mkdir(parents=True, exist_ok=True)

    if (target / ".git").exists():
        subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=True, capture_output=True, text=True)
        return target

    if target.exists() and any(target.iterdir()):
        return target

    subprocess.run(["git", "clone", "--depth", "1", github_url, str(target)], check=True, capture_output=True, text=True)
    return target


def cleanup_cloned_repository(github_url: str, projects_dir: str) -> bool:
    projects_root = Path(projects_dir).expanduser().resolve()
    target = projects_root / github_slug(github_url)

    if target.parent != projects_root:
        raise ValueError("Refusing to delete a path outside projects_dir")

    if not target.exists():
        return False

    shutil.rmtree(target)
    return True
