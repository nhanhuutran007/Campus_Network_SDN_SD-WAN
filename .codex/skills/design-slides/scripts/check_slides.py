#!/usr/bin/env python3
"""Kiểm tra cấu trúc cơ bản của một deck LaTeX Beamer."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
IMAGE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", re.S)
SECTION_RE = re.compile(r"\\section\*?\{([^}]+)\}")
FRAME_BEGIN_RE = re.compile(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{([^}]*)\})?")
FRAME_END_RE = re.compile(r"\\end\{frame\}")
LOG_WARNING_RE = re.compile(
    r"Overfull|Underfull|LaTeX Font Warning|Package hyperref Warning|pdfTeX warning"
)


@dataclass
class Source:
    path: Path
    text: str


def strip_comments(text: str) -> str:
    cleaned: list[str] = []
    for line in text.splitlines():
        match = re.search(r"(?<!\\)%", line)
        cleaned.append(line[: match.start()] if match else line)
    return "\n".join(cleaned)


def resolve_tex(root: Path, raw: str) -> Path:
    candidate = root / raw.strip()
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".tex")
    return candidate.resolve()


def collect_sources(main: Path) -> tuple[list[Source], list[str]]:
    root = main.parent.resolve()
    queue = [main.resolve()]
    visited: set[Path] = set()
    sources: list[Source] = []
    errors: list[str] = []

    while queue:
        path = queue.pop(0)
        if path in visited:
            continue
        visited.add(path)
        if not path.is_file():
            errors.append(f"Thiếu source: {path}")
            continue

        text = strip_comments(path.read_text(encoding="utf-8"))
        sources.append(Source(path, text))
        for raw in INPUT_RE.findall(text):
            child = resolve_tex(root, raw)
            if child not in visited:
                queue.append(child)

    return sources, errors


def inspect(main: Path) -> int:
    sources, errors = collect_sources(main)
    root = main.parent.resolve()
    warnings: list[str] = []
    frame_titles: list[str] = []
    section_count = 0
    image_count = 0

    for source in sources:
        begins = FRAME_BEGIN_RE.findall(source.text)
        ends = FRAME_END_RE.findall(source.text)
        if len(begins) != len(ends):
            errors.append(
                f"Frame không cân bằng trong {source.path.name}: "
                f"{len(begins)} begin / {len(ends)} end"
            )
        frame_titles.extend(title.strip() for title in begins if title.strip())
        section_count += len(SECTION_RE.findall(source.text))

        for raw in IMAGE_RE.findall(source.text):
            image_count += 1
            if "\\" in raw or "#" in raw:
                warnings.append(f"Không thể kiểm tra đường dẫn ảnh động: {raw}")
                continue
            image = (root / raw.strip()).resolve()
            if not image.is_file():
                errors.append(f"Thiếu ảnh: {image}")

    duplicates = sorted({title for title in frame_titles if frame_titles.count(title) > 1})
    for title in duplicates:
        warnings.append(f"Tiêu đề frame trùng: {title}")

    log_path = main.with_suffix(".log")
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        log_warnings = sorted(
            {line.strip() for line in log_text.splitlines() if LOG_WARNING_RE.search(line)}
        )
        warnings.extend(f"Log: {line}" for line in log_warnings)
    else:
        warnings.append(f"Chưa có log biên dịch: {log_path.name}")

    frame_count = sum(len(FRAME_BEGIN_RE.findall(source.text)) for source in sources)
    print(f"Main: {main.resolve()}")
    print(f"Sources: {len(sources)}")
    print(f"Sections: {section_count}")
    print(f"Frames: {frame_count}")
    print(f"Images: {image_count}")

    for warning in warnings:
        print(f"[WARN] {warning}")
    for error in errors:
        print(f"[ERROR] {error}")

    if errors:
        print(f"FAIL: {len(errors)} lỗi, {len(warnings)} cảnh báo")
        return 1
    print(f"PASS: 0 lỗi, {len(warnings)} cảnh báo")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_tex", type=Path, help="Đường dẫn tới file .tex gốc")
    args = parser.parse_args()

    main_tex = args.main_tex.resolve()
    if not main_tex.is_file():
        print(f"[ERROR] Không tìm thấy file: {main_tex}")
        return 2
    if main_tex.suffix.lower() != ".tex":
        print(f"[ERROR] File nguồn phải có phần mở rộng .tex: {main_tex}")
        return 2
    return inspect(main_tex)


if __name__ == "__main__":
    sys.exit(main())
