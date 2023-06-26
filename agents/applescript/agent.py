import re
import subprocess
import json
import os

CWD = os.path.abspath(os.path.dirname(__file__))

gen_applescript_function = {
  "name": "gen_applescript",
  "description": "Use applescript to complete user request.Do not use markdown code block tag.",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "applescript code for user request",
      },
    },
    "required": ["code"]
  }
}


class Agent:
    def __init__(self):
        self.name = "applescript"
        self.description = "生成和运行applescript脚本"
        self.model_config = os.path.join(CWD, "model.yaml") # 可以在agent的目录下放一个该agent专用的模型配置文件。
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):

        pattern = r"```applescript(.*?)```"
        # 是否运行脚本判断
        if len(context)>0:
            pre_answer = context[-1][1]
            matches = re.findall(pattern, pre_answer, re.DOTALL)
            if len(matches) == 1:
                if "y" in question.lower():
                    answer = "已执行  \n"
                    pattern = r"```applescript(.*?)```"
                    answer += self.run_script(matches[0])
                    return question, answer, [], ""
                elif "n" in question.lower():
                    answer = "取消执行"
                    return question, answer, [], ""
        
        # 响应用户请求，生成脚本
        prompt = f"""user request:{question}"""

        #现在需要把context中所有```和```之间的内容替换为空,否则会影响生成的代码
        pattern2 = r"```.*?```"
        for i in range(len(context)):
            context[i] = (re.sub(pattern2, "", context[i][0], flags=re.DOTALL), re.sub(pattern2, "", context[i][1], flags=re.DOTALL))
        
        out = mygpt.llm(prompt, 
                        context=context,
                        model_config_yaml = self.model_config, 
                        functions=[gen_applescript_function],
                        function_call= {"name": "gen_applescript"})

        # 后处理,格式化输出
        out_obj = json.loads(out)
        code = out_obj['code']

        out = f"""```applescript
{code}
```"""

        matches = re.findall(pattern, out, re.DOTALL)
        if len(matches) == 1: 
            answer = out + "  \n" + "是否执行脚本(y/n)"
        else:
            answer = out + "  \n" + "生成的代码似乎有问题，建议重新生成"
        
        return question, answer, [], ""

    def run_script(self, script):
        try:
          return subprocess.check_output(['osascript', '-e', script]).decode("utf-8")
        except subprocess.CalledProcessError as e:
          return e.output.decode("utf-8")

