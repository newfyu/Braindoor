# 🧠 大脑门 Braindoor

中文 | [English](doc/README_EN.md)

## 概述

大脑门可以方便的用本地文件来构建ChatGPT的外部知识库。支持自然语言搜索、问答和全文分析本地文档。

![](doc/demo.gif)

### 功能

- 用自然语言检索个人文档或笔记
- 用本地文本构建一个特定领域的问答机器人
- 超长文本分析和问答

### 特点

- 灵活简单的构建本地的知识库（支持txt，md，html，pdf，docx），只需要指定本地文件夹路径
- 跟踪文件内容变化，增量更新向量数据库
- 本地部署的Web UI 和托盘快捷开关
- 支持任意长度文档的作为上下文 [原理](#长文本阅读原理) 

----

### 安装和启动

1、创建一个python3.9的conda虚拟环境

```shell
conda create -n braindoor python=3.9
conda activate braindoor
```

2、安装依赖包

```shell
git clone https://github.com/newfyu/Braindoor.git
cd Braindoor
pip install -r requirements.txt
# conda install -c conda-forge faiss-cpu # windows
```

3、启动

```shell
python run.py
```

**浏览器中打开地址 `127.0.0.1:7086`，然后在`Config`标签中配置你的`openai key`才能正常使用！** 
国内用户可能还要在`Config`标签中配置http代理服务器地址，或则开全局代理。    

> 安装在macos, macos m1, ubuntu, windows10通过，有其他安装问题可以查看[FAQ](doc/FAQ.md)，或留言。

>  后台运行可以 `nohup python run.py &`  然后通过托盘图标来开关         

>  注意！启动时加入share参数或修改了server_name可以开启公网访问，但目前没有加入多用户访问权限，把服务穿透到外网可能导致你的对话历史或其他信息泄露。所以目前版本最好还是个人部署本地使用，不要作为公开服务！   

---

### 测试连接

填写好openai的key，或完成一些代理配置后。可在`Ask`模块中，选择`default`知识库进行一次提问。如果能返回结果，表示和chatgpt连接正常。

> `default`表示不访问本地知识库，返回的是chatgpt的原始回答。   
> `review`模块在连接api成功后也可直接使用，不依赖创建本地知识库。  

---

### 创建知识库

- 可以参考 [创建你的一个知识库](doc/createhelp.md)

- 在大脑门儿中，一个向量仓库及它索引的文件夹，称为一个knowledge base。     

- 在`Config`标签`Create a new knowledge base`栏中，填写库名、索引文件夹路径、文件类型，即可创建一个knowledge base。

- 创建时只允许加入一个索引文件夹，但创建成功后可以在`Update`栏中添加更多的文件夹

- chunk size是将文件切片后嵌入的大小，如果你希望进行问答，切片大小1000-2000是合适的。超过2000容易突破gpt3.5-turbo的token限制。

> 例：我想用我的obsidian笔记构建一个知识库，笔记路径为 `~/obsidian/myvult` 
> 
> 1. 填写库名如: `mybase`
> 2. `~/obsidian/myvult`地址粘贴到 `Directory`文本框中
> 3. 文件类型选择`md`
> 4. 点击`Create`按钮

---

### 更新知识库

- 当索引文件夹内容有改动，在`Config`标签 `Update knowledge base`中`Load`已创建的知识库后。再点击`Update`按钮后开始检查改动情况并更新向量库
- 改变知识库的一些配置后，需要点击`Save base config`按钮
- 可以在这个地方为一个知识库增加更多的索引文件夹

> 例：我想继续把我的印象笔记也加入刚才创建的知识库中。
> 
> 1. 先使用印象笔记的导出功能把所有笔记用单个html的格式导出到任意文件夹比如`~/evernote` 中。
> 
> 2. 然后在`Add a new directory to current knowledge base`文本框中，填写`~/evernote`，类型选择`html`。 
> 
> 3. 点击 `Save base config`按钮。确认信息无误后，点击`Update`更新。

> 删除知识库: 在`bases`文件夹中直接删除对应的`base`文件

---

### 搜索 Search

搜索模块主要用于检索你的知识库。选择一个知识库，使用任意自然语言搜索你的库，将会找到相似的文档。支持浏览器中直接打开文档。

---

### 问答 Ask

- 一个chatbot，将访问你的知识库中的内容作为证据来来回答你问题
- 默认情况下会访问库中最相似的文档片段（docoment chunk）
- 可以增加answer depth让chatbot去参考更多相似文档
- 支持连续的问答

---

### 全文阅读 Review：

- 传入一份文档后即可针对该文档自由提问
- 和Ask不同的是，Review模块不仅仅参考向量相似性匹配的文档片段，而是完整的阅读全文后给出答案
- 全文速度较慢，但不会遗漏信息，威力巨大
- 适用于详细的总结分析一份长文档，或辅助阅读文献
- 由于token限制，Review模块取消了连续对话，仅对最近请求做出反应。所以每次提问都要清晰完整

![](doc/fig4.png)

##### 长文本阅读原理

> gpt3.5只支持4000个token，为了让一个用户问题可以完整浏览任意长度的全文后再做回答，在review模块中采取了循环阅读的方式。原理类似带记忆的循环神经网络，将长文本分割到2000以下的片段后，带着问题依次阅读每一个片段，得到的中间信息合并到下一个片段，直到读完全文。

---

### 开销

需要准备openai的key。入库（Embeding）和Search使用text-ada-002模型。Ask和Review使用gpt-3.5-turbo模型，这两个模型费用都很低。但如果你的知识库很庞大，仍需要留意入库的开销。另外，增加answer_depth和频繁的使用review功能也会根据本地文本的长度相应的增加开销。

---

### 配置

常用配置可以在config标签中设置
还有一些高级参数，不建议改动。如果需要可以在config.yaml文件中修改

| 参数名                             | 类型    | 说明                                                                         | 默认值   |
| ------------------------------- | ----- | -------------------------------------------------------------------------- | ----- |
| key                             | str   | 填写openai的key                                                               | ‘‘    |
| rate_limit                      | int   | 由于openai有请求速率限制，在创建向量仓库时候如果短时间有大量请求，很容易被限制访问。1表示发送一个请求后休息1秒。只在创建和更新知识库时生效。 | 1     |
| proxy                           | str   | 可在请求openai api时启用代理。填写你的http代理地址，比如："http://127.0.0.1:1087"                | ‘‘    |
| search_topk                     | int   | 作用于Search模块。搜索返回的结果数。                                                      | 20    |
| result_size                     | int   | 作用于Search模块。预览文字的长度。                                                       | 300   |
| answer_depth                    | int:  | 作用于Ask模块，chabot在回答时，访问本地文档片段的最大数量。默认1表示只会访问最相似的一个片段。                       | 1     |
| max_context                     | int   | 作用于Ask模块。上下文最大token值。                                                      | 1000  |
| max_l2                          | float | 作用于Ask模块。匹配相似本地片段时允许的最大L2距离。                                               | 0.4   |
| HyDE                            | bool  | 作用于ASK模块。chatbot在匹配本地文档前，根据你的问题预先用chatgpt生成一个初步回答后再匹配。可增加准确性，但也会增加一点开销。    | false |
| review_chunk_size               | int   | 作用于Review模块。对长文本分割时每块的最大token值。                                            | 2000  |
| review_chunk_overlap            | int   | 作用于Review模块。长文本分割时重叠的token数。                                               | 50    |
| enable_search/ask/review/config | bool  | 启用各个模块。false可以隐藏模块。                                                        | true  |

---

### 主要第三方依赖

- 语言模型：ChatGPT
- 文本拆分：LangChain
- 向量储存：Faiss
- Web界面：Gradio

### 后续计划

- google或wiki搜索作为联网知识库

- 打包

- 用户prompt模板管理

- 多用户权限

大脑门定位主要是通过本地知识库增强GPT的后端服务。web前端将在基本功能完成后分离，另用桌面端接入，以更好的和系统集成改善交互性。
