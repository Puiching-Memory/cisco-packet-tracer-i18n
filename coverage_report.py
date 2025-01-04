"""
该代码用于生成中文翻译的覆盖率报告。
---

"""

import json
import xmltodict


def get_language_coverage(xml_path: str) -> tuple[int, int]:
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_data = f.read()

    decode_data = xmltodict.parse(xml_data)

    language_sum = 0
    language_cover = 0

    for ctx in decode_data["TS"]["context"]:  # name,message
        # print(ctx["name"])
        # print("-" * 20)
        for msg in ctx["message"]:  # ['location', 'source', 'translation']
            if isinstance(msg, dict):
                if msg["translation"] is None:
                    continue
                # print(msg["translation"])
                if "#text" in msg["translation"]:
                    language_cover += 1
                language_sum += 1
            else:
                # print("warning:", msg)
                continue
        # break
    return language_sum, language_cover


def draw_progress_bar(language_sum: int, language_cover: int) -> str:
    # TODO
    return image_path


if __name__ == "__main__":
    xml_path = r"C:\workspace\github\cisco-packet-tracer-i18n\chinese.ts"

    language_sum, language_cover = get_language_coverage(xml_path)

    print("-" * 20)
    print("总翻译条数:", language_sum)
    print("已翻译条数:", language_cover)
    print("翻译率:", language_cover / language_sum * 100, "%")
