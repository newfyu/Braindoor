from functools import partial
import gradio as gr
from utils import (
    with_proxy,
    copy_html,
    remove_asklink,
    html2txt,
    txt2html,
    tiktoken_encoder,
    save_chat_history,
    get_history_pages,
    load_context,
    del_page
)
import shutil
from pathlib import Path
from mygpt import mygpt
import os
import uuid

opt = mygpt.opt


@with_proxy(opt["proxy"])
def run_chat(question, history, base_name, chat_id):
    dir_name = "temp"
    # cutoff context
    context = []
    context_len = 0
    for q, a in reversed(history):
        q = str(q)
        a = str(a)
        a = remove_asklink(a)
        a = html2txt(a)
        qa_len = len(tiktoken_encoder.encode(q + a))
        if qa_len + context_len < mygpt.opt["max_context"]:
            context_len += qa_len
            context.insert(0, (q, a))
        else:
            break
    answer, mydocs, _ = mygpt.ask(question, context, base_name)

    links = list()
    i = 1
    path_list = list()
    for doc in mydocs:
        score = doc[1]
        content = doc[0].page_content
        if score < float(mygpt.opt["max_l2"]):
            file_path = Path(doc[0].metadata["file_path"])

            if not os.path.exists("temp"):
                os.mkdir("temp")
            with open(f"./temp/reference-{i}.txt", "w") as f:
                f.write(content)
            if not file_path in path_list:
                if file_path.suffix == ".html":
                    copy_html(file_path)
                else:
                    shutil.copy2(file_path, dir_name)
                links.append(
                    f'<a href="file/temp/reference-{i}.txt" class="asklink" title="Open text snippet {score:.3}">[{i}] </a> '
                )
                links.append(
                    f'<a href="file/temp/{file_path.name}" class="asklink" title="Open full text">{file_path.stem}</a><br>'
                )
                path_list.append(file_path)
            else:
                index = links.index(
                    f'<a href="file/temp/{file_path.name}" class="asklink" title="Open full text">{file_path.stem}</a><br>'
                )
                links.insert(
                    index,
                    f'<a href="file/temp/reference-{i}.txt" class="asklink" title="Open text snippet {score:.3}">[{i}]</a> ',
                )
            i += 1
    links = "".join(links)

    answer = txt2html(answer)
    answer = f"{answer}<br><br>{links}"
    history.append((question, answer))
    save_chat_history(chat_id=chat_id, history=history)

    return history, history, gr.update(value="")

def go_page(current_page, offset, pages):
    current_page += offset
    if current_page >= len(pages) or current_page < 0:
        current_page -= offset
    chat_id = pages[current_page].split(".")[0]
    context = load_context(chat_id)
    return context, context, chat_id, current_page, f"{current_page+1}/{len(pages)}" 

def run_show_answer(question, history):
    if mygpt.temp_result:
        answer = txt2html(mygpt.temp_result)
        _history = history.copy()
        _history.append((question, answer))
        return _history
    else:
        return history


def run_clear_context():
    new_chat_id = uuid.uuid1()
    pages = get_history_pages()
    pages.insert(0, f"{new_chat_id}.json")
    return "", [], new_chat_id, 0, pages, f"1/{len(pages)}" 

def run_del_page(chat_id, pages):
    if f"{chat_id}.json" in pages:
        del_page(chat_id)
        pages.remove(f"{chat_id}.json")
    new_chat_id = uuid.uuid1()
    pages = get_history_pages()
    pages.insert(0, f"{new_chat_id}.json")
    return "", [], new_chat_id, 0, pages, f"1/{len(pages)}",gr.update(value="▶️"), gr.update(visible=False),gr.update(visible=False)

def fold_tool(fold):
    if fold == "▶️":
        fold = "◀️"
        visible = True
    else:
        fold = "▶️"
        visible = False
    return gr.update(value=fold), gr.update(visible=visible),gr.update(visible=visible)

def change_hyde(i):
    mygpt.opt["HyDE"] = i


with gr.Blocks(title="ask") as ask_interface:
    base_list_ask = sorted((mygpt.bases.keys()))
    base_list_ask.insert(0, "default")
    chatbot = gr.Chatbot(elem_id="chatbot", show_label=False)
    chatbot.style(color_map=("Orange", "SteelBlue "))
    state_chat = gr.State([])

    # create new chat id
    chat_id = str(uuid.uuid1())
    state_chat_id = gr.State(chat_id)
    pages = get_history_pages()
    pages.insert(0, f"{chat_id}.json")
    state_pages = gr.State(pages)
    state_current_page = gr.State(0)

    with gr.Row(elem_id="ask_toolbar"):
        btn_clear_context = gr.Button("🆕", elem_id="btn_clear_context")
        btn_clear_context.style(full_width=False)
        btn_fold = gr.Button("▶️", elem_id="btn_fold")
        btn_fold.style(full_width=False)
        btn_stop = gr.Button("⏹️", elem_id="btn_stop", visible=False)
        btn_stop.style(full_width=False)
        btn_del = gr.Button("🗑", elem_id="btn_del", visible=False)
        btn_del.style(full_width=False)
    with gr.Row(elem_id="page_bar"):
        btn_next = gr.Button("<", elem_id="ask_next")
        btn_next.style(full_width=False)
        btn_page = gr.Button(f"1/{len(state_pages.value)}", elem_id="ask_page")
        btn_page.style(full_width=False)
        btn_prev = gr.Button(">", elem_id="ask_prev")
        btn_prev.style(full_width=False)

    chat_inp = gr.Textbox(
        show_label=False, placeholder="Enter text and press enter", lines=1
    )
    chat_inp.style(container=False)
    with gr.Row():
        radio_base_name_ask = gr.Radio(
            base_list_ask, show_label=False, value=base_list_ask[0], interactive=True
        )
        radio_base_name_ask.style(container=False, item_container=False)
        box_hyde = gr.Checkbox(
            value=mygpt.opt["HyDE"], label="HyDE", elem_id="box_hyde", interactive=True
        )
        box_hyde.style(container=True)

    # magic tags
    samples = []
    for tag in mygpt.magictags.keys():
        samples.append([tag])

    box_magictags = gr.Dataset(components=[gr.Textbox(visible=False)],
    label="Magic tag",
    samples=samples)

    def insert_magictag(value,inp):
        inp += f" #{str(value[0])} "
        return inp

    box_magictags.click(fn=insert_magictag,inputs=[box_magictags, chat_inp], outputs=[chat_inp])
    
    


    chatting = chat_inp.submit(
        fn=run_chat,
        inputs=[chat_inp, state_chat, radio_base_name_ask, state_chat_id],
        outputs=[chatbot, state_chat, chat_inp],
        api_name="ask",
    )

    stream_answer = chat_inp.submit(
        fn=run_show_answer, inputs=[chat_inp, state_chat], outputs=[chatbot], every=0.1
    )
    chat_inp.change(fn=lambda: None, cancels=[stream_answer])

    btn_prev.click(
        fn=go_page,
        inputs=[state_current_page, gr.State(1), state_pages],
        outputs=[chatbot, state_chat, state_chat_id, state_current_page, btn_page],
        api_name="ask_prev",
    )
    btn_next.click(
        fn=go_page,
        inputs=[state_current_page, gr.State(-1), state_pages],
        outputs=[chatbot, state_chat, state_chat_id, state_current_page, btn_page],
        api_name="ask_next",
    )

    btn_fold.click(fn=fold_tool,inputs=[btn_fold],outputs=[btn_fold, btn_stop,btn_del])

    btn_del.click(fn=run_del_page,inputs=[state_chat_id, state_pages], outputs=[chatbot, state_chat, state_chat_id, state_current_page, state_pages, btn_page, btn_fold, btn_stop,btn_del])


    btn_clear_context.click(
        fn=run_clear_context,
        outputs=[chatbot, state_chat, state_chat_id, state_current_page, state_pages, btn_page],
        api_name="clear_context",
    )
    btn_stop.click(fn=lambda: None, cancels=[chatting, stream_answer])
    box_hyde.change(fn=change_hyde, inputs=[box_hyde])
