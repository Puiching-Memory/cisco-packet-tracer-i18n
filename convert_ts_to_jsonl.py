#!/usr/bin/env python3
"""Convert Qt Linguist TS files into JSONL requests for batch translation."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set
import xml.etree.ElementTree as ET

DEFAULT_SYSTEM_PROMPT = (
    "你是思科 Packet Tracer 及网络工程领域的本地化专家，请将输入文本精准翻译为简体中文。"
    "保持 HTML/XML 标签、富文本格式、占位符（例如 %1、%2、{0}、{name}、&lt;br&gt;、\\n 等）以及前后空白完全一致。"
    "务必沿用业界常用的网络工程术语（如 VLAN、ACL、OSPF、Interface 等），CLI 命令、设备型号和寄存器名称不要翻译或改写，注意大小写和标点符号保持原样。"
)


class ContextMode(str, Enum):
    FULL = "full"
    COMPACT = "compact"
    MINIMAL = "minimal"


@dataclass
class TsMessage:
    context: str
    source: str
    comment: Optional[str]
    translator_comment: Optional[str]
    extra_comment: Optional[str]
    locations: Sequence[str]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a Qt Linguist TS template into JSONL batch requests."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input .ts file (e.g. template-8.2.2.0400.ts)",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Path to the output .jsonl file.",
    )
    parser.add_argument(
        "--model",
        default="qwen-max",
        help="Target LLM model name to include in the batch payload.",
    )
    parser.add_argument(
        "--system-prompt",
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt used for each batch request.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Starting index for the custom_id field (default: 1).",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help="Limit the number of entries exported (useful for dry-runs).",
    )
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Skip duplicated source strings to reduce repeated translation requests.",
    )
    parser.add_argument(
        "--include-finished",
        action="store_true",
        help="Include messages that already contain a translated string.",
    )
    parser.add_argument(
        "--context-mode",
        choices=[mode.value for mode in ContextMode],
        default=ContextMode.COMPACT.value,
        help=(
            "How much contextual information to embed in each user prompt. "
            "'full' mirrors the legacy verbose prompt, 'compact' keeps key meta-data "
            "with concise phrasing, 'minimal' only sends the raw text."
        ),
    )
    parser.add_argument(
        "--max-locations",
        type=int,
        default=3,
        help=(
            "Maximum number of location entries to include per message (default: 3). "
            "Set to 0 to omit location info entirely."
        ),
    )
    return parser.parse_args()


def iter_messages(ts_path: Path, *, include_finished: bool = False) -> Iterable[TsMessage]:
    tree = ET.parse(ts_path)
    root = tree.getroot()

    for context_elem in root.findall("context"):
        context_name = context_elem.findtext("name") or ""
        context_name = context_name.strip()

        for message_elem in context_elem.findall("message"):
            source_text = message_elem.findtext("source")
            if source_text is None:
                continue
            if not source_text.strip():
                continue

            translation_elem = message_elem.find("translation")
            if not include_finished and translation_elem is not None:
                translation_type = translation_elem.get("type")
                translation_text = translation_elem.text or ""
                if translation_type != "unfinished" and translation_text.strip():
                    # Already translated, skip.
                    continue

            locations: List[str] = []
            for location in message_elem.findall("location"):
                filename = location.get("filename")
                line = location.get("line")
                if filename and line:
                    locations.append(f"{filename}:{line}")
                elif filename:
                    locations.append(filename)
                elif line:
                    locations.append(f"line {line}")

            comment = message_elem.findtext("comment")
            translator_comment = message_elem.findtext("translatorcomment")
            extra_comment = message_elem.findtext("extracomment")

            yield TsMessage(
                context=context_name,
                source=source_text,
                comment=comment.strip() if comment else None,
                translator_comment=(
                    translator_comment.strip() if translator_comment else None
                ),
                extra_comment=extra_comment.strip() if extra_comment else None,
                locations=locations,
            )


def format_locations(locations: Sequence[str], limit: int) -> Optional[str]:
    if limit == 0 or not locations:
        return None
    if limit > 0 and len(locations) > limit:
        truncated = list(locations[:limit])
        truncated.append(f"(+{len(locations) - limit} more)")
        locations = truncated
    return " | ".join(locations)


def build_user_prompt(
    message: TsMessage,
    *,
    context_mode: ContextMode,
    max_locations: int,
) -> str:
    if context_mode is ContextMode.MINIMAL:
        return f"Translate to Simplified Chinese, keep formatting.\nText: {message.source}"

    header = (
        "请翻译成简体中文，保持占位符、标签和前后空白。"
        if context_mode is ContextMode.COMPACT
        else "请将下面的文本从英文准确翻译为简体中文，注意保持占位符、HTML/XML 标签、换行符及前后空白不变。"
    )

    sections: List[str] = [header]

    if message.context:
        sections.append(f"Context: {message.context}")
    if message.comment:
        sections.append(f"Dev: {message.comment}")
    if message.extra_comment:
        sections.append(f"Extra: {message.extra_comment}")
    if message.translator_comment:
        sections.append(f"Note: {message.translator_comment}")

    loc_blob = format_locations(message.locations, max_locations)
    if loc_blob:
        label = "Locations" if context_mode is ContextMode.FULL else "Loc"
        sections.append(f"{label}: {loc_blob}")

    sections.append("Text:")
    sections.append(message.source)
    return "\n".join(sections)


def main() -> None:
    args = parse_arguments()

    if not args.input.is_file():
        raise FileNotFoundError(f"Input TS file not found: {args.input}")

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_sources: Set[str] = set()
    exported = 0
    custom_index = args.start_index

    context_mode = ContextMode(args.context_mode)
    max_locations = args.max_locations if args.max_locations is not None else -1

    with output_path.open("w", encoding="utf-8", newline="\n") as writer:
        for message in iter_messages(
            args.input, include_finished=args.include_finished
        ):
            source_key = message.source
            if args.deduplicate:
                if source_key in seen_sources:
                    continue
                seen_sources.add(source_key)

            user_prompt = build_user_prompt(
                message,
                context_mode=context_mode,
                max_locations=max_locations,
            )
            payload = {
                "custom_id": f"request-{custom_index}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": args.model,
                    "messages": [
                        {"role": "system", "content": args.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            }

            writer.write(json.dumps(payload, ensure_ascii=False))
            writer.write("\n")

            exported += 1
            custom_index += 1

            if args.max_entries is not None and exported >= args.max_entries:
                break

    print(
        f"Exported {exported} translation requests to {output_path} "
        f"(starting index {args.start_index})."
    )


if __name__ == "__main__":
    main()
