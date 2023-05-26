import re
import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import wikipedia


class Agent:
    def __init__(self):
        self.name = 'wikipedia'
        self.description = "根据问题在wikipedia上查找合适的词条后回答用户问题，只从summary中获取上下文，不深入wiki页面内部"
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):
        
        prompt_search_key = f"""
question：```{question}```
Your task is to convert question into a keyword for wiki search
question is delimited with triple backticks above
Ignore the language used in the question itself
If the problem is related to Chinese knowledge, return the language code 'zh'; otherwise, return 'en'
Provide the output in JSON format with the following keys: "key", "lang"
"""
        
        # 提取搜索关键词
        search_key = mygpt.llm(prompt_search_key, model_config_yaml = "chatgpt_t0", format_fn=lambda x:f"生成查询词：{x}")
        search_key = re.findall(r'\{[\s\S]*?\}', search_key)[0]
        search_obj = eval(search_key)

        # 得到wikipedia搜索结果
        mygpt.temp_result += '\n\n正在获取搜索结果...'
        wikipedia.set_lang(search_obj['lang'])
        search_result = wikipedia.search(search_obj['key'])
        
        # 分析搜索结果，回答用户问题
        
        prompt_get_page = f"""
search result:```{search_result}```
The search result is a list that stores some wiki pages
Your task is to determine which page's content should be most suitable for answering questions: qustion:```{question}```
Use JSON format to output the most suitable page name with the following key: 'page_name'
The page name should be completely consistent with the search result
"""
        
        page_name = mygpt.llm(prompt_get_page, model_config_yaml = "chatgpt_t0")
        page_name   = re.findall(r'\{[\s\S]*?\}', page_name)[0]
        page_name  = eval(page_name)
        page_name_str = page_name['page_name']
        if search_obj['lang'] == 'zh':
            page_name_str = page_name_str.replace(' ', '')

        # 获取回答
        summary = wikipedia.summary(page_name_str)
        prompt_answer = f"""
summary:```{summary}```
Your task is to answer the following questions based on the summary above
question: ```{question}```
you must use the same language or the language requested by the question to answer
"""
        answer = mygpt.llm(prompt_answer, model_config_yaml = "chatgpt_t0")
        ny = wikipedia.page(page_name_str)

        # 后处理
        source = f'详细内容查看：<a href="{ny.url}">{page_name_str}</a><br>'
        rearslot =  "<rearslot>" + source + "</rearslot>"
        answer = answer + rearslot
        return question, answer, [], ""


