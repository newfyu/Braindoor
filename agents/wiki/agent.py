# 插件的入口文件，必须实现Agent类，文件名必须是agent.py
# agent.py文件放置在"用户文件夹/brainoor/agents"目录下的一个文件夹，文件夹名字就是插件名
# 插件名不能和已有插件重复，也不能和系统保留的插件名重复
import re
import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
# agent中如果要引入python第三方的包，如wikipedia，要在上面语句之后import
# 同时还要把这个包复制到agent目录下
import wikipedia

class Agent: # 实现这个类，类名必须是Agent
    def __init__(self):
        self.name = 'wikipedia' # agent的名字，任意
        self.description = "根据问题在wikipedia上查找合适的词条后回答用户问题，只从summary中获取上下文，不深入wiki页面内部" # agent的描述，以后会用于模型自动选择agent
        self.model_config = "../agents/wiki/chatgpt-t0" # 可以在agent的目录下放一个该agent专用的模型配置文件。因为模型默认是在models文件下查找配置文件。如果要在agents目录下查找，需要返回上一级后再进入当前agent的目录
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):
        # 实现这个方法，即插件运行的逻辑
        # question是用户的输入，字符串类型，会自动传入
        # context是对话的上下文，列表类型，会自动传入
        # mygpt是核心对象，这儿主要是调用mygpt.llm方法来生成回答
        # model_config_yaml是一个字符串，指定了当前模型的配置文件，可以用来区分不同模型
        # 以上是应用会自动传入的参数, 下面就是自己去实现逻辑了
        
        prompt_search_key = f"""
question：```{question}```
Your task is to convert question into a keyword for wiki search
question is delimited with triple backticks above
Ignore the language used in the question itself
If the problem is related to Chinese knowledge, return the language code 'zh'; otherwise, return 'en'
Provide the output in JSON format with the following keys: "key", "lang"
"""
        
        # 写一个prompt,然后把这个prompt传给mygpt.llm方法，就可以得到模型生成的回答了,此处用来提取搜索关键词
        # chatgpt_t0是一个预定义的语言模型配置，就是温度为0的chatgpt
        # llm在生成过程中，会在用户界面流式显示生成过程
        # format_fn 是用来对输出的中间过程格式化，用于在用户界面实时的显示时改变格式,非必须
        search_key = mygpt.llm(prompt_search_key, model_config_yaml = self.model_config, format_fn=lambda x:f"生成查询词：{x}")


        # prompt指定了模型用json输出我们需要的结果，下面是提取json
        search_key = re.findall(r'\{[\s\S]*?\}', search_key)[0]
        search_obj = eval(search_key) # 用eval提取json其实是有风险的，但比json.loads兼容性更好,自己考量风险

        # 得到wikipedia搜索结果
        mygpt.temp_result += '\n\n正在获取搜索结果...' # temp_result属性用来在用户界面输出中间过程
        wikipedia.set_lang(search_obj['lang'])
        # 用wikipedia包获取在wiki上的搜索结果
        search_result = wikipedia.search(search_obj['key'])
        
        # 然后需要分析返回的搜索结果，选择最合适的页面读取
        prompt_get_page = f"""
search result:```{search_result}```
The search result is a list that stores some wiki pages
Your task is to determine which page's content should be most suitable for answering questions: qustion:```{question}```
Use JSON format to output the most suitable page name with the following key: 'page_name'
The page name should be completely consistent with the search result
"""
        
        # 仍然是同样的逻辑，包装prompt后传给模型，得到模型生成的回答，仍然是用json输出方便提取,这一步主要是判断哪个搜索结果最合适
        page_name = mygpt.llm(prompt_get_page, model_config_yaml = self.model_config)
        page_name   = re.findall(r'\{[\s\S]*?\}', page_name)[0]
        page_name  = eval(page_name)
        page_name_str = page_name['page_name']
        if search_obj['lang'] == 'zh':
            page_name_str = page_name_str.replace(' ', '')

        # 根据最合适的搜索结果去获取summary。也能获取完整内容，但token太长。用chatgpt基本上会超过限制。当然也可以不使用mygpt.llm, 而使用mygpt.review这个方法来分析内容，这个方法可以处理任意长的文字。或则自己预处理文字的长度
        summary = wikipedia.summary(page_name_str)
        prompt_answer = f"""
summary:```{summary}```
Your task is to answer the following questions based on the summary above
question: ```{question}```
you must use the same language or the language requested by the question to answer
"""
        answer = mygpt.llm(prompt_answer, model_config_yaml = self.model_config)
        ny = wikipedia.page(page_name_str)

        # 后处理,把最后的结果调整一下格式,返回给应用
        # 用户界面默认对输出结果是按markdown格式解析的
        # 如果你要显示一些html内容，用<rearslot>或<frontslot>包裹起来，就会按html格式解析
        source = f'详细内容查看：<a href="{ny.url}">{page_name_str}</a><br>'
        rearslot =  "<rearslot>" + source + "</rearslot>"
        answer = answer + rearslot

        # 必须返回这四个值，第一个是问题，第二个是回答，第三个本地知识库文档，第四个是预回答。本地文档和预回答在这个agent中没有使用，可以为空
        return question, answer, [], ""


