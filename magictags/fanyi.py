class MagicTag(object):
    def __init__(self):
        self.name = "fanyi"
        self.tag = "翻译"
        self.discription = "用于把中文翻译成英文"

    # 在进入模型前执行
    def before_llm(self, text):
        text = f"""翻译以下文字为中文：
{text}"""
        return text

    # 在模型返回结果后执行
    def after_llm(self, text):
        return text
