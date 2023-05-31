import logging
import yaml
import os
from pathlib import Path
import re
import shutil
import urllib
import unicodedata
import tiktoken
import docx
import PyPDF2
import html2text
import html
import json
from urllib.parse import quote

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(os.path.expanduser("~"), "braindoor/")
log_path = os.path.join(USER, "run.log")
temp_path = os.path.join(ROOT, "temp/")
HISTORY = os.path.join(USER, "history/")
TEMP = os.path.join(ROOT, "temp")
HOST = "http://127.0.0.1:7860"


def get_logger(log_path=log_path):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = get_logger()
tiktoken_encoder = tiktoken.get_encoding("cl100k_base")


def remove_markdown(text):
    text = re.sub(r"#\s+", "", text)
    text = re.sub(r"(\*|_)\w+(\*|_)", "", text)
    text = re.sub(r"(\*\*|__)\w+(\*\*|__)", "", text)
    text = re.sub(r"~~\w+~~", "", text)
    text = re.sub(r"```.*```", "", text, flags=re.DOTALL)
    text = re.sub(r"`.*`", "", text)
    text = re.sub(r"\[.*\]\(.*\)", "", text)
    text = re.sub(r">\s+", "", text)
    text = re.sub(r"-\s+", "", text)
    text = re.sub(r"\d+\.\s+", "", text)
    return text


def remove_asklink(html):
    html = re.sub(r'<a[^>]*class="asklink"[^>]*>.*?</a>', "", html)
    return html


# This tool copies html files to a temporary directory for viewing
def copy_html(html_path, save_root=temp_path):
    try:
        html_path = Path(html_path)
        html_dir = html_path.parent
        save_root = Path(save_root)
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        img_tags = soup.find_all("img")
        img_urls = []
        for img_tag in img_tags:
            img_url = img_tag["src"]
            img_url = urllib.parse.unquote(img_url)
            if not img_url.startswith("http"):
                img_urls.append(img_url)

        if not os.path.exists(save_root):
            os.makedirs(save_root)

        for img_url in img_urls:
            try:
                dst_dir = save_root.joinpath(Path(img_url).parent)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)

                img_dst_path = os.path.join(save_root, img_url)
                img_src_path = html_dir.joinpath(img_url)

                shutil.copyfile(img_src_path, img_dst_path)
            except Exception as e:
                pass

        shutil.copy2(html_path, save_root)
    except Exception as e:
        print(f"copy html error: {e}")


def with_proxy(proxy_address):
    def wrapper(fn):
        def inner_wrapper(*args, **kwargs):
            if proxy_address:
                os.environ["http_proxy"] = f"{proxy_address}"
                os.environ["https_proxy"] = f"{proxy_address}"
            result = fn(*args, **kwargs)
            if proxy_address:
                del os.environ["http_proxy"]
                del os.environ["https_proxy"]
            return result

        return inner_wrapper

    return wrapper


def html_escape(text):
    text = html.escape(text)
    text = text.replace(" ", "&nbsp;")
    return text


def txt2html(text):
    p = re.compile(r"(```)(.*?)(```)", re.DOTALL)
    #  text = p.sub(lambda m: m.group(1) + html.escape(m.group(2)) + m.group(3), text)
    text = p.sub(lambda m: m.group(1) + html_escape(m.group(2)) + m.group(3), text)
    #  text = text.replace(" ", "&nbsp;")
    text = text.replace("\n", "<br>")
    text = re.sub(
        r"```(.+?)```",
        r"<code><div class='codebox'>\1</div></code>",
        text,
        flags=re.DOTALL,
    )
    #  text = re.sub(r"`(.+?)`", r"<code>\1</code>", text, flags=re.DOTALL)
    return text


def html2txt(text):
    text = text.replace("<code><div class='codebox'>", "```")
    text = text.replace("</div></code>", "```")
    text = text.replace("<br>", "\n")
    text = text.replace("&nbsp;", " ")
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return text


def read_docx(filename):
    doc = docx.Document(filename)
    fullText = []
    for para in doc.paragraphs:
        fullText.append(para.text)
    return "\n".join(fullText)


def read_pdf(filename):
    with open(filename, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        num_pages = len(reader.pages)
        contents = []
        for i in range(0, num_pages):
            page = reader.pages[i]
            contents.append(page.extract_text())
        return "\n".join(contents)


def read_html(filename):
    with open(filename, "r", encoding="utf-8") as f:
        html = f.read()
        text = html2text.HTML2Text().handle(html)
    return text


def read_text_file(file_path):
    file_type = (Path(file_path).suffix).lower()
    if file_type in [".md", ".txt"]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    elif file_type in [".docx"]:
        text = read_docx(file_path)
    elif file_type in [".pdf"]:
        text = read_pdf(file_path)
    elif file_type in [".html"]:
        text = read_html(file_path)
    else:
        raise TypeError("Expected a md,txt,docx,pdf or html file")
    return text


def get_last_log():
    with open(log_path, "rb") as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b"\n":
            f.seek(-2, os.SEEK_CUR)
        last_line = f.readline().decode()
    return last_line


def cutoff_localtext(local_text, max_len=2000):
    code = tiktoken_encoder.encode(local_text)
    if len(code) > max_len:
        code = code[:max_len]
        local_text = tiktoken_encoder.decode(code)
    return local_text


def save_page(chat_id, context, dir="ask"):
    path = Path(f"{HISTORY}/ask")
    if not os.path.exists(path):
        os.makedirs(path)
    with open(Path(f"{HISTORY}/ask/{chat_id}.json"), "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=4)
    if dir == "review":
        path = Path(f"{HISTORY}/{dir}")
        if not os.path.exists(path):
            os.makedirs(path)
        with open(Path(f"{HISTORY}/{dir}/{chat_id}.json"), "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=4)


def save_review_chunk(chat_id, chunks):
    path = Path(f"{HISTORY}/review")
    if not os.path.exists(path):
        os.makedirs(path)
    with open(Path(f"{HISTORY}/review/{chat_id}.chunk"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=4)


def get_history_pages(dir="ask"):
    history_dir = Path(f"{HISTORY}/{dir}")
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)
    history_jsons = sorted(
        [f for f in os.listdir(history_dir) if f.endswith(".json")],
        key=lambda x: os.path.getmtime(os.path.join(history_dir, x)),
        reverse=True,
    )
    return history_jsons


def load_context(chat_id, dir="ask"):
    try:
        with open(Path(f"{HISTORY}/{dir}/{chat_id}.json"), "r", encoding="utf-8") as f:
            context = json.load(f)
    except:
        context = []
    return context


def load_review_chunk(chat_id):
    try:
        with open(
            Path(f"{HISTORY}/review/{chat_id}.chunk"), "r", encoding="utf-8"
        ) as f:
            chunks = json.load(f)
    except:
        chunks = []
    return chunks


def del_page(chat_id, dir="ask"):
    if os.path.exists(Path(f"{HISTORY}/ask/{chat_id}.json")):
        os.remove(Path(f"{HISTORY}/ask/{chat_id}.json"))
    if os.path.exists(Path(f"{HISTORY}/review/{chat_id}.json")):
        os.remove(Path(f"{HISTORY}/review/{chat_id}.json"))
    if os.path.exists(Path(f"{HISTORY}/review/{chat_id}.chunk")):
        os.remove(Path(f"{HISTORY}/review/{chat_id}.chunk"))
        return True
    else:
        return False


def parse_codeblock(text):
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "```" in line:
            if line != "```":
                lines[i] = f'<pre><code class="{lines[i][3:]}">'
            else:
                lines[i] = "</code></pre>"
        else:
            if i > 0:
                lines[i] = "<br/>" + line.replace("<", "&lt;").replace(">", "&gt;")
    return "".join(lines)


def format_chat_text(text):
    if isinstance(text, str):
        text = parse_codeblock(text)
        #  text = md2html(text)
        return text
    elif isinstance(text, list):
        for i, line in enumerate(text):
            text[i][0] = format_chat_text(line[0])
            text[i][1] = format_chat_text(line[1])
        return text


def cutoff_context(context, mygpt):
    truncated_context = []
    context_len = 0
    for q, a in reversed(context):
        q = str(q)
        a = str(a)
        # remove local link
        a = remove_asklink(a)
        # remove etag
        for etag in mygpt.all_etags["name"]:
            q = q.replace(f"#{etag}", "")
        # remove frontslot
        a = re.sub(r"<frontslot>.*?</frontslot>", "", a)
        # remove rearslot
        a = re.sub(r"<rearslot>.*?</rearslot>", "", a)

        qa_len = len(tiktoken_encoder.encode(q + a))
        if qa_len + context_len < mygpt.opt["max_context"]:
            context_len += qa_len
            truncated_context.insert(0, (q, a))
        else:
            break
    return truncated_context


def create_links(mydocs, frontend, dir_name, mygpt):
    links = list()
    i = 1
    path_list = list()
    for doc in mydocs:
        score = doc[1]
        content = doc[0].page_content
        if score < float(mygpt.opt["max_l2"]):
            file_path = Path(doc[0].metadata["file_path"])

            if not os.path.exists(TEMP):
                os.mkdir(TEMP)
            reference_path = os.path.join(TEMP, f"reference-{i}.txt")
            with open(reference_path, "w", encoding="utf-8") as f:
                f.write(content)
            if not file_path in path_list:
                try:
                    if file_path.suffix == ".html":
                        copy_html(file_path)
                    else:
                        shutil.copy2(file_path, dir_name)
                except Exception as e:
                    logger.error(e)
                links.append(
                    f'<a href="{HOST}/file/temp/reference-{i}.txt" class="asklink" title="Open text snippet {score:.3}">[{i}] </a> '
                )
                links.append(
                    f'<a href="{HOST}/file/temp/{file_path.name}" class="asklink" title="Open full text">{file_path.stem}</a><br>'
                )

                path_list.append(file_path)
            else:
                index = links.index(
                    f'<a href="{HOST}/file/temp/{file_path.name}" class="asklink" title="Open full text">{file_path.stem}</a><br>'
                )
                links.insert(
                    index,
                    f'<a href="{HOST}/file/temp/reference-{i}.txt" class="asklink" title="Open text snippet {score:.3}">[{i}]</a> ',
                )
            i += 1
    if len(links) > 0:
        links = "".join(links)
        links = f"<rearslot>{links}</rearslot>"
    else:
        links = ""
    return links


# 更新新版本的配置文件
def update_config(dir_a, dir_b, filename="config.yaml"):
    path_a = os.path.join(dir_a, filename)
    path_b = os.path.join(dir_b, filename)

    if not os.path.exists(path_a):
        print(f"{path_a} does not exist.")
        return

    if not os.path.exists(path_b):
        shutil.copy(path_a, path_b)
    else:
        with open(path_a, "r") as f:
            config_a = yaml.safe_load(f)
        with open(path_b, "r") as f:
            config_b = yaml.safe_load(f)

        # 如果b中存在和a相同的字段，保持不变
        # 如果a中存在b中不存在的字段，那么给b添加该字段和值
        for key, value in config_a.items():
            if key not in config_b:
                config_b[key] = value

        with open(path_b, "w") as f:
            yaml.safe_dump(config_b, f)


# 把根目录下的默认etag文件复制到用户目录下
def update_etag(src_dir, dst_dir):
    filelist = Path(src_dir).rglob("*.*")
    for file in filelist:
        if (
            file.name == ".DS_Store"
            or ".ipynb_checkpoints" in str(file)
            or "__pycache__" in str(file)
        ):
            continue

        src_file = file
        dst_file = str(src_file).replace(src_dir, dst_dir)
        dst_file = Path(dst_file)
        os.makedirs(str(dst_file.parent), exist_ok=True)
        try:
            if not os.path.exists(dst_file):
                shutil.copy2(src_file, dst_file)
        except:
            pass


class TokenSplitter:
    def __init__(self, chunk_size, chunk_overlap, len_fn):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.len_fn = len_fn

    def split_string(self, string, n):
        size = len(string) // n
        pieces = [string[i : i + size] for i in range(0, len(string), size)]
        if len(pieces) > n:
            pieces[-2] += pieces[-1]
            pieces = pieces[:-1]
        return pieces

    def split_text(self, text):
        token_len = self.len_fn(text)
        n_chunk = int(token_len / self.chunk_size) + 1
        n_piece = n_chunk * 10
        pieces = self.split_string(text, n_piece)
        chunks = []
        _chunk = ""
        for i, p in enumerate(pieces):
            if len(tiktoken_encoder.encode(_chunk + p)) > self.chunk_size:
                chunks.append(_chunk)
                _chunk = p
                if self.chunk_overlap > 0:
                    while (
                        len(tiktoken_encoder.encode(pieces[i - 1] + _chunk))
                        < self.chunk_overlap
                    ):
                        _chunk = pieces[i - 1] + _chunk
                        i = i - 1
            else:
                _chunk += p
        chunks.append(_chunk)
        return chunks
