# 🧠  Braindoor

[中文](../README.md) | English

## Overview

Braindoor can easily use local files to build ChatGPT's external knowledge base. Support natural language search, Q&A and full text analysis of local documents.

![](doc/fig1.png)

### Use Cases

- Search personal documents or notes with natural language
- Build a domain-specific question answering robot using local text
- Use chatgpt to analyze and answer long text

### Features

- Flexible construction of local knowledge base. Support  txt, md, html, pdf, docx
- Incremental update
- Provides a Web UI. Documents referenced by Search module or Ask module can be opened directly in the browser.
- Full-text deep review

----

### Installation and launch

1、Create a python3.9 conda virtual environment

```shell
conda create -n braindoor python=3.9
```

2、Install dependent packages

```shell
conda activate braindoor
git clone https://github.com/newfyu/Braindoor.git
cd Braindoor
pip install -r requirements.txt
```

3、launch

```shell
python app.py
```

Open "127.0.0.1:7086" in browser and configure your openai key in the Config TAB to work!  

---

### Create a new knowledge base

在大脑门儿中，一个向量仓库及它索引的文件夹中的文件，称为一个knowledge base。     
在Config --> Create a new knowledge base中，填写库名和一个本地文件夹路径，文件类型即可创建一个knowledge base。创建时只允许加入一个文件夹，但创建成功后可以在update中添加更多的文件夹。chunk size是将文件切片后嵌入的大小，如果你希望进行问答，切片大小1000-2000是合适的。超过2000容易突破gpt3.5-turbo的token限制。

> 例：假设我有一个obidian笔记仓库，路径为 `~/obsidian/myvult`。 
> 
> 1. 先填写一个知识库名如: "mybase“
> 2. obsidian地址粘贴到 “Directory“中
> 3. 文件类型选择"md"和“txt“
> 4. 然后点击Create按钮

---

### Update existing knowledge base

- When the contents of the indexed folder have changed, click the update button to check the changes and update the vector store.
- After changing some configurations of the knowledge base, you need to click the "Save base config" button
- You can add more index folders for a knowledge base

> 例：我想把我的印象笔记也加入知识库中。先使用印象笔记的导出功能把所有笔记用单个html的形式导出到文件夹`~/evernote` 中。在“Add a new directory to current knowledge base”文本框中，填写`~/evernote`，类型选择`html`。 然后点击 "Save base config"按钮。确认信息无误后，点击“Update"更新。

> Delete a knowledge base: directly delete the corresponding. base file in the bases folder

---

### Search

The search module is used to retrieve your knowledge base. Select a knowledge base and search in any natural language to find similar documents. It supports opening documents directly in the browser.

![](doc/fig2.png)

---

### Ask

- Ask module is a chatbot, which will use the content in your knowledge base as evidence to answer your questions
- By default, the most similar document chunk in the base is referenced
- You can increase the answer depth to allow chatbot to refer to more similar documents
- Support continuous Q & A, but reopen the dialogue on different topics as much as possible
  ![](/doc/fig3.png)

> "Default" means that the local knowledge base is not used, and the original answer of chatgpt is returned.

---

### Review

- After passing in a document, you can freely ask questions about the document
- Unlike Ask, the Review chatbot will not only refer to the document chunk matched by vector similarity, but will read the full text for each question and give the answer
- Full text reading does not omit information, which is slow but powerful
- It is suitable for detailed summary and analysis of a long document or auxiliary reading of literature
- 

![](doc/fig4.png)

> Due to token restrictions, Review canceled the contact context dialog and only responded to the latest request. So every question should be clear and complete

---

### 开销

The openai key needs to be prepared. The text-ada-001 model is used for create vector store and Search. Ask module use the gpt-3.5-turbo model, both of which cost very little. But be aware, if you have a large knowledge base, be aware of the cost of access. In addition, increasing answer_depth value and frequent use of Review can add overhead depending on the length of the local text.

---

### Configuration

General configuration can be set in the config tab
There are some advanced parameters, which are not recommended to be changed. Modify it in the config.yaml file if necessary

| 参数名                  | 类型    | 说明                                                                                                                                                                                                                          | 默认值   |
| -------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| key                  | str   | Fill in your openai key                                                                                                                                                                                                     | ‘‘    |
| rate_limit           | int   | Because openai has a request rate limit, it is easy to restrict access when creating a vector warehouse. 1 means to rest for 1 second after sending a request. It only works when creating and updating the knowledge base. | 1     |
| proxy                | str   | The proxy can be enabled when the openai api is requested. Enter your http proxy address, for example: "http://127.0.0.1:1087"                                                                                              | ‘‘    |
| search_topk          | int   | Applies to the Search module. The number of results returned by the search.                                                                                                                                                 | 20    |
| result_size          | int   | Applies to the Search module. Preview the length of the text.                                                                                                                                                               | 300   |
| answer_depth         | int:  | For Ask. chabot answers with reference to the maximum number of local document chunk.                                                                                                                                       | 1     |
| max_context          | int   | For Ask. The maximum token value of the context.                                                                                                                                                                            | 1000  |
| max_l2               | float | 作用于Ask模块。搜索相似本地片段时允许的最大L2距离。                                                                                                                                                                                                | 0.4   |
| HyDE                 | bool  | 作用于ASK模块。chatbot在参考本地文档前，根据你的问题预先用chatgpt生成一个初步回答，然后再匹配相似的本地文档。会增加准确性，但也会增加一点开销。                                                                                                                                            | false |
| review_chunk_size    | int   | 作用于Review模块，对传入的长文本切片时每块的最大token值。                                                                                                                                                                                          | 2000  |
| review_chunk_overlap | int   | 作用于Review模块，对传入的长文本切片时重叠的token值。                                                                                                                                                                                            | 50    |

---

### Main third-party dependencies

- Language model: chatgpt
- Text splitting: langchain
- Vector stores: faiss
- Web interface: gradio
