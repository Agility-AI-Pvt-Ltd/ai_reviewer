import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class GitCommandError(RuntimeError):
    pass


def parse_github_repo_url(github_url: str) -> tuple[str, str]:
    parsed = urlparse(github_url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("Only github.com repository URLs are supported")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repository")

    return parts[0], parts[1].removesuffix(".git")


def github_slug(github_url: str) -> str:
    owner_part, repo_part = parse_github_repo_url(github_url)
    owner = re.sub(r"[^A-Za-z0-9_.-]+", "-", owner_part)
    repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", repo_part)
    return f"{owner}-{repo}"


def _format_git_error(args: list[str], exc: subprocess.CalledProcessError) -> str:
    detail = (exc.stderr or exc.stdout or "").strip()
    command = " ".join(args)
    if detail:
        return f"Git command failed ({command}): {detail}"
    return f"Git command failed ({command}) with exit status {exc.returncode}"


def _run_git(args: list[str], access_token: str | None = None) -> None:
    if access_token:
        with tempfile.TemporaryDirectory() as temp_dir:
            askpass = Path(temp_dir) / "git-askpass.sh"
            askpass.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "*Username*) printf '%s\\n' x-access-token ;;\n"
                "*Password*) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
                "*) printf '\\n' ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            env = os.environ.copy()
            env["GIT_ASKPASS"] = str(askpass)
            env["GITHUB_TOKEN"] = access_token
            env["GIT_TERMINAL_PROMPT"] = "0"
            try:
                subprocess.run(args, check=True, capture_output=True, text=True, env=env)
            except subprocess.CalledProcessError as exc:
                raise GitCommandError(_format_git_error(args, exc)) from exc
            return

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, env=env)
    except subprocess.CalledProcessError as exc:
        raise GitCommandError(_format_git_error(args, exc)) from exc


def clone_or_update_repository(github_url: str, projects_dir: str, access_token: str | None = None) -> Path:
    target = Path(projects_dir).expanduser().resolve() / github_slug(github_url)
    target.parent.mkdir(parents=True, exist_ok=True)

    if (target / ".git").exists():
        _run_git(
            ["git", "-C", str(target), "remote", "set-url", "origin", github_url],
            access_token=access_token,
        )
        try:
            _run_git(["git", "-C", str(target), "pull", "--ff-only"], access_token=access_token)
        except GitCommandError:
            shutil.rmtree(target)
            _run_git(
                ["git", "clone", "--depth", "1", github_url, str(target)],
                access_token=access_token,
            )
        return target

    if target.exists() and any(target.iterdir()):
        return target

    _run_git(["git", "clone", "--depth", "1", github_url, str(target)], access_token=access_token)
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
