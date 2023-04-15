import argparse
import argparse
import os
import pickle
import time

import backoff
import numpy as np
import openai
import openai
import pandas as pd
import yaml
from yaml.loader import SafeLoader

from create_base import create_new_df_docs, get_file_list, make_file_md5
from utils import logger, with_proxy
from pathlib import Path

USER = os.path.join(os.path.expanduser("~"),'braindoor/')
config_path = os.path.join(USER, "config.yaml")


def load_config():
    with open(config_path) as f:
        opt = yaml.load(f, Loader=SafeLoader)
    openai.api_key = opt["key"]
    logger.info(f"Updata config: {opt}")
    return opt


opt = load_config()


def load_base(base_path):
    with open(base_path, "rb") as f:
        base = pickle.load(f)
    vstore = base["vstore"]
    df_file_md5 = base["df_file_md5"]
    df_docs = base["df_docs"]
    metadata = base["metadata"]
    metadata["name"] = Path(base_path).stem
    logger.info(f"Knowledge base loaded successfully:{metadata}")
    return vstore, df_file_md5, df_docs, metadata


def check_update(metadata, df_file_md5):
    df_old = df_file_md5
    files = get_file_list(metadata["paths"])
    file_md5_new = make_file_md5(files)
    df_new = pd.DataFrame(file_md5_new, columns=["file_path", "md5"])

    merged_df = df_new.merge(
        df_old, on=["file_path", "md5"], how="outer", indicator=True
    )

    df_add = merged_df[merged_df["_merge"] == "left_only"]
    df_add = df_add.drop(labels=["_merge"], axis=1)
    df_add.columns = ["file_path", "md5"]

    df_remove = merged_df[merged_df["_merge"] == "right_only"]
    df_remove = df_remove.drop(labels=["_merge"], axis=1)
    df_remove.columns = ["file_path", "md5"]

    return df_add, df_remove, df_new


@with_proxy(opt["proxy"])
@backoff.on_exception(
    backoff.expo, (openai.error.RateLimitError, openai.error.ServiceUnavailableError)
)
def add_texts_to_vstore_with_backoff(vstore, doc, metadata):
    vstore.add_texts([doc], metadatas=[metadata])


def add_vstore(df_docs_add, vstore, opt):
    totel_doc_num = len(df_docs_add)

    for i, row in df_docs_add.iterrows():
        doc = row["doc"]
        file_path = row["file_path"]
        metadata = {"file_path": file_path}
        add_texts_to_vstore_with_backoff(vstore, doc, metadata)
        logger.info(
            f"{i+1}/{totel_doc_num} Successfully embedded document {file_path} with length of {len(doc)}"
        )
        time.sleep(opt["rate_limit"])
    return vstore


# rerange index_to_docstore_id
def reorder_index_to_docstore_id(remove_ids, vstore):
    index_to_docstore_id = vstore.index_to_docstore_id
    for key in remove_ids:
        if key in index_to_docstore_id:
            del index_to_docstore_id[key]
    values = list(index_to_docstore_id.values())
    new_index_to_docstore_id = dict()
    for i, v in enumerate(values):
        new_index_to_docstore_id[i] = v
    vstore.index_to_docstore_id = new_index_to_docstore_id
    return vstore


def print_set(st):
    lst = sorted(list(st))
    for i in lst:
        logger.info(i)


def update_base(base_name):
    opt = load_config()
    if not ".base" in base_name:
        base_name = base_name + ".base"
    base_path = os.path.join(USER, opt["bases_root"], base_name)

    vstore, df_file_md5, df_docs, metadata = load_base(base_path)
    df_add, df_remove, df_new = check_update(metadata, df_file_md5)

    if len(df_add) + len(df_remove) > 0:
        add_set = set(df_add.file_path.to_list())
        remove_set = set(df_remove.file_path.to_list())
        modify_set = add_set & remove_set
        add_set = add_set - modify_set
        remove_set = remove_set - modify_set

        logger.info("-" * 80)
        if len(add_set) > 0:
            logger.info("add:")
            print_set(add_set)
            logger.info("-" * 80)
        if len(remove_set) > 0:
            logger.info("remove:")
            logger.info(remove_set)
            logger.info("-" * 80)
        if len(modify_set) > 0:
            logger.info("modify:")
            print_set(modify_set)
            logger.info("-" * 80)

        start_len = len(vstore.index_to_docstore_id)
        df_docs_add = create_new_df_docs(
            df_add,
            start_len,
            metadata["chunk_size"],
            metadata["chunk_overlap"],
            metadata["max_chunk_num"],
        )
        #  find index to be deleted
        df_merged = pd.merge(df_docs, df_remove, on=["md5", "file_path"], how="inner")
        remove_ids = np.array(df_merged["index"].to_list())
        logger.info("Text split completed!")

        # update vstores
        if len(df_add) > 0:
            vstore = add_vstore(df_docs_add, vstore, opt)
        if len(remove_ids) > 0:
            vstore.index.remove_ids(remove_ids)
            vstore = reorder_index_to_docstore_id(remove_ids, vstore)

        # update df_docs
        df_docs = pd.concat([df_docs, df_docs_add], ignore_index=True)
        df_docs = df_docs[~df_docs["index"].isin(remove_ids.tolist())]
        df_docs = df_docs.reset_index(drop=True)
        df_docs["index"] = df_docs.index

        with open(base_path, "wb") as f:
            save = {
                "df_file_md5": df_new,
                "df_docs": df_docs,
                "metadata": metadata,
                "vstore": vstore,
            }
            pickle.dump(save, f)
        logger.info("Successfully updated base!")
    else:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, help="base's name")
    args = parser.parse_args()

    update_base(args.name)
