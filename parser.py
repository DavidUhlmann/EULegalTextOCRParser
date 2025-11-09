"""Utilities for converting EU legal PDFs into structured JSON.

This module exposes two entry points:

```
python parser.py input.pdf output.json
```

The script extracts the text from the PDF, applies a set of heuristics to
identify recitals ("Whereas" statements), chapters, articles and paragraphs,
and stores the information in a machine readable JSON structure.  The parsing
logic is intentionally conservative so that the JSON preserves as much of the
original wording as possible while still being easy to consume programmatically.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass
class Paragraph:
    label: str
    text: str

    def to_dict(self) -> Dict[str, str]:
        return {"label": self.label, "text": self.text.strip()}


@dataclass
class Article:
    number: str
    title: Optional[str] = None
    intro: str = ""
    paragraphs: List[Paragraph] = field(default_factory=list)

    def add_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self.paragraphs:
            self.paragraphs[-1].text += (" " if self.paragraphs[-1].text else "") + text
        else:
            self.intro += (" " if self.intro else "") + text

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "number": self.number,
            "paragraphs": [paragraph.to_dict() for paragraph in self.paragraphs],
        }
        if self.title:
            data["title"] = self.title
        if self.intro:
            data["intro"] = self.intro.strip()
        return data


@dataclass
class Chapter:
    number: Optional[str]
    title: Optional[str] = None
    preamble: List[str] = field(default_factory=list)
    articles: List[Article] = field(default_factory=list)

    def add_text(self, text: str) -> None:
        text = text.strip()
        if text:
            self.preamble.append(text)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "articles": [article.to_dict() for article in self.articles],
        }
        if self.number is not None:
            data["number"] = self.number
        if self.title:
            data["title"] = self.title
        if self.preamble:
            data["preamble"] = " ".join(self.preamble)
        return data


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from *path* using pdfplumber (preferred) or PyPDF2."""

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(path)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except ModuleNotFoundError:
        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ModuleNotFoundError as exc:  # pragma: no cover - import fallback guard
            raise RuntimeError(
                "Neither pdfplumber nor PyPDF2 is installed. Install one of them to "
                "enable PDF text extraction."
            ) from exc


def _normalise_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


_CHAPTER_RE = re.compile(r"^chapter\s+([ivxlcdm\d]+)\.?\s*(.*)$", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^article\s+([\d]+[a-zA-Z]?)(?:\.|:)?\s*(.*)$", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(
    r"^(?P<label>\(?\d+[a-z]?\)?|\(?[a-z]\)?|\(?[ivxlcdm]+\)?)[\.)]?\s+(?P<text>.+)$",
    re.IGNORECASE,
)
_WHEREAS_RE = re.compile(r"^whereas\s*(?:(?P<number>\d+|\(\d+\))[:.)-]?\s*)?(?P<text>.*)$", re.IGNORECASE)


def parse_legal_text(text: str) -> Dict[str, object]:
    lines = [_normalise_line(line) for line in text.splitlines() if _normalise_line(line)]

    whereas_items: List[Dict[str, str]] = []
    preamble_before_body: List[str] = []
    current_whereas: Optional[Dict[str, str]] = None

    chapters: List[Chapter] = []
    current_chapter: Optional[Chapter] = None
    current_article: Optional[Article] = None

    body_started = False

    def finish_whereas() -> None:
        nonlocal current_whereas
        if current_whereas is not None:
            whereas_items.append(current_whereas)
            current_whereas = None

    for line in lines:
        chapter_match = _CHAPTER_RE.match(line)
        article_match = _ARTICLE_RE.match(line)

        if not body_started:
            whereas_match = _WHEREAS_RE.match(line)
            if whereas_match and line.lower().startswith("whereas"):
                if current_whereas is not None:
                    finish_whereas()
                number_token = whereas_match.group("number")
                number = (
                    str(len(whereas_items) + 1)
                    if number_token is None
                    else re.sub(r"[^\d]", "", number_token) or str(len(whereas_items) + 1)
                )
                whereas_text = whereas_match.group("text").strip()
                whereas_text = whereas_text or line[len("Whereas"):].strip(" ,:-")
                current_whereas = {"number": number, "text": whereas_text}
                continue

            if chapter_match or article_match:
                body_started = True
                finish_whereas()
            else:
                if current_whereas is not None:
                    current_whereas["text"] += (" " if current_whereas["text"] else "") + line
                else:
                    preamble_before_body.append(line)
                continue

        if chapter_match:
            finish_whereas()
            chapter_number = chapter_match.group(1).strip().upper()
            title = chapter_match.group(2).strip() or None
            current_chapter = Chapter(number=chapter_number, title=title)
            chapters.append(current_chapter)
            current_article = None
            continue

        if article_match:
            finish_whereas()
            if current_chapter is None:
                current_chapter = Chapter(number=None, title=None)
                chapters.append(current_chapter)
            article_number = article_match.group(1).strip()
            title = article_match.group(2).strip() or None
            current_article = Article(number=article_number, title=title)
            current_chapter.articles.append(current_article)
            continue

        if current_article is not None:
            paragraph_match = _PARAGRAPH_RE.match(line)
            if paragraph_match:
                label = paragraph_match.group("label")
                label = re.sub(r"[()\s]", "", label)
                text_content = paragraph_match.group("text").strip()
                current_article.paragraphs.append(Paragraph(label=label, text=text_content))
            else:
                current_article.add_text(line)
            continue

        if current_chapter is not None:
            current_chapter.add_text(line)
        else:
            preamble_before_body.append(line)

    finish_whereas()

    result: Dict[str, object] = {}
    if preamble_before_body:
        result["preamble"] = " ".join(preamble_before_body)
    if whereas_items:
        result["whereas"] = whereas_items
    if chapters:
        result["chapters"] = [chapter.to_dict() for chapter in chapters]

    return result


def parse_pdf_to_json(pdf_path: Path) -> Dict[str, object]:
    text = extract_text_from_pdf(pdf_path)
    return {
        "source": str(pdf_path),
        "content": parse_legal_text(text),
    }


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Parse EU legal PDFs into JSON.")
    parser.add_argument(
        "pdfs",
        metavar="pdf",
        type=Path,
        nargs="+",
        help="One or more PDF files to parse",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help=(
            "Optional output path. For a single PDF this is the JSON file to write. "
            "For multiple PDFs this must be (or will be created as) a directory."
        ),
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    pdf_paths: List[Path] = args.pdfs

    if len(pdf_paths) == 1:
        data = parse_pdf_to_json(pdf_paths[0])
        json_text = json.dumps(data, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json_text)
        else:
            print(json_text)
        return

    output_path: Optional[Path] = args.output
    if output_path is not None:
        if output_path.exists() and not output_path.is_dir():
            parser.error("When parsing multiple PDFs the output path must be a directory.")
        output_path.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdf_paths:
        data = parse_pdf_to_json(pdf_path)
        json_text = json.dumps(data, indent=2, ensure_ascii=False)
        target_path = (
            output_path / f"{pdf_path.stem}.json" if output_path else pdf_path.with_suffix(".json")
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json_text)
        print(f"Wrote {target_path}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

