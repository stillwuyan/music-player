import vlc
import time
import json
import random
from pathlib import Path

import window
from prompt_toolkit.key_binding import KeyBindings

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
        file = self.music_list[self.music_index]['file']
        self.media = vlc.MediaPlayer(file)
        self.media.play()
        self.state = 'playing'

    def pause(self):
        if self.state == 'playing':
            self.media.pause()

    def stop(self):
        prev_state = self.state
        self.state = 'exit'
        if prev_state == 'playing':
            self.media.stop()

    def is_exit(self):
        return self.state == 'exit'

    def next(self):
        if self.state != 'playing':
            return

        self.media.stop()
        next_flag = True
        while next_flag:
            if self.music_index + 1 >= len(self.music_list):
                self.music_index = 0
            else:
                self.music_index += 1
            next_flag = ('delete' in self.music_list[self.music_index])

        self.play()

    def previous(self):
        if self.state != 'playing':
            return

        self.media.stop()
        prev_flag = True
        while prev_flag:
            if self.music_index <= 0:
                self.music_index = len(self.music_list) - 1
            else:
                self.music_index -= 1
            prev_flag = ('delete' in self.music_list[self.music_index])

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

    def get_title(self):
        total_time = self.media.get_length() // 1000
        minutes = total_time // 60
        seconds = total_time % 60
        music = self.music_list[self.music_index]
        if 'rate' not in music:
            music['rate'] = 0
        return f"[{minutes:02d}:{seconds:02d}] [{music['singer']}] [{music['name']}] [{music['rate']}]"

    def get_count(self):
        return len(self.music_list)

    def get_music_time(self):
        return self.media.get_time()

    def get_music_length(self):
        return self.media.get_length()

    def is_end(self):
        state = self.media.get_state()
        match state:
            case vlc.State.Stopped:
                return True
            case vlc.State.Ended:
                self.next()
                return True
            case _:
                return False

    def wait_play(self):
        while self.media.get_state() != vlc.State.Playing:
            time.sleep(0.01)

    def get_keybindings(self):
        kb = KeyBindings()

        @kb.add('right')
        def do_fast_forward(event):
            self.fast_forward()

        @kb.add('left')
        def do_fast_backard(event):
            self.fast_backward()

        @kb.add('p')
        def do_pause(event):
            self.pause()

        @kb.add('space')
        def _(event):
            do_pause(event)

        @kb.add('n')
        def do_next(event):
            self.next()

        @kb.add('N')
        def do_previus(event):
            self.previous()

        @kb.add('up')
        def do_up_volume(event):
            self.up_volume()

        @kb.add('down')
        def do_down_volume(event):
            self.down_volume()

        @kb.add('=')
        def do_add_rate(event):
            self.add_rate()

        @kb.add('-')
        def do_sub_rate(event):
            self.sub_rate()

        @kb.add('delete')
        def do_delete(event):
            self.drop()

        return kb

    def run(self):
        self.play()
        with window.PlayerWindow(self, self.get_keybindings()) as pb:
            pb.loop()
        self.save_db()
