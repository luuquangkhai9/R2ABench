# -*- coding: utf-8 -*-
"""Prepare E-R2A source evidence and SRS-normalization prompt files.

This script is intentionally deterministic and does not call any LLM service.
It discovers educational-project source requirement documents, extracts text,
chunks the text into traceable evidence items, and writes a compact evidence
pack plus a prompt/context file that can be used for SRS normalization.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable, List, Optional
from xml.etree import ElementTree


SUPPORTED_SOURCE_SUFFIXES = (".md", ".txt", ".docx", ".pdf")

CATEGORY_KEYWORDS = {
    "functional": [
        "function",
        "feature",
        "shall",
        "support",
        "user",
        "api",
        "endpoint",
        "功能",
        "用户",
        "系统应",
        "支持",
        "接口",
        "用例",
    ],
    "non_functional": [
        "performance",
        "security",
        "reliability",
        "availability",
        "usability",
        "maintainability",
        "nfr",
        "性能",
        "安全",
        "可靠",
        "可用",
        "易用",
        "维护",
    ],
    "technical_constraint": [
        "technology",
        "framework",
        "database",
        "platform",
        "runtime",
        "version",
        "vue",
        "spring",
        "mysql",
        "redis",
        "技术",
        "框架",
        "数据库",
        "平台",
        "运行环境",
        "版本",
        "约束",
    ],
    "architecture": [
        "architecture",
        "layer",
        "component",
        "service",
        "deployment",
        "module",
        "架构",
        "层",
        "组件",
        "服务",
        "部署",
        "模块",
    ],
    "data": [
        "data",
        "database",
        "schema",
        "entity",
        "table",
        "field",
        "数据",
        "表",
        "字段",
        "实体",
    ],
    "actor": [
        "actor",
        "role",
        "administrator",
        "visitor",
        "用户",
        "管理员",
        "访客",
        "角色",
    ],
}


SRS_PROMPT_TEMPLATE = """# E-R2A SRS Normalization Prompt Context

Use the prompt and rules documented in the repository root README section
"E-R2A SRS Normalization Prompt".

## Project

- Sample ID: `{sample_id}`
- Language group: `{language}`
- Source document: `{source_document}`

## Evidence Pack

Use the companion JSON file:

```text
{evidence_pack_name}
```

The SRS must cite evidence item IDs from that JSON file and must not introduce
requirements, technologies, interfaces, or architecture decisions unsupported
by the evidence.
"""


@dataclass
class SourceDocument:
    path: Path
    text: str
    source_type: str


@dataclass
class EvidenceItem:
    item_id: str
    title: str
    location: str
    evidence_type: str
    categories: List[str]
    extracted_facts: List[str]
    raw_excerpt: str


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic E-R2A evidence packs and SRS prompt contexts."
    )
    parser.add_argument(
        "--dataset-dir",
        default="Dataset/E-R2A",
        help="E-R2A dataset root or a single E-R2A project directory.",
    )
    parser.add_argument(
        "--out-dir",
        default="construction_output/e_r2a",
        help="Output directory for generated evidence packs and prompt files.",
    )
    parser.add_argument(
        "--project",
        help="Optional project folder name to process, such as SmartRecipe.",
    )
    parser.add_argument(
        "--max-chars-per-item",
        type=int,
        default=2200,
        help="Maximum raw excerpt size per evidence item before splitting.",
    )
    parser.add_argument(
        "--facts-per-item",
        type=int,
        default=8,
        help="Maximum number of extracted facts kept for each evidence item.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and summarize projects without writing files.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail immediately when a source document cannot be read.",
    )
    args = parser.parse_args(argv)

    dataset_dir = Path(args.dataset_dir)
    out_dir = Path(args.out_dir)
    projects = discover_projects(dataset_dir, args.project)
    if not projects:
        print(f"No E-R2A projects found under {dataset_dir}", file=sys.stderr)
        return 2

    manifest = []
    skipped = []
    for project_dir in projects:
        try:
            source = find_source_document(project_dir)
        except Exception as exc:  # noqa: BLE001 - CLI should report and continue by default.
            if args.strict:
                raise
            skipped.append({"project_dir": safe_relative(project_dir, Path.cwd()), "reason": str(exc)})
            print(f"[skip] {project_dir.name}: {exc}", file=sys.stderr)
            continue
        if source is None:
            skipped.append(
                {
                    "project_dir": safe_relative(project_dir, Path.cwd()),
                    "reason": "no *_origin source document found",
                }
            )
            print(f"[skip] {project_dir.name}: no *_origin source document found", file=sys.stderr)
            continue
        language = infer_language_group(project_dir)
        sample_id = project_dir.name
        evidence = build_evidence_items(
            sample_id=sample_id,
            source=source,
            repo_root=Path.cwd(),
            max_chars=args.max_chars_per_item,
            facts_per_item=args.facts_per_item,
        )
        entry = {
            "sample_id": sample_id,
            "language": language,
            "project_dir": safe_relative(project_dir, Path.cwd()),
            "source_document": safe_relative(source.path, Path.cwd()),
            "source_type": source.source_type,
            "evidence_items": len(evidence),
        }
        manifest.append(entry)

        if args.dry_run:
            print(
                f"[dry-run] {sample_id}: {len(evidence)} evidence items from "
                f"{safe_relative(source.path, Path.cwd())}"
            )
            continue

        project_out = out_dir / language / sample_id
        project_out.mkdir(parents=True, exist_ok=True)
        evidence_path = project_out / "evidence_pack.json"
        prompt_path = project_out / "srs_prompt.md"
        source_text_path = project_out / "source_text.txt"
        for path in (evidence_path, prompt_path, source_text_path):
            if path.exists() and not args.overwrite:
                raise FileExistsError(f"{path} exists; use --overwrite to replace it")

        evidence_pack = {
            "schema": "r2abench_e_r2a_source_evidence_pack_v1",
            "sample_id": sample_id,
            "language": language,
            "source_document": safe_relative(source.path, Path.cwd()),
            "source_type": source.source_type,
            "extraction_rules": {
                "unit": "section_or_paragraph_chunk",
                "evidence_policy": "include explicit source-supported facts only",
                "traceability": "every normalized SRS requirement must cite evidence item IDs",
                "unsupported_content_policy": "exclude or mark as out of scope",
            },
            "evidence_items": [item.__dict__ for item in evidence],
        }
        write_text(evidence_path, json.dumps(evidence_pack, ensure_ascii=False, indent=2))
        write_text(
            prompt_path,
            SRS_PROMPT_TEMPLATE.format(
                sample_id=sample_id,
                language=language,
                source_document=safe_relative(source.path, Path.cwd()),
                evidence_pack_name=evidence_path.name,
            ),
        )
        write_text(source_text_path, source.text)
        print(f"[write] {safe_relative(project_out, Path.cwd())}")

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_text(
            out_dir / "manifest.json",
            json.dumps({"processed": manifest, "skipped": skipped}, ensure_ascii=False, indent=2),
        )
    print(f"Processed {len(manifest)} project(s); skipped {len(skipped)}.")
    return 0 if manifest else 1


def discover_projects(dataset_dir: Path, project_name: Optional[str]) -> List[Path]:
    if is_project_dir(dataset_dir):
        projects = [dataset_dir]
    else:
        projects = []
        for language_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
            projects.extend(sorted(p for p in language_dir.iterdir() if is_project_dir(p)))
    if project_name:
        projects = [p for p in projects if p.name == project_name]
    return projects


def is_project_dir(path: Path) -> bool:
    return path.is_dir() and any(p.is_file() and "_origin" in p.stem for p in path.iterdir())


def find_source_document(project_dir: Path) -> Optional[SourceDocument]:
    candidates = sorted(
        p
        for p in project_dir.iterdir()
        if p.is_file()
        and "_origin" in p.stem
        and p.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
    )
    if not candidates:
        return None
    path = candidates[0]
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        text = read_text_with_fallback(path)
        source_type = suffix.lstrip(".")
    elif suffix == ".docx":
        text = extract_docx_text(path)
        source_type = "docx"
    elif suffix == ".pdf":
        text = extract_pdf_text(path)
        source_type = "pdf"
    else:
        raise ValueError(f"Unsupported source type: {path}")
    return SourceDocument(path=path, text=text, source_type=source_type)


def read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_bytes)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for para in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in para.findall(".//w:t", namespace))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n\n".join(paragraphs)


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "PDF extraction requires pypdf or PyPDF2. Install one of them, "
                "or provide a Markdown/text source document."
            ) from exc
    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {index}]\n{text.strip()}")
    return "\n\n".join(pages)


def build_evidence_items(
    sample_id: str,
    source: SourceDocument,
    repo_root: Path,
    max_chars: int,
    facts_per_item: int,
) -> List[EvidenceItem]:
    sections = split_into_sections(source.text, max_chars=max_chars)
    prefix = make_id_prefix(sample_id)
    items = []
    for index, section in enumerate(sections, start=1):
        title = section["title"] or f"Source chunk {index}"
        excerpt = section["text"].strip()
        if not excerpt:
            continue
        facts = extract_facts(excerpt, limit=facts_per_item)
        categories = classify_categories(excerpt)
        items.append(
            EvidenceItem(
                item_id=f"{prefix}-{index:03d}",
                title=clean_inline(title)[:120],
                location=f"{safe_relative(source.path, repo_root)} lines {section['start']}-{section['end']}",
                evidence_type="explicit",
                categories=categories,
                extracted_facts=facts,
                raw_excerpt=excerpt,
            )
        )
    return items


def split_into_sections(text: str, max_chars: int) -> List[dict]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_re = re.compile(r"^\s*(#{1,6}\s+.+|\d+(?:\.\d+)*[、.．\s]+.+)$")
    sections = []
    current_title = "Document overview"
    current_start = 1
    current_lines: List[str] = []

    def flush(end_line: int) -> None:
        nonlocal current_lines, current_start, current_title
        block = "\n".join(current_lines).strip()
        if not block:
            current_lines = []
            return
        for part_index, part in enumerate(split_large_block(block, max_chars), start=1):
            title = current_title if part_index == 1 else f"{current_title} (part {part_index})"
            sections.append(
                {
                    "title": title,
                    "start": current_start,
                    "end": end_line,
                    "text": part,
                }
            )
        current_lines = []

    for line_number, line in enumerate(lines, start=1):
        if heading_re.match(line) and current_lines:
            flush(line_number - 1)
            current_title = clean_heading(line)
            current_start = line_number
            current_lines = [line]
        else:
            if heading_re.match(line) and not current_lines:
                current_title = clean_heading(line)
                current_start = line_number
            current_lines.append(line)
    flush(len(lines))
    return sections


def split_large_block(block: str, max_chars: int) -> List[str]:
    if len(block) <= max_chars:
        return [block]
    paragraphs = re.split(r"\n\s*\n", block)
    chunks = []
    current = []
    current_size = 0
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and current_size + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_size = 0
        if len(paragraph) > max_chars:
            chunks.extend(paragraph[i : i + max_chars] for i in range(0, len(paragraph), max_chars))
            continue
        current.append(paragraph)
        current_size += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def extract_facts(text: str, limit: int) -> List[str]:
    candidates = []
    for raw in re.split(r"[\n。；;.!?]+", text):
        fact = clean_inline(raw)
        if len(fact) < 12:
            continue
        if fact.startswith("|") and fact.endswith("|"):
            fact = " ".join(part.strip() for part in fact.strip("|").split("|") if part.strip())
        candidates.append(fact)
    deduped = []
    seen = set()
    for fact in candidates:
        key = fact.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact[:500])
        if len(deduped) >= limit:
            break
    return deduped


def classify_categories(text: str) -> List[str]:
    lowered = text.lower()
    categories = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            categories.append(category)
    return categories or ["general"]


def clean_heading(line: str) -> str:
    line = re.sub(r"^\s*#{1,6}\s*", "", line)
    return clean_inline(line)


def clean_inline(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -\t")


def make_id_prefix(sample_id: str) -> str:
    letters = re.findall(r"[A-Za-z0-9]+", sample_id)
    if not letters:
        return "ER2A"
    compact = "".join(part[:3] for part in letters[:3]).upper()
    return compact[:10] or "ER2A"


def infer_language_group(project_dir: Path) -> str:
    parent = project_dir.parent.name
    return parent if parent in {"JAVA", "Python"} else "Unknown"


def safe_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
