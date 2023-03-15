import logging
from notifypy import Notify
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

from bs4 import BeautifulSoup


def get_logger(log_path="./run.log"):
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
tiktoken_encoder = tiktoken.get_encoding('cl100k_base')


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
def copy_html(html_path, save_root="temp"):
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
    p = re.compile(r"(```)(.*?)(```)",re.DOTALL)
    #  text = p.sub(lambda m: m.group(1) + html.escape(m.group(2)) + m.group(3), text)
    text = p.sub(lambda m: m.group(1) + html_escape(m.group(2)) + m.group(3), text)
    #  text = text.replace(" ", "&nbsp;")
    text = text.replace("\n", "<br>")
    text = re.sub(r"```(.+?)```", r"<code><div class='codebox'>\1</div></code>", text, flags=re.DOTALL)
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
    with open(filename, "r") as f:
        html = f.read()
        text = html2text.HTML2Text().handle(html)
    return text

def read_text_file(file_path):
    file_type = (Path(file_path).suffix).lower()
    if file_type in [".md", ".txt"]:
        with open(file_path, "r", encoding='utf-8') as f:
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
    with open("run.log", "rb") as f:
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

def send_notify(msg):
    notification = Notify()
    notification.title = "New message"
    notification.message = f"{msg}"
    notification.application_name = 'Braindoor'
    notification.icon = "doc/nao.png"
    notification.send(block=False)
