import gradio as gr
from gradio.components import Markdown, Textbox
from utils import with_proxy,copy_html, remove_markdown
import os
import shutil
from pathlib import Path
from mygpt import mygpt

opt = mygpt.opt

def change_search_mode(search_mode):
    if search_mode:
        return {
            box_results_similarity: gr.update(visible=False),
            box_results_keyword: gr.update(visible=True),
        }
    else:
        return {
            box_results_similarity: gr.update(visible=True),
            box_results_keyword: gr.update(visible=False),
        }

@with_proxy(opt['proxy'])
def run_search(query, base_name):
    dir_name = "temp"
    if os.path.isdir(dir_name):
        shutil.rmtree(dir_name)
    os.mkdir(dir_name)

    outputs = []

    for search_mode in ["similarity", "keyword"]:
        results = mygpt.search(query, base_name, search_mode)
        if search_mode == "keyword":
            k = 10
        else:
            k = opt["search_topk"]
        output = ""
        file_paths = set()
        num_result = 0
        for result in results:
            if isinstance(result, tuple):
                score = result[1]
                result = result[0]
            else:
                score = ""
            if num_result < k:
                file_path = Path(result.metadata["file_path"])
                abstract = result.page_content[: opt["result_size"]]
                if not file_path in file_paths:
                    if file_path.suffix == ".html":
                        copy_html(file_path)
                    else:
                        shutil.copy2(file_path, dir_name)

                    file_name = str(file_path.name)
                    file_name = file_name.replace(" ", "%20")
                    abstract = abstract.replace("\n", "    ")
                    abstract = remove_markdown(abstract)

                    output += rf"""
                        ##### [{file_path.stem}](file/temp/{file_name})     
                        <div title="{score:.3}">{abstract}……</div>
                        """
                    file_paths.add(file_path)
                    num_result += 1
        outputs.append(output)
    return outputs[0], outputs[1]

with gr.Blocks(title="search") as search_interface:
    box_search = Textbox(
        lines=1,
        show_label=False,
        placeholder="Search with any natural language",
        elem_id="query",
    )
    box_search.style(container=False)
    base_list = sorted((mygpt.bases.keys()))
    with gr.Row():
        if len(base_list)>0:
            radio_base_name = gr.Radio(
                base_list, show_label=False, value=base_list[0], interactive=True
            )
        else:
            radio_base_name = gr.Radio(
                base_list, show_label=False, interactive=True
            )

        radio_base_name.style(container=False, item_container=False)
        search_mode = gr.Checkbox(False,label='keyword', elem_id='checkbox_search_mode')

    box_results_similarity = Markdown(elem_id="box_results_similarity")
    box_results_keyword = Markdown(visible=False, elem_id="box_results_keyword")
    box_search.submit(
        fn=run_search,
        inputs=[box_search, radio_base_name],
        outputs=[box_results_similarity, box_results_keyword],
        #  api_name="search"
    )
    search_mode.change(
        fn=change_search_mode,
        inputs=search_mode,
        outputs=[box_results_similarity, box_results_keyword],
    )
