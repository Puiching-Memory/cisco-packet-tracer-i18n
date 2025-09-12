from lxml import etree

tree = etree.parse("zh_cn_Hunyuan-MT-7B.ts")
root = tree.getroot()