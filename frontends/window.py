"""
The window front end (GUI) of Neuro Blender, made with Tkinter. It has the same colours as the terminal
(frontends/theme.py). It gives the functions that backend/ui.py lists, and it has no logic of its own:
the back end decides what to ask, and it checks the answers.

How it works:
  - The window runs in the main thread. The back end (backend/flow.py) runs in a second thread.
  - The back end sends each message (note, table, image, progress) and each question through a queue.
  - For a question, the back end waits until the user pushes Next (or Back). Then it gets the answer.

The window:
  +--------------------------------------------------------------------------------+
  |  Neuro Blender                                        Enter = next  Esc = back |
  +----------+---------------------------------------+-----------------------------+
  | 1 File   |  the messages: notes, tables, stack   |  the image: the layers, the |
  | 2 Device |                                       |  devices, the views, your   |
  | 3 Stack  +---------------------------------------+  result                     |
  | 4 Render |  the question, its help, your answer  |                             |
  | 5 Labels |  [Back]                       [Next]  |  [<]  2 of 7  [>]    [Open] |
  +----------+---------------------------------------+-----------------------------+
  |  progress bar and what the tool does now                                       |
  +--------------------------------------------------------------------------------+
"""
import copy
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk

from backend import flow
from backend.answers import GoBack, GoToStep, Stop, join_colour, read_colour
from backend.ui import STEPS
from frontends.desktop import open_on_screen, sharp_on_windows
from frontends.forms import PageForm
from frontends.stack_form import StackForm, draw_stack
from frontends.theme import CANARD, FONTS, GREY_ON_WHITE, GROSEILLE, LEMAN, PANEL, PERLE, RED, TAUPE, WHITE, mix

STOPPED = "Stopped. Answers saved for next run."
BACK, STOP, GOTO = "__back__", "__stop__", "__goto__"
IMAGE_ENDINGS = (".png", ".jpg", ".jpeg")


class NoScreen(Exception):
    """The window cannot open (example: no screen)."""


_app = None         # the open window
SHOWS_FORMS = True  # step 3 is one form (backend/ui.py: shows_forms)


# ═════════════════════════════════════════════════════════ the functions for the back end ══
# The back end calls these functions in its own thread. They send the work to the window thread.

def _show(name, *args):
    """Send a message to the window. Do not wait."""
    _app.calls.put((name, args, None))


def _ask(name, *args):
    """Send a question to the window, and wait for the answer."""
    reply = queue.Queue(maxsize=1)
    _app.calls.put((name, args, reply))
    answer = reply.get()
    if isinstance(answer, tuple) and answer[0] == GOTO:  # a click on a step: (GOTO, step number)
        raise GoToStep(answer[1])
    if answer == BACK:
        raise GoBack
    if answer == STOP:
        raise SystemExit(STOPPED)
    return answer


def header(step, title):
    _show("header", step, title)


def section(text):
    _show("section", text)


def steps_with_answers(steps):
    _show("steps_with_answers", steps)


def note(text):
    _show("note", text)


def warn(text):
    _show("warn", text)


def success(text, file=None):
    _show("success", text, file)


def show_path(label, file, open_now=False):
    _show("show_path", label, os.path.abspath(file))


def show_table(columns, rows, title=None):
    _show("table", list(columns), [[(str(cell), getattr(cell, "style", None)) for cell in row] for row in rows], title)


def stack_drawing(layers):
    _show("stack", copy.deepcopy(layers))


class _Working:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        _show("busy", self.text)
        return self

    def __exit__(self, *error):
        _show("idle")


def working(text):
    return _Working(text)


class _Progress:
    def __init__(self, text, total):
        self.text, self.total = text, total

    def __enter__(self):
        _show("progress", self.text, self.total)
        return self

    def __exit__(self, *error):
        _show("idle")

    def advance(self, text=None):
        _show("progress_advance", text)

    def update(self, text):
        _show("progress_text", text)


def progress(text, total):
    return _Progress(text, total)


def ask_text(question, help_text="", default=None, check=None):
    return _ask("ask_text", question, help_text, default, check)


def ask_choice(question, help_text, options, default=None, details=None, side=None):
    return _ask("ask_choice", question, help_text, dict(options), default, details or {}, side or {})


def ask_yes_no(question, help_text="", default="y"):
    return _ask("ask_yes_no", question, help_text, default)


def ask_ticks(question, help_text, options, ticked, check, side=None):
    return _ask("ask_ticks", question, help_text, list(options), list(ticked), check, side or {})


def ask_colour(question, default=None):
    return _ask("ask_colour", question, default)


def edit_stack(layers, make_questions, problems, open_layer=None):
    return _ask("edit_stack", layers, make_questions, problems, open_layer)


def ask_page(help_text, questions, values):
    return _ask("ask_page", help_text, questions, values)


def pick_file(title, start_folder, file_types):
    return _ask("pick_file", title, start_folder, file_types)


def run(mask_file=None):
    """Open the window, and run the back end (backend/flow.py) in a second thread."""
    global _app
    from backend import ui
    _app = App()
    ui.use(sys.modules[__name__])
    _app.start(mask_file)


# ═════════════════════════════════════════════════════════ small parts of the window ══

class FlatButton(tk.Label):
    """A flat button in the colours of the theme (a tk.Button ignores the colours on some computers)."""

    def __init__(self, master, text, command, main=False, **options):
        self.colours = (RED, WHITE, GROSEILLE) if main else (WHITE, TAUPE, PANEL)   # background, text, mouse over
        super().__init__(master, text=text, bg=self.colours[0], fg=self.colours[1], cursor="hand2",
                         highlightthickness=0 if main else 1, highlightbackground=PERLE, **options)
        self.command, self.enabled = command, True
        self.bind("<Button-1>", lambda event: self.enabled and self.command())
        self.bind("<Enter>", lambda event: self.enabled and self.configure(bg=self.colours[2]))
        self.bind("<Leave>", lambda event: self.configure(bg=self.colours[0] if self.enabled else PANEL))

    def enable(self, on=True):
        self.enabled = on
        self.configure(bg=self.colours[0] if on else PANEL, fg=self.colours[1] if on else PERLE,
                       cursor="hand2" if on else "")


class ScrollArea(tk.Frame):
    """A frame with a scroll bar, for long lists. Put the content into .inner."""

    def __init__(self, master, max_height, bg):
        super().__init__(master, bg=bg)
        self.max_height = max_height
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, height=10)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self.fit)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))

    def fit(self, event=None):
        height = self.inner.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, 0, height), height=min(height, self.max_height))
        if height > self.max_height:
            self.bar.pack(side="right", fill="y")
        else:
            self.bar.pack_forget()

    def wheel(self, event):
        if self.inner.winfo_reqheight() > self.max_height:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def show(self, widget):
        """Scroll so that the widget is visible."""
        self.update_idletasks()
        top, height = widget.winfo_y(), self.inner.winfo_reqheight()
        if height > self.max_height:
            first, last = self.canvas.yview()
            if top < first * height or top + widget.winfo_height() > last * height:
                self.canvas.yview_moveto(max(0, top - 10) / height)


# ═════════════════════════════════════════════════════════ the window ══

class App:
    def __init__(self):
        sharp_on_windows()
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            raise NoScreen(str(error))
        root = self.root
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        family = next((f for f in FONTS if f in tkfont.families(root)), "TkDefaultFont")
        self.font = {name: tkfont.Font(root, family=family, size=size, weight=weight) for name, size, weight in (
            ("title", 17, "bold"), ("step", 11, "normal"), ("step bold", 11, "bold"), ("body", 10, "normal"),
            ("bold", 10, "bold"), ("small", 9, "normal"), ("question", 13, "bold"), ("option", 11, "normal"),
            ("heading", 13, "bold"), ("button", 11, "bold"))}
        self.font["mono"] = tkfont.Font(root, family="Consolas" if sys.platform == "win32" else "Courier", size=9)

        self.calls = queue.Queue()          # messages and questions from the back end
        self.reply = None                   # the reply queue of the question that is open now
        self.keys = {}                      # the keys of the question that is open now: {key name: function}
        self.closed = False
        self.final_file = None
        self.links = 0
        self.log_images = []                # the small images in the messages (Tkinter needs a reference)

        root.title("Neuro Blender")
        root.configure(bg=WHITE)
        width, height = int(root.winfo_screenwidth() * 0.82), int(root.winfo_screenheight() * 0.82)
        root.geometry(f"{width}x{height}+{(root.winfo_screenwidth() - width) // 2}+{(root.winfo_screenheight() - height) // 3}")
        screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
        root.minsize(min(self.px(900), int(screen_width * 0.9)), min(self.px(600), int(screen_height * 0.8)))
        self.build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.wheel_target = None            # the long list of the question that is open now (it scrolls)
        root.bind_all("<MouseWheel>", self.wheel)
        icon = tk.PhotoImage(master=root, width=32, height=32)    # the icon of the window: a red square
        icon.put(RED, to=(0, 0, 32, 32))
        icon.put(WHITE, to=(9, 9, 23, 23))
        icon.put(RED, to=(13, 13, 19, 19))
        root.iconphoto(True, icon)
        self.icon = icon
        for key in ("Return", "Escape", "Up", "Down", "Left", "Right", "space", "y", "n"):
            root.bind(f"<{key}>", lambda event, k=key: self.key(k, event))

    def px(self, n):
        """Pixels on a normal screen -> pixels on this screen."""
        return int(n * self.scale)

    def wheel(self, event):
        """The mouse wheel scrolls the long list of the question, when the mouse is on it.
        On a table or a drawing in the messages, it scrolls the messages: the text box scrolls by itself only when
        the mouse is on its text. The step is the same as on the text (the rule of Tk 8.6 for a text box)."""
        under = self.root.winfo_containing(event.x_root, event.y_root)
        target = self.wheel_target
        if target is not None and target.winfo_exists():
            if under is not None and str(under).startswith(str(target)):
                target.wheel(event)
                return
        if under is not None and str(under).startswith(str(self.log) + "."):
            pixels = -event.delta // 3 if event.delta >= 0 else (2 - event.delta) // 3
            self.log.yview_scroll(pixels, "pixels")

    # ── building the window ──

    def build(self):
        root, px, font = self.root, self.px, self.font
        top = tk.Frame(root, bg=WHITE, padx=px(20), pady=px(12))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(top, text="Neuro Blender", font=font["title"], fg=RED, bg=WHITE).pack(side="left")
        tk.Label(top, text="Enter = next      Esc = back", font=font["small"], fg=GREY_ON_WHITE,
                 bg=WHITE).pack(side="right")
        tk.Frame(root, bg=PERLE, height=1).grid(row=1, column=0, columnspan=2, sticky="ew")

        # The steps (left).
        side = tk.Frame(root, bg=WHITE, padx=px(14), pady=px(16))
        side.grid(row=2, column=0, sticky="ns")
        self.step_labels = []
        self.current_step = 1
        for number, (name, _) in enumerate(STEPS, start=1):
            label = tk.Label(side, text=f"  {number}   {name}", font=font["step"], fg=PERLE, bg=WHITE, anchor="w",
                             width=12, pady=px(7))
            label.pack(fill="x", pady=px(2))
            label.bind("<Button-1>", lambda e, n=number: self.go_to_step(n))
            self.step_labels.append(label)
        self.answered = set()                  # the steps with saved answers: they can be clicked
        self.finished = False                  # True at the end of a run: a click on a step starts a new run

        # The middle (the messages above the question) and the image (right).
        panes = tk.PanedWindow(root, orient="horizontal", bg=PERLE, sashwidth=px(4), bd=0)
        panes.grid(row=2, column=1, sticky="nsew")
        middle = tk.Frame(panes, bg=WHITE)
        right = tk.Frame(panes, bg=WHITE)
        panes.add(middle, minsize=px(460), stretch="always")
        panes.add(right, minsize=px(300), stretch="always")
        root.after(300, lambda: panes.sash_place(0, int(panes.winfo_width() * 0.5), 0))

        # The question panel is packed first, at the bottom: it always gets its full height. The messages get the rest.
        card = self.card = tk.Frame(middle, bg=PANEL, padx=px(20), pady=px(14))
        card.pack(side="bottom", fill="x")
        tk.Frame(middle, bg=PERLE, height=1).pack(side="bottom", fill="x")
        log_frame = self.log_frame = tk.Frame(middle, bg=WHITE)
        log_frame.pack(fill="both", expand=True)
        self.middle, self.form, self.drawer, self.images_title = middle, None, None, ""
        self.log = tk.Text(log_frame, wrap="word", bg=WHITE, fg=TAUPE, font=font["body"], bd=0, padx=px(18),
                           pady=px(12), highlightthickness=0, cursor="arrow", spacing1=px(2), spacing3=px(2))
        bar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set, state="disabled")
        bar.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        for tag, options in {
                "step": dict(font=font["heading"], foreground=RED, spacing1=px(14), spacing3=px(4)),
                "section": dict(font=font["bold"], foreground=RED, spacing1=px(10)),
                "note": dict(foreground=GREY_ON_WHITE),
                "warn title": dict(font=font["bold"], foreground=RED, spacing1=px(6)),
                "warn": dict(foreground=RED, lmargin1=px(12), lmargin2=px(12)),
                "success": dict(font=font["heading"], foreground=LEMAN, spacing1=px(12)),
                "question": dict(foreground=TAUPE, spacing1=px(6)),
                "answer": dict(font=font["bold"], foreground=LEMAN),
                "mono": dict(font=font["mono"], foreground=GREY_ON_WHITE)}.items():
            self.log.tag_configure(tag, **options)

        # The question panel.
        self.q_title = tk.Label(card, font=font["question"], fg=TAUPE, bg=PANEL, anchor="w", justify="left")
        self.q_title.pack(fill="x")
        self.q_help = tk.Label(card, font=font["body"], fg=GREY_ON_WHITE, bg=PANEL, anchor="w", justify="left")
        self.q_help.pack(fill="x")                         # packed only when it has a text (see set_text)
        self.q_body = tk.Frame(card, bg=PANEL)
        self.q_body.pack(fill="x", pady=(px(8), 0))
        self.q_error = tk.Label(card, font=font["body"], fg=RED, bg=PANEL, anchor="w", justify="left")
        buttons = self.buttons_row = tk.Frame(card, bg=PANEL)
        buttons.pack(fill="x", pady=(px(10), 0))
        self.back_button = FlatButton(buttons, "Back", self.back, font=font["button"], padx=px(18), pady=px(6))
        self.back_button.pack(side="left")
        self.next_button = FlatButton(buttons, "Next", self.next, main=True, font=font["button"], padx=px(26),
                                      pady=px(6))
        self.next_button.pack(side="right")
        self.extra_buttons = tk.Frame(buttons, bg=PANEL)
        self.extra_buttons.pack(side="right", padx=px(8))
        card.bind("<Configure>", lambda e: [w.configure(wraplength=e.width - px(40))
                                            for w in (self.q_title, self.q_help, self.q_error)])

        # The image (right).
        self.image_title = tk.Label(right, font=font["bold"], fg=TAUPE, bg=WHITE, anchor="w", padx=px(14), pady=px(8))
        self.image_title.pack(fill="x")
        self.canvas = tk.Canvas(right, bg=WHITE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw_image())
        controls = tk.Frame(right, bg=WHITE, padx=px(12), pady=px(8))
        controls.pack(fill="x")
        self.prev_button = FlatButton(controls, " < ", lambda: self.turn_page(-1), font=font["button"], padx=px(8))
        self.page_label = tk.Label(controls, font=font["small"], fg=GREY_ON_WHITE, bg=WHITE, padx=px(8))
        self.next_page_button = FlatButton(controls, " > ", lambda: self.turn_page(1), font=font["button"], padx=px(8))
        self.open_button = FlatButton(controls, "Open image", lambda: self.images and open_on_screen(
            self.images[self.page]), font=font["small"], padx=px(10), pady=px(3))
        self.images, self.page, self.picture, self.photo = [], 0, None, None

        # The status line (bottom).
        tk.Frame(root, bg=PERLE, height=1).grid(row=3, column=0, columnspan=2, sticky="ew")
        status = tk.Frame(root, bg=WHITE, padx=px(16), pady=px(6))
        status.grid(row=4, column=0, columnspan=2, sticky="ew")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Red.Horizontal.TProgressbar", background=RED, troughcolor=PANEL, bordercolor=PERLE,
                        lightcolor=RED, darkcolor=RED, thickness=px(10))
        style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=WHITE, bordercolor=WHITE,
                        arrowcolor=GREY_ON_WHITE)
        self.bar = ttk.Progressbar(status, style="Red.Horizontal.TProgressbar", length=px(260), mode="determinate")
        self.status = tk.Label(status, font=font["small"], fg=GREY_ON_WHITE, bg=WHITE, anchor="w", padx=px(10))
        self.status.pack(side="left", fill="x", expand=True)

        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(1, weight=1)
        self.no_question("Starting ...")
        self.show_images([], "")
        self.paint_steps(1)
        self.write("Exploded view of an implant, from its mask file.\n"
                   "Click an answer, then Next. Each answer is saved.\n", "note")

    # ── the back end thread ──

    def start(self, mask_file):
        threading.Thread(target=self.work, args=(mask_file,), daemon=True).start()
        self.root.after(30, self.poll)
        self.root.after(200, self.come_to_front)
        self.root.mainloop()

    def come_to_front(self):
        """Show the window above the other windows, with the keys (Enter, Esc) active. Windows does not give the
        front to a program that a start file opens (a double-click): without this, the window opens behind the
        other windows. "Always on top" for a moment puts it in front."""
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(500, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def start_again(self, go_to=None):
        """Run the work again with the same mask file. go_to: a step to open at once with the saved answers."""
        self.write("\nNew run\n", "step")
        self.final_file, self.finished = None, False
        self.extra_buttons.pack_configure(side="right", padx=self.px(8))
        self.back_button.pack(side="left", before=self.extra_buttons)
        self.next_button.configure(text="Next")
        self.next_button.command = self.next
        self.paint_steps(1)
        self.no_question("Starting ...")
        threading.Thread(target=self.work, args=(flow.LAST_MASK_FILE, go_to), daemon=True).start()

    def work(self, mask_file, go_to=None):
        """The back end thread: do all the work, then tell the window how it ended."""
        try:
            final = flow.run(mask_file, go_to)
            self.calls.put(("finished", (final,), None))
        except Stop as problem:                           # a problem that ends the run (back end)
            self.calls.put(("stopped", (str(problem),), None))
        except SystemExit as stop:                        # the window closed during a question
            self.calls.put(("stopped", (str(stop.code or "").strip(),), None))
        except Exception:
            self.calls.put(("crashed", (traceback.format_exc(),), None))

    def poll(self):
        """Do the messages and questions from the back end (in the window thread)."""
        if self.closed:
            return
        try:
            while True:
                name, args, reply = self.calls.get_nowait()
                try:
                    method = getattr(self, "do_" + name)
                    method(*args) if reply is None else method(*args, reply=reply)
                except Exception:                           # an error in the window: show it, stop the back end
                    self.write("Window cannot show this message. Details:\n", "warn title")
                    self.write(traceback.format_exc() + "\n", "mono")
                    if reply is not None:
                        reply.put(STOP)
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    def close(self):
        """The user closes the window: stop the back end and Blender."""
        self.closed = True
        if self.reply is not None:
            self.reply.put(STOP)
        flow.stop()
        self.root.destroy()

    # ── the messages ──

    def write(self, text, *tags):
        self.log.configure(state="normal")
        self.log.insert("end", text, tags)
        self.log.configure(state="disabled")
        self.log.see("end")

    def embed(self, widget):
        self.log.configure(state="normal")
        self.log.window_create("end", window=widget, padx=self.px(18))
        self.log.insert("end", "\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def link(self, label, file):
        """A line with a link: a click opens the file or the folder."""
        self.links += 1
        tag = f"link {self.links}"
        self.log.tag_configure(tag, foreground=CANARD, underline=True)
        self.log.tag_bind(tag, "<Button-1>", lambda e: open_on_screen(file))
        self.log.tag_bind(tag, "<Enter>", lambda e: self.log.configure(cursor="hand2"))
        self.log.tag_bind(tag, "<Leave>", lambda e: self.log.configure(cursor="arrow"))
        self.write(label + " ", "note")
        self.write(os.path.basename(file.rstrip("\\/")) or file, tag)
        self.write("\n")

    def can_open(self, step):
        """True if a click on this step can open it: the current step, a step before it, or a step with answers."""
        return step <= self.current_step or step in self.answered

    def paint_steps(self, step):
        """The current step: white on red. The steps that can open (done, or with saved answers): dark red, they
        can be clicked. The other steps: grey."""
        self.current_step = step
        for number, label in enumerate(self.step_labels, start=1):
            if number == step:
                label.configure(bg=RED, fg=WHITE, font=self.font["step bold"], cursor="hand2")
            else:
                label.configure(bg=WHITE, fg=GROSEILLE if self.can_open(number) else PERLE, font=self.font["step"],
                                cursor="hand2" if self.can_open(number) else "")

    def do_steps_with_answers(self, steps):
        self.answered = set(steps)
        self.paint_steps(self.current_step)

    def go_to_step(self, step):
        """A click on a step: the back end asks the questions of that step again (old answers = defaults).
        At the end of a run: a new run opens that step with the saved answers."""
        if self.finished and 2 <= step <= 4 and step in self.answered:
            self.start_again(go_to=step)
            return
        if self.reply is None or not self.can_open(step):
            return
        reply = self.reply
        self.write(f"Go to step {step}: {STEPS[step - 1][0]}\n", "note")
        self.no_question("Going to step ...")
        reply.put((GOTO, step))

    def do_header(self, step, title):
        self.paint_steps(step)
        self.write(f"Step {step}: {title}\n", "step")

    def do_section(self, text):
        self.write(text + "\n", "section")

    def do_note(self, text):
        self.write(text + "\n", "note")

    def do_warn(self, text):
        self.write("Warning\n", "warn title")
        self.write(text + "\n", "warn")

    def do_success(self, text, file):
        self.write(text + "\n", "success")
        if file:
            self.final_file = file
            self.link("Image:", file)
            self.link("Folder:", os.path.dirname(file))
            self.show_images([file], "Exploded view")

    def do_show_path(self, label, file):
        self.link(label, file)
        if file.lower().endswith(IMAGE_ENDINGS) and os.path.exists(file):
            self.show_images([file], label.rstrip(":"))
        elif os.path.isdir(file):
            images = sorted(os.path.join(file, f) for f in os.listdir(file) if f.lower().endswith(IMAGE_ENDINGS))
            if images:
                self.show_images(images, label.rstrip(":"))

    def do_table(self, columns, rows, title):
        px = self.px
        frame = tk.Frame(self.log, bg=WHITE)
        row_number = 0
        if title:
            tk.Label(frame, text=title, font=self.font["bold"], fg=TAUPE, bg=WHITE).grid(
                row=0, column=0, columnspan=len(columns), sticky="w", pady=(0, px(4)))
            row_number = 1
        right = {"#", "closed", "open", "shapes"}
        for c, name in enumerate(columns):
            tk.Label(frame, text=name, font=self.font["bold"], fg=GREY_ON_WHITE, bg=WHITE).grid(
                row=row_number, column=c, sticky="e" if name in right else "w", padx=(0, px(18)))
        tk.Frame(frame, bg=PERLE, height=1).grid(row=row_number + 1, column=0, columnspan=len(columns), sticky="ew")
        for r, row in enumerate(rows, start=row_number + 2):
            for c, (text, style) in enumerate(row):
                colour = {"faded": PERLE, "alert": RED}.get(style, TAUPE)
                tk.Label(frame, text=text, font=self.font["body"], fg=colour, bg=WHITE).grid(
                    row=r, column=c, sticky="e" if columns[c] in right else "w", padx=(0, px(18)))
        self.embed(frame)

    def do_stack(self, layers):
        """The stack, top to bottom: one bar in the colour of each material (mixed with white if transparent),
        the material, and for the first material of each layer: the layer name, its type and its openings."""
        if not layers:
            return
        width = max(self.log.winfo_width() - self.px(60), self.px(520))
        canvas = tk.Canvas(self.log, width=width, height=10, bg=WHITE, highlightthickness=0)
        canvas.configure(height=draw_stack(canvas, layers, self.font, self.px, width))
        self.write("Stack (top to bottom)\n", "section")
        self.embed(canvas)

    def do_busy(self, text):
        self.bar.configure(mode="indeterminate")
        self.bar.pack(side="left", before=self.status)
        self.bar.start(12)
        self.status.configure(text=text)
        self.no_question(text)

    def do_progress(self, text, total):
        self.bar.stop()
        self.bar.configure(mode="determinate", maximum=max(total, 1), value=0)
        self.bar.pack(side="left", before=self.status)
        self.status.configure(text=text)
        self.no_question(text)

    def do_progress_advance(self, text):
        self.bar.configure(value=min(float(self.bar.cget("value")) + 1, float(self.bar.cget("maximum"))))
        if text:
            self.status.configure(text=text)
            self.q_title.configure(text=text)

    def do_progress_text(self, text):
        self.status.configure(text=text)
        self.q_title.configure(text=text)

    def do_idle(self):
        self.bar.stop()
        self.bar.pack_forget()
        self.status.configure(text="")

    # ── the image (right) ──

    def show_drawing(self, title, drawer):
        """Show a drawing in the image pane in place of the images. drawer(canvas, width) draws it."""
        self.drawer = drawer
        self.image_title.configure(text=title)
        for widget in (self.prev_button, self.page_label, self.next_page_button, self.open_button):
            widget.pack_forget()
        self.draw_image()

    def show_images(self, files, title):
        self.images, self.page, self.images_title = files, 0, title
        self.image_title.configure(text=title)
        many = len(files) > 1
        for widget in (self.prev_button, self.page_label, self.next_page_button, self.open_button):
            widget.pack_forget()
        if many:
            self.prev_button.pack(side="left")
            self.page_label.pack(side="left")
            self.next_page_button.pack(side="left")
        if files:
            self.open_button.pack(side="right")
        self.load_page()

    def show_option_image(self, value):
        """If the images on the right are the images of the mask layers (01_OUTLINE.png ...), show the image of
        this mask layer."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(value))
        for n, file in enumerate(self.images):
            name = os.path.basename(file)
            if name.split("_", 1)[-1] == safe + ".png" and n != self.page:
                self.page = n
                self.load_page()
                return

    def turn_page(self, step):
        if self.images:
            self.page = (self.page + step) % len(self.images)
            self.load_page()

    def load_page(self):
        self.picture = None
        if self.images:
            try:
                from PIL import Image
                self.picture = Image.open(self.images[self.page])
                self.picture.load()
            except Exception:
                self.picture = None
            self.page_label.configure(text=f"{self.page + 1} of {len(self.images)}   "
                                           f"{os.path.basename(self.images[self.page])}")
        self.draw_image()

    def draw_image(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if self.drawer is not None:
            self.drawer(canvas, width)
            return
        if self.picture is None:
            canvas.create_text(width / 2, height / 2, fill=GREY_ON_WHITE, font=self.font["body"], width=width * 0.7,
                               text="" if self.images else
                               "Images show here: layers, devices, views, result.")
            return
        from PIL import Image, ImageTk
        picture = self.picture.copy()
        if picture.mode in ("RGBA", "LA", "P"):                    # transparent parts: on white
            picture = picture.convert("RGBA")
            background = Image.new("RGBA", picture.size, WHITE)
            background.alpha_composite(picture)
            picture = background.convert("RGB")
        margin = self.px(12)
        picture.thumbnail((max(width - 2 * margin, 10), max(height - 2 * margin, 10)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(picture)
        canvas.create_image(width / 2, height / 2, image=self.photo)

    # ── the questions ──

    def no_question(self, text):
        """No question is open: the back end works. Show what it does."""
        self.close_form()
        self.reply = None
        self.keys = {}
        self.wheel_target = None
        self.clear_body()
        self.q_title.configure(text=text, fg=GREY_ON_WHITE)
        self.set_text(self.q_help, "")
        self.set_text(self.q_error, "")
        self.back_button.enable(False)
        self.next_button.enable(False)

    def set_text(self, label, text):
        """Show the help or the error text of the question. An empty label is not packed: it takes no room."""
        label.configure(text=text)
        if not text:
            label.pack_forget()
        elif label is self.q_help:
            label.pack(fill="x", before=self.q_body)
        else:
            label.pack(fill="x", pady=(self.px(6), 0), before=self.buttons_row)

    def clear_body(self):
        for widget in self.q_body.winfo_children() + self.extra_buttons.winfo_children():
            widget.destroy()
        self.q_body.configure(width=1, height=1)          # an empty frame keeps its old size: make it small again
        self.extra_buttons.configure(width=1, height=1)

    def do_edit_stack(self, layers, make_questions, problems, open_layer, reply):
        """Step 3 as one form, in the middle pane in place of the messages (see frontends/stack_form.py)."""
        self.clear_body()
        self.form = StackForm(self, self.middle, layers, make_questions, problems, open_layer)
        self.log_frame.pack_forget()
        self.form.frame.pack(fill="both", expand=True)
        self.open_question("Stack:", "", reply, self.form.get, show=lambda result: f"{len(result)} layers")
        self.q_title.pack_forget()                         # the form has its own title
        self.wheel_target = self.form.scroll

    def do_ask_page(self, help_text, questions, values, reply):
        """The questions of a page as one form, in the middle pane in place of the messages (frontends/forms.py)."""
        self.clear_body()
        self.form = PageForm(self, self.middle, help_text, questions, values)
        self.log_frame.pack_forget()
        self.form.frame.pack(fill="both", expand=True)
        self.open_question("Values:", "", reply, self.form.get,
                           show=lambda result: ", ".join(str(v) for v in result.values()))
        self.q_title.pack_forget()                         # the form has its own title
        self.wheel_target = self.form.scroll

    def close_form(self):
        """Close the form: the messages come back in the middle pane, the images in the image pane."""
        if self.form is None:
            return
        self.form.frame.destroy()
        self.form, self.drawer = None, None
        self.log_frame.pack(fill="both", expand=True)
        self.q_title.pack(fill="x", before=self.q_help if self.q_help.winfo_manager() else self.q_body)
        self.show_images(self.images, self.images_title)

    def open_question(self, question, help_text, reply, get, check=None, keys=None, show=str):
        """Show a question. get() returns the answer from the widgets. check(answer) returns an error or None.
        show(answer) gives the text of the answer in the messages."""
        self.do_idle()
        self.reply, self.get, self.check, self.shown_answer = reply, get, check, show
        self.keys = keys or {}
        self.question_text = question
        self.q_title.configure(text=question, fg=TAUPE)
        self.set_text(self.q_help, help_text or "")
        self.set_text(self.q_error, "")
        self.back_button.enable(True)
        self.next_button.enable(True)
        self.next_button.configure(text="Next")

    def key(self, name, event):
        if self.reply is None:
            if name == "Return" and self.next_button.enabled:
                self.next_button.command()
            return
        if name == "Return":
            self.next()
        elif name == "Escape":
            self.back()
        elif name in self.keys and not isinstance(event.widget, tk.Entry):
            self.keys[name]()
            return "break"

    def next(self):
        if self.reply is None:
            return
        answer = self.get()
        error = answer if isinstance(answer, Error) else (self.check(answer) if self.check else None)
        if error:
            self.set_text(self.q_error, str(error))
            return
        self.write(self.question_text + "   ", "question")
        self.write(self.shown_answer(answer) + "\n", "answer")
        reply = self.reply
        self.no_question("Working ...")
        reply.put(answer)

    def back(self):
        if self.reply is None:
            return
        reply = self.reply
        self.write("Back\n", "note")
        self.no_question("Going back ...")
        reply.put(BACK)

    # One kind of widget for each kind of question.

    def do_ask_text(self, question, help_text, default, check, reply):
        self.clear_body()
        help_parts = [help_text] if help_text else []
        entry = tk.Entry(self.q_body, font=self.font["option"], relief="solid", bd=1, fg=TAUPE,
                         highlightthickness=1, highlightcolor=RED, highlightbackground=PERLE)
        entry.pack(fill="x", ipady=self.px(4))
        if default is not None:
            entry.insert(0, str(default))
            entry.select_range(0, "end")
        entry.focus_set()

        def get():
            text = entry.get().strip()
            if not text:
                return str(default) if default is not None else Error("Type an answer.")
            return text

        def checked(text):
            return None if (default is not None and text == str(default)) or not check else check(text)
        self.open_question(question, ".  ".join(help_parts), reply, get, checked)

    def option_rows(self, options, details, side, selected, tick=False):
        """The rows of a list: one row for each option, with a mark (a circle, or a box for ticks)."""
        px, font = self.px, self.font
        # The list is in a scroll area: a scroll bar shows only when the list is taller than 42 % of the window.
        holder = ScrollArea(self.q_body, max_height=max(self.px(150), int(self.root.winfo_height() * 0.42)), bg=PANEL)
        parent = holder.inner
        holder.pack(fill="x")
        self.wheel_target = holder
        rows = {}
        for value, text in options:
            row = tk.Frame(parent, bg=PANEL, padx=px(8), pady=px(5), cursor="hand2")
            row.pack(fill="x", pady=px(1))
            mark = tk.Canvas(row, width=px(18), height=px(18), bg=PANEL, highlightthickness=0)
            mark.grid(row=0, column=0, rowspan=2, sticky="n", pady=(px(2), 0))
            title = tk.Label(row, text=text, font=font["option"], fg=TAUPE, bg=PANEL, anchor="w")
            title.grid(row=0, column=1, sticky="w", padx=(px(10), 0))
            parts = [mark, title, row]
            if side.get(value):
                note_label = tk.Label(row, text=side[value], font=font["small"], fg=GREY_ON_WHITE, bg=PANEL)
                note_label.grid(row=0, column=2, sticky="e", padx=(px(16), 0))
                parts.append(note_label)
            if details.get(value):
                detail = tk.Label(row, text=details[value], font=font["small"], fg=GREY_ON_WHITE, bg=PANEL,
                                  anchor="w", justify="left",
                                  wraplength=max(px(280), self.card.winfo_width() - px(120)))
                detail.grid(row=1, column=1, columnspan=2, sticky="w", padx=(px(10), 0))
                parts.append(detail)
            row.grid_columnconfigure(1, weight=1)
            rows[value] = (row, mark, parts)
        return rows, holder

    def paint_rows(self, rows, chosen, active=None, tick=False):
        px = self.px
        for value, (row, mark, parts) in rows.items():
            on = value in chosen
            background = WHITE if on else PANEL
            for widget in parts:
                widget.configure(bg=background)
            row.configure(highlightthickness=1, highlightbackground=RED if value == active else background)
            mark.delete("all")
            s = px(18)
            if tick:
                mark.create_rectangle(px(2), px(2), s - px(2), s - px(2), outline=RED if on else GREY_ON_WHITE,
                                      fill=RED if on else WHITE, width=px(1.5))
                if on:
                    mark.create_line(px(5), px(9), px(8), px(12), px(13), px(5), fill=WHITE, width=px(2))
            else:
                mark.create_oval(px(2), px(2), s - px(2), s - px(2), outline=RED if on else GREY_ON_WHITE,
                                 fill=WHITE, width=px(1.5))
                if on:
                    mark.create_oval(px(6), px(6), s - px(6), s - px(6), outline=RED, fill=RED)

    def do_ask_choice(self, question, help_text, options, default, details, side, reply):
        self.clear_body()
        values = list(options)
        state = {"chosen": default if default in options else values[0]}
        rows, holder = self.option_rows(list(options.items()), details, side, state["chosen"])

        def choose(value, confirm=False):
            state["chosen"] = value
            self.paint_rows(rows, {value})
            self.show_option_image(value)
            if holder:
                holder.show(rows[value][0])
            if confirm:
                self.next()

        def move(step):
            choose(values[(values.index(state["chosen"]) + step) % len(values)])
        for value, (row, mark, parts) in rows.items():
            for widget in parts:
                widget.bind("<Button-1>", lambda e, v=value: choose(v))
                widget.bind("<Double-Button-1>", lambda e, v=value: choose(v, confirm=True))
        choose(state["chosen"])
        self.open_question(question, help_text, reply, lambda: state["chosen"],
                           keys={"Up": lambda: move(-1), "Down": lambda: move(1)}, show=lambda v: options[v])

    def do_ask_yes_no(self, question, help_text, default, reply):
        self.clear_body()
        px = self.px
        state = {"answer": "yes" if default == "y" else "no"}
        buttons = {}
        holder = tk.Frame(self.q_body, bg=PANEL)
        holder.pack(anchor="w")

        def paint():
            for value, button in buttons.items():
                on = value == state["answer"]
                button.colours = (RED, WHITE, GROSEILLE) if on else (WHITE, TAUPE, PANEL)
                button.configure(bg=button.colours[0], fg=button.colours[1])

        def answer(value):
            state["answer"] = value
            paint()
            self.next()

        def toggle():
            state["answer"] = "no" if state["answer"] == "yes" else "yes"
            paint()
        for value in ("yes", "no"):
            buttons[value] = FlatButton(holder, value.capitalize(), lambda v=value: answer(v), font=self.font["button"],
                                        padx=px(30), pady=px(8))
            buttons[value].pack(side="left", padx=(0, px(10)))
        paint()
        self.open_question(question, help_text, reply, lambda: state["answer"],
                           keys={"y": lambda: answer("yes"), "n": lambda: answer("no"), "Left": toggle,
                                 "Right": toggle},
                           show=lambda v: v)

    def do_ask_ticks(self, question, help_text, options, ticked, check, side, reply):
        self.clear_body()
        values = [value for value, _ in options]
        titles = dict(options)
        state = {"ticked": set(ticked), "active": values[0]}
        rows, holder = self.option_rows(options, {}, side, None, tick=True)

        def paint():
            self.paint_rows(rows, state["ticked"], state["active"], tick=True)

        def toggle(value):
            state["active"] = value
            state["ticked"] ^= {value}
            paint()
            self.show_option_image(value)

        def move(step):
            state["active"] = values[(values.index(state["active"]) + step) % len(values)]
            paint()
            self.show_option_image(state["active"])
            if holder:
                holder.show(rows[state["active"]][0])
        for value, (row, mark, parts) in rows.items():
            for widget in parts:
                widget.bind("<Button-1>", lambda e, v=value: toggle(v))
        paint()
        if state["ticked"]:                                   # show the image of the first ticked mask layer
            self.show_option_image(next(v for v in values if v in state["ticked"]))
        self.open_question(question, help_text or "Click boxes to tick (or Space). Then Next.", reply,
                           lambda: [v for v in values if v in state["ticked"]], check,
                           keys={"Up": lambda: move(-1), "Down": lambda: move(1),
                                 "space": lambda: toggle(state["active"])},
                           show=lambda chosen: ", ".join(titles[v] for v in chosen))

    def do_ask_colour(self, question, default, reply):
        self.clear_body()
        px = self.px
        line = tk.Frame(self.q_body, bg=PANEL)
        line.pack(fill="x")
        swatch = tk.Canvas(line, width=px(64), height=px(34), highlightthickness=1, highlightbackground=PERLE, bg=WHITE)
        swatch.pack(side="left")
        text = tk.StringVar(value=default or "")
        entry = tk.Entry(line, textvariable=text, font=self.font["option"], relief="solid", bd=1, fg=TAUPE, width=18,
                         highlightthickness=1, highlightcolor=RED, highlightbackground=PERLE)
        entry.pack(side="left", padx=px(12), ipady=px(4))
        entry.select_range(0, "end")
        entry.focus_set()

        def paint(*_):
            swatch.delete("all")
            picked = read_colour(text.get())
            check = px(8)
            for i in range(0, px(64), check):
                for j in range(0, px(34), check):
                    background = WHITE if (i // check + j // check) % 2 == 0 else PERLE
                    fill = mix(picked[0], background, 1 - picked[1] / 100) if picked else background
                    swatch.create_rectangle(i, j, i + check, j + check, fill=fill, width=0)
        text.trace_add("write", paint)
        paint()

        def window():
            from frontends.colour_window import ColourWindow
            start = read_colour(text.get()) or ("#808080", 0)
            picked = ColourWindow(start[0], start[1], master=self.root).run()
            if picked:
                text.set(join_colour(*picked))
        FlatButton(line, "Colour window ...", window, font=self.font["body"], padx=px(12), pady=px(5)).pack(side="left")

        def get():
            picked = read_colour(text.get())
            if not picked:
                return Error("Type colour name (gold) or hex code (#e3b04b), or use colour window.")
            return join_colour(*picked)
        self.open_question(question, "name or hex code (gold, #e3b04b). Colour window also sets transparency.",
                           reply, get)

    def do_pick_file(self, title, start_folder, file_types, reply):
        file = filedialog.askopenfilename(parent=self.root, title=title, initialdir=start_folder, filetypes=file_types)
        reply.put(file or None)

    # ── the end ──

    def end_buttons(self, title, colour, with_image):
        """The end of a run: Start again, Open the image, Open the folder and Close. (Back has no use here.)"""
        self.no_question(title)
        self.q_title.configure(fg=colour)
        self.back_button.pack_forget()
        buttons = []
        if flow.LAST_MASK_FILE:
            buttons.append(("Start again", self.start_again))
        if with_image and self.final_file:
            buttons += [("Open image", lambda: open_on_screen(self.final_file)),
                        ("Open folder", lambda: open_on_screen(os.path.dirname(self.final_file)))]
        for text, command in buttons:
            FlatButton(self.extra_buttons, text, command, font=self.font["option"], padx=self.px(12),
                       pady=self.px(6)).pack(side="left", padx=(0, self.px(8)))
        self.extra_buttons.pack_configure(side="left", padx=0)
        self.next_button.configure(text="Close")
        self.next_button.command = self.close
        self.next_button.enable(True)
        self.finished = bool(flow.LAST_MASK_FILE)          # a click on a step with answers starts a new run

    def do_finished(self, final):
        self.do_idle()
        self.end_buttons("Your exploded view is ready.", LEMAN, True)

    def do_stopped(self, message):
        self.do_idle()
        self.write((message or STOPPED) + "\n", "warn")
        self.end_buttons(message or STOPPED, RED, False)

    def do_crashed(self, details):
        self.do_idle()
        self.write("Stopped with an error. Details:\n", "warn title")
        self.write(details + "\n", "mono")
        self.end_buttons("Stopped with an error. Details in messages above.", RED, False)


class Error(str):
    """An answer that is not good: the text of the problem (the window shows it under the question)."""
