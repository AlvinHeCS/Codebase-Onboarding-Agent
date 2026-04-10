import pytest

REPO_URL = "https://github.com/test/repo"
BAD_REPO_URL = "https://github.com/nonexistent/repo"


# --- list_files ---


async def test_list_files(client):
    resp = await client.post("/tools/list_files", json={"repo_url": REPO_URL})
    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["files"]) == ["src/index.ts", "src/main.py", "src/utils.py"]


async def test_list_files_with_glob(client):
    resp = await client.post("/tools/list_files", json={"repo_url": REPO_URL, "glob": "*.py"})
    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["files"]) == ["src/main.py", "src/utils.py"]


async def test_list_files_repo_not_found(client):
    resp = await client.post("/tools/list_files", json={"repo_url": BAD_REPO_URL})
    assert resp.status_code == 404


# --- read_file ---


async def test_read_file(client):
    resp = await client.post("/tools/read_file", json={"repo_url": REPO_URL, "path": "src/main.py"})
    assert resp.status_code == 200
    data = resp.json()
    assert "def hello():" in data["content"]
    assert data["total_lines"] == 8


async def test_read_file_with_range(client):
    resp = await client.post("/tools/read_file", json={"repo_url": REPO_URL, "path": "src/main.py", "start": 4, "end": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["start"] == 4
    assert data["end"] == 5
    assert "def hello():" in data["content"]


async def test_read_file_not_found(client):
    resp = await client.post("/tools/read_file", json={"repo_url": REPO_URL, "path": "nonexistent.py"})
    assert resp.status_code == 404


async def test_read_file_repo_not_found(client):
    resp = await client.post("/tools/read_file", json={"repo_url": BAD_REPO_URL, "path": "src/main.py"})
    assert resp.status_code == 404


# --- search_code ---


async def test_search_code(client):
    resp = await client.post("/tools/search_code", json={"repo_url": REPO_URL, "query": "def hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    files = [m["file"] for m in data["matches"]]
    assert "src/main.py" in files
    assert "src/utils.py" in files


async def test_search_code_with_file_type(client):
    resp = await client.post("/tools/search_code", json={"repo_url": REPO_URL, "query": "def hello", "file_type": ".py"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


async def test_search_code_no_matches(client):
    resp = await client.post("/tools/search_code", json={"repo_url": REPO_URL, "query": "zzz_no_match_zzz"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_search_code_invalid_regex(client):
    resp = await client.post("/tools/search_code", json={"repo_url": REPO_URL, "query": "[invalid"})
    assert resp.status_code == 400


async def test_search_code_repo_not_found(client):
    resp = await client.post("/tools/search_code", json={"repo_url": BAD_REPO_URL, "query": "hello"})
    assert resp.status_code == 404


# --- find_references ---


async def test_find_references_function(client):
    resp = await client.post("/tools/find_references", json={"repo_url": REPO_URL, "symbol": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "hello"
    assert len(data["matches"]) == 2
    for match in data["matches"]:
        assert match["chunk_type"] == "function"
        assert "file_path" in match
        assert "line" in match
        assert "end_line" in match


async def test_find_references_class(client):
    resp = await client.post("/tools/find_references", json={"repo_url": REPO_URL, "symbol": "Helper"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) == 1
    assert data["matches"][0]["chunk_type"] == "class"
    assert data["matches"][0]["file_path"] == "src/utils.py"


async def test_find_references_no_matches(client):
    resp = await client.post("/tools/find_references", json={"repo_url": REPO_URL, "symbol": "NonExistent"})
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


async def test_find_references_case_sensitive(client):
    resp = await client.post("/tools/find_references", json={"repo_url": REPO_URL, "symbol": "helper"})
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


async def test_find_references_repo_not_found(client):
    resp = await client.post("/tools/find_references", json={"repo_url": BAD_REPO_URL, "symbol": "hello"})
    assert resp.status_code == 404
