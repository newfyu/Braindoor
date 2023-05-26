import requests
import json
import re


class Agent:
    def __init__(self):
        pass
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):
        
        prompt_search_key = f"""
Convert the following question into relevant search keywords for Google
question：```{question}```
Provide the output in JSON format with the following keys: "q"
"""
        
        # 提取搜索关键词
        search_key = mygpt.llm(prompt_search_key, model_config_yaml = "chatgpt_t0", format_fn=lambda x:f"生成关键词：{x}")
        search_key = re.findall(r'\{[\s\S]*?\}', search_key)[0]
        search_obj = eval(search_key)

        # 得到google搜索结果
        mygpt.temp_result += '\n\n正在获取搜索结果...'
        url = "https://google.serper.dev/search"
        payload = json.dumps(search_obj)
        headers = {
          'X-API-KEY': '7f69a023e4f07552f4f4179c0fd1061a1f812908',
          'Content-Type': 'application/json'
        }
        search_result = requests.request("POST", url, headers=headers, data=payload).text
        search_result_dict = json.loads(search_result)['organic']
        search_result_text = [{k:v for k,v in dic.items() if (k != 'link') and (k != 'sitelinks')} for dic in search_result_dict]
        
        # 分析搜索结果，回答用户问题
        
        prompt_link = f"""
first analysis what language is used in the user question delimited with triple backticks. Then use the same language or the language requested by the user question to answer the following two questions
Output all result in JSON format

search results:```{search_result_text}```
user question: ```{question}```

1. Read the search results, answer the user question as detailed as possible. json key: 'answer'
2. Which search results were used to answer user questions, represented by corresponding positions. json key: 'position'
2. If you are unable to answer the question based on the search results, output the new keyword you suggest. json key: 'new key'

Output all result in JSON format with the following keys: :
"answer","position", "newkey"
"""     
        
        out = mygpt.llm(prompt_link, model_config_yaml = "chatgpt_t0", format_fn=lambda x:f"正在生成答案：{x}")

        # 后处理
        out_obj = eval(re.findall(r'\{[\s\S]*?\}', out)[0])
        position = out_obj['position']
        answer = out_obj['answer']
        search_result = eval(search_result)

        newkey = ""
        if 'newkey' in out_obj.keys():
            if len(out_obj['newkey'])>0:
                newkey = f"<br>结果如果不理想，可以尝试搜索关键词：{out_obj['newkey']}"
        
        links = []
        for i,p in enumerate(position):
            s = search_result['organic'][int(int(p)-1)]
            if 'link' in s.keys():
                _link= s['link']
            if 'title' in s.keys():
                _title = s['title']
                if len(_title)>20:
                    _title = _title[:20]
            links.append(f'<a href="{_link} title="{_link}">{[i]} {_title}...</a><br>')
        
        links = "".join(links)
        
        frontslot = "<frontslot>" + "关键词：" +str(search_obj['q'])+ "</frontslot>"
        rearslot =  "<rearslot>" + links + newkey + "</rearslot>"

        answer = frontslot + answer + rearslot
        return question, answer, [], ""

