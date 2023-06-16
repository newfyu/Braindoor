import requests
import json
import re

SERPER_API_KEY = "7f69a023e4f07552f4f4179c0fd1061a1f812908"

search_function = {
  "name": "get_keyword",
  "description": "Translate users' questions into keywords suitable for Google search",
  "parameters": {
    "type": "object",
    "properties": {
      "q": {
        "type": "array",
        "description": "keyword for search, separate with spaces",
        "items":{"type":"string"}
      },
    },
    "required": ["q"]
  }
}

read_function = {
  "name": "read_and_answer_search_result",
  "description": "Read the search results and answer the questions in the parameters below",
  "parameters": {
    "type": "object",
    "properties": {
      "answer": {
        "type": "string",
        "description": "Answer user questions in detail based on search results"
      },
      "position": {
        "type": "array",
        "description": "Which search results were used to answer user questions, represented by corresponding positions.",
        "items":{"type":"number"}
      },
      "new key":{
        "type": "array",
        "description":"If you are unable to answer the question based on the search results, output the new search keyword you suggest.",
        "items":{"type":"string"}
      }
    },
    "required": ["answer"]
  }
}

class Agent:
    def __init__(self):
        self.name = "google_search"
        self.description = "轻量级google搜索插件，调用google搜索引擎，回答用户问题。仅读取搜索的摘要，不深入获取网页内容"
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):
        
        prompt_search_key = f"""user question：```{question}```"""
        
        # 提取搜索关键词
        search_key = mygpt.llm(
            prompt_search_key, 
            model_config_yaml = "../agents/google_search/chatgpt-t0", 
            format_fn=lambda x:f"生成关键词：{x}",
            functions=[search_function],
            function_call = {"name": "get_keyword"},  
        )
        search_obj = eval(search_key)
        search_obj["q"] = " ".join(search_obj["q"])

        # 得到google搜索结果
        mygpt.temp_result += '\n\n正在获取搜索结果...'
        url = "https://google.serper.dev/search"
        payload = json.dumps(search_obj)
        headers = {
          'X-API-KEY': SERPER_API_KEY,
          'Content-Type': 'application/json'
        }
        search_result = requests.request("POST", url, headers=headers, data=payload).text
        search_result_dict = json.loads(search_result)['organic']
        search_result_text = [{k:v for k,v in dic.items() if (k != 'link') and (k != 'sitelinks')} for dic in search_result_dict]
        
        # 分析搜索结果，回答用户问题
        prompt_link = prompt_link = f"""
search results:```{search_result_text}```
user question: ```{question}```
"""
        
        out = mygpt.llm(
            prompt_link, 
            model_config_yaml = "../agents/google_search/chatgpt-t0", 
            format_fn=lambda x:f"正在生成答案：{x}",
            functions=[read_function],
            function_call= {"name": "read_and_answer_search_result"},
        )

        # 后处理,格式化输出
        out_obj = eval(out)
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
            links.append(f'<a href="{_link}">{[i+1]} {_title}...</a><br>')
        
        links = "".join(links)
        
        frontslot = "<frontslot>" + "关键词：" +str(search_obj['q'])+ "</frontslot>"
        rearslot =  "<rearslot>" + links + newkey + "</rearslot>"

        answer = frontslot + answer + rearslot
        return question, answer, [], ""

