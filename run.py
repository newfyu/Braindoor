import webbrowser
import time
import signal
from utils import logger
import os

from pystray import Icon as icon, Menu as menu, MenuItem as item
from PIL import Image
import sys
import subprocess

p = subprocess.Popen(['python', 'app.py'])
running = True
time.sleep(2)
run_icon = Image.open('doc/nao.png')
stop_icon = Image.open('doc/zzz.png')
logger.info('Launch service')

def run_open():
    url = "http://127.0.0.1:7860"
    webbrowser.open(url)

def run_quit(icon):
    p.terminate()
    icon.stop()
    sys.exit()

def run_switch(icon):
    global running 
    global p
    if running:
        p.terminate()
        running = False
        icon.icon = stop_icon
        icon.update_menu()
        logger.info('Stop service')
    else:
        p = subprocess.Popen(['python', 'app.py'])
        time.sleep(2)
        running = True
        icon.icon = run_icon
        icon.update_menu()
        logger.info('Restart service')

def switch_title(_):
    if running:
        return "Stop"
    else:
        return "Run"

def handler(signum,_):
    if signum == signal.SIGINT:
        p.terminate()


item_open = item("Open", run_open, visible=lambda _:running)
item_switch = item(switch_title, run_switch)
item_quit = item('Quit',run_quit)
signal.signal(signal.SIGINT, handler)

icon('braindoor', icon=run_icon, menu=menu(item_open,item_switch,item_quit)).run()


