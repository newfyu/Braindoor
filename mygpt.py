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
import os
import shutil


class Result:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class MyGPT:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.bases_root = self.opt["bases_root"]
        self.bases = dict()
        base_paths = list(Path(self.bases_root).glob("*.base"))
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
            logger.info('no base exists')

        openai.api_key = self.opt["key"]

        if self.opt["key"]:
            self.base_embedding = OpenAIEmbeddings(openai_api_key=self.opt["key"])

        self.fulltext_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.opt['review_chunk_size'],
            chunk_overlap=self.opt['review_chunk_overlap'],
            length_function=partial(token_len, encoder=tiktoken_encoder),
        )


    def load_config(self, config_path="config.yaml"):
        with open(config_path) as f:
            self.opt = yaml.load(f, Loader=SafeLoader)
        return self.opt

    def search(self, query, base_name, mode="similarity"):
    def search(self, query, base_name, mode="similarity"):
        """
        Search for documents based on the query string and return the results.

        Args:
        query (str): The query string.
        base_name (str): The name of the database to search.
        mode (str, optional): The search mode, can be "similarity" or "keyword". Defaults to "similarity".

        Returns:
        list: A list of search results containing documents related to the query string.
        """

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
    def chatgpt(self, input,context=[],sys_msg='',  temperature=1., max_tokens=1000):
        """
        This function interacts with the GPT model to generate a response based on the input, context, and system message.
        It handles rate limit errors and other API errors using the backoff library.

        Args:
        input (str): The input message from the user.
        context (list): A list of tuples containing previous user and assistant messages.
        sys_msg (str, optional): A system message to set the behavior of the assistant. Defaults to ''.
        temperature (float, optional): Controls the randomness of the generated response. Defaults to 1.0.
        max_tokens (int, optional): The maximum number of tokens in the generated response. Defaults to 1000.

        Returns:
        str: The generated response from the GPT model.
        """
        if sys_msg == '':
            messages = [{"role": "system", "content": "You are a helpful assistant."}]
        else:
            messages = [{"role": "system", "content": f"{sys_msg}"}]
        if len(context) > 0:
            for q, a in context:
                messages.append({"role": "user", "content": f"{q}"})
                messages.append({"role": "assistant", "content": f"{a}"})
        messages.append({"role": "user", "content": f"{input}"})
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            api_key=self.opt["key"],
            max_tokens=max_tokens,
            messages=messages,
            temperature = temperature,
        )
        logger.info("[message]: " + str(messages) + "\n" + "-" * 60)
        return completion.choices[0].message.content

    def ask(self, question, context, base_name):
        """
        Ask a question and get an answer based on the context and the specified base_name.

        Args:
        question (str): The question to ask.
        context (list): A list of tuples containing previous user and assistant messages.
        base_name (str): The name of the database to search for relevant information.

        Returns:
        tuple: A tuple containing the answer, the documents found, and the draft response.
        """

        
        if base_name != "default":
            base = self.bases[base_name]
            if self.opt['HyDE']:
                draft = self.chatgpt(question, context)
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
            if self.opt["answer_depth"]<2: # simple answer
                    ask_prompt = f"""You can refer to given local text and your own knowledge to answer users' questions. If local text does not provide relevant information for answering user questions, feel free to generate a answer for question based on general knowledge or context:
        local text:{local_text}
        user question:{question}"""
                    answer = self.chatgpt(ask_prompt, context)

            else: # deep answer
                answer_depth = min(self.opt["answer_depth"], self.opt["ask_topk"])
                chunks = [i[0].page_content for i in mydocs[0:answer_depth][::-1]] 
                answer = self.review(question, chunks)

        else: # default answer
            draft = self.chatgpt(question, context)
            answer = draft
            mydocs = []

        logger.info("[answer]: " + answer + "\n" + "-" * 60)
        return answer, mydocs, draft

    # prompt 1
    #  def review(self, question, chunks):
        #  prev_answer = ""
        #  logger.info(f"Start long text reading, estimated to take {len(chunks)*15} seconds")
        #  chunk_num = len(chunks)
        #  for i,chunk in enumerate(chunks):
            #  if i != chunk_num - 1:
                #  ask_prompt = f"""known:{prev_answer}
#  Extra text:{chunk}
#  quesion:{question}
#  The text is incomplete. Don't answer the questions immediately. First record the original text say about the answer
#  """
            #  else:
                #  ask_prompt = f"""known:{prev_answer}
#  Extra text:{chunk}
#  Please answer the following question only according to the text provided above:
#  {question}"""
            #  answer = mygpt.chatgpt(ask_prompt, temperature=1)
            #  prev_answer = answer
            #  logger.info(f"answer {i}: {answer} \n Reading progress {i+1}/{len(chunks)}")
        #  return prev_answer

    def review(self, question, chunks):
        """
        Review the given chunks of text and generate an answer to the question based on the content.

        Args:
        question (str): The question to be answered.
        chunks (list): A list of text chunks to review for answering the question.

        Returns:
        str: The generated answer based on the reviewed text chunks.
        """
        prev_answer = ""
        logger.info(f"Start long text reading, estimated to take {len(chunks)*15} seconds")
        chunk_num = len(chunks)

        for i,chunk in enumerate(chunks):
            if i != chunk_num - 1:
                ask_prompt = f"""known:{prev_answer}
Extra text:{chunk}
quesiton:{question}。完全根据前面提供的内容回答，不要自由回答。"""
            else:
                ask_prompt = f"""known:{prev_answer}
Extra text:{chunk}
Please answer the following question only according to the text provided above:
{question}"""
            answer = mygpt.chatgpt(ask_prompt, temperature=1)
            prev_answer = answer
            logger.info(f"answer {i}: {answer} \n Reading progress {i+1}/{len(chunks)}")
        return prev_answer

mygpt = MyGPT()
