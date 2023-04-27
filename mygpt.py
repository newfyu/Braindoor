from pathlib import Path
import openai
import backoff
import os

import yaml
from yaml.loader import SafeLoader
from utils import logger, tiktoken_encoder

from update_base import load_base
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from functools import partial
from create_base import token_len
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"), "braindoor/")
config_path = os.path.join(USER, "config.yaml")
prompt_path = os.path.join(USER, "prompts")


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
            with open(prompt_file, "r", encoding='utf-8') as file:
                data = yaml.load(file, Loader=yaml.FullLoader)
                prompt_etags[data["name"]] = data["template"]
        return prompt_etags

    def load_etag_list(self):
        etags = []
        for tag_name in self.prompt_etags.keys():
            etags.append([tag_name, "prompt", "/abbr"])
        for tag_name in self.bases.keys():
            etags.append([tag_name, "base", "/abbr"])
        
        # 此处添加engine etag
        etags.append(["HyDE", "engine", "/abbr"])
        etags.append(["DeepAnswer3", "engine", "/abbr"])
        etags.append(["DeepAnswer5", "engine", "/abbr"])

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
        with open(config_path) as f:
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
                etype = self.all_etags[self.all_etags["name"] == etag]["type"].values[0]
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
    def chatgpt(
        self,
        input,
        context=[],
        sys_msg="",
        temperature=1.0,
        max_tokens=1500,
        stream=False,
    ):
        self.abort_msg = False
        if sys_msg == "":
            messages = [{"role": "system", "content": "You are a helpful assistant."}]
        else:
            messages = [{"role": "system", "content": f"{sys_msg}"}]
        if len(context) > 0:
            for q, a in context:
                messages.append({"role": "user", "content": f"{q}"})
                messages.append({"role": "assistant", "content": f"{a}"})
        messages.append({"role": "user", "content": f"{input}"})
        #  logger.info("[message]: " + str(messages) + "\n" + "-" * 60)
        logger.info("Send message")

        if not stream:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                api_key=self.opt["key"],
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
            )
            #  logger.info("[message]: " + str(messages) + "\n" + "-" * 60)
            logger.info("Send message")
            return completion.choices[0].message.content
        else:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                api_key=self.opt["key"],
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
                stream=True,
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

            return mygpt.temp_result

    def ask(self, question, context, base_name):
        # 解析etag并处理
        prompt_tags, base_tags, engine_tags, _, _ = self.get_etag_list(question)
        # 应用base_tag
        if len(base_tags) > 0:
            base_name = base_tags[-1]
        # 应用prompt
        if len(prompt_tags) > 0:
            question = self.inject_prompt(question, prompt_tags)
        # 判断question最后一行中的有etag，移除etags
        for etag in self.all_etags["name"]:
            question = question.replace(f"#{etag}", "")

        if base_name != "default":
            base = self.bases[base_name]
            if self.opt["HyDE"] or "HyDE" in engine_tags:
                draft = self.chatgpt(question, context, stream=True)
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

            local_text = mydocs[0][0].page_content
            if self.opt["answer_depth"] < 2:  # simple answer
                ask_prompt = f"""You can refer to given local text and your own knowledge to answer users' questions. If local text does not provide relevant information, feel free to generate a answer for question based on general knowledge and context:
local text:{local_text}
user question:{question}"""
                answer = self.chatgpt(ask_prompt, context, stream=True)
                mygpt.temp_result = ""

            else:  # deep answer
                answer_depth = min(self.opt["answer_depth"], self.opt["ask_topk"])
                chunks = [
                    i[0].page_content for i in mydocs[0 : int(answer_depth)][::-1]
                ]
                answer = self.review(question, chunks)
                mygpt.temp_result = ""

        else:  # default answer
            draft = self.chatgpt(question, context, stream=True)
            answer = draft
            mydocs = []
            mygpt.temp_result = ""

        logger.info("Received answer")
        #  logger.info("[answer]: " + answer + "\n" + "-" * 60)
        return answer, mydocs, draft

    # prompt 1
    def review(self, question, chunks):
        prev_answer = ""
        logger.info(
            f"Start long text reading, estimated to take {len(chunks)*15} seconds"
        )
        chunk_num = len(chunks)
        for i, chunk in enumerate(chunks):
            if i != chunk_num - 1:
                ask_prompt = f"""known:{prev_answer}
                Extra text:{chunk}
                quesion:{question}
                The text is incomplete. Don't answer the questions immediately. First record the related text about the question
                """
            else:
                ask_prompt = f"""known:{prev_answer}
                Extra text:{chunk}
                Please answer the following question only according to the text provided above:
                {question}"""
            answer = mygpt.chatgpt(ask_prompt, temperature=1, stream=True)
            prev_answer = answer
            #  logger.info(f"answer {i}: {answer} \n Reading progress {i+1}/{len(chunks)}")
            logger.info(f"Received answer {i}: \n Reading progress {i+1}/{len(chunks)}")
        mygpt.temp_result = ""
        return prev_answer

    #  def review(self, question, chunks):
    #  prev_answer = ""
    #  logger.info(
    #  f"Start long text reading, estimated to take {len(chunks)*15} seconds"
    #  )
    #  chunk_num = len(chunks)

    #  for i, chunk in enumerate(chunks):
    #  if i != chunk_num - 1:
    #  ask_prompt = f"""known:{prev_answer}


#  Extra text:{chunk}
#  quesiton:{question}。完全根据前面提供的内容回答，不要自由回答。"""
#  else:
#  ask_prompt = f"""known:{prev_answer}
#  Extra text:{chunk}
#  Please answer the following question only according to the text provided above:
#  {question}"""
#  answer = mygpt.chatgpt(ask_prompt, temperature=1, stream=True)
#  prev_answer = answer
#  logger.info(f"answer {i}: {answer} \n Reading progress {i+1}/{len(chunks)}")
#  mygpt.temp_result = ''
#  return prev_answer


mygpt = MyGPT()
