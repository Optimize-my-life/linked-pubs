"""Document sets: PDFs or text files dropped onto a documents block."""
from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

from ..models import Document

TEXT_SUFFIXES = {".txt", ".md"}


class DocsetStore:
    def __init__(self, root: Path):
        self.root = root / "docsets"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self) -> str:
        docset_id = uuid.uuid4().hex[:8]
        (self.root / docset_id).mkdir()
        return docset_id

    def _dir(self, docset_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{8}", docset_id) or not (self.root / docset_id).is_dir():
            raise KeyError(docset_id)
        return self.root / docset_id

    def add_file(self, docset_id: str, filename: str, content: bytes) -> Document:
        d = self._dir(docset_id)
        name = Path(filename).name
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf":
            text = pdf_text(content)
        elif suffix in TEXT_SUFFIXES:
            text = content.decode("utf-8", errors="replace")
        else:
            raise ValueError(f"{name}: only .pdf, .txt and .md files are supported")
        if not text.strip():
            raise ValueError(f"{name}: no text found (scanned PDF without a text layer?)")
        doc = Document(id=f"{docset_id}-{len(self.documents(docset_id)) + 1}", title=Path(name).stem, text=text)
        (d / "files").mkdir(exist_ok=True)
        (d / "files" / name).write_bytes(content)
        with (d / "documents.jsonl").open("a", encoding="utf-8") as f:
            f.write(doc.model_dump_json() + "\n")
        return doc

    def documents(self, docset_id: str) -> list[Document]:
        path = self._dir(docset_id) / "documents.jsonl"
        if not path.exists():
            return []
        return [Document.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def summary(self, docset_id: str) -> dict:
        docs = self.documents(docset_id)
        return {"id": docset_id, "documents": [{"id": d.id, "title": d.title, "chars": len(d.text)} for d in docs]}


def pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    # Join hyphenated line breaks and keep paragraph breaks.
    text = "\n\n".join(pages)
    return re.sub(r"-\n(?=[a-z])", "", text)
