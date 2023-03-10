import argparse
import os

import gradio as gr

from ui import search, ask, config, review
from mygpt import mygpt


parser = argparse.ArgumentParser()
parser.add_argument("--share", action="store_true", default=False)
app_args = parser.parse_args()


opt = mygpt.opt
with open("ui/style.css", "r", encoding="utf8") as file:
    css = file.read()

with gr.Blocks(css=css, title="Braindoor", elem_id="main_block") as demo:
    gr.Markdown("## 🧠 Braindoor")
    base_list = sorted((mygpt.bases.keys()))
    if opt['enable_search']:
        with gr.Tab("Search"):
            search.search_interface.render()

    if opt['enable_ask']:
        with gr.Tab("Ask"):
            ask.ask_interface.render()

    if opt['enable_review']:
        with gr.Tab("Review"):
            review.reaview_interface.render()

    if opt['enable_config']:
        with gr.Tab("Config", elem_id="tabs"):
            config.config_interface.render()


def load_js():
    GradioTemplateResponseOriginal = gr.routes.templates.TemplateResponse

    def template_response(*args, **kwargs):
        head = f'<script type="text/javascript" src="file={os.path.abspath("ui/script.js")}?{os.path.getmtime("ui/script.js")}"></script>\n'
        res = GradioTemplateResponseOriginal(*args, **kwargs)
        res.body = res.body.replace(b"</head>", f"{head}</head>".encode("utf8"))
        res.init_headers()
        return res

    gr.routes.templates.TemplateResponse = template_response


if __name__ == "__main__":
    load_js()
    demo.queue().launch(share=app_args.share)
