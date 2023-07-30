import argparse
import hashlib
import os
import re
from pathlib import Path
import yaml
from yaml.loader import SafeLoader
import openai
import json
import pickle

import pandas as pd
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from functools import partial
import argparse
from utils import logger,set_proxy, del_proxy,tiktoken_encoder, read_text_file, TokenSplitter

USER = os.path.join(os.path.expanduser("~"),'braindoor/')
config_path = os.path.join(USER, "config.yaml")

with open(config_path) as f:
    opt = yaml.load(f, Loader=SafeLoader)
    openai.api_key = opt["key"]
    if 'api_base' in opt.keys() and opt["api_base"]:
        openai.api_base = opt["api_base"] + '/v1'
    else:
        openai.api_base = "https://api.openai.com/v1"

def get_file_list(bases):
    files = []
    for base_path, suffix in bases.items():
        root_dir = Path(base_path)
        pattern = re.compile(f".*\.({suffix})$", re.IGNORECASE)
        for file in root_dir.rglob("*"):
            if pattern.match(str(file)):
                files.append(file)
    return files


def make_file_md5(files):
    file_md5 = []
    for file_path in files:
        #  print(file_path)
        with open(file_path, "rb") as f:
            h = hashlib.md5()
            h.update(f.read())
            md5 = h.hexdigest()
            file_md5.append((str(file_path), md5))
    df_file_md5 = pd.DataFrame(file_md5, columns=["file_path", "md5"])
    return df_file_md5




def token_len(text, encoder):
    code = encoder.encode(text)
    return len(code)


def create_new_df_docs(
    df_file_md5, start_len, chunk_size, chunk_overlap, max_chunk_num
):
    docs = []
    text_splitter = TokenSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        len_fn=partial(token_len, encoder=tiktoken_encoder),
    )
    

    for _, file_path, md5 in df_file_md5.itertuples():
        try:
            text = read_text_file(file_path)
            chunks = text_splitter.split_text(text)

            if len(chunks) > max_chunk_num:
                chunks = chunks[:max_chunk_num]

            for chunk in chunks:
                file_name = Path(file_path).stem
                chunk = file_name + "\n\n" + chunk
                docs.append((start_len, chunk, md5, file_path))
                start_len += 1
                logger.info(
                    f"split {file_name}, len:{len(chunk)},token:{token_len(chunk,tiktoken_encoder)}"
                )
        except Exception as e:
            logger.error(file_path)
            logger.error("split text error:" + str(e))
    df_docs = pd.DataFrame(docs, columns=["index", "doc", "md5", "file_path"])
    return df_docs


def create_vstore(df_docs):
    set_proxy()
    with open(config_path) as f:
        opt = yaml.load(f, Loader=SafeLoader)
        openai.api_key = opt["key"]
        if 'api_base' in opt.keys() and opt["api_base"]:
            openai.api_base = opt["api_base"] + '/v1'
        else:
            openai.api_base = "https://api.openai.com/v1"
    embeddings = OpenAIEmbeddings(openai_api_key=opt["key"])
    metadatas = []
    for file_path in df_docs.file_path:
        metadatas.append({"file_path": file_path})
    vstore = FAISS.from_texts(list(df_docs["doc"]), embeddings, metadatas=metadatas)
    del_proxy()
    return vstore


def create_base(base_name, paths, chunk_size, chunk_overlap, max_chunk_num):
    metadata = {
        "name": base_name,
        "paths": paths,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "max_chunk_num": max_chunk_num,
    }

    files = get_file_list(paths)
    if len(files) > 0:
        files = files[0:1]
        df_file_md5 = make_file_md5(files)

        df_docs = create_new_df_docs(
            df_file_md5, 0, chunk_size, chunk_overlap, max_chunk_num
        )

        logger.info("\nCreate base parameter:")
        for name, value in metadata.items():
            logger.info(f"{name}: {value}")

        logger.info("Creating base, may take several minutes……")
        vstore = create_vstore(df_docs)
        if not ".base" in base_name:
            base_name = base_name + ".base"
        base_root =os.path.join(USER, opt["bases_root"])
        base_path = os.path.join(base_root, base_name)

        if not os.path.exists(base_root):
            os.mkdir(base_root)

        if not os.path.exists(base_path):
            with open(base_path, "wb") as f:
                save = {
                    "df_file_md5": df_file_md5,
                    "df_docs": df_docs,
                    "metadata": metadata,
                    "vstore": vstore,
                }
                pickle.dump(save, f)
                logger.info(f"Knowledge base created successfully!")
        else:
            logger.error('The base name already exists!')
    else:
        logger.error("Empty folder cannot create base!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, help="base's name")
    parser.add_argument(
        "--paths",
        type=json.loads,
        help="""bases path need a dict, example: --paths '{"path1":"md|txt", "path2":"html"}'""",
    )
    parser.add_argument("--chunk_size", type=int, default=2000, help="")
    parser.add_argument("--chunk_overlap", type=int, default=50, help="")
    parser.add_argument("--max_chunk_num", type=int, default=10, help="")
    args = parser.parse_args()

    create_base(
        args.name, args.paths, args.chunk_size, args.chunk_overlap, args.max_chunk_num
    )
