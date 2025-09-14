# https://huggingface.co/tencent/Hunyuan-MT-7B

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import sys
sys.path.append("./model")
from xmlPraser import TSParser

model_name_or_path = "tencent/Hunyuan-MT-7B"

tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
model = AutoModelForCausalLM.from_pretrained(model_name_or_path,
                                             device_map="auto",
                                             dtype=torch.bfloat16,
                                             low_cpu_mem_usage=True,
                                             )  # You may want to use bfloat16 and/or move to GPU here

parser = TSParser('zh_cn_Hunyuan-MT-7B.ts')
for context_name, source_text, translation_elem in parser.get_unfinished_translations():
    # 获取并打印当前进度
    processed, total, percentage = parser.get_progress()
    print(f"翻译进度: {processed}/{total} ({percentage:.2f}%)")

    messages = [
        {"role": "user", "content": f"翻译成简体中文\n\n{source_text}"},
    ]

    tokenized_chat = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=False,
        return_tensors="pt"
    )

    outputs = model.generate(tokenized_chat.to(model.device), max_new_tokens=2048)
    output_text = tokenizer.decode(outputs[0])
    
    # 处理模型输出，提取真正的翻译文本
    if '<|extra_0|>' in output_text:
        # 提取 <|extra_0|> 和 <|eos|> 之间的内容
        start_index = output_text.find('<|extra_0|>') + len('<|extra_0|>')
        end_index = output_text.find('<|eos|>')
        if end_index == -1:  # 如果没有找到 <|eos|>
            translated_text = output_text[start_index:]
        else:
            translated_text = output_text[start_index:end_index]
    else:
        # 如果没有特殊标记，使用整个输出（去掉开始和结束标记）
        translated_text = output_text.replace('<|startoftext|>', '').replace('<|eos|>', '')

    parser.update_translation(context_name, source_text, translation_elem, translated_text)

    print("=" * 50)
    print(f"Context: {context_name}")
    print(f"Source: {source_text}")
    print(f"Translation: {translated_text}")

parser.save('zh_cn_Hunyuan-MT-7B.ts')