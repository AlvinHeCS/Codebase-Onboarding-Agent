import os
import re
import shutil
import tempfile
import httpx
from openai import OpenAI
from git import Repo
from temporalio import activity
from app.config import settings
import tree_sitter_python as ts_python
import tree_sitter_javascript as ts_javascript
import tree_sitter_typescript as ts_typescript
import tree_sitter_java as ts_java
import tree_sitter_go as ts_go
import tree_sitter_rust as ts_rust
import tree_sitter_ruby as ts_ruby
import tree_sitter_c as ts_c
import tree_sitter_cpp as ts_cpp
from tree_sitter import Language, Parser

API_BASE = "http://localhost:8001"

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".tox",
}

# Map file extensions to tree-sitter languages and the node types we want to extract
TREE_SITTER_LANGUAGES = {
    ".py": (Language(ts_python.language()), [
        "function_definition", "class_definition", "decorated_definition",
    ]),
    ".js": (Language(ts_javascript.language()), [
        "function_declaration", "class_declaration", "export_statement",
        "lexical_declaration", "variable_declaration",
    ]),
    ".jsx": (Language(ts_javascript.language()), [
        "function_declaration", "class_declaration", "export_statement",
        "lexical_declaration", "variable_declaration",
    ]),
    ".ts": (Language(ts_typescript.language_typescript()), [
        "function_declaration", "class_declaration", "export_statement",
        "lexical_declaration", "variable_declaration", "interface_declaration",
        "type_alias_declaration", "enum_declaration",
    ]),
    ".tsx": (Language(ts_typescript.language_tsx()), [
        "function_declaration", "class_declaration", "export_statement",
        "lexical_declaration", "variable_declaration", "interface_declaration",
        "type_alias_declaration", "enum_declaration",
    ]),
    ".java": (Language(ts_java.language()), [
        "class_declaration", "interface_declaration", "method_declaration",
        "enum_declaration",
    ]),
    ".go": (Language(ts_go.language()), [
        "function_declaration", "method_declaration", "type_declaration",
    ]),
    ".rs": (Language(ts_rust.language()), [
        "function_item", "struct_item", "enum_item", "impl_item", "trait_item",
    ]),
    ".rb": (Language(ts_ruby.language()), [
        "class", "method", "module",
    ]),
    ".c": (Language(ts_c.language()), [
        "function_definition", "struct_specifier", "enum_specifier",
    ]),
    ".h": (Language(ts_c.language()), [
        "function_definition", "struct_specifier", "enum_specifier",
    ]),
    ".cpp": (Language(ts_cpp.language()), [
        "function_definition", "class_specifier", "struct_specifier",
        "enum_specifier", "namespace_definition",
    ]),
}

SUPPORTED_EXTENSIONS = set(TREE_SITTER_LANGUAGES.keys())


@activity.defn
async def greet(name: str) -> str:
    return f"Hello {name}!"


@activity.defn
async def create_user() -> int:
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{API_BASE}/users")
        response.raise_for_status()
        data = response.json()
        return data["id"]


@activity.defn
async def ingest_repo(repo_url: str) -> str:
    tmp_dir = tempfile.mkdtemp()
    try:
        # Clone the repository
        activity.logger.info(f"Cloning {repo_url}")
        Repo.clone_from(repo_url, tmp_dir)

        # Extract repo name from URL
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        # Create repository via API (skips if already exists)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{API_BASE}/repositories", json={
                "name": repo_name,
                "url": repo_url,
            })
            resp.raise_for_status()
            repo_data = resp.json()
            repo_id = repo_data["id"]

            if repo_data.get("exists"):
                return f"Repository '{repo_name}' already exists with id {repo_id}"

            # Walk through all files
            file_count = 0
            for root, dirs, files in os.walk(tmp_dir):
                # Skip unwanted directories
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

                for filename in files:
                    ext = os.path.splitext(filename)[1]
                    if ext not in SUPPORTED_EXTENSIONS:
                        continue

                    filepath = os.path.join(root, filename)
                    relative_path = os.path.relpath(filepath, tmp_dir)

                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except Exception:
                        continue

                    if not content.strip():
                        continue

                    # Store file with original content via API
                    resp = await client.post(
                        f"{API_BASE}/repositories/{repo_id}/files",
                        json={
                            "name": filename,
                            "filePath": relative_path,
                            "content": content,
                            "repository_id": repo_id,
                        },
                    )
                    resp.raise_for_status()
                    file_data = resp.json()
                    file_id = file_data["id"]

                    # Chunk the file and generate embeddings
                    chunks = chunk_file(content, filename)
                    chunk_payloads = build_chunk_payloads(chunks, content, file_id)

                    if chunk_payloads:
                        # Generate embeddings for all chunks in one batch
                        embeddings = get_embeddings([c["content"] for c in chunk_payloads])

                        for payload, embedding in zip(chunk_payloads, embeddings):
                            payload["embedding"] = embedding

                        # Store chunks via API
                        resp = await client.post(
                            f"{API_BASE}/chunks",
                            json={"chunks": chunk_payloads},
                        )
                        resp.raise_for_status()

                    file_count += 1

        return f"Ingested '{repo_name}': {file_count} files processed"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def chunk_file(content: str, filename: str) -> list[str]:
    """Parse code files into chunks using tree-sitter by functions, classes, etc."""
    ext = os.path.splitext(filename)[1]
    language, target_types = TREE_SITTER_LANGUAGES[ext]
    parser = Parser(language)

    source_bytes = content.encode("utf-8")
    tree = parser.parse(source_bytes)

    chunks = []
    lines = content.splitlines(keepends=True)

    # Build a set of line ranges covered by recognized nodes (imports, functions, classes)
    covered_lines = set()

    # Collect import/require statements as one chunk
    import_nodes = []
    for node in tree.root_node.children:
        if node.type in ("import_statement", "import_from_statement",
                         "import_declaration", "expression_statement",
                         "package_declaration"):
            text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            if "import" in text or "require" in text or "package" in text:
                import_nodes.append(text)
                for line_num in range(node.start_point[0], node.end_point[0] + 1):
                    covered_lines.add(line_num)

    if import_nodes:
        chunks.append("\n".join(import_nodes).strip())

    # Collect target node types (functions, classes, etc.)
    # Store as (start_line, chunk_text) so we can interleave with uncovered sections
    structured_chunks = []
    for node in tree.root_node.children:
        if node.type in target_types:
            text = source_bytes[node.start_byte:node.end_byte].decode("utf-8").strip()
            if text:
                structured_chunks.append((node.start_point[0], text))
                for line_num in range(node.start_point[0], node.end_point[0] + 1):
                    covered_lines.add(line_num)

    # Collect uncovered lines (top-level code not in any import/function/class)
    uncovered_sections = []
    current_section = []
    for i, line in enumerate(lines):
        if i not in covered_lines:
            current_section.append(line)
        else:
            if current_section:
                text = "".join(current_section).strip()
                if text:
                    uncovered_sections.append((i - len(current_section), text))
                current_section = []
    if current_section:
        text = "".join(current_section).strip()
        if text:
            uncovered_sections.append((len(lines) - len(current_section), text))

    # Merge structured chunks and uncovered sections in file order
    uncovered_starts = {start for start, _ in uncovered_sections}
    all_sections = structured_chunks + uncovered_sections
    all_sections.sort(key=lambda x: x[0])

    for start, text in all_sections:
        if start in uncovered_starts:
            # Unrecognized top-level code gets fixed-size chunking
            chunks.extend(chunk_by_fixed_size(text))
        else:
            # Functions, classes, etc. stay as-is
            chunks.append(text)

    if not chunks:
        chunks = chunk_by_fixed_size(content)

    return chunks


def chunk_by_fixed_size(content: str, max_lines: int = 50) -> list[str]:
    """Fallback: split content into fixed-size chunks by line count."""
    lines = content.splitlines()
    chunks = []
    for i in range(0, len(lines), max_lines):
        chunk = "\n".join(lines[i:i + max_lines]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks if chunks else [content.strip()]


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI."""
    openai_client = OpenAI(api_key=settings.openai_api_key)
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def _extract_name(chunk_text: str, pattern: str) -> str | None:
    """Extract symbol name from chunk text using a regex pattern."""
    match = re.search(pattern, chunk_text)
    return match.group(1) if match else None


def build_chunk_payloads(chunks: list[str], full_content: str, file_id: int) -> list[dict]:
    """Build chunk payloads with metadata (type, line numbers)."""
    lines = full_content.splitlines()
    payloads = []

    for chunk_text in chunks:
        # Find the chunk's line numbers in the original file
        chunk_lines = chunk_text.splitlines()
        start_line = 0
        end_line = 0

        if chunk_lines:
            first_line = chunk_lines[0]
            for i, line in enumerate(lines):
                if first_line in line:
                    start_line = i + 1
                    end_line = start_line + len(chunk_lines) - 1
                    break

        # Determine chunk type from content
        chunk_type = "code"
        name = None
        lower = chunk_text.lower()
        if lower.startswith(("import ", "from ", "require(", "package ")):
            chunk_type = "import"
        elif "class " in lower[:50]:
            chunk_type = "class"
            name = _extract_name(chunk_text, r'class\s+(\w+)')
        elif "def " in lower[:50] or "function " in lower[:50] or "func " in lower[:50] or "fn " in lower[:50]:
            chunk_type = "function"
            name = _extract_name(chunk_text, r'(?:def|function|func|fn)\s+(\w+)')
        elif lower.startswith(("interface ", "type ")):
            chunk_type = "interface"
            name = _extract_name(chunk_text, r'(?:interface|type)\s+(\w+)')
        elif lower.startswith(("struct ", "enum ")):
            chunk_type = "struct"
            name = _extract_name(chunk_text, r'(?:struct|enum)\s+(\w+)')

        payloads.append({
            "content": chunk_text,
            "chunk_type": chunk_type,
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "file_id": file_id,
        })

    return payloads
