from pathlib import Path
from numpy import mod
import openai
import backoff
import os
from pandas.core.series import base

import yaml
from yaml.loader import SafeLoader
from utils import logger, tiktoken_encoder

from update_base import load_base
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from functools import partial
from create_base import token_len
import pandas as pd
import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"), "braindoor/")
config_path = os.path.join(USER, "config.yaml")
prompt_path = os.path.join(USER, "prompts")
model_path = os.path.join(USER, "models")


class Result:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


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
        self.abort_msg = False
        self.all_etags = self.load_etag_list()

        openai.api_key = self.opt["key"]
        if self.opt["key"]:
            self.base_embedding = OpenAIEmbeddings(openai_api_key=self.opt["key"])

        self.fulltext_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.opt["review_chunk_size"],
            chunk_overlap=self.opt["review_chunk_overlap"],
            length_function=partial(token_len, encoder=tiktoken_encoder),
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
            with open(model_file, "r", encoding="utf-8") as file:
                data = yaml.load(file, Loader=yaml.FullLoader)
                model_etags.append(Path(model_file).stem)
        return model_etags

    def load_etag_list(self):
        etags = []

        # 此处添加prompt, base, model etag
        for tag_name in self.prompt_etags.keys():
            etags.append([tag_name, "prompt", "/abbr"])
        for tag_name in self.bases.keys():
            etags.append([tag_name, "base", "/abbr"])
        for tag_name in self.model_etags:
            etags.append([tag_name, "model", "/abbr"])

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
        with open(config_path, encoding='utf-8') as f:
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
    def llm(self, input, context=[], model_config_yaml=None):
        self.abort_msg = False

        if model_config_yaml is None:
            model_config_path = os.path.join(ROOT, "models", "chatgpt.yaml")
        else:
            model_config_path = os.path.join(
                USER, "models", model_config_yaml + ".yaml"
            )

        with open(model_config_path, encoding='utf-8') as f:
            model_config = yaml.load(f, Loader=SafeLoader)

        # chatgpt
        if model_config["model"] == "chatgpt":
            sys_msg = model_config.get("system_message", "You are a helpful assistant")
            messages = [{"role": "system", "content": sys_msg}]
            if len(context) > 0:
                for q, a in context:
                    messages.append({"role": "user", "content": q})
                    messages.append({"role": "assistant", "content": a})
            messages.append({"role": "user", "content": input})
            logger.info("Send message to chatgpt")
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                api_key=self.opt["key"],
                messages=messages,
                stream=True,
                **model_config["params"],
            )
            report = []
            for resp in completion:
                if not self.abort_msg:
                    if hasattr(resp["choices"][0].delta, "content"):
                        report.append(resp["choices"][0].delta.content)
                        mygpt.temp_result = "".join(report).strip()
                else:
                    mygpt.temp_result += "...abort!"
                    self.abort_msg = False
                    logger.info("abort by user")
                    break
        # gpt3
        elif model_config["model"] == "gpt3":
            prompt = ""
            if len(context) > 0:
                for q, a in context:
                    prompt += f"{q}\n\n"
                    prompt += f"{a}\n\n"
            prompt += f"{input}"
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
                    mygpt.temp_result = "".join(report).strip()
                else:
                    mygpt.temp_result += "...abort!"
                    self.abort_msg = False
                    logger.info("abort by user")
                    break
        return mygpt.temp_result

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

        if not "Memo" in engine_tags:
            if base_name != "default":
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
                if self.opt["answer_depth"] < 2 and (not "ReadTop3" in engine_tags) and (not "ReadTop5" in engine_tags):  # simple answer
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
                    chunks = [
                        i[0].page_content for i in mydocs[0 : int(answer_depth)][::-1]
                    ]
                    answer = self.review(question, chunks)
                    mygpt.temp_result = ""

            else:  # default answer
                draft = self.llm(question, context, model_config_yaml)
                answer = draft
                mydocs = []
                mygpt.temp_result = ""

            logger.info("Received answer")
            #  logger.info("[answer]: " + answer + "\n" + "-" * 60)
        else:
            draft = ""
            answer = ""
            mydocs = []
            now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            question_out = f"{now_time} 备忘录\n\n{question}"
        return question_out, answer, mydocs, draft

    # prompt 1
    #  def review(self, question, chunks):
    #  prev_answer = ""
    #  logger.info(
    #  f"Start long text reading, estimated to take {len(chunks)*15} seconds"
    #  )
    #  chunk_num = len(chunks)
    #  for i, chunk in enumerate(chunks):
    #  if i != chunk_num - 1:
    #  ask_prompt = f"""known:```{prev_answer}```
    #  Extra text:```{chunk}```
    #  quesion:```{question}```
    #  The text is incomplete. Don't answer the questions immediately. First record the related text about the question"""
    #  else:
    #  ask_prompt = f"""known:{prev_answer}
    #  Extra text:{chunk}
    #  Please answer the following question only according to the text provided above, If there is no specific indication, you need answer the following qusting in Chinese:
    #  ```{question}```"""
    #  answer = mygpt.llm(ask_prompt,[],'chatgpt_review')
    #  prev_answer = answer
    #  logger.info(f"Received answer {i}: \n Reading progress {i+1}/{len(chunks)}")
    #  mygpt.temp_result = ""
    #  return prev_answer

    # prompt 2
    def review(self, question, chunks):
        # 预处理
        question, model_config_yaml, _, _, _, = self.preprocess_question(question)
        if model_config_yaml is None:
            model_config_yaml = "chatgpt_review"

        prev_answer = ""
        logger.info(f"Start full text reading")
        chunk_num = len(chunks)
        answer_list = []
        for i, chunk in enumerate(chunks):
            if i != chunk_num - 1:
                ask_prompt = f"""known:```{prev_answer}```
Extra text:```{chunk}```
quesion:```{question}```
The text is incomplete. Don't answer the questions immediately. Output the related text about the question for delayed answer"""
            else:
                ask_prompt = f"""known:{prev_answer}
                Extra text:{chunk}
                Please answer the following question only according to the text provided above, If there is no specific indication, you need answer the following qusting in Chinese:
                ```{question}```"""
            answer = mygpt.llm(ask_prompt, [], model_config_yaml)
            prev_answer = answer
            logger.info(f"Received answer {i}: \n Reading progress {i+1}/{len(chunks)}")

            if i != chunk_num - 1:
                answer_list.append(answer)

        mygpt.temp_result = ""
        frontslot = "<hr>".join(answer_list)
        frontslot = f"""<frontslot><details><summary>中间回答</summary>{frontslot}</details><hr></frontslot>"""
        final_answer = frontslot + prev_answer
        return final_answer


mygpt = MyGPT()
