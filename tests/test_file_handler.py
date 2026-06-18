import subprocess

from app.utils import file_handler
from app.utils.file_handler import (
    GitCommandError,
    cleanup_cloned_repository,
    clone_or_update_repository,
    github_slug,
)


def test_cleanup_cloned_repository_deletes_matching_project_dir(tmp_path):
    github_url = "https://github.com/example/project"
    target = tmp_path / github_slug(github_url)
    target.mkdir()
    (target / "README.md").write_text("hello", encoding="utf-8")

    deleted = cleanup_cloned_repository(github_url, str(tmp_path))

    assert deleted is True
    assert not target.exists()


def test_cleanup_cloned_repository_is_noop_when_repo_dir_is_missing(tmp_path):
    deleted = cleanup_cloned_repository(
        "https://github.com/example/missing",
        str(tmp_path),
    )

    assert deleted is False


def test_run_git_includes_git_stderr_in_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            stderr="fatal: repository not found",
        )

    monkeypatch.setattr(file_handler.subprocess, "run", fake_run)

    try:
        file_handler._run_git(["git", "pull"])
    except GitCommandError as exc:
        assert "fatal: repository not found" in str(exc)
    else:
        raise AssertionError("Expected GitCommandError")


def test_clone_or_update_reclones_when_existing_checkout_pull_fails(monkeypatch, tmp_path):
    github_url = "https://github.com/example/private"
    target = tmp_path / github_slug(github_url)
    (target / ".git").mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run_git(args, access_token=None):
        calls.append(args)
        assert access_token == "token"
        if args[3:] == ["pull", "--ff-only"]:
            raise GitCommandError("Git command failed")

    monkeypatch.setattr(file_handler, "_run_git", fake_run_git)

    result = clone_or_update_repository(github_url, str(tmp_path), access_token="token")

    assert result == target
    assert not (target / ".git").exists()
    assert calls == [
        ["git", "-C", str(target), "remote", "set-url", "origin", github_url],
        ["git", "-C", str(target), "pull", "--ff-only"],
        ["git", "clone", "--depth", "1", github_url, str(target)],
    ]
