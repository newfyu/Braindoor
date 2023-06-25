import json
import yaml
import os

CWD = os.path.abspath(os.path.dirname(__file__))
HOME = os.path.expanduser('~')
HOME = os.path.join(HOME, "braindoor")

def get_all_agent_description():
    agents_root = os.path.join(HOME, "agents")
    agent_description = []
    for agent in os.listdir(agents_root):
        if agent == "autotag":
            continue
        config_path = os.path.join(agents_root, agent, "config.yaml")
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                config = yaml.load(f, Loader=yaml.FullLoader)
                if "description" in config.keys():
                    agent_description.append({agent: config["description"]})
                else:
                    agent_description.append({agent: ""})
    return agent_description

def get_all_base_description():
    bases_root = os.path.join(HOME, "bases")
    if not os.path.exists(bases_root):
        return []
    base_description = []
    for base in os.listdir(bases_root):
        base_path = os.path.join(bases_root, base)
        if os.path.isfile(base_path) and base.endswith(".base"):
            base_description.append({base[:-5]: f"在本地知识库{base[:-5]}中搜索信息"})
    return base_description

all_tag_description = {}
for dictionary in get_all_agent_description() + get_all_base_description():
    all_tag_description.update(dictionary)

select_tag_function = {
  "name": "select_tag",
    "description": f"A represents a tool in a toolset. B represents something to do. If the user's request is 'use A to do B ', 'do B on A'. and A is in toolset. You need to separate A and B.\ntoolset:```{all_tag_description}```\nIf A is not explicitly mentioned in the user request, but selecting A according to the description of the toolset can help solve B, then A can also be chosen",
  "parameters": {
    "type": "object",
    "properties": {
      "A": {
        "type": "string",
        "description": "output A, want to use something.",
        "enum":list(all_tag_description.keys())
      },
      "B":{
          "type":"string",
          "description": "output B, 即'use A to do B'中的B",
      }
    },
    "required": ["A","B"]
  }
}

class Agent:
    def __init__(self):
        self.name = "autotag"
        self.description = "根据用户请求自动选择合适的etag"
        
    def run(self, question, context, mygpt, model_config_yaml, base_name, agent_tags, **kwarg):

        # 去掉#autotag
        question = question.replace("#autotag", "").strip()

        out = mygpt.llm(
            question,
            functions=[select_tag_function])

        # 判断out是否可以转为一个json，并且有tag字段
        try:
            out = json.loads(out)
            suggested_tag = out["A"]
            question = out["B"]
        except:
            suggested_tag = None

        if suggested_tag:
            info = f"<frontslot>自动选择标签：#{suggested_tag}</frontslot>"
            question = question + f"  \n#{suggested_tag}"
            question, answer, mydocs, draft = mygpt.ask(question, context, base_name) 
            answer = info + answer
            return question, answer, mydocs, draft
        else:
            answer = out

        
        return question, answer, [], ""
