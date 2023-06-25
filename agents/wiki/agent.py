# 插件的入口文件，必须实现Agent类，文件名必须是agent.py
# agent.py文件放置在"用户文件夹/brainoor/agents"目录下的一个文件夹，文件夹名字就是插件名
# 插件名不能和已有插件重复，也不能和系统保留的插件名重复
import re
import os
import sys
import json
CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)
# agent中如果要引入python第三方的包，如wikipedia，要在上面语句之后import
# 同时还要把这个包复制到对应agent目录下
import wikipedia

# 用于function_call
search_function = {
  "name": "get_keyword",
  "description": "Your task is to convert user question into a keyword for wiki search",
  "parameters": {
    "type": "object",
    "properties": {
      "key": {
        "type": "array",
        "description": "keyword for wikipedia search, separate with spaces",
        "items":{"type":"string"}
      },
      "lang": {
      "type": "string",
      "description": "Set the language for Wikipedia search, Ignore the language used in the question itself. If the user question is related to Chinese knowledge, return 'zh'; otherwise, return 'en'",
      "enum":["zh","en"]
      },
    },
    "required": ["key","lang"]
  }
}

read_function = {
    "name": "get_page",
    "description": "read search result and select a page for user question",
    "parameters": {
        "type": "object",
        "properties": {
          "page_name": {
            "type": "string",
            "description": "which page's content should be most suitable for answering user question, return one page name, the page name should be completely consistent with the search result",
        },
        },
        "required": ["page_name"]
      }
}





class Agent: # 实现这个类，类名必须是Agent
    def __init__(self):
        self.name = 'wikipedia' # agent的名字，任意
        self.description = "根据问题在wikipedia上查找合适的词条后回答用户问题，只从summary中获取上下文，不深入wiki页面内部" # agent的描述，以后会用于模型自动选择agent
        self.model_config = os.path.join(CWD,"chatgpt-t0") # 可以在agent的目录下放一个该agent专用的模型配置文件。
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):
        # 实现这个方法，完成插件或智能体的运行逻辑
        # question是用户的输入，字符串类型，自动传入
        # context是对话的上下文，列表类型，自动传入, 此处我们不需要上下文
        # mygpt是核心对象，这儿主要是调用mygpt.llm方法来生成回答。另有mygpt.review方法用于长文本问答。mygpt.ask方法用于完整问答，可以识别扩展标签。
        # model_config_yaml是一个字符串，指定了当前模型的配置文件，可以用来调用不同模型
        
        prompt_search_key = f"""user question：```{question}```"""
        # 写一个prompt,然后把这个prompt传给mygpt.llm方法，就可以得到模型生成的回答了,此处用来提取搜索关键词
        # chatgpt_t0是一个预定义的语言模型配置，就是温度为0的chatgpt
        # llm在生成过程中，会在用户界面流式显示生成过程
        # format_fn 是用来对输出的中间过程格式化，用于流式输出时改变格式,非必须
        search_key = mygpt.llm(
            prompt_search_key, 
            model_config_yaml = self.model_config, 
            format_fn=lambda x:f"生成查询词：{x}",
            functions=[search_function],
            function_call = {"name": "get_keyword"},  
        )


        # 得到结果后，由于使用了function_call，所以返回的是json字符串，需要提取json
        search_obj = json.loads(search_key)
        search_obj['key'] = " ".join(search_obj['key'])

        # 得到wikipedia搜索结果
        mygpt.temp_result += '\n\n正在获取搜索结果...' # temp_result属性用来在用户界面输出任意信息
        wikipedia.set_lang(search_obj['lang'])
        # 用wikipedia包获取在wiki上的搜索结果
        search_result = wikipedia.search(search_obj['key'])
        
        # 然后需要分析返回的搜索结果，选择最合适的页面读取
        prompt_get_page = f"""
search result:```{search_result}```
user qustion:```{question}```
"""
        
        # 仍然是同样的逻辑，包装prompt后传给模型，得到模型生成的回答，这一步主要是判断哪个搜索结果最合适
        page_name = mygpt.llm(
            prompt_get_page, 
            model_config_yaml = self.model_config,
            functions=[read_function],
            function_call = {"name": "get_page"},  
            
        )
        page_name  = json.loads(page_name)
        page_name_str = page_name['page_name']
        if search_obj['lang'] == 'zh':
            page_name_str = page_name_str.replace(' ', '')

        # 根据最合适的搜索结果去获取summary。
        summary = wikipedia.summary(page_name_str)
        prompt_answer = f"""
summary:```{summary}```
Your task is to answer the following questions based on the summary above
question: ```{question}```
you must use the same language or the language requested by the question to answer
"""
        answer = mygpt.llm(prompt_answer, model_config_yaml = self.model_config)
        ny = wikipedia.page(page_name_str)

        # 后处理,把最后的结果调整一下格式,返回给用户界面
        # 用户界面默认对输出结果是按markdown格式解析的
        # 如果你要渲染一些html内容，用<rearslot>或<frontslot>包裹起来，就会按html格式解析
        source = f'详细内容查看：<a href="{ny.url}">{page_name_str}</a><br>'
        rearslot =  "<rearslot>" + source + "</rearslot>"
        answer = answer + rearslot

        # 必须返回这四个值，第一个是问题，第二个是回答，第三个本地知识库文档，第四个是预回答。本地文档和预回答在这个插件中没有使用，可以为空
        return question, answer, [], ""
