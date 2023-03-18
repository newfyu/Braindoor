import gradio as gr
from utils import get_last_log
from utils import with_proxy, logger, read_text_file,txt2html, send_notify
from pathlib import Path
from mygpt import mygpt

opt = mygpt.opt


def run_clear_context():
    return "",[]


@with_proxy(opt['proxy'])
def run_review(question, context, chunks):
    answer = mygpt.review(question, chunks)
    answer = txt2html(answer)
    context.append((question, answer))
    if opt['notify']:
        send_notify(answer[:20]+'...')
    return context, context, ""


def get_text(file):
    file_path = file.name
    try:
        text = read_text_file(file_path)
        chunks = mygpt.fulltext_splitter.split_text(text)
        info = f"{Path(file_path).name} ({len(chunks)} chunk)"
        return (
            info,
            gr.update(
                interactive=True, placeholder="You can now ask questions about the file"
            ),
            chunks,
        )
    except Exception as e:
        logger.error(file_path)
        logger.error("read or split text error:" + str(e))
        return str(e), "", []

def run_show_answer(question, history):
    if mygpt.temp_result:
        answer = txt2html(mygpt.temp_result)
        _history = history.copy()
        _history.append((question, answer))
        return _history
    else:
        return history



with gr.Blocks(title="review") as reaview_interface:
    reviewbot = gr.Chatbot(elem_id="reviewbot", show_label=False)
    reviewbot.style(color_map=("Orange", "SteelBlue "))
    state_chunks = gr.State([])
    state_context = gr.State([])
    btn_clear_context = gr.Button("🔄", elem_id="btn_clear_context_review")
    btn_clear_context.style(full_width=False)
    btn_stop = gr.Button("⏸️", elem_id="btn_stop_review")
    btn_stop.style(full_width=False)
    with gr.Row():
        chat_inp = gr.Textbox(
            show_label=False, placeholder="Wait for file upload", interactive=False, lines=1
        )
        chat_inp.style(container=False)
        btn_upload = gr.UploadButton(
            file_types=["file"],
        )
        btn_upload.style(full_width=False)
    with gr.Box():
        box_info = gr.HTML("")
        box_log = gr.Markdown()

    reviewing = chat_inp.submit(
        fn=run_review,
        inputs=[chat_inp, state_context, state_chunks],
        outputs=[reviewbot, state_context, chat_inp],
        api_name='review'
    )

    show_answer = chat_inp.submit(
        fn=run_show_answer,
        inputs=[chat_inp, state_context],
        outputs=[reviewbot],
        every=0.2
    )
    chat_inp.change(fn=lambda:None,  cancels=[show_answer])    


    btn_clear_context.click(fn=run_clear_context, outputs=[reviewbot, state_context])
    btn_upload.upload(
        fn=get_text,
        inputs=[btn_upload],
        outputs=[
            box_info,
            chat_inp,
            state_chunks,
        ],
    )
    
    show_log = chat_inp.submit(fn=get_last_log, outputs=box_log, every=0.2)
    reviewbot.change(fn=lambda: "", outputs=box_log, cancels=[show_log])
    btn_stop.click(fn=lambda :None, cancels=[reviewing,show_answer])
