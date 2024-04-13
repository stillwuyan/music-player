import vlc
import time
import json
import random
from pathlib import Path

import ui

class LocalPlayer:
    def __init__(self):
        self.media = None
        self.state = 'idle'
        self.music_index = 0
        self.music_list = []
        self.db = None
        self.db_file = 'music_db.json'

    def load_db(self, root_path):
        db_root = Path(root_path)
        self.db_file = db_root / self.db_file
        if self.db_file.exists():
            with open(self.db_file, 'rt', encoding='utf-8') as f:
                self.db = json.load(f)
                self.music_list = [item for item in self.db['music'].values()]
                random.shuffle(self.music_list)
                self.music_index = 0
        else:
            # TODO: need analyze all the music file
            return
            self.music_list = [file for file in db_root.glob('**/*.*') if file.is_file()]

    def save_db(self):
        if self.db:
            with open(self.db_file, 'wt', encoding='utf-8') as f:
                json.dump(self.db, f, ensure_ascii=False)

    def play(self):
        if self.state == 'idle':
            file = self.music_list[self.music_index]['file']
            self.media = vlc.MediaPlayer(file)
            self.media.play()
            self.wait(lambda : self.media.get_state() == vlc.State.Playing)
            self.state = 'playing'
        elif self.state == 'playing':
            self.media.pause()

    def stop(self):
        prev_state = self.state
        self.state = 'idle'
        if prev_state == 'playing':
            self.media.stop()

    def exit(self):
        prev_state = self.state
        self.state = 'exit'
        if prev_state == 'playing':
            self.media.stop()

    def next(self):
        if self.state != 'playing':
            return

        self.media.stop() if self.media else None
        next_flag = True
        while next_flag:
            if self.music_index + 1 >= len(self.music_list):
                self.music_index = 0
            else:
                self.music_index += 1
            next_flag = ('delete' in self.music_list[self.music_index])

        self.state = 'idle'
        self.play()

    def previous(self):
        if self.state != 'playing':
            return

        self.media.stop() if self.media else None
        prev_flag = True
        while prev_flag:
            if self.music_index <= 0:
                self.music_index = len(self.music_list) - 1
            else:
                self.music_index -= 1
            prev_flag = ('delete' in self.music_list[self.music_index])

        self.state = 'idle'
        self.play()

    def fast_forward(self):
        self.media.pause()
        total_time = self.media.get_length()
        current_time = self.media.get_time()
        if (current_time + 5000) > total_time:
            next_time = total_time - 100
        else:
            next_time = current_time + 5000
        self.media.set_time(next_time)
        self.media.play()

    def fast_backward(self):
        self.media.pause()
        current_time = self.media.get_time()
        if (current_time - 5000) < 0:
            next_time = 0
        else:
            next_time = current_time - 5000
        self.media.set_time(next_time)
        self.media.play()

    def up_volume(self):
        vol = self.media.audio_get_volume()
        if vol + 5 > 99:
            new_vol = 99
        else:
            new_vol = vol + 5
        self.media.audio_set_volume(new_vol)

    def down_volume(self):
        vol = self.media.audio_get_volume()
        if vol - 5 < 1:
            new_vol = 1
        else:
            new_vol = vol - 5
        self.media.audio_set_volume(new_vol)

    def add_rate(self):
        music = self.music_list[self.music_index]
        rate = music.setdefault('rate', 0)
        music['rate'] = rate + 1

    def sub_rate(self):
        music = self.music_list[self.music_index]
        rate = music.setdefault('rate', 0)
        music['rate'] = rate - 1

    def drop(self):
        music = self.music_list[self.music_index]
        music['delete'] = 0

    def wait(self, condition):
        while not condition():
            time.sleep(0.01)

    def get_title(self):
        total_time = self.media.get_length() // 1000
        minutes = total_time // 60
        seconds = total_time % 60
        music = self.music_list[self.music_index]
        if 'rate' not in music:
            music['rate'] = 0
        return f"[{minutes:02d}:{seconds:02d}] [{music['singer']}] [{music['name']}] [{music['rate']}]"

    def run(self):
        window = ui.CmdUI(self)
        window.loop()
        self.save_db()
