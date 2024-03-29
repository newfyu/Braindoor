import argparse

import os
ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"),'braindoor/')
if not os.path.exists(USER):
    os.makedirs(USER)
from utils import update_etag, update_config
# copy default files to user folder
update_config(ROOT,USER)
update_etag(os.path.join(ROOT, "prompts"), os.path.join(USER, "prompts"))
update_etag(os.path.join(ROOT, "models"), os.path.join(USER, "models"))
update_etag(os.path.join(ROOT, "agents"), os.path.join(USER, "agents"))
update_etag(os.path.join(ROOT, "bases"), os.path.join(USER, "bases"))

import gradio as gr

from ui import search, ask, config
from mygpt import mygpt

parser = argparse.ArgumentParser()
parser.add_argument("--share", action="store_true", default=False)
app_args = parser.parse_args()

opt = mygpt.opt
style_path = os.path.join(ROOT, "ui/style.css")
with open(style_path, "r", encoding="utf8") as file:
    css = file.read()

with gr.Blocks(css=css, title="Braindoor", elem_id="main_block") as demo:
    gr.Markdown("## 🧠 Braindoor")
    base_list = sorted((mygpt.bases.keys()))
    if opt["enable_search"]:
        with gr.Tab("Search"):
            search.search_interface.render()

    if opt["enable_ask"]:
        with gr.Tab("Ask"):
            ask.ask_interface.render()

    #  if opt["enable_review"]:
        #  with gr.Tab("Review"):
            #  review.reaview_interface.render()

    if opt["enable_config"]:
        with gr.Tab("Config", elem_id="tabs"):
            config.config_interface.render()


def load_js():
    GradioTemplateResponseOriginal = gr.routes.templates.TemplateResponse

    def template_response(*args, **kwargs):
        script_path = os.path.join(ROOT, "ui/script.js")
        head = f'<script type="text/javascript" src="file={script_path}?{os.path.getmtime(script_path)}"></script>\n'
        res = GradioTemplateResponseOriginal(*args, **kwargs)
        res.body = res.body.replace(b"</head>", f"{head}</head>".encode("utf8"))
        res.init_headers()
        return res

    gr.routes.templates.TemplateResponse = template_response


if __name__ == "__main__":
    load_js()
    demo.queue().launch(share=app_args.share)
