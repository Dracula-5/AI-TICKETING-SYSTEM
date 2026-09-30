"""
Document text extraction and chunking for the knowledge base.

Supported: Markdown, plain text, HTML, PDF (pypdf), DOCX (python-docx).
Extraction keeps section headings so every chunk can carry the heading it
came from — shown as the citation label and prepended when embedding, which
helps short passages that only make sense under their heading.

Chunking: split into sections at headings, then pack paragraphs into chunks of
about CHUNK_CHARS characters with CHUNK_OVERLAP characters carried over, never
cutting inside a paragraph unless the paragraph alone is too long.
"""

import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser

CHUNK_CHARS = 1000
CHUNK_OVERLAP = 150
MAX_CHUNKS_PER_DOCUMENT = 2000

SUPPORTED = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ParseError(Exception):
    pass


@dataclass
class Section:
    heading: str | None
    text: str


@dataclass
class Chunk:
    ordinal: int
    heading: str | None
    content: str


def _markdown_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    heading: str | None = None
    buf: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^\s{0,3}(#{1,4})\s+(.*?)\s*#*\s*$", line)
        if m:
            if "".join(buf).strip():
                sections.append(Section(heading, "\n".join(buf).strip()))
            heading, buf = m.group(2).strip()[:300] or None, []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append(Section(heading, "\n".join(buf).strip()))
    return sections


class _HTMLText(HTMLParser):
    BLOCK = {"p", "div", "li", "tr", "br", "section", "article", "pre", "table", "ul", "ol", "blockquote"}
    HEAD = {"h1", "h2", "h3", "h4"}
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.cur: list[str] = []
        self.skip = 0
        self.in_head = False

    def _flush(self, prefix: str = ""):
        text = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        if text:
            self.lines.append(prefix + text)
        self.cur = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.HEAD:
            self._flush()
            self.in_head = True
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.HEAD:
            self._flush("## ")
            self.in_head = False
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)


def html_to_markdownish(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    parser._flush()
    return "\n\n".join(parser.lines)


def extract(filename: str, data: bytes) -> tuple[str, str]:
    """Return (content_type, text-with-markdown-headings)."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    ctype = SUPPORTED.get(ext)
    if ctype is None:
        raise ParseError(f"Unsupported file type {ext or '(none)'}; use {', '.join(sorted(SUPPORTED))}")
    try:
        if ext in (".md", ".markdown", ".txt"):
            text = data.decode("utf-8-sig", errors="replace")
        elif ext in (".html", ".htm"):
            text = html_to_markdownish(data.decode("utf-8-sig", errors="replace"))
        elif ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
            text = "\n\n".join(p for p in pages if p)
        else:
            from docx import Document

            doc = Document(io.BytesIO(data))
            parts = []
            for para in doc.paragraphs:
                style = (para.style.name or "").lower() if para.style is not None else ""
                t = para.text.strip()
                if not t:
                    continue
                parts.append(f"## {t}" if style.startswith("heading") or style == "title" else t)
            text = "\n\n".join(parts)
    except ParseError:
        raise
    except Exception as e:  # malformed files: report, don't crash the worker
        raise ParseError(f"Could not read {filename}: {type(e).__name__}") from None
    text = text.replace("\x00", "")
    if not text.strip():
        raise ParseError("No text could be extracted (scanned PDFs need OCR, which is not supported)")
    return ctype, text


def _pack(heading: str | None, text: str) -> list[tuple[str | None, str]]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:  # hard-split paragraphs longer than a chunk at sentence boundaries
        while len(p) > CHUNK_CHARS:
            cut = max(p.rfind(". ", 0, CHUNK_CHARS), p.rfind("\n", 0, CHUNK_CHARS))
            cut = cut + 1 if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)
    out, buf = [], ""
    for piece in pieces:
        if buf and len(buf) + len(piece) + 2 > CHUNK_CHARS:
            out.append((heading, buf))
            tail = buf[-CHUNK_OVERLAP:]
            tail = tail[tail.find(" ") + 1 :] if " " in tail else tail
            buf = f"{tail}\n\n{piece}" if CHUNK_OVERLAP else piece
        else:
            buf = f"{buf}\n\n{piece}" if buf else piece
    if buf:
        out.append((heading, buf))
    return out


def chunk(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in _markdown_sections(text):
        for heading, content in _pack(section.heading, section.text):
            chunks.append(Chunk(len(chunks), heading, content))
            if len(chunks) >= MAX_CHUNKS_PER_DOCUMENT:
                return chunks
    return chunks


def title_from(filename: str, text: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}#{1,2}\s+(.+)", line)
        if m:
            return m.group(1).strip()[:200]
    return filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:200] or filename[:200]
