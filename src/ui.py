from prompt_toolkit import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import ProgressBar, clear
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts.progress_bar import formatters
from prompt_toolkit.layout.dimension import D
import time

import vlc

class CmdUI(ProgressBar):
    def __init__(self, player):
        self.player = player

        self.kb = KeyBindings()
        @self.kb.add('c-q')
        def do_stop(event):
            self.player.stop()

        @self.kb.add('right')
        def do_fast_forward(event):
            self.player.fast_forward()

        @self.kb.add('left')
        def do_fast_backard(event):
            self.player.fast_backward()

        @self.kb.add('p')
        def do_play(event):
            self.player.play()

        @self.kb.add('space')
        def _(event):
            do_play(event)

        @self.kb.add('n')
        def do_next(event):
            self.player.next()

        @self.kb.add('N')
        def do_previus(event):
            self.player.previous()

        @self.kb.add('up')
        def do_up_volume(event):
            self.player.up_volume()

        @self.kb.add('down')
        def do_down_volume(event):
            self.player.down_volume()

        @self.kb.add('=')
        def do_add_rate(event):
            self.player.add_rate()

        @self.kb.add('-')
        def do_sub_rate(event):
            self.player.sub_rate()

        @self.kb.add('delete')
        def do_delete(event):
            self.player.drop()

    def loop(self):
        class engine_idle:
            def __init__(self, player):
                self.player = player
            def __len__(self):
                return 1
            def __iter__(self):
                while self.player.state == 'idle':
                    time.sleep(0.1)
                yield

        class engine_play:
            def __init__(self, player):
                self.player = player
            def __len__(self):
                self.total = self.player.media.get_length()//1000
                self.next = 1
                return self.total
            def __iter__(self):
                while True:
                    time.sleep(0.01)
                    self.current = self.player.media.get_time()//1000
                    if self.current >= self.next:
                        yield self.current
                        self.next += 1
                    state = self.player.media.get_state()
                    match state:
                        case vlc.State.Stopped:
                            return
                        case vlc.State.Ended:
                            self.player.next()
                            return

        class PlayTime(formatters.Formatter):
            def __init__(self, player):
                self.player = player
            def format(self, progress_bar, progress, width):
                current_time = self.player.media.get_time() // 1000
                if current_time < 0:
                    minutes = 0
                    seconds = 0
                else:
                    minutes = current_time // 60
                    seconds = current_time % 60
                return f'[{minutes:02d}:{seconds:02d}]'

            def get_width(self, progress_bar):
                return D.exact(7)


        idle_formatters = [
            formatters.Label(),
        ]

        playing_formatters = [
            PlayTime(self.player),
            formatters.Text(' '),
            formatters.Bar(sym_a='=', sym_b='>', sym_c=' '),
            formatters.Text(' '),
        ]

        bottom_toolbar = HTML(' <b>[p]</b> Play/Pause'
                              ' <b>[n]</b> Next'
                              ' <b>[N]</b> Prev'
                              ' <b>[-&gt;]</b> FF'
                              ' <b>[&lt;-]</b> FB'
                              ' <b>[c-c]</b> Exit')

        engine = {
#          'state': [
#               [0] lambda function to get title,
#               [1] formatters,
#               [2] iterator,
#               [3] lambda function to get label,
#           ],
            'idle': [
                lambda : f'Total music: {len(self.player.music_list)}',
                idle_formatters,
                engine_idle(self.player),
                lambda : f'Current idx: {self.player.music_index}',
            ],
            'playing' : [
                lambda : self.player.get_title(),
                playing_formatters,
                engine_play(self.player),
                lambda : '',
            ],
        }

        while self.player.state != 'exit':
            with ProgressBar(key_bindings=self.kb,
                             cancel_callback=self.player.exit,
                             title=engine[self.player.state][0](),
                             formatters=engine[self.player.state][1],
                             bottom_toolbar=bottom_toolbar) as pb:
                for _ in pb(engine[self.player.state][2], label=engine[self.player.state][3]()):
                    pass
        clear()