import gradio as gr
from gradio.helpers import plt
from utils import (
    save_chat_history,
    with_proxy,
    logger,
    read_text_file,
    txt2html,
    get_history_pages,
    save_review_chunk,
    load_context,
    load_review_chunk,
    del_page,
)
from pathlib import Path
from mygpt import mygpt
import uuid

opt = mygpt.opt



def run_clear_context():
    new_chat_id = uuid.uuid1()
    pages = get_history_pages(dir="review")
    pages.insert(0, f"{new_chat_id}.json")
    placeholder = "Wait for file upload"
    return "", [], new_chat_id, 0, pages, f"1/{len(pages)}", gr.update(interactive=False, placeholder=placeholder)


@with_proxy(opt["proxy"])
def run_review(question, context, chunks, chat_id):
    answer = mygpt.review(question, chunks)
    answer = txt2html(answer)
    context.append((question, answer))
    save_chat_history(chat_id, context, dir="review")
    return context, context, ""


def handle_upload_file(file, chat_id, context):
    file_path = file.name
    try:
        text = read_text_file(file_path)
        chunks = mygpt.fulltext_splitter.split_text(text)
        # chunk save
        save_review_chunk(chat_id, chunks)
        info = (f'Can you see this file: <b><div class="filebox">{Path(file_path).name}<br>{len(chunks)} chunk </div>',
                "Yes, you can now ask any questions about the file.")
        
        context.append(info)
        return (
            context,
            context,
            gr.update(
                interactive=True, placeholder="You can now ask questions about the file"
            ),
            chunks,
        )
    except Exception as e:
        logger.error(file_path)
        logger.error("read or split text error:" + str(e))
        return str(e), "", "", []


def run_show_answer(question, history):
    if mygpt.temp_result:
        answer = txt2html(mygpt.temp_result)
        _history = history.copy()
        _history.append((question, answer))
        return _history
    else:
        return history


def go_page(current_page, offset, pages):
    current_page += offset
    if current_page >= len(pages) or current_page < 0:
        current_page -= offset
    chat_id = pages[current_page].split(".")[0]
    context = load_context(chat_id, dir="review")
    chunks = load_review_chunk(chat_id)
    if chunks:
        enable_chat = True
        placeholder = "You can ask questions about the file"
    else:
        enable_chat = False
        placeholder = "wait for file upload"
    return (
        context,
        context,
        chat_id,
        current_page,
        f"{current_page+1}/{len(pages)}",
        chunks,
        gr.update(
            interactive=enable_chat, placeholder=placeholder
        ),
    )


def run_del_page(chat_id, pages):
    if f"{chat_id}.json" in pages:
        del_page(chat_id, dir="review")
        pages.remove(f"{chat_id}.json")
    new_chat_id = uuid.uuid1()
    pages = get_history_pages(dir='review')
    pages.insert(0, f"{new_chat_id}.json")
    chunks = []
    return (
        "",
        [],
        new_chat_id,
        0,
        pages,
        f"1/{len(pages)}",
        gr.update(value="▶️"),
        gr.update(visible=False),
        gr.update(visible=False),
        chunks,
    )


def fold_tool(fold):
    if fold == "▶️":
        fold = "◀️"
        visible = True
    else:
        fold = "▶️"
        visible = False
    return gr.update(value=fold), gr.update(visible=visible), gr.update(visible=visible)


with gr.Blocks(title="review") as reaview_interface:
    # create new chat id
    chat_id = str(uuid.uuid1())
    state_chat_id = gr.State(chat_id)
    pages = get_history_pages(dir="review")
    pages.insert(0, f"{chat_id}.json")
    state_pages = gr.State(pages)
    state_current_page = gr.State(0)

    reviewbot = gr.Chatbot(elem_id="reviewbot", show_label=False)
    reviewbot.style(color_map=("Orange", "SteelBlue "))
    state_chunks = gr.State([])
    state_chat = gr.State([])

    with gr.Row(elem_id="review_toolbar"):
        btn_clear_context = gr.Button("🆕", elem_id="btn_clear_context_review")
        btn_clear_context.style(full_width=False)
        btn_fold = gr.Button("▶️", elem_id="btn_fold_review")
        btn_fold.style(full_width=False)
        btn_stop = gr.Button("⏹️", elem_id="btn_stop_review", visible=False)
        btn_stop.style(full_width=False)
        btn_del = gr.Button("🗑", elem_id="btn_del_review", visible=False)
        btn_del.style(full_width=False)
    with gr.Row(elem_id="page_bar_review"):
        btn_next = gr.Button("<", elem_id="review_next")
        btn_next.style(full_width=False)
        btn_page = gr.Button(f"1/{len(state_pages.value)}", elem_id="review_page")
        btn_page.style(full_width=False)
        btn_prev = gr.Button(">", elem_id="review_prev")
        btn_prev.style(full_width=False)

    with gr.Row():
        chat_inp = gr.Textbox(
            show_label=False,
            placeholder="Wait for file upload",
            interactive=False,
            lines=1,
        )
        chat_inp.style(container=False)
        btn_upload = gr.UploadButton(
            file_types=["file"],
        )
        btn_upload.style(full_width=False)

    reviewing = chat_inp.submit(
        fn=run_review,
        inputs=[chat_inp, state_chat, state_chunks, state_chat_id],
        outputs=[reviewbot, state_chat, chat_inp],
        api_name="review",
    )

    show_answer = chat_inp.submit(
        fn=run_show_answer,
        inputs=[chat_inp, state_chat],
        outputs=[reviewbot],
        every=0.1,
    )
    chat_inp.change(fn=lambda: None, cancels=[show_answer])

    btn_clear_context.click(fn=run_clear_context, outputs=[reviewbot, state_chat, state_chat_id, state_current_page, state_pages, btn_page, chat_inp])

    btn_upload.upload(
        fn=handle_upload_file,
        inputs=[btn_upload, state_chat_id, state_chat],
        outputs=[
            reviewbot,
            state_chat,
            chat_inp,
            state_chunks,
        ],
    )

    btn_prev.click(
        fn=go_page,
        inputs=[state_current_page, gr.State(1), state_pages],
        outputs=[
            reviewbot,
            state_chat,
            state_chat_id,
            state_current_page,
            btn_page,
            state_chunks,
            chat_inp
        ],
        api_name="review_prev",
    )
    btn_next.click(
        fn=go_page,
        inputs=[state_current_page, gr.State(-1), state_pages],
        outputs=[
            reviewbot,
            state_chat,
            state_chat_id,
            state_current_page,
            btn_page,
            state_chunks,
            chat_inp
        ],
        api_name="review_next",
    )

    btn_fold.click(
        fn=fold_tool, inputs=[btn_fold], outputs=[btn_fold, btn_stop, btn_del]
    )
    btn_del.click(
        fn=run_del_page,
        inputs=[state_chat_id, state_pages],
        outputs=[
            reviewbot,
            state_chat,
            state_chat_id,
            state_current_page,
            state_pages,
            btn_page,
            btn_fold,
            btn_stop,
            btn_del,
            state_chunks,
        ],
    )
    btn_stop.click(fn=lambda: None, cancels=[reviewing, show_answer])
