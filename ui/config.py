import gradio as gr
from mygpt import mygpt
import os
import yaml
import openai
import pickle
from utils import logger, get_last_log
from create_base import create_base
from update_base import update_base
from ui import search, ask

opt = mygpt.opt
ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"), "braindoor/")
config_path = os.path.join(USER, "config.yaml")


def load_config():
    with open(config_path, encoding="utf-8") as f:
        opt = yaml.safe_load(f)
    openai.api_key = opt["key"]
    return opt


def reload():
    opt = load_config()
    output = (
        opt["key"],
        opt["rate_limit"],
        opt["search_topk"],
        opt["HyDE"],
        opt["answer_depth"],
        opt["proxy"],
        opt["input_limit"],
        opt["max_context"],
        opt["save_edit"],
    )
    mygpt.load_config()
    return output


def update_config(
    key,
    rate_limit,
    search_topk,
    hyde,
    answer_depth,
    proxy,
    input_limit,
    max_context,
    save_edit,
):
    opt["key"] = key
    opt["rate_limit"] = rate_limit
    opt["search_topk"] = search_topk
    opt["HyDE"] = hyde
    opt["answer_depth"] = answer_depth
    opt["proxy"] = proxy
    opt["input_limit"] = input_limit
    opt["max_context"] = max_context
    opt["save_edit"] = save_edit
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(opt, f)
    mygpt.__init__()
    return "Save successfully!"


# for brainshell
def save_config_from_brainshell(key, proxy, input_limit, max_context, save_edit):
    opt["key"] = key
    opt["proxy"] = proxy
    opt["input_limit"] = input_limit
    opt["max_context"] = max_context
    opt["save_edit"] = save_edit
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(opt, f)
    mygpt.__init__()
    logger.info("Save config from brainshell")
    return "Save config from brainshell successfully!"

def get_base_list():
    base_list =sorted((mygpt.bases.keys()))
    return gr.update(choices=base_list)

def get_base_info(base_name):
    base = mygpt.bases[base_name]
    metadata = base["metadata"]
    dir_list = get_dir_list(metadata["paths"])
    return (
        metadata["chunk_size"],
        metadata["chunk_overlap"],
        metadata["max_chunk_num"],
        gr.update(choices=dir_list),
        metadata["paths"],
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(visible=True),
    )


def get_dir_list(state_dir_list: dict):
    dir_list = []
    for k, v in state_dir_list.items():
        dir_list.append(f"{k}:{v}")
    return dir_list


def remove_dir(state_dir_list, dir_name):
    dir_name = dir_name.split(":")[0]
    if len(state_dir_list) > 1:
        del state_dir_list[dir_name]
        info = f"{dir_name} will be removed (take effect after saving confi)."
    else:
        info = "Only one directory cannot be deleted"

    dir_list = get_dir_list(state_dir_list)
    return (
        state_dir_list,
        gr.update(choices=dir_list),
        info,
        gr.update(variant="primary"),
    )


def add_dir(state_dir_list, dir_path, types):
    if len(dir_path) > 0 and len(types) > 0:
        types = (
            str(types)
            .replace("'", "")
            .replace("[", "")
            .replace("]", "")
            .replace(",", "|")
            .replace(" ", "")
        )
        state_dir_list[dir_path] = types
        info = f"{dir_path} will be added (take effect after saving config)."
    else:
        info = "Directory path and file type cannot be empty"
    dir_list = get_dir_list(state_dir_list)
    return (
        state_dir_list,
        gr.update(choices=dir_list),
        info,
        gr.update(variant="primary"),
    )


def save_base_config(base_name, chunk_size, chunk_overlap, max_chunk_num, dir_list):
    base = mygpt.bases[base_name]
    metadata = {
        "name": base_name,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "max_chunk_num": max_chunk_num,
        "paths": dir_list,
    }
    base["metadata"] = metadata
    if not ".base" in base_name:
        base_name = base_name + ".base"
    base_path = os.path.join(ROOT, "bases", base_name)
    with open(base_path, "wb") as f:
        pickle.dump(base, f)
    info = f"Save {base_name} config successfully! {metadata}"
    mygpt.__init__()
    return info, gr.update(variant="secondary")


def run_update_base(base_name):
    try:
        update_base(base_name)
        info = f"Update {base_name} successfully!"
        logger.info(info)
        mygpt.__init__()
        return info
    except Exception as e:
        logger.error(e)
        info = f"Failed to update {base_name}! Error:{e}"
        return info


def run_create_base(base_name, path, types, chunk_size, chunk_overlap, max_chunk_num):
    try:
        types = "|".join(types)
        path = {path: types}
        chunk_size = int(chunk_size)
        chunk_overlap = int(chunk_overlap)
        max_chunk_num = int(max_chunk_num)
        create_base(base_name, path, chunk_size, chunk_overlap, max_chunk_num)
        update_base(base_name)
        mygpt.__init__()
        base_list = sorted((mygpt.bases.keys()))
        base_list_ask = base_list.copy()
        base_list_ask.insert(0, "default")
        info = f"创建成功!"
        return (
            info,
            gr.update(choices=base_list),
            gr.update(choices=base_list),
            gr.update(choices=base_list_ask),
            gr.update(visible=True),
        )
    except Exception as e:
        info = f"Failed to create {base_name}! Error:{e}"
        return info


with gr.Blocks(title="ask") as config_interface:
    base_list = sorted((mygpt.bases.keys()))
    with gr.Accordion("General configuration", open=False):
        cmpt_key = gr.Textbox(value=opt["key"], label="OpenAI api key")
        with gr.Row():
            box_rate_limit = gr.Number(
                value=opt["rate_limit"], label="Rate limit", precision=0
            )
            box_topk = gr.Number(
                value=opt["search_topk"], label="Search topk", precision=0
            )
        with gr.Row().style(equal_height=True):
            box_proxy = gr.Textbox(opt["proxy"], label="Proxy")
            box_answer_depth = gr.Number(opt["answer_depth"], label="Answer depth")
        with gr.Row().style(equal_height=True):
            box_input_limit = gr.Number(
                opt["input_limit"], label="input limit", precision=0
            )
            box_max_context = gr.Number(
                opt["max_context"], label="max_context limit", precision=0
            )
            box_save_edit = gr.Checkbox(opt["save_edit"], label="save edit")
        with gr.Row():
            btn_load = gr.Button("Reload config", variant="primary")
            btn_save = gr.Button("Save config", variant="primary")
            btn_save_from_brainshell = gr.Button(
                "Save config from brainshell", visible=False
            )
    general_configs = [
        cmpt_key,
        box_rate_limit,
        box_topk,
        ask.box_hyde,
        box_answer_depth,
        box_proxy,
        box_input_limit,
        box_max_context,
        box_save_edit,
    ]

    with gr.Accordion("Update existing knowledge base", open=False, elem_id="acc"):
        with gr.Row().style(equal_height=True):
            btn_get_base_list = gr.Button("Get base list", visible=False)
            if len(base_list) > 0:
                box_base_name = gr.Dropdown(base_list, label="Select a knowledge base")
                btn_load_base = gr.Button("Load", elem_id="low_btn1", variant="primary")
                btn_load_base.style(full_width=False)
            else:
                box_base_name = gr.Dropdown(base_list, label="Select a knowledge base")
                btn_load_base = gr.Button(
                    "Load", elem_id="low_btn1", variant="primary", visible=False
                )
                btn_load_base.style(full_width=False)

        with gr.Row():
            box_chunk_size = gr.Number(label="chunk size", value=0)
            box_chunk_overlap = gr.Number(label="chunk overlap", value=0)
            box_max_chunk_num = gr.Number(label="max chunk num", value=0)
        with gr.Row():
            menu_dir = gr.Dropdown(label="Remove existing directory", interactive=True)
            btn_remove_dir = gr.Button(
                "Remove directory", visible=False, elem_id="low_btn2"
            )
            btn_remove_dir.style(full_width=False)
            state_dir_list = gr.State()
        box_add_dir_path = gr.Textbox(
            label="Add a new directory to current knowledge base",
            placeholder="Paste the new directory path you need to add to the base",
        )
        with gr.Row():
            box_types = gr.Checkboxgroup(
                ["txt", "md", "pdf", "html", "docx"], show_label=False
            )
            btn_add_dir = gr.Button("Add directory", visible=False)
            btn_add_dir.style(full_width=False)
        with gr.Row():
            btn_save_base_config = gr.Button(
                "Save base config", visible=False, variant="primary"
            )
            btn_update_base = gr.Button("Update", visible=False, variant="primary")
    with gr.Accordion("Create a new knowledge base", open=False):
        with gr.Row():
            box_base_name_new = gr.Textbox(
                label="Knowledge base name",
                placeholder="Give the new knowledge base a name",
            )
        with gr.Row():
            box_chunk_size_new = gr.Number(label="chunk size", value=2000)
            box_chunk_overlap_new = gr.Number(label="chunk overlap", value=0)
            box_max_chunk_num_new = gr.Number(label="max chunk num", value=10)
        box_add_dir_path_new = gr.Textbox(
            label="Directory",
            placeholder="Paste the first directory path you need to create to the base",
        )
        with gr.Row():
            box_types_new = gr.Checkboxgroup(
                ["txt", "md", "pdf", "html", "docx"], show_label=False
            )
            btn_create_base = gr.Button(
                "Create", visible=True, variant="primary", elem_id="cv"
            )
            btn_create_base.style(full_width=False)

    box_info = gr.Markdown("")
    box_log = gr.Markdown("")

    btn_get_base_list.click(fn=get_base_list, outputs=box_base_name,api_name="get_base_list")

    # save general_configs
    btn_save.click(
        fn=update_config,
        inputs=general_configs,
        outputs=box_info,
    )

    # save general_configs from brainshell
    btn_save_from_brainshell.click(
        fn=save_config_from_brainshell,
        inputs=[cmpt_key, box_proxy, box_input_limit, box_max_context, box_save_edit],
        outputs=box_info,
        api_name="save_config_from_brainshell",
    )

    # load general_configs
    btn_load.click(fn=reload, outputs=general_configs, api_name="general_config")

    # load base for update
    btn_load_base.click(
        fn=get_base_info,
        inputs=box_base_name,
        outputs=[
            box_chunk_size,
            box_chunk_overlap,
            box_max_chunk_num,
            menu_dir,
            state_dir_list,
            btn_remove_dir,
            btn_add_dir,
            btn_update_base,
            btn_save_base_config,
        ],api_name="get_base_info"
    )


    btn_remove_dir.click(
        fn=remove_dir,
        inputs=[state_dir_list, menu_dir],
        outputs=[state_dir_list, menu_dir, box_info, btn_save_base_config],
    )
    btn_add_dir.click(
        fn=add_dir,
        inputs=[state_dir_list, box_add_dir_path, box_types],
        outputs=[state_dir_list, menu_dir, box_info, btn_save_base_config],
    )
    btn_save_base_config.click(
        fn=save_base_config,
        inputs=[
            box_base_name,
            box_chunk_size,
            box_chunk_overlap,
            box_max_chunk_num,
            state_dir_list,
        ],
        outputs=[box_info, btn_save_base_config],
    )
    # update base
    btn_update_base.click(fn=run_update_base, inputs=box_base_name, outputs=box_info, api_name="update_base")
    show_log = btn_update_base.click(fn=get_last_log, outputs=box_log, every=1)
    box_info.change(fn=lambda: "", outputs=box_log, cancels=[show_log, show_log])

    # create base
    btn_create_base.click(
        fn=run_create_base,
        inputs=[
            box_base_name_new,
            box_add_dir_path_new,
            box_types_new,
            box_chunk_size_new,
            box_chunk_overlap,
            box_max_chunk_num_new,
        ],
        outputs=[
            box_info,
            box_base_name,
            search.radio_base_name,
            ask.radio_base_name_ask,
            btn_load_base,
        ],
        api_name="create_base",
    )
    show_log_create = btn_create_base.click(
        fn=get_last_log, outputs=box_log, every=1, api_name="get_log"
    )
    box_info.change(fn=lambda: "", outputs=box_log, cancels=[show_log_create, show_log])
