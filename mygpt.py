from pathlib import Path
import openai
import backoff

import yaml
from yaml.loader import SafeLoader

from update_base import load_base
from langchain.embeddings import OpenAIEmbeddings
from utils import logger, tiktoken_encoder, cutoff_localtext
from langchain.text_splitter import RecursiveCharacterTextSplitter
from functools import partial
from create_base import token_len
import importlib

class Result:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class MyGPT:
    def __init__(self, config_path="config.yaml"):
        self.temp_result = ""
        self.load_config(config_path)
        self.bases_root = self.opt["bases_root"]
        self.bases = dict()
        base_paths = list(Path(self.bases_root).glob("*.base"))
        self.load_base(base_paths)
        self.magictags = self.load_magictags()

        openai.api_key = self.opt["key"]
        if self.opt["key"]:
            self.base_embedding = OpenAIEmbeddings(openai_api_key=self.opt["key"])

        self.fulltext_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.opt["review_chunk_size"],
            chunk_overlap=self.opt["review_chunk_overlap"],
            length_function=partial(token_len, encoder=tiktoken_encoder),
        )

    # load magic tag from tags/
    def load_magictags(self):
        tag_file = list(Path('magictags').glob("*.py"))
        magictags = dict()
        for tag_file in tag_file:
            tag_name = tag_file.stem
            magictag = importlib.import_module(f"magictags.{tag_name}")
            magictag = magictag.MagicTag()
            magictags[magictag.tag] = magictag
        return magictags


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

    def load_config(self, config_path="config.yaml"):
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
        if sys_msg == "":
            messages = [{"role": "system", "content": "You are a helpful assistant."}]
        else:
            messages = [{"role": "system", "content": f"{sys_msg}"}]
        if len(context) > 0:
            for q, a in context:
                messages.append({"role": "user", "content": f"{q}"})
                messages.append({"role": "assistant", "content": f"{a}"})
        messages.append({"role": "user", "content": f"{input}"})

        if not stream:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                api_key=self.opt["key"],
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
            )
            logger.info("[message]: " + str(messages) + "\n" + "-" * 60)
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
                if hasattr(resp['choices'][0].delta, 'content'):
                    report.append(resp['choices'][0].delta.content)
                    mygpt.temp_result = "".join(report).strip()
            logger.info("[message]: " + str(messages) + "\n" + "-" * 60)
            return mygpt.temp_result

    def ask(self, question, context, base_name):
        # 解析question中的magic tag，加入use_magictag列表
        use_magictags = []
        for key in self.magictags.keys():
            tag = f" #{key} " 
            if  tag in question:
                question = question.replace(tag, "")
                use_magictags.append(self.magictags[key])

        # qustion前处理
        for magictag in use_magictags:
            try:
                question = magictag.before_llm(question)
            except Exception as e:
                logger.error(e)

        if base_name != "default":
            base = self.bases[base_name]
            if self.opt["HyDE"]:
                draft = self.chatgpt(question, context, stream=True)
                query = question + "\n" + draft
                logger.info("[draft]: " + draft + "\n" + "-" * 60)
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
                mygpt.temp_result = ''

            else:  # deep answer
                answer_depth = min(self.opt["answer_depth"], self.opt["ask_topk"])
                chunks = [i[0].page_content for i in mydocs[0: int(answer_depth)][::-1]]
                answer = self.review(question, chunks)
                mygpt.temp_result = ''

        else:  # default answer
            draft = self.chatgpt(question, context, stream=True)
            answer = draft
            mydocs = []
            mygpt.temp_result = ''

        # question后处理
        for magictag in use_magictags:
            try:
                answer = magictag.after_llm(answer)
            except Exception as e:
                logger.error(e)

        return answer, mydocs, draft

    # prompt 1
    def review(self, question, chunks):
        prev_answer = ""
        logger.info(f"Start long text reading, estimated to take {len(chunks)*15} seconds")
        chunk_num = len(chunks)
        for i,chunk in enumerate(chunks):
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
            logger.info(f"answer {i}: {answer} \n Reading progress {i+1}/{len(chunks)}")
        mygpt.temp_result = ''
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
