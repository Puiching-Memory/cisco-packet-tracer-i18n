from lxml import etree
import os
import json


class TSParser:
    """
    思科Packet Tracer GUI翻译文件(.ts)解析器
    支持流式更新和中断恢复功能
    """
    
    def __init__(self, ts_file_path, checkpoint_file=None, backup_interval=10):
        """
        初始化TSParser实例
        
        Args:
            ts_file_path (str): TS文件路径
            checkpoint_file (str, optional): 检查点文件路径，默认为ts_file_path + '.checkpoint'
            backup_interval (int): 定期保存XML文件的间隔（处理条目数），默认为10
        """
        self.ts_file_path = ts_file_path
        self.tree = etree.parse(ts_file_path)
        self.root = self.tree.getroot()
        self.checkpoint_file = checkpoint_file or ts_file_path + '.checkpoint'
        self.backup_interval = backup_interval
        self.processed_count = 0
        self.processed_items = set()
        
        # 初始化进度统计并加载检查点
        self._initialize()

    def _initialize(self):
        """初始化未完成项目计数并加载检查点文件"""
        # 如果存在检查点文件，则加载已处理的项目
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.processed_items = set(data.get('processed_items', []))
            except Exception:
                self.processed_items = set()
        
        # 计算总条目数（所有有source的条目）
        self.total_items = 0
        for context in self.root.findall('.//context'):
            for message in context.findall('.//message'):
                source_elem = message.find('source')
                # 只统计有source的条目
                if source_elem is not None and source_elem.text:
                    self.total_items += 1
        
        # 与XML文件同步，将已完成的条目添加到已处理项目中
        for context in self.root.findall('.//context'):
            context_name = context.find('name').text if context.find('name') is not None else ''
            for message in context.findall('.//message'):
                source_elem = message.find('source')
                translation_elem = message.find('translation')
                
                # 检查已完成的翻译条目
                if (source_elem is not None and source_elem.text and 
                    translation_elem is not None and
                    translation_elem.text is not None and 
                    translation_elem.text.strip() != '' and
                    translation_elem.get('type') != 'unfinished'):
                    item_key = f"{context_name}:{source_elem.text}"
                    self.processed_items.add(item_key)

    def get_unfinished_translations(self):
        """
        生成器接口，每次迭代返回一个待翻译的文本
        
        Yields:
            tuple: (context_name, source_text, translation_element)
                - context_name (str): 上下文名称
                - source_text (str): 源文本
                - translation_element (etree.Element): 翻译元素
        """
        for context in self.root.findall('.//context'):
            context_name = context.find('name').text if context.find('name') is not None else ''
            for message in context.findall('.//message'):
                source_elem = message.find('source')
                translation_elem = message.find('translation')
                
                # 检查是否需要翻译（translation元素没有内容或者type为unfinished）
                if translation_elem is not None:
                    is_unfinished = (translation_elem.text is None or 
                                   translation_elem.text.strip() == '' or
                                   translation_elem.get('type') == 'unfinished')
                    
                    if is_unfinished and source_elem is not None and source_elem.text:
                        item_key = f"{context_name}:{source_elem.text}"
                        
                        # 如果该项目尚未处理，则返回它
                        if item_key not in self.processed_items:
                            yield (context_name, source_elem.text, translation_elem)

    def get_translation_stats(self):
        """
        获取翻译统计信息
        
        Returns:
            tuple: (total_count, finished_count, unfinished_count)
                - total_count (int): 总条目数
                - finished_count (int): 已完成条目数
                - unfinished_count (int): 未完成条目数
        """
        total_count = 0
        finished_count = 0
        
        for context in self.root.findall('.//context'):
            for message in context.findall('.//message'):
                source_elem = message.find('source')
                translation_elem = message.find('translation')
                
                # 只统计有source的条目
                if source_elem is not None and source_elem.text:
                    total_count += 1
                    
                    # 检查是否已完成翻译
                    if translation_elem is not None:
                        is_finished = (translation_elem.text is not None and 
                                     translation_elem.text.strip() != '' and
                                     translation_elem.get('type') != 'unfinished')
                        
                        if is_finished:
                            finished_count += 1
        
        unfinished_count = total_count - finished_count
        return (total_count, finished_count, unfinished_count)

    def get_progress(self):
        """
        获取当前翻译进度
        
        Returns:
            tuple: (processed_count, total_items, percentage)
                - processed_count (int): 已处理条目数
                - total_items (int): 总条目数
                - percentage (float): 完成百分比
        """
        # 总数是所有有source的条目数
        total = self.total_items
        
        # 已处理数是processed_items集合的大小（包括已完成和当前处理的）
        processed = len(self.processed_items)
        
        if total == 0:
            percentage = 100.0
        else:
            percentage = (processed / total) * 100
        
        return (processed, total, percentage)

    def update_translation(self, context_name, source_text, translation_element, translated_text):
        """
        流式更新接口，将翻译完成的文本写入translation元素，并记录处理状态
        
        Args:
            context_name (str): 上下文名称
            source_text (str): 源文本
            translation_element (etree.Element): 翻译元素
            translated_text (str): 翻译后的文本
        """
        translation_element.text = translated_text
        # 移除unfinished属性，表示已完成翻译
        if 'type' in translation_element.attrib:
            del translation_element.attrib['type']
        
        # 记录已处理的项目
        item_key = f"{context_name}:{source_text}"
        self.processed_items.add(item_key)
        self.processed_count += 1
        
        # 保存检查点
        try:
            # 准备保存的数据
            data = {
                'processed_items': list(self.processed_items)
            }
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存检查点文件失败: {e}")
        
        # 每隔一定次数保存一次XML文件，防止中断时丢失翻译内容
        if self.processed_count % self.backup_interval == 0:
            try:
                self.tree.write(self.ts_file_path, encoding='utf-8', xml_declaration=True, pretty_print=True)
            except Exception as e:
                print(f"保存XML文件失败: {e}")

    def save(self, output_file_path=None):
        """
        保存修改后的TS文件，并清理检查点文件
        
        Args:
            output_file_path (str, optional): 输出文件路径，默认为原始文件路径
        """
        file_path = output_file_path if output_file_path else self.ts_file_path
        self.tree.write(file_path, encoding='utf-8', xml_declaration=True, pretty_print=True)
        
        # 保存成功后删除检查点文件
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
        
        # 清空已处理项目记录
        self.processed_items.clear()
        self.processed_count = 0