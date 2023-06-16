from pathlib import Path
import openai
import backoff
import os
import sys
import importlib

import yaml
from yaml.loader import SafeLoader
from utils import logger, tiktoken_encoder, TokenSplitter

from update_base import load_base
from langchain.embeddings import OpenAIEmbeddings
from functools import partial
from create_base import token_len
import pandas as pd
import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"), "braindoor/")
config_path = os.path.join(USER, "config.yaml")
prompt_path = os.path.join(USER, "prompts")
model_path = os.path.join(USER, "models")
agent_path = os.path.join(USER, "agents")


class Result:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata

class AbortRetryException(Exception):
    pass

class MyGPT:
    def __init__(self, config_path=config_path):
        self.temp_result = ""
        self.load_config(config_path)
        self.bases_root = self.opt["bases_root"]
        self.bases_root = os.path.join(USER, self.bases_root)
        self.bases = dict()
        base_paths = list(Path(self.bases_root).glob("*.base"))
        self.load_base(base_paths)
        self.prompt_etags = self.load_prompt_etags()
        self.model_etags = self.load_model_etags()
        self.agent_etags = self.load_agent_etags()
        self.abort_msg = False
        self.stop_retry = False
        self.stop_review = False
        self.all_etags = self.load_etag_list()

        openai.api_key = self.opt["key"]
        if self.opt["key"]:
            self.base_embedding = OpenAIEmbeddings(openai_api_key=self.opt["key"])

        self.engine = self.opt["review_chunk_size"] = 8000 # 暂时写死一下
        self.fulltext_splitter = TokenSplitter(
            chunk_size=self.opt["review_chunk_size"],
            chunk_overlap=self.opt["review_chunk_overlap"],
            len_fn=partial(token_len, encoder=tiktoken_encoder),
        )

    def load_prompt_etags(self):
        prompt_files = list(Path(prompt_path).glob("*.yaml"))
        prompt_etags = dict()
        for prompt_file in prompt_files:
            with open(prompt_file, "r", encoding="utf-8") as file:
                data = yaml.load(file, Loader=yaml.FullLoader)
                prompt_etags[data["name"]] = data["template"]
        return prompt_etags

    def load_model_etags(self):
        model_files = list(Path(model_path).glob("*.yaml"))
        model_etags = []
        for model_file in model_files:
            #  with open(model_file, "r", encoding="utf-8") as file:
            #  data = yaml.load(file, Loader=yaml.FullLoader)
            model_etags.append(Path(model_file).stem)
        return model_etags

    def load_agent_etags(self):
        agent_files = list(Path(agent_path).rglob("agent.py"))
        agent_etags = []
        for agent_file in agent_files:
            agent_etags.append(Path(agent_file).parts[-2])
        return agent_etags

    def load_etag_list(self):
        etags = []

        # 此处添加prompt, base, model etag
        for tag_name in self.prompt_etags.keys():
            etags.append([tag_name, "prompt", "/abbr"])
        for tag_name in self.bases.keys():
            etags.append([tag_name, "base", "/abbr"])
        for tag_name in self.model_etags:
            etags.append([tag_name, "model", "/abbr"])
        for tag_name in self.agent_etags:
            etags.append([tag_name, "agent", "/abbr"])

        # 此处添加engine etag
        etags.append(["HyDE", "engine", "/abbr"])
        etags.append(["ReadTop3", "engine", "/abbr"])
        etags.append(["ReadTop5", "engine", "/abbr"])
        etags.append(["Memo", "engine", "/abbr"])

        etags = pd.DataFrame(etags, columns=["name", "type", "abbr"])
        return etags

    def load_base(self, base_paths):
        if len(base_paths) > 0:
            base_paths = list(Path(self.bases_root).glob("*.base"))
            for base_path in base_paths:
                vstore, df_file_md5, df_docs, metadata = load_base(base_path)
                base_name = metadata["name"]
                self.bases[base_name] = {
                    "df_docs": df_docs,
                    "df_file_md5": df_file_md5,
                    "metadata": metadata,
                    "vstore": vstore,
                }
        else:
            logger.info("no base exists")

    def load_config(self, config_path=config_path):
        with open(config_path, encoding="utf-8") as f:
            self.opt = yaml.load(f, Loader=SafeLoader)
        return self.opt

    def search(self, query, base_name, mode="similarity"):
        base = self.bases[base_name]
        if mode == "keyword":
            results = []
            df = base["df_docs"]
            df_results = df[df["doc"].str.contains(query, case=False)]
            for i, row in df_results.iterrows():
                page_content = row["doc"]
                metadata = {"file_path": row["file_path"]}
                result = Result(page_content, metadata)
                results.append(result)
        else:
            results = base["vstore"].similarity_search_with_score(
                query, k=self.opt["search_topk"]
            )
        return results

    # 解析text中所有的etag
    def get_etag_list(self, text):
        prompt_tags = []
        base_tags = []
        agent_tags = []
        engine_tags = []
        model_tags = []
        for i in text.split():
            if i.startswith("#"):
                etag = i[1:]
                if not self.all_etags[self.all_etags["name"] == etag].empty:
                    etype = self.all_etags[self.all_etags["name"] == etag][
                        "type"
                    ].values[0]
                    if etype == "prompt":
                        prompt_tags.append(etag)
                    elif etype == "base":
                        base_tags.append(etag)
                    elif etype == "agent":
                        agent_tags.append(etag)
                    elif etype == "engine":
                        engine_tags.append(etag)
                    elif etype == "model":
                        model_tags.append(etag)
        return prompt_tags, base_tags, engine_tags, model_tags, agent_tags

    # 应用prompt
    def inject_prompt(self, question, prompt_tags):
        all_prompt_etags = list(self.prompt_etags.keys())
        for tag in prompt_tags:
            if tag in all_prompt_etags:
                template = self.prompt_etags[tag]
                question = template.replace("{text}", question)
        return question

    @backoff.on_exception(
        backoff.expo,
        (
            openai.error.RateLimitError,
            openai.error.ServiceUnavailableError,
            openai.error.APIConnectionError,
        ),
    )
    def llm(
        self, input, context=[], model_config_yaml=None, format_fn=None, max_tokens=None, functions=None, function_call=None):
        # input: 输入的字符串
        # context: 上下文
        # model_config_yaml: 模型的配置文件名
        # format_fn: 流式输出中间过程显示的格式化函数
        # max_tokens: 最大生成长度, 不指定则使用模型配置文件自动计算
        if self.stop_retry:
            self.stop_retry = False
            self.stop_review = False
            self.abort_msg = False
            logger.info("Stop retry")
            raise AbortRetryException("Stop retry")
        self.abort_msg = False

        if model_config_yaml is None:
            model_config_path = os.path.join(ROOT, "models", "chatgpt-default.yaml")
        else:
            model_config_path = os.path.join(
                USER, "models", model_config_yaml + ".yaml"
            )

        with open(model_config_path, encoding="utf-8") as f:
            model_config = yaml.load(f, Loader=SafeLoader)

        if isinstance(max_tokens, int) and max_tokens > 0:
            model_config["params"]["max_tokens"] = max_tokens

        out = ""
        # chatgpt
        if model_config["model"] == "chatgpt":
            if functions:
                model_config["params"]["functions"] = functions
            if function_call:
                model_config["params"]["function_call"] = function_call

            sys_msg = model_config.get("system_message", "You are a helpful assistant")
            messages = [{"role": "system", "content": sys_msg}]
            if len(context) > 0:
                for q, a in context:
                    messages.append({"role": "user", "content": q})
                    messages.append({"role": "assistant", "content": a})
            messages.append({"role": "user", "content": input})

            message_len = len(tiktoken_encoder.encode(str(messages)))
            model_name = model_config["params"].get("model", "")

            if model_name == "gpt-3.5-turbo":
                model_max_token = 4000
            elif model_name == "gpt-3.5-turbo-0613":
                model_max_token = 4000
            elif model_name == "gpt-3.5-turbo-16k":
                model_max_token = 15000
            elif message_len < 4000:
                model_name = "gpt-3.5-turbo-0613"
                model_config["params"]["model"] = model_name
                model_max_token = 4000
            else:
                model_name = "gpt-3.5-turbo-16k"
                model_config["params"]["model"] = model_name
                model_max_token = 15000


            # 计算模型可用的最大token数
            free_tokens = model_max_token - message_len
            # 如果模型可用的最大token数小于0，尝试移除messages中的第一个元素，直到模型可用的最大token数大于1000
            while free_tokens < 1000 and len(messages) > 1:
                messages.pop(0)
                message_len = len(tiktoken_encoder.encode(str(messages)))
                free_tokens = model_max_token - message_len
            # max_token是用户指定的token数，如果存在，就尝试使用用户指定的，但也不能超过模型可用的最大token数
            if max_tokens:
                free_tokens = min(free_tokens, max_tokens)
                model_config["params"]["max_tokens"] = free_tokens


            logger.info(f"Send message to {model_name} with {message_len} tokens")
            completion = openai.ChatCompletion.create(
                api_key=self.opt["key"],
                messages=messages,
                stream=True,
                **model_config["params"],
            )
            report = []
            for resp in completion:
                if not self.abort_msg:
                    if hasattr(resp["choices"][0].delta, "content") or hasattr(resp.choices[0].delta, "function_call"):
                        if hasattr(resp.choices[0].delta, "function_call"):
                            report.append(resp.choices[0].delta.function_call.arguments)
                        else:
                            report.append(resp["choices"][0].delta.content)
                        out = "".join(report).strip()
                        if format_fn is not None:
                            mygpt.temp_result = format_fn(out)
                        else:
                            mygpt.temp_result = out
                else:
                    mygpt.temp_result += "...abort!"
                    self.abort_msg = False
                    logger.info("abort by user")
                    out = mygpt.temp_result
                    break
        # gpt3
        elif model_config["model"] == "gpt3":
            model_max_token = 3900
            prompt = ""
            if len(context) > 0:
                for q, a in context:
                    prompt += f"{q}\n\n"
                    prompt += f"{a}\n\n"
            prompt += f"{input}"
            if not max_tokens:
                free_tokens = model_max_token - len(tiktoken_encoder.encode(prompt))
                model_config["params"]["max_tokens"] = free_tokens
            logger.info("Send message to gpt3")
            openai.api_key = self.opt["key"]
            completion = openai.Completion.create(
                engine="text-davinci-003",
                prompt=prompt,
                stream=True,
                **model_config["params"],
            )
            report = []
            for resp in completion:
                if not self.abort_msg:
                    report.append(resp["choices"][0]["text"])
                    out = "".join(report).strip()
                    if format_fn is not None:
                        mygpt.temp_result = format_fn(out)
                    else:
                        mygpt.temp_result = out
                else:
                    mygpt.temp_result += "...abort!"
                    self.abort_msg = False
                    logger.info("abort by user")
                    out = mygpt.temp_result
                    break
        return out

    def preprocess_question(self, question):
        (
            prompt_tags,
            base_tags,
            engine_tags,
            model_tags,
            agent_tags,
        ) = self.get_etag_list(question)
        # 应用base_tag
        if len(base_tags) > 0:
            base_name = base_tags
        else:
            base_name = "default"
        # 应用prompt
        if len(prompt_tags) > 0:
            question = self.inject_prompt(question, prompt_tags)
        if len(model_tags) > 0:
            model_config_yaml = model_tags[-1]
        else:
            model_config_yaml = None
        # 判断question最后一行中的有etag，移除etags
        for etag in self.all_etags["name"]:
            question = question.replace(f"#{etag}", "")
        return question, model_config_yaml, base_name, engine_tags, agent_tags

    def ask(self, question, context, base_name):
        question_out = question
        # 解析etag并处理
        (
            question,
            model_config_yaml,
            base_name,
            engine_tags,
            agent_tags,
        ) = self.preprocess_question(question)

        # 备忘录
        if "Memo" in engine_tags:
            now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            answer = f"{question}\n\n{now_time} 备忘录"
            return question_out, answer, [], ""

        # run agent
        if len(agent_tags) > 0:
            sys.path.append(agent_path)
            agent = importlib.import_module(f"{agent_tags[-1]}.agent")
            importlib.reload(agent)
            _agent = agent.Agent()
            mygpt.temp_result = ""
            logger.info("Received answer")
            question, answer, mydocs, draft = _agent.run(
                question, context, self, model_config_yaml
            )
            return question_out, answer, mydocs, draft

        # default base
        if base_name == "default":
            draft = self.llm(question, context, model_config_yaml)
            mygpt.temp_result = ""
            logger.info("Received answer")
            return question_out, draft, [], draft

        mydocs_list = []
        for base_name in base_name:
            base = self.bases[base_name]
            if self.opt["HyDE"] or "HyDE" in engine_tags:
                draft = self.llm(question, context, model_config_yaml)
                query = question + "\n" + draft
                #  logger.info("[draft]: " + draft + "\n" + "-" * 60)
                logger.info("Generated draft")
            else:
                draft = ""
                context_str = "\n".join(["\n".join(t) for t in context])
                query = context_str + "\n" + question

            mydocs = base["vstore"].similarity_search_with_score(
                query, k=self.opt["ask_topk"]
            )
            mydocs_list.extend(mydocs)

        mydocs = sorted(mydocs_list, key=lambda x: x[1])

        local_text = mydocs[0][0].page_content
        if (
            self.opt["answer_depth"] < 2
            and (not "ReadTop3" in engine_tags)
            and (not "ReadTop5" in engine_tags)
        ):  # simple answer
            ask_prompt = f"""You can refer to given local text and your own knowledge to answer users' questions. If local text does not provide relevant information, feel free to generate a answer for question based on general knowledge and context:
local text:```{local_text}```
user question:```{question}```"""
            answer = self.llm(ask_prompt, context, model_config_yaml)
            mygpt.temp_result = ""

        else:  # deep reading
            if "ReadTop3" in engine_tags:
                answer_depth = 3
            elif "ReadTop5" in engine_tags:
                answer_depth = 5
            else:
                answer_depth = min(self.opt["answer_depth"], self.opt["ask_topk"])
            chunks = [i[0].page_content for i in mydocs[0 : int(answer_depth)][::-1]]
            answer = self.review(question, chunks)
            mygpt.temp_result = ""

        logger.info("Received answer")
        return question_out, answer, mydocs, draft

    def review(self, question, chunks):
        (
            question,
            model_config_yaml,
            _,
            _,
            _,
        ) = self.preprocess_question(question)
        self.stop_review = False
        if model_config_yaml is None:
            model_config_yaml = "chatgpt-review"

        logger.info(f"Start full text reading")
        answer = ""
        answer_list = []
        memory = 8000  # 为最终回答分配的上下文长度
        chunk_memory = memory // len(chunks)  # 每个片段分配的上下文长度


        if len(chunks) == 1:
            answer_list.append(chunks[0])
        else:
            for i, chunk in enumerate(chunks):
                if self.stop_review:
                    final_answer = self.temp_result + '...stop by user!'
                    self.temp_result = ""
                    self.stop_retry = False
                    self.stop_review = False
                    self.abort_msg = False
                    return final_answer

                print(f'memory:{memory},chunk_memory:{chunk_memory}')
                ask_prompt = f"""local text:{chunk}
    1.Answer the final user instruction only based on above local text and user requests, do not answer irrelevant content. If the local text is unrelated to the user's request, only output 'no relevant information'
    2.Use the same language as the following instructions or the language requested in the following instructions
    3.{question}
    """
                answer = mygpt.llm(
                    ask_prompt,
                    [],
                    model_config_yaml,
                    format_fn=lambda x: f"正在分析片段{i+1}：\n\n{x}",
                    max_tokens=chunk_memory,
                )
                answer_list.append(answer)
                chunk_memory = chunk_memory * 2 - len(tiktoken_encoder.encode(answer))
                logger.info(
                    f"Received answer {i+1}: \n Reading progress {i+1}/{len(chunks)}"
                )

        ask_prompt = ""
        for j in range(len(answer_list)):
            ask_prompt += f"{answer_list[j]}\n"
        ask_prompt += f"""
1.Answer the following user instruction only based on above text and user requests
2.Use the same language as the following instructions or the language requested in the following instructions
3.{question}
"""
        answer = mygpt.llm(
            ask_prompt, [], model_config_yaml, format_fn=lambda x: f"生成最终答案：\n\n{x}"
        )
        logger.info(f"Received final answer")

        frontslot = "<hr>".join(answer_list)
        if len(chunks) > 1:
            frontslot = f"""<frontslot><details><summary>中间回答</summary>{frontslot}</details><hr></frontslot>"""
            final_answer = frontslot + answer
        else:
            final_answer = answer
        mygpt.temp_result = ""
        return final_answer


mygpt = MyGPT()
