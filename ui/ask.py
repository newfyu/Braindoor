import gradio as gr
from utils import (
    save_page,
    with_proxy,
    get_history_pages,
    load_context,
    del_page,
    cutoff_context,
    create_links
)
from mygpt import mygpt
import os
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"),'braindoor/')
opt = mygpt.opt


@with_proxy(opt["proxy"])
def run_chat(question, history, context, base_name, chat_id, frontend):
    dir_name = "temp"
    truncated_context = cutoff_context(context,mygpt) # 还移除了link和tag

    # 进入模型
    question, answer, mydocs, _ = mygpt.ask(question, truncated_context, base_name)
    links = create_links(mydocs, frontend, dir_name, mygpt)

    if frontend == "gradio":
        format_answer = answer
        format_answer = f"{format_answer}<br><br>{links}"
    else:
        format_answer = answer
        format_answer = f"{format_answer}\n\n{links}"
    format_question = f"{question}"
    history.append((format_question, format_answer))
    context.append((question, answer))

    save_page(chat_id=chat_id, context=context)
    pages = get_history_pages()

    return history, history, context, gr.update(value=""), 0, f"1/{len(pages)}", pages


def go_page(current_page, offset, pages):
    current_page += offset
    if current_page >= len(pages) or current_page < 0:
        current_page -= offset
    chat_id = pages[current_page].split(".")[0]
    context = load_context(chat_id)
    history = context.copy()
    return (
        history,
        history,
        context,
        chat_id,
        current_page,
        f"{current_page+1}/{len(pages)}",
    )


def get_stream_answer(question, history):
    if mygpt.temp_result:
        answer = mygpt.temp_result
        _history = history.copy()
        _history.append((question, answer))
        return _history
    else:
        _history = history.copy()
        _history.append((question, "..."))
        return _history


def run_new_page():
    pages = get_history_pages()
    new_chat_id = uuid.uuid1()
    pages.insert(0, f"{new_chat_id}.json")
    etag_list = mygpt.all_etags
    #  save_page(chat_id=new_chat_id,context=[])
    return "", [], [], new_chat_id, 0, pages, f"1/{len(pages)}", etag_list


def run_del_page(chat_id, pages, current_page):
    if f"{chat_id}.json" in pages:
        del_page(chat_id)
        pages.remove(f"{chat_id}.json")
    #  pages = get_history_pages()
    if len(pages) <= 0:
        new_chat_id = uuid.uuid1()
        pages.insert(0, f"{new_chat_id}.json")
        return "", [], [], new_chat_id, 0, pages, f"1/{len(pages)}"
    elif current_page >= len(pages):
        current_page = len(pages) - 1
    chat_id = pages[current_page].split(".")[0]
    context = load_context(chat_id)
    history = context
    return (
        history,
        history,
        context,
        chat_id,
        current_page,
        pages,
        f"{current_page+1}/{len(pages)}",
    )


def fold_tool(fold):
    if fold == "▶️":
        fold = "◀️"
        visible = True
    else:
        fold = "▶️"
        visible = False
    return gr.update(value=fold), gr.update(visible=visible), gr.update(visible=visible)


def change_hyde(i):
    mygpt.opt["HyDE"] = i

def abort():
    mygpt.abort_msg = True


with gr.Blocks(title="ask") as ask_interface:
    frontend = gr.Textbox(value="gradio", visible=False)
    base_list_ask = sorted((mygpt.bases.keys()))
    base_list_ask.insert(0, "default")

    greet = []
    chatbot = gr.Chatbot(value=greet, elem_id="chatbot", show_label=False)
    #  chatbot.style(color_map=("Orange", "SteelBlue"))
    state_history = gr.State([])  # history储存chatbot的结果，显示的时候经过了html转换
    state_context = gr.State([])  # context存储未格式化的上下文
    etag_list = gr.DataFrame(value=[], visible=False)

    # create new chat id
    chat_id = str(uuid.uuid1())
    state_chat_id = gr.State(chat_id)
    pages = get_history_pages()
    pages.insert(0, f"{chat_id}.json")
    state_pages = gr.State(pages)  # 要用组件储存
    state_current_page = gr.State(0)  # 要用组件存储

    with gr.Row(elem_id="ask_toolbar"):
        btn_new_page = gr.Button("🆕", elem_id="btn_clear_context")
        btn_new_page.style(full_width=False)
        btn_stop = gr.Button("⏹️", elem_id="btn_stop")
        btn_stop.style(full_width=False)
        btn_del = gr.Button("🗑", elem_id="btn_del")
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

    # etags
    samples = []
    for tag in mygpt.all_etags.name:
        samples.append([tag])

    box_etags = gr.Dataset(
        components=[gr.Textbox(visible=False)], label="Extension tags", samples=samples
    )

    def insert_etag(value, inp):
        inp += f" #{str(value[0])} "
        return inp

    box_etags.click(
        fn=insert_etag, inputs=[box_etags, chat_inp], outputs=[chat_inp]
    )

    chatting = chat_inp.submit(
        fn=run_chat,
        inputs=[
            chat_inp,
            state_history,
            state_context,
            radio_base_name_ask,
            state_chat_id,
            frontend,
        ],
        outputs=[
            chatbot,
            state_history,
            state_context,
            chat_inp,
            state_current_page,
            btn_page,
            state_pages,
        ],
        api_name="ask",
    )

    stream_answer = chat_inp.submit(
        fn=get_stream_answer,
        inputs=[chat_inp, state_history],
        outputs=[chatbot],
        every=0.1,
        api_name="get_ask_stream_answer",
    )
    chat_inp.change(fn=lambda: None, cancels=[stream_answer])

    btn_prev.click(
        fn=go_page,
        inputs=[state_current_page, gr.State(1), state_pages],
        outputs=[
            chatbot,
            state_history,
            state_context,
            state_chat_id,
            state_current_page,
            btn_page,
        ],
        api_name="prev_page",
    )
    btn_next.click(
        fn=go_page,
        inputs=[state_current_page, gr.State(-1), state_pages],
        outputs=[
            chatbot,
            state_history,
            state_context,
            state_chat_id,
            state_current_page,
            btn_page,
        ],
        api_name="next_page",
    )

    btn_del.click(
        fn=run_del_page,
        inputs=[state_chat_id, state_pages, state_current_page],
        outputs=[
            chatbot,
            state_history,
            state_context,
            state_chat_id,
            state_current_page,
            state_pages,
            btn_page,
        ],
        api_name="del_page",
    )

    btn_new_page.click(
        fn=run_new_page,
        outputs=[
            chatbot,
            state_history,
            state_context,
            state_chat_id,
            state_current_page,
            state_pages,
            btn_page,
            etag_list,
        ],
        api_name="new_page",
    )
    btn_stop.click(
        fn=abort, cancels=[chatting, stream_answer], api_name="stop"
    )
    box_hyde.change(fn=change_hyde, inputs=[box_hyde])

