# cisco-packet-tracer-i18n

[中文][English]

思科模拟器的GUI国际化翻译仓库

## 进度

| 语言                                            | 版本       | 总翻译条数 | 已翻译条数 | 覆盖率 | 人工校订 | 下载链接 |
| ----------------------------------------------- | ---------- | ---------- | ---------- | ------ | -------- | -------- |
| 简体中文                                        | 9.0.0.0700 | 10298      | 10298      | 100%   | 进行中   | None     |
| 没有你想要的语言？<br />提出新的issue告诉我们！ |            |            |            |        |          |          |

## 效果预览

## 环境

```bash
$env:HF_ENDPOINT = "https://hf-mirror.com"
conda create -n cisco python=3.13
conda activate cisco
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu129
pip install -r requirements.txt
```

## 如何翻译
各个版本的思科模拟器bin目录内都会附带翻译工具  
linguist.exe  

但是可能会缺少一些运行库，需要手动下载QT开发工具包：  
版本：6.8.3  
1. QT Design Studio 

然后将{QT安装目录}\Tools\QtDesignStudio\bin写入环境变量PATH  

思科模拟器自带一个翻译模板，位于{思科模拟器安装目录}/languages/template.ts  
linguist.exe可以读取该模板，源语言English，目标语言Chinese(简体中文)  
此时可以开始人工翻译，最后使用“发布”导出为qm文件  
将qm文件修改后缀名为ptl文件，然后移动至{思科模拟器安装目录}/languages/目录下即可  
启动思科模拟器，在选项->首选项->语言中选择Chinese(简体中文)，重启软件即可  
