#!/usr/bin/env python3
"""Apply translated batch responses back into a Qt Linguist TS file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
import xml.etree.ElementTree as ET


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct a translated Qt Linguist TS file using a batch API "
            "success JSONL payload (e.g. *_success.jsonl)."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the original .ts template file.",
    )
    parser.add_argument(
        "responses",
        type=Path,
        help="Path to the *_success.jsonl file containing translated responses.",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Destination path for the translated .ts file.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Starting request index (matches --start-index used during export).",
    )
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Mirror --deduplicate flag used during export to reuse identical sources.",
    )
    parser.add_argument(
        "--include-finished",
        action="store_true",
        help="Match --include-finished flag from export (default skips already translated entries).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if there are unexpected or missing custom_id entries.",
    )
    return parser.parse_args()


def extract_translated_text(content: str) -> str:
    markers = ["Text:\r\n", "Text:\n"]
    for marker in markers:
        if marker in content:
            return content.split(marker, 1)[1]
    return content


def load_translations(jsonl_path: Path) -> Dict[str, str]:
    translations: Dict[str, str] = {}

    with jsonl_path.open("r", encoding="utf-8") as reader:
        for line_no, raw_line in enumerate(reader, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc

            custom_id = payload.get("custom_id")
            if not custom_id:
                raise ValueError(f"Missing custom_id on line {line_no}")
            if custom_id in translations:
                raise ValueError(f"Duplicate custom_id '{custom_id}' on line {line_no}")

            error = payload.get("error")
            if error:
                raise ValueError(
                    f"Error response for custom_id '{custom_id}': {json.dumps(error, ensure_ascii=False)}"
                )

            response = payload.get("response")
            if not response:
                raise ValueError(f"Missing response for custom_id '{custom_id}'")

            body = response.get("body", {})
            choices = body.get("choices") or []
            if not choices:
                raise ValueError(f"No choices found for custom_id '{custom_id}'")

            message = choices[0].get("message") or {}
            content = message.get("content")
            if content is None:
                raise ValueError(f"Empty translation content for custom_id '{custom_id}'")

            translations[custom_id] = extract_translated_text(content)

    if not translations:
        raise ValueError(f"No translations parsed from {jsonl_path}")

    return translations


def should_update(translation_elem: Optional[ET.Element], include_finished: bool) -> bool:
    if translation_elem is None:
        return True

    text = translation_elem.text or ""
    is_unfinished = translation_elem.get("type") == "unfinished"

    if include_finished:
        return True

    return not text.strip() or is_unfinished


def ensure_translation_elem(message_elem: ET.Element) -> ET.Element:
    translation_elem = message_elem.find("translation")
    if translation_elem is None:
        translation_elem = ET.SubElement(message_elem, "translation")
        translation_elem.set("type", "unfinished")
    return translation_elem


def apply_translations(
    ts_path: Path,
    translations: Dict[str, str],
    *,
    start_index: int,
    deduplicate: bool,
    include_finished: bool,
    strict: bool,
    ) -> Tuple[int, ET.ElementTree]:
    tree = ET.parse(ts_path)
    root = tree.getroot()

    seen_sources: Dict[str, str] = {}
    used_custom_ids: set[str] = set()

    current_index = start_index
    updates = 0

    for context_elem in root.findall("context"):
        for message_elem in context_elem.findall("message"):
            source_elem = message_elem.find("source")
            if source_elem is None:
                continue

            source_text = source_elem.text or ""
            if not source_text.strip():
                continue

            translation_elem = ensure_translation_elem(message_elem)
            if not should_update(translation_elem, include_finished):
                continue

            if deduplicate and source_text in seen_sources:
                translation_elem.text = seen_sources[source_text]
                translation_elem.attrib.pop("type", None)
                updates += 1
                continue

            custom_id = f"request-{current_index}"
            translation_text = translations.get(custom_id)
            if translation_text is None:
                if strict:
                    raise KeyError(
                        f"Missing translation for custom_id '{custom_id}'. "
                        f"Available keys: {len(translations)}."
                    )
                current_index += 1
                continue

            translation_elem.text = translation_text
            translation_elem.attrib.pop("type", None)

            seen_sources[source_text] = translation_text
            used_custom_ids.add(custom_id)
            updates += 1
            current_index += 1

    unused_ids = set(translations.keys()) - used_custom_ids
    if unused_ids and strict:
        raise ValueError(
            "Unused translations detected: "
            + ", ".join(sorted(unused_ids))
        )

    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")  # type: ignore[attr-defined]

    return updates, tree


def main() -> None:
    args = parse_arguments()

    if not args.input.is_file():
        raise FileNotFoundError(f"Input TS file not found: {args.input}")
    if not args.responses.is_file():
        raise FileNotFoundError(f"Responses JSONL file not found: {args.responses}")

    translations = load_translations(args.responses)
    updates, tree = apply_translations(
        args.input,
        translations,
        start_index=args.start_index,
        deduplicate=args.deduplicate,
        include_finished=args.include_finished,
        strict=args.strict,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)

    print(f"Applied {updates} translations to {args.output}.")


if __name__ == "__main__":
    main()
