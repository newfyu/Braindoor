class MagicTag(object):
    def __init__(self):
        self.tag = "润色"
        self.discription = "用于学术文章的润色"

    # 在进入模型前执行
    def before_llm(self, text):
        text = f"""I would like to engage your services as an academic writing consultant to improve my writing. 
I will provide you with text that requires refinement, and you will enhance it with more academic language and sentence structures.
The essence of the text should remain unaltered, including any LaTeX commands. 
I request that you provide only the improved version of the text without any further explanations.
The following paragraphs are the text that needs improvement:

{text}"""
        return text

    # 在模型返回结果后执行
    def after_llm(self, text):
        return text
