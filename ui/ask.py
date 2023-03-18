import gradio as gr
from utils import with_proxy,copy_html, remove_asklink,html2txt,txt2html, tiktoken_encoder, send_notify
import shutil
from pathlib import Path
from mygpt import mygpt
import os
import time

opt = mygpt.opt


@with_proxy(opt['proxy'])
def run_chat(question, history, base_name):
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

            if not os.path.exists('temp'):
                os.mkdir('temp')
            with open(f"./temp/reference-{i}.txt",'w') as f:
                f.write(content)
            if not file_path in path_list:
                if file_path.suffix == ".html":
                    copy_html(file_path)
                else:
                    shutil.copy2(file_path, dir_name)
                links.append(f'<a href="file/temp/reference-{i}.txt" class="asklink" title="Open text snippet {score:.3}">[{i}] </a> ')
                links.append(f'<a href="file/temp/{file_path.name}" class="asklink" title="Open full text">{file_path.stem}</a><br>')
                path_list.append(file_path)
            else:
                index = links.index(f'<a href="file/temp/{file_path.name}" class="asklink" title="Open full text">{file_path.stem}</a><br>')
                links.insert(index,f'<a href="file/temp/reference-{i}.txt" class="asklink" title="Open text snippet {score:.3}">[{i}]</a> ')
            i += 1
    links = "".join(links)

    answer = txt2html(answer)
    answer = f"{answer}<br><br>{links}"
    history.append((question, answer))
    if opt['notify']:
        send_notify(answer[:20]+'...')
    return history, history, gr.update(value="")

def run_show_answer(question, history):
    if mygpt.temp_result:
        answer = txt2html(mygpt.temp_result)
        _history = history.copy()
        _history.append((question, answer))
        return _history
    else:
        return history

def run_clear_context():
    return "", []

def change_hyde(i):
    mygpt.opt["HyDE"]= i

with gr.Blocks(title="ask") as ask_interface:
    base_list_ask = sorted((mygpt.bases.keys()))
    base_list_ask.insert(0, "default")
    chatbot = gr.Chatbot(elem_id="chatbot",show_label=False)
    #  chatbot.style(color_map=("Orange", "DimGray"))
    chatbot.style(color_map=("Orange", "SteelBlue "))
    state_chat = gr.State([])
    btn_clear_context = gr.Button("🔄", elem_id="btn_clear_context")
    btn_clear_context.style(full_width=False)
    btn_stop = gr.Button("⏸️",elem_id="btn_stop")
    btn_stop.style(full_width=False)
    chat_inp = gr.Textbox(
        show_label=False, placeholder="Enter text and press enter", lines=1
    )
    chat_inp.style(container=False)
    with gr.Row():
        radio_base_name_ask = gr.Radio(
            base_list_ask, show_label=False, value=base_list_ask[0], interactive=True
        )
        radio_base_name_ask.style(container=False, item_container=False)
        box_hyde = gr.Checkbox(value=mygpt.opt['HyDE'],label='HyDE',elem_id='box_hyde',interactive=True)
        box_hyde.style(container=True)

    chatting = chat_inp.submit(
        fn=run_chat,
        inputs=[chat_inp, state_chat, radio_base_name_ask],
        outputs=[chatbot, state_chat, chat_inp],
        api_name='ask'
    )
    show_answer = chat_inp.submit(
        fn=run_show_answer,
        inputs=[chat_inp, state_chat],
        outputs=[chatbot],
        every=0.2
    )
    chat_inp.change(fn=lambda:None,  cancels=[show_answer])    
    

    btn_clear_context.click(fn=run_clear_context, outputs=[chatbot, state_chat])
    btn_stop.click(fn=lambda :None, cancels=[chatting,show_answer]) 
    box_hyde.change(fn=change_hyde, inputs=[box_hyde])

