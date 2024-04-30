from __future__ import annotations

import contextvars
import functools
import os
import time
import signal
import threading
import traceback
from typing import (
    Callable,
    Iterable,
    Sequence,
    TextIO,
    TypeVar,
)

from prompt_toolkit.application import Application, get_app_or_none
from prompt_toolkit.application.current import get_app_session
from prompt_toolkit.filters import Condition, is_done, renderer_height_is_known
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    StyleAndTextTuples,
    to_formatted_text,
)
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import (
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.dimension import AnyDimension, D
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.styles import Style, BaseStyle
from prompt_toolkit import HTML
from prompt_toolkit.utils import in_main_thread

from prompt_toolkit.shortcuts.progress_bar.formatters import Formatter, Bar, Text, create_default_formatters
from prompt_toolkit.shortcuts.progress_bar import ProgressBarCounter
from prompt_toolkit.shortcuts import clear

from prompt_toolkit.widgets import TextArea
from prompt_toolkit.completion import WordCompleter

_T = TypeVar("_T")

E = KeyPressEvent

class MusicRange:
    def __init__(self, player):
        self.player = player
    def __len__(self):
        total = self.player.get_music_length()//1000
        self.next = 1
        return total
    def __iter__(self):
        while True:
            time.sleep(0.01)
            self.current = self.player.get_music_time()//1000
            if self.current >= self.next:
                yield self.current
                self.next += 1

            if self.player.is_end():
                return

class PlayTime(Formatter):
    def __init__(self, player):
        self.player = player
    def format(self, progress_bar, progress, width):
        current_time = self.player.get_music_time() // 1000
        if current_time < 0:
            minutes = 0
            seconds = 0
        else:
            minutes = current_time // 60
            seconds = current_time % 60
        return f'[{minutes:02d}:{seconds:02d}]'

    def get_width(self, progress_bar):
        return D.exact(7)

class PlayerWindow:
    def __init__(
        self,
        player: _T,
        keymap: Iterable[_T],
    ) -> None:
        self.player = player
        self.header = None
        self.title = None
        self.formatters = [
            PlayTime(self.player),
            Text(' '),
            Bar(sym_a='=', sym_b='>', sym_c=' '),
            Text(' '),
        ]
        self.bottom_toolbar = HTML(
            ' <b>[p]</b> Play/Pause'
            ' <b>[n]</b> Next'
            ' <b>[N]</b> Prev'
            ' <b>[-&gt;]</b> FF'
            ' <b>[&lt;-]</b> FB'
            ' <b>[c-c]</b> Exit')
        self.counters: list[ProgressBarCounter[object]] = []
        self.key_bindings = KeyBindings()
        @self.key_bindings.add('c-c')
        def _(event):
            self.player.stop()

        self.keymap = keymap

        # Note that we use __stderr__ as default error output, because that
        # works best with `patch_stdout`.
        self.color_depth = None
        self.output = get_app_session().output
        self.input = get_app_session().input
        self._thread: threading.Thread | None = None
        self._app_started = threading.Event()

    def __enter__(self) -> ProgressBar:
        # Create UI Application.
        header_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(lambda: self.header),
                height=1,
            ),
            filter=Condition(lambda: self.header is not None),
        )

        title_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(lambda: self.title),
                height=1,
                style="class:progressbar,title",
            ),
            filter=Condition(lambda: self.title is not None),
        )

        completer = WordCompleter(self.player.get_all(), ignore_case=True, match_middle=True)
        search_toolbar = TextArea(
            height=1,
            prompt="Search: ",
            style="class:input-field",
            multiline=False,
            wrap_lines=False,
            completer=completer,
        )

        def accept(buff):
            output = search_toolbar.text
            self.player.play_with_title(output)

        search_toolbar.accept_handler = accept

        bottom_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(
                    lambda: self.bottom_toolbar, style="class:bottom-toolbar.text"
                ),
                style="class:bottom-toolbar",
                height=1,
            ),
            filter=~is_done
            & renderer_height_is_known
            & Condition(lambda: self.bottom_toolbar is not None),
        )

        def width_for_formatter(formatter: Formatter) -> AnyDimension:
            # Needs to be passed as callable (partial) to the 'width'
            # parameter, because we want to call it on every resize.
            return formatter.get_width(progress_bar=self)

        progress_controls = [
            Window(
                content=_ProgressControl(self, f, self.keymap),
                width=functools.partial(width_for_formatter, f),
            )
            for f in self.formatters
        ]

        self.style = Style(
            [
                ("input-field", "bg:#000044 #ffffff"),
            ]
        )

        @self.key_bindings.add("/")
        def search(event: E) -> None:
            event.app.layout.focus(search_toolbar)

        @self.key_bindings.add("f3")
        def _(event: E) -> None:
            search(event)

        @self.key_bindings.add("escape")
        def exit_search(event: E) -> None:
            event.app.layout.focus(next(event.app.layout.get_focusable_windows()))

        self.app: Application[None] = Application(
            min_redraw_interval=0.05,
            layout=Layout(
                HSplit(
                    [
                        header_toolbar,
                        title_toolbar,
                        VSplit(
                            progress_controls,
                            height=lambda: D(
                                preferred=len(self.counters), max=len(self.counters)
                            ),
                        ),
                        Window(),
                        search_toolbar,
                        bottom_toolbar,
                    ]
                ),
            ),
            style=self.style,
            key_bindings=self.key_bindings,
            refresh_interval=0.3,
            color_depth=self.color_depth,
            output=self.output,
            input=self.input,
            full_screen=True,
        )

        # Run application in different thread.
        def run() -> None:
            try:
                self.app.run(pre_run=self._app_started.set)
            except BaseException as e:
                traceback.print_exc()
                print(e)

        ctx: contextvars.Context = contextvars.copy_context()

        self._thread = threading.Thread(target=ctx.run, args=(run,))
        self._thread.start()

        return self

    def __exit__(self, *a: object) -> None:
        # Wait for the app to be started. Make sure we don't quit earlier,
        # otherwise `self.app.exit` won't terminate the app because
        # `self.app.future` has not yet been set.
        self._app_started.wait()

        # Quit UI application.
        if self.app.is_running and self.app.loop is not None:
            self.app.loop.call_soon_threadsafe(self.app.exit)

        if self._thread is not None:
            self._thread.join()

    def loop(self):
        while not self.player.is_exit():
            self.player.wait_play()
            self.header = self.player.get_header()
            self.title = self.player.get_title()
            for i in self(MusicRange(self.player), remove_when_done=True):
                pass
        clear()

    def __call__(
        self,
        data: Iterable[_T] | None = None,
        label: AnyFormattedText = "",
        remove_when_done: bool = False,
        total: int | None = None,
    ) -> ProgressBarCounter[_T]:
        """
        Start a new counter.

        :param label: Title text or description for this progress. (This can be
            formatted text as well).
        :param remove_when_done: When `True`, hide this progress bar.
        :param total: Specify the maximum value if it can't be calculated by
            calling ``len``.
        """
        counter = ProgressBarCounter(
            self, data, label=label, remove_when_done=remove_when_done, total=total
        )
        self.counters.append(counter)
        return counter

    def invalidate(self) -> None:
        self.app.invalidate()

def create_key_bindings(keymap: Iterable[_T]) -> KeyBindings:
    """
    Key bindings handled by the progress bar.
    (The main thread is not supposed to handle any key bindings.)
    """
    kb = KeyBindings()
    for key, func in keymap:
        def wrap(func):
            def _do(event: Event) -> None:
                func()
            return _do
        kb.add(key)(wrap(func))

    @kb.add("c-l")
    def _clear(event: E) -> None:
        event.app.renderer.clear()

    return kb

class _ProgressControl(UIControl):
    """
    User control for the progress bar.
    """

    def __init__(
        self,
        progress_bar: ProgressBar,
        formatter: Formatter,
        keymap: Iterable[_T],
    ) -> None:
        self.progress_bar = progress_bar
        self.formatter = formatter
        self._key_bindings = create_key_bindings(keymap)

    def create_content(self, width: int, height: int) -> UIContent:
        items: list[StyleAndTextTuples] = []

        for pr in self.progress_bar.counters:
            try:
                text = self.formatter.format(self.progress_bar, pr, width)
            except BaseException:
                traceback.print_exc()
                text = "ERROR"

            items.append(to_formatted_text(text))

        def get_line(i: int) -> StyleAndTextTuples:
            return items[i]

        return UIContent(get_line=get_line, line_count=len(items), show_cursor=False)

    def is_focusable(self) -> bool:
        return True  # Make sure that the key bindings work.

    def get_key_bindings(self) -> KeyBindings:
        return self._key_bindings