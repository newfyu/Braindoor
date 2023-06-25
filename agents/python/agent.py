import re
import subprocess
import json
import distutils.spawn
import yaml
import os

PYTHON_PATH = ""
cwd = os.path.abspath(os.path.dirname(__file__))

# 查找系统python目录
def find_python_interpreter():
    python_executable = distutils.spawn.find_executable("python")
    if python_executable:
        return python_executable
    else:
        python3_executable = distutils.spawn.find_executable("python3")
        if python3_executable:
            return python3_executable
        else:
            return None

# 从当前目录下读取config.yaml,如果值为空则使用find_python_interpreter查找系统python
config_path = os.path.join(cwd, "config.yaml")
with open(config_path, 'r') as stream:
    try:
        agent_config = yaml.safe_load(stream)
        PYTHON_PATH = agent_config.get('python_path', "")
        if PYTHON_PATH == "" or PYTHON_PATH == None:
            PYTHON_PATH = find_python_interpreter()
    except yaml.YAMLError as exc:
        PYTHON_PATH = find_python_interpreter()


gen_applescript_function = {
  "name": "gen_python",
  "description": "Use python code to complete the user request.",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "python code for user request. If ~ is involved in the path provided by the user, please expand it with os.path.expanduser.",
      },
      "file": {
        "type": "string",
        "description": "If Python code processes and saves a file, output the complete absolute path of the saved file",
      },
      "image": {
        "type": "string",
        "description": "If Python code uses libraries such as PIL, opencv, matplotlib, seaborn, etc. to output an image, use plt.show output",
      },
    },
    "required": ["code"]
  }
}



class Agent:
    def __init__(self):
        self.name = "python"
        self.description = "生成和运行python脚本"
        
    def run(self, question, context, mygpt, model_config_yaml, **kwarg):

        if PYTHON_PATH == None:
            answer = f"未找到python解释器,请在配置文件`{config_path}`中指定路径"
            return question, answer, [], ""

        pattern = r"```python(.*?)```"
        # 是否运行脚本判断
        if len(context)>0:
            pre_answer = context[-1][1]
            matches = re.findall(pattern, pre_answer, re.DOTALL)
            if len(matches) == 1:
                if "y" in question.lower():
                    answer = "已执行"
                    matches = re.findall(pattern, pre_answer, re.DOTALL)
                    answer = self.run_script(matches[0])
                    return question, answer, [], ""
                elif "n" in question.lower():
                    answer = "取消执行"
                    return question, answer, [], ""
        
        # 响应用户请求，生成脚本
        prompt = f"""
        user request:{question}
Write python code to complete the above user request.
If output a pandas DataFrame, you should convert to markdown format
All results must be output using the print function, even on the last line of the code
"""
        
        out = mygpt.llm(prompt, 
                        context=context,
                        format_fn = lambda x: f"```json\n{x}\n```",
                        functions=[gen_applescript_function],
                        function_call= {"name": "gen_python"})

        # 后处理,格式化输出
        out_obj = json.loads(out)
        code = out_obj['code']

        out = f"""```python
{code}
```"""
        # 判断out_obj是否有file和image
        if 'file' in out_obj.keys():
            file = out_obj['file']
            out = out + f"  \n文件已保存至{file}"
        if 'image' in out_obj.keys():
            image = out_obj['image']
            out = out + f"  \n图片已保存至{image}"

        matches = re.findall(pattern, out, re.DOTALL)
        if len(matches) == 1: 
            answer = out + "  \n" + f"当前解释器:  \n```bash\n{PYTHON_PATH}\n```  \n" + "是否执行脚本(y/n)"
        else:
            answer = out + "  \n" + "生成的代码似乎有问题，建议重新生成"
        
        return question, answer, [], ""

    def run_script(self, code):
        process = subprocess.Popen([PYTHON_PATH, '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            # 设置超时时间为5秒
            stdout, stderr = process.communicate(code, timeout=60)
            #  print(stdout)
            return "已执行  \n" + stdout + stderr
        except subprocess.TimeoutExpired:
            process.kill()  # 杀掉子进程
            stdout, stderr = process.communicate()
            return stderr
