from app.utils.file_handler import cleanup_cloned_repository, github_slug


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
