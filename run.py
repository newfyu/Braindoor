import subprocess
import rumps
import webbrowser


class BrainDoorBar(rumps.App):
    def __init__(self):
        super().__init__("🧠", quit_button=None)
        self.p = subprocess.Popen(['python', 'app.py'])
        self.item_open = rumps.MenuItem("Open",callback=self.run_open)
        self.item_run = rumps.MenuItem("Run",callback=self.run_app)
        self.item_stop = rumps.MenuItem("Stop",callback=self.stop_app)
        self.item_quit = rumps.MenuItem("Quit",callback=self.quit)
        self.menu.add(self.item_open)
        self.menu.add(self.item_stop)
        self.menu.add(self.item_quit)

    def run_open(self,_):
        url = "http://127.0.0.1:7860"
        webbrowser.open(url)

    def run_app(self, _):
        self.p = subprocess.Popen(['python', 'app.py'])
        self.menu.clear()
        self.menu.add(self.item_open)
        self.menu.add(self.item_stop)
        self.menu.add(self.item_quit)
        self.title = "🧠"


    def stop_app(self, _):
        self.p.terminate()
        self.menu.clear()
        self.menu.add(self.item_run)
        self.menu.add(self.item_quit)
        self.title = "🌀"
        

    def quit(self, _):
        self.p.terminate()
        rumps.quit_application()


if __name__ == "__main__":
    BrainDoorBar().run()
