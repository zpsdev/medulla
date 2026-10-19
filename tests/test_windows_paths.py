"""Windows portability — backslash paths, UTF-8 file I/O, opening the vault."""
import os
import sys
import types
from pathlib import Path, PureWindowsPath

import pytest

from medulla.episodic.parser import is_subagent_file, project_name
from medulla.episodic.store import get_project_context, list_sessions, upsert_session
from medulla.semantic.wiki import append_log, write_source_page
from tests.test_store import make_session


# ── is_subagent_file ──────────────────────────────────────────────────────────

def test_is_subagent_file_windows_path():
    p = PureWindowsPath(r"C:\Users\me\sessions\C--repo\abc\subagents\agent-xyz.jsonl")
    assert is_subagent_file(p) is True


def test_is_subagent_file_windows_normal_session():
    p = PureWindowsPath(r"C:\Users\me\sessions\C--repo\abc.jsonl")
    assert is_subagent_file(p) is False


# ── project_name ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("project_dir,expected", [
    (r"C:\Users\me\repo", "repo"),
    ("/Users/me/repo", "repo"),
    ("C:/Users/me/repo", "repo"),
    (None, ""),
    ("", ""),
])
def test_project_name(project_dir, expected):
    assert project_name(project_dir) == expected


# ── project filters match either separator ────────────────────────────────────

@pytest.mark.parametrize("query", [r"C:\Users\me\repo", "C:/Users/me/repo", "repo"])
def test_list_sessions_matches_windows_project(db, query):
    upsert_session(db, make_session("win-1", project_dir=r"C:\Users\me\repo"))
    rows = list_sessions(db, project=query)
    assert [r["session_id"] for r in rows] == ["win-1"]


def test_project_context_matches_forward_slash_query(db):
    upsert_session(db, make_session("win-2", project_dir=r"C:\Users\me\repo"))
    ctx = get_project_context(db, "C:/Users/me/repo")
    assert [s["session_id"] for s in ctx["sessions"]] == ["win-2"]


# ── wiki files are UTF-8 regardless of locale ─────────────────────────────────

def test_wiki_pages_written_as_utf8(tmp_path):
    wiki = tmp_path / "wiki"
    title = "Café — naïve 日本語"
    data = {"title": title, "tags": [], "summary": "Résumé ✓", "key_points": [],
            "concepts": [], "entities": [], "connections": [], "gaps": []}
    path = write_source_page(wiki, "cafe", data, "file.pdf")
    assert title in path.read_bytes().decode("utf-8")

    append_log(wiki, "ingest", title, "détails · more")
    append_log(wiki, "ingest", title)
    assert path.parent.parent.joinpath("log.md").read_bytes().decode("utf-8").count(title) == 2


# ── wiki open ─────────────────────────────────────────────────────────────────

def test_open_vault_macos(monkeypatch, tmp_path):
    from medulla import cli
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(cli.subprocess, "run", lambda args, **kw: calls.append(args))
    assert cli._open_vault(tmp_path) == "Obsidian"
    assert calls == [["open", "-a", "Obsidian", str(tmp_path)]]


def test_open_vault_linux(monkeypatch, tmp_path):
    from medulla import cli
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cli.subprocess, "run", lambda args, **kw: calls.append(args))
    assert cli._open_vault(tmp_path) == "Obsidian"
    assert calls[0][0] == "xdg-open" and calls[0][1].startswith("obsidian://open?path=")


def _fake_winreg(installed: bool):
    def open_key(root, name):
        if not installed:
            raise OSError("not found")
        return object()
    return types.SimpleNamespace(HKEY_CLASSES_ROOT=0, OpenKey=open_key, CloseKey=lambda k: None)


@pytest.mark.parametrize("installed,app_name", [(True, "Obsidian"), (False, "File Explorer")])
def test_open_vault_windows(monkeypatch, tmp_path, installed, app_name):
    from medulla import cli
    opened = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(installed))
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)
    assert cli._open_vault(tmp_path) == app_name
    if installed:
        assert str(opened[0]).startswith("obsidian://open?path=")
    else:
        assert opened == [tmp_path]
