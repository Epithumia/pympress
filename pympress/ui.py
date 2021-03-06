# -*- coding: utf-8 -*-
#       Copyright 2010 Thomas Jost <thomas.jost@gmail.com>
#
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

"""
:mod:`pympress.ui` -- GUI management
------------------------------------

This module contains the whole graphical user interface of pympress, which is
made of two separate windows: the Content window, which displays only the
current page in full size, and the Presenter window, which displays both the
current and the next page, as well as a time counter and a clock.

Both windows are managed by the :class:`~pympress.ui.UI` class.
"""

from __future__ import print_function

import os, os.path, subprocess
import sys
import time

import pkg_resources

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import GObject, Gtk, Gdk, Pango

#: "Regular" PDF file (without notes)
PDF_REGULAR      = 0
#: Content page (left side) of a PDF file with notes
PDF_CONTENT_PAGE = 1
#: Notes page (right side) of a PDF file with notes
PDF_NOTES_PAGE   = 2

import pympress.document
import pympress.surfacecache
import pympress.util
import pympress.slideselector
try:
    import pympress.vlcvideo
    vlc_enabled = True
except:
    vlc_enabled = False
    print("Warning: video support is disabled")

from pympress.util import IS_POSIX, IS_MAC_OS, IS_WINDOWS

if IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        import _winreg as winreg
else:
    try:
        gi.require_version('GdkX11', '3.0')
        from gi.repository import GdkX11
    except:
        pass

try:
    PermissionError()
except NameError:
    class PermissionError(Exception):
        pass

media_overlays = {}

class UI:
    """ Pympress GUI management.
    """

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: Content window, as a :class:`Gtk.Window` instance.
    c_win = Gtk.Window(Gtk.WindowType.TOPLEVEL)
    #: :class:`~Gtk.AspectFrame` for the Content window.
    c_frame = Gtk.AspectFrame(yalign=0, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = Gtk.Overlay()
    #: :class:`~Gtk.DrawingArea` for the Content window.
    c_da = Gtk.DrawingArea()

    #: Presentation window, as a :class:`Gtk.Window` instance.
    p_win = Gtk.Window(Gtk.WindowType.TOPLEVEL)
    #: :class:`~Gtk.AspectFrame` for the current slide in the Presenter window.
    p_frame_cur = Gtk.AspectFrame(xalign=0, yalign=0, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.DrawingArea` for the current slide in the Presenter window.
    p_da_cur = Gtk.DrawingArea()
    #: Slide counter :class:`~Gtk.Label` for the current slide.
    label_cur = Gtk.Label()
    #: Slide counter :class:`~Gtk.Label` for the last slide.
    label_last = Gtk.Label()
    #: :class:`~Gtk.EventBox` associated with the slide counter label in the Presenter window.
    eb_cur = Gtk.EventBox()
    #: forward keystrokes to the Content window even if the window manager puts Presenter on top
    editing_cur = False
    #: :class:`~Gtk.SpinButton` used to switch to another slide by typing its number.
    spin_cur = None
    #: forward keystrokes to the Content window even if the window manager puts Presenter on top
    editing_cur_ett = False
    #: Estimated talk time :class:`~gtk.Label` for the talk.
    label_ett = Gtk.Label()
    #: :class:`~gtk.EventBox` associated with the estimated talk time.
    eb_ett = Gtk.EventBox()
    #: :class:`~gtk.Entry` used to set the estimated talk time.
    entry_ett = Gtk.Entry()

    #: :class:`~Gtk.AspectFrame` for the next slide in the Presenter window.
    p_frame_next = Gtk.AspectFrame(yalign=0, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.DrawingArea` for the next slide in the Presenter window.
    p_da_next = Gtk.DrawingArea()
    #: :class:`~Gtk.AspectFrame` for the current slide copy in the Presenter window.
    p_frame_pres = Gtk.AspectFrame(yalign=0, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.DrawingArea` for the current slide copy in the Presenter window.
    p_da_pres = Gtk.DrawingArea()

    #: :class:`~Gtk.AspectFrame` for the annotations in the Presenter window.
    p_frame_annot = Gtk.AspectFrame(yalign=0, ratio=4./3., obey_child=False)

    #: Elapsed time :class:`~Gtk.Label`.
    label_time = Gtk.Label()
    #: Clock :class:`~Gtk.Label`.
    label_clock = Gtk.Label()

    #: Time at which the counter was started.
    start_time = 0
    #: Time elapsed since the beginning of the presentation.
    delta = 0
    #: Estimated talk time.
    est_time = 0
    #: Timer paused status.
    paused = True

    #: Fullscreen toggle. By config value, start in fullscreen mode.
    c_win_fullscreen = False

    #: Current :class:`~pympress.document.Document` instance.
    doc = None

    #: Whether to use notes mode or not
    notes_mode = False

    #: Whether to display annotations or not
    annotation_mode = True

    #: number of page currently displayed in Controller window's miniatures
    page_preview_nb = 0

    #: remember DPMS setting before we change it
    dpms_was_enabled = None

    #: track state of preview window
    p_win_maximized = True

    #: :class:`configparser.RawConfigParser` to remember preferences
    config = None

    #: track whether we blank the screen
    blanked = False

    #: The default color of the info labels
    label_color_default = None
    #: The color of the elapsed time label if the estimated talk time is reached
    label_color_ett_reached = None
    #: The color of the elapsed time label if the estimated talk time is exceeded by 2:30 minutes
    label_color_ett_info = None
    #: The color of the elapsed time label if the estimated talk time is exceeded by 5 minutes
    label_color_ett_warn = None

    #: The containing widget for the annotations
    scrolled_window = None
    #: Making the annotations list scroll if it's too long
    scrollable_treelist = Gtk.ScrolledWindow()


    def __init__(self, docpath = None, ett = 0):
        """
        :param docpath: the path to the document to open
        :type  docpath: string
        :param ett: the estimated (intended) talk time
        :type  ett: int
        """
        self.est_time = ett
        self.config = pympress.util.load_config()
        self.blanked = self.config.getboolean('content', 'start_blanked')

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            pympress.util.get_style_provider(),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Document
        self.doc = pympress.document.Document.create(self.on_page_change, docpath or self.pick_file())

        # Use notes mode by default if the document has notes
        self.notes_mode = self.doc.has_notes()

        # Surface cache
        self.cache = pympress.surfacecache.SurfaceCache(self.doc, self.config.getint('cache', 'maxpages'))

        # Make and populate windows
        self.make_cwin()
        self.make_pwin()
        self.setup_screens()

        # Common to both windows
        icon_list = pympress.util.load_icons()
        self.c_win.set_icon_list(icon_list)
        self.p_win.set_icon_list(icon_list)

        # Setup timer
        GObject.timeout_add(250, self.update_time)

        # Connect events
        self.add_events()

        # Show all windows
        self.c_win.show_all()
        self.p_win.show_all()

        # Add media
        self.replace_media_overlays()

        # Queue some redraws
        self.c_overlay.queue_draw()
        self.c_da.queue_draw()
        self.p_da_cur.queue_draw()
        self.p_da_next.queue_draw()
        self.p_da_pres.queue_draw()

        # Necessary to hide the "current slide" thumbnail when not in notes mode
        if not self.notes_mode:
            self.p_frame_pres.set_visible(False)

        self.label_color_default = self.label_time.get_style_context().get_color(Gtk.StateType.NORMAL)


    def make_cwin(self):
        """ Creates and initializes the content window.
        """
        black = Gdk.Color(0, 0, 0)

        # Content window
        self.c_win.set_name('ContentWindow')
        self.c_win.set_title("pympress content")
        self.c_win.set_default_size(1067, 600)
        self.c_win.modify_bg(Gtk.StateType.NORMAL, black)
        self.c_win.add(self.c_frame)

        self.c_frame.modify_bg(Gtk.StateType.NORMAL, black)
        self.c_frame.set_shadow_type(Gtk.ShadowType.NONE)
        self.c_frame.set_property("yalign", self.config.getfloat('content', 'yalign'))
        self.c_frame.set_property("xalign", self.config.getfloat('content', 'xalign'))
        self.c_frame.add(self.c_overlay)

        self.c_overlay.props.margin = 0
        self.c_frame.props.border_width = 0
        self.c_overlay.add(self.c_da)

        self.c_da.props.expand = True
        self.c_da.props.halign = Gtk.Align.FILL
        self.c_da.props.valign = Gtk.Align.FILL
        self.c_da.set_name("c_da")
        if self.notes_mode:
            self.cache.add_widget("c_da", pympress.document.PDF_CONTENT_PAGE)
        else:
            self.cache.add_widget("c_da", pympress.document.PDF_REGULAR)

        pr = self.doc.current_page().get_aspect_ratio(self.notes_mode)
        self.c_frame.set_property("ratio", pr)


    def make_pwin(self):
        """ Creates and initializes the presenter window.
        """
        # Presenter window
        self.p_win.set_name('PresenterWindow')
        self.p_win.set_title("pympress presenter")
        self.p_win.set_default_size(1067, 600)
        self.p_win.set_position(Gtk.WindowPosition.CENTER)

        # Put Menu and Table in VBox
        bigvbox = Gtk.VBox(False, 2)
        self.p_win.add(bigvbox)

        # make & get menu
        bigvbox.pack_start(self.make_menubar(), False, False, 0)

        # panes
        hpaned = self.make_pwin_panes()
        bigvbox.pack_start(hpaned, True, True, 0)

        # bottom row
        bigvbox.pack_start(self.make_pwin_bottom(), False, False, 0)

        # Set relative pane sizes
        # dynamic computation requires to have p_win already visible
        self.p_win.show_all()

        pane_size = self.config.getfloat('presenter', 'slide_ratio')
        avail_size = self.p_frame_cur.get_allocated_width() + self.p_frame_next.get_allocated_width()
        hpaned.set_position(int(round(pane_size * avail_size)))
        self.on_page_change(False)


    def add_events(self):
        """ Connects the events we want to the different widgets.
        """
        self.p_win.connect("destroy", self.save_and_quit)
        self.c_win.connect("destroy", self.save_and_quit)
        self.p_win.connect("delete-event", self.save_and_quit)
        self.c_win.connect("delete-event", self.save_and_quit)

        self.c_da.connect("draw", self.on_draw)
        self.c_da.connect("configure-event", self.on_configure_da)
        self.p_da_cur.connect("draw", self.on_draw)
        self.p_da_cur.connect("configure-event", self.on_configure_da)
        self.p_da_next.connect("draw", self.on_draw)
        self.p_da_next.connect("configure-event", self.on_configure_da)
        self.p_da_pres.connect("draw", self.on_draw)
        self.p_da_pres.connect("configure-event", self.on_configure_da)

        self.p_win.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.p_win.connect("key-press-event", self.on_navigation)
        self.p_win.connect("scroll-event", self.on_navigation)
        self.c_win.connect("window-state-event", self.on_window_state_event)
        self.p_win.connect("window-state-event", self.on_window_state_event)
        self.c_win.connect("configure-event", self.on_configure_win)
        self.p_win.connect("configure-event", self.on_configure_win)

        self.c_win.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.c_win.connect("key-press-event", self.on_navigation)
        self.c_win.connect("scroll-event", self.on_navigation)

        # Hyperlinks
        self.c_da.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.c_da.connect("button-press-event", self.on_link)
        self.c_da.connect("motion-notify-event", self.on_link)

        self.p_da_cur.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.p_da_cur.connect("button-press-event", self.on_link)
        self.p_da_cur.connect("motion-notify-event", self.on_link)


    def make_pwin_panes(self):
        """ Creates and initializes the presenter window's panes.

        :return: the preview panes with current and next slide
        :rtype: :class:`Gtk.Paned`
        """
        # Panes
        hpaned = Gtk.Paned()
        hpaned.set_orientation(Gtk.Orientation.HORIZONTAL)
        if gi.version_info >= (3,16): hpaned.set_wide_handle(True)
        hpaned.set_margin_top(5)
        hpaned.set_margin_bottom(5)
        hpaned.set_margin_left(5)
        hpaned.set_margin_right(5)

        # "Current slide" frame or "Notes" frame
        self.p_frame_cur.set_label("Current slide")
        self.p_frame_cur.get_label_widget().get_style_context().add_class("frame-label")
        self.p_frame_cur.set_margin_right(5)

        hpaned.pack1(self.p_frame_cur, True, True)
        self.p_da_cur.set_name("p_da_cur")
        if self.notes_mode:
            self.cache.add_widget("p_da_cur", PDF_NOTES_PAGE)
        else:
            self.cache.add_widget("p_da_cur", PDF_REGULAR)
        self.p_frame_cur.add(self.p_da_cur)

        # Righthand side container
        right_pane = Gtk.VBox(False, 15)
        right_pane.set_halign(Gtk.Align.FILL)
        right_pane.set_margin_left(5)
        right_pane.set_homogeneous(False)
        right_pane.set_name('right pane')

        # "Current slide" frame (note mode)
        self.p_frame_pres.set_label("Current slide")
        self.p_frame_pres.get_label_widget().get_style_context().add_class("frame-label")
        self.p_da_pres.set_name("p_da_pres")
        self.cache.add_widget("p_da_pres", PDF_CONTENT_PAGE)
        self.p_frame_pres.add(self.p_da_pres)

        right_pane.pack_start(self.p_frame_pres, True, True, 0)

        # "Next slide" frame
        self.p_frame_next.set_label("Next slide")
        self.p_frame_next.get_label_widget().get_style_context().add_class("frame-label")
        self.p_da_next.set_name("p_da_next")
        if self.notes_mode:
            self.cache.add_widget("p_da_next", PDF_CONTENT_PAGE)
        else:
            self.cache.add_widget("p_da_next", PDF_REGULAR)
        self.p_frame_next.add(self.p_da_next)

        right_pane.pack_start(self.p_frame_next, True, True, 0)

        # Annotations
        self.annotation_renderer = Gtk.CellRendererText()
        self.annotation_renderer.props.wrap_mode = Pango.WrapMode.WORD_CHAR

        column = Gtk.TreeViewColumn(None, self.annotation_renderer, text=0)
        column.props.sizing = Gtk.TreeViewColumnSizing.AUTOSIZE
        column.set_fixed_width(1)

        self.scrolled_window = Gtk.TreeView.new_with_model(Gtk.ListStore(str))
        self.scrolled_window.set_headers_visible(False)
        self.scrolled_window.props.fixed_height_mode = False
        self.scrolled_window.props.enable_search = False
        self.scrolled_window.get_selection().set_mode(Gtk.SelectionMode.NONE)
        self.scrolled_window.append_column(column)
        self.scrolled_window.set_size_request(0, 0)

        self.scrollable_treelist.set_hexpand(True)
        self.scrollable_treelist.add(self.scrolled_window)

        self.p_frame_annot.set_label("Annotations")
        self.p_frame_annot.get_label_widget().get_style_context().add_class("frame-label")
        self.p_frame_annot.add(self.scrollable_treelist)

        #right_pane.pack_end(self.scrollable_treelist, False, False, 0)
        right_pane.pack_end(self.p_frame_annot, False, False, 0)

        hpaned.pack2(right_pane, True, True)

        return hpaned


    def make_pwin_bottom(self):
        """ Creates and initializes the presenter window's bottom row of numerical displays

        :return: the preview panes with current and next slide
        :rtype: :class:`Gtk.HBox`
        """
        hbox = Gtk.HBox(False, 0)
        hbox.set_margin_right(5)
        hbox.set_halign(Gtk.Align.FILL)
        hbox.pack_start(self.make_frame_slidenum(), True, True, 0)
        hbox.pack_start(self.make_frame_time(), True, True, 0)
        hbox.pack_start(self.make_frame_ett(), False, True, 0)
        hbox.pack_start(self.make_frame_clock(), False, True, 0)

        return hbox


    def setup_screens(self):
        """ Sets up the position of the windows
        """
        # If multiple monitors, apply windows to monitors according to config
        screen = self.p_win.get_screen()
        if screen.get_n_monitors() > 1:
            c_monitor = self.config.getint('content', 'monitor')
            p_monitor = self.config.getint('presenter', 'monitor')
            p_full = self.config.getboolean('presenter', 'start_fullscreen')
            c_full = self.config.getboolean('content', 'start_fullscreen')

            if c_monitor == p_monitor and (c_full or p_full):
                print("Warning: Content and presenter window must not be on the same monitor if you start full screen!", file=sys.stderr)
                p_monitor = 0 if c_monitor > 0 else 1

            p_bounds = screen.get_monitor_geometry(p_monitor)
            self.p_win.move(p_bounds.x, p_bounds.y)
            if p_full:
                self.p_win.fullscreen()
            else:
                self.p_win.maximize()

            c_bounds = screen.get_monitor_geometry(c_monitor)
            self.c_win.move(c_bounds.x, c_bounds.y)
            if c_full:
                self.c_win.fullscreen()


    def make_frame_slidenum(self):
        """ Make "Current slide" label and entry.

        The left part is a label that shows the current slide number.
        The right part is a label that shows the total number of slides.
        Both parts are within an event box that gets all events on the whole.

        The left label may be replaced by a spinner to choose which slide to jump to.
        """
        self.label_cur.set_name("LSlideCur")
        self.label_cur.get_style_context().add_class("info-label")
        self.label_cur.props.halign = Gtk.Align.END
        self.label_cur.set_use_markup(True)
        self.label_last.set_name("LSlideLast")
        self.label_last.get_style_context().add_class("info-label")
        self.label_last.props.halign = Gtk.Align.START
        self.label_last.set_text("/{}".format(self.doc.pages_number()))

        self.hb_cur=Gtk.HBox()
        self.hb_cur.pack_start(self.label_cur, True, True, 0)
        self.hb_cur.pack_start(self.label_last, True, True, 0)
        self.eb_cur.add(self.hb_cur)
        self.spin_cur = pympress.slideselector.SlideSelector(self, self.doc.pages_number())
        self.spin_cur.set_alignment(0.5)

        self.eb_cur.set_visible_window(False)
        self.eb_cur.connect("event", self.on_label_event)
        frame = Gtk.Frame()
        frame.set_label("Slide number")
        frame.get_label_widget().get_style_context().add_class("frame-label")
        frame.set_size_request(200, 0)
        frame.add(self.eb_cur)
        return frame


    def make_frame_clock(self):
        """ Make "Clock" frame, that will display the time.
        """
        frame = Gtk.Frame()
        frame.set_label("Clock")
        frame.set_size_request(170, 0)
        frame.get_label_widget().get_style_context().add_class("frame-label")
        frame.add(self.label_clock)
        self.label_clock.set_name("LClock")
        self.label_clock.get_style_context().add_class("info-label")
        return frame


    def make_frame_time(self):
        """ Make "Time elapsed" frame that shows how much time spent in presentation.
        This label may change styles depending on the talk duration estimate.
        """
        frame = Gtk.Frame()
        frame.set_label("Time elapsed")
        frame.set_size_request(170, 0)
        frame.get_label_widget().get_style_context().add_class("frame-label")
        self.label_time.set_name("LTimeElapsed")

        # Load color from CSS
        style_context = self.label_time.get_style_context()
        style_context.add_class("ett-reached")
        self.label_time.show();
        self.label_color_ett_reached = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class("ett-reached")
        style_context.add_class("ett-info")
        self.label_time.show();
        self.label_color_ett_info = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class("ett-info")
        style_context.add_class("ett-warn")
        self.label_time.show();
        self.label_color_ett_warn = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class("ett-warn")
        style_context.add_class("info-label")
        self.label_time.show();
        frame.add(self.label_time)
        return frame


    def make_frame_ett(self):
        """ Make "Time estimation" frame that shows the time allocated for the talk.
        """
        self.label_ett.set_name("LEstTalkTime")
        self.label_ett.get_style_context().add_class("info-label")
        self.label_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
        self.eb_ett.set_visible_window(False)
        self.eb_ett.connect("button-press-event", self.on_label_ett_event)
        self.eb_ett.connect("key-press-event", self.on_label_ett_event)
        self.eb_ett.add(self.label_ett)
        self.entry_ett.set_alignment(0.5)
        frame = Gtk.Frame()
        frame.set_label("Time estimation")
        frame.get_label_widget().get_style_context().add_class("frame-label")
        frame.set_size_request(170, 0)
        frame.add(self.eb_ett)
        return frame


    def make_menubar(self):
        """ Creates and initializes the menu bar.

        :return: the menu bar
        :rtype: :class:`Gtk.Widget`
        """
        # UI Manager for menu
        ui_manager = Gtk.UIManager()

        # UI description
        ui_desc = '''
        <menubar name="MenuBar">
          <menu action="File">
            <menuitem action="Quit"/>
          </menu>
          <menu action="Presentation">
            <menuitem action="Pause timer"/>
            <menuitem action="Reset timer"/>
            <menuitem action="Set talk time"/>
            <menuitem action="Fullscreen"/>
            <menuitem action="Swap screens"/>
            <menuitem action="Notes mode"/>
            <menuitem action="Show annotations"/>
            <menuitem action="Blank screen"/>
            <menuitem action="Align content"/>
          </menu>
          <menu action="Navigation">
            <menuitem action="Next"/>
            <menuitem action="Previous"/>
            <menuitem action="First"/>
            <menuitem action="Last"/>
            <menuitem action="Go to..."/>
          </menu>
          <menu action="Starting Configuration">
            <menuitem action="Content blanked"/>
            <menuitem action="Content fullscreen"/>
            <menuitem action="Presenter fullscreen"/>
          </menu>
          <menu action="Help">
            <menuitem action="About"/>
          </menu>
        </menubar>'''
        ui_manager.add_ui_from_string(ui_desc)

        # Accelerator group
        accel_group = ui_manager.get_accel_group()
        self.p_win.add_accel_group(accel_group)

        # Action group
        action_group = Gtk.ActionGroup('MenuBar')
        # Name, stock id, label, accelerator, tooltip, action [, is_active]
        action_group.add_actions([
            ('File',         None,           '_File'),
            ('Presentation', None,           '_Presentation'),
            ('Navigation',   None,           '_Navigation'),
            ('Starting Configuration', None, '_Starting Configuration'),
            ('Help',         None,           '_Help'),

            ('Quit',         Gtk.STOCK_QUIT, '_Quit',        'q',     None, self.save_and_quit),
            ('Reset timer',  None,           '_Reset timer', 'r',     None, self.reset_timer),
            ('Set talk time',None,           'Set talk _Time','t',    None, self.on_label_ett_event),
            ('About',        None,           '_About',       None,    None, self.menu_about),
            ('Swap screens', None,           '_Swap screens','s',     None, self.swap_screens),
            ('Align content',None,           '_Align content',None,   None, self.adjust_frame_position),

            ('Next',         None,           '_Next',        'Right', None, self.doc.goto_next),
            ('Previous',     None,           '_Previous',    'Left',  None, self.doc.goto_prev),
            ('First',        None,           '_First',       'Home',  None, self.doc.goto_home),
            ('Last',         None,           '_Last',        'End',   None, self.doc.goto_end),
            ('Go to...',     None,           '_Go to...',    'g',     None, self.on_label_event),
        ])
        action_group.add_toggle_actions([
            ('Pause timer',  None,           '_Pause timer', 'p',     None, self.switch_pause,         True),
            ('Fullscreen',   None,           '_Fullscreen',  'f',     None, self.switch_fullscreen,    self.config.getboolean('content', 'start_fullscreen')),
            ('Notes mode',   None,           '_Note mode',   'n',     None, self.switch_mode,          self.notes_mode),
            ('Show annotations',   None,           '_Show annotations',   'a',     None, self.switch_annotations,          self.annotation_mode),
            ('Blank screen', None,           '_Blank screen','b',     None, self.switch_blanked,       self.blanked),
            ('Content blanked',      None,   'Content blanked',       None, None, self.switch_start_blanked,    self.config.getboolean('content', 'start_blanked')),
            ('Content fullscreen',   None,   'Content fullscreen',    None, None, self.switch_start_fullscreen, self.config.getboolean('content', 'start_fullscreen')),
            ('Presenter fullscreen', None,   'Presenter fullscreen',  None, None, self.switch_start_fullscreen, self.config.getboolean('presenter', 'start_fullscreen')),
        ])
        ui_manager.insert_action_group(action_group)

        # Add menu bar to the window
        h = ui_manager.get_widget('/MenuBar/Help')
        h.set_right_justified(True)
        return ui_manager.get_widget('/MenuBar')


    def add_annotations(self, annotations):
        """ Insert text annotations into the tree view that displays them.
        """
        list_annot = Gtk.ListStore(str)

        for annot in annotations:
            list_annot.append(('• '+annot,))

        self.scrolled_window.set_model(list_annot)
        self.resize_annotation_list()


    def run(self):
        """ Run the GTK main loop.
        """
        Gtk.main()


    def save_and_quit(self, *args):
        """ Save configuration and exit the main loop.
        """
        cur_pane_size = self.p_frame_cur.get_allocated_width()
        next_pane_size = self.p_frame_next.get_allocated_width()
        ratio = float(cur_pane_size) / (cur_pane_size + next_pane_size)
        self.config.set('presenter', 'slide_ratio', "{0:.2f}".format(ratio))

        pympress.util.save_config(self.config)
        Gtk.main_quit()


    def pick_file(self):
        """ Ask the user which file he means to open.
        """
        # Use a GTK file dialog to choose file
        dialog = Gtk.FileChooserDialog('Open...', self.p_win,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        filter = Gtk.FileFilter()
        filter.set_name('PDF files')
        filter.add_mime_type('application/pdf')
        filter.add_pattern('*.pdf')
        dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name('All files')
        filter.add_pattern('*')
        dialog.add_filter(filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            name = dialog.get_filename()
            dialog.destroy()
        else:
            dialog.destroy()

            # Use a GTK dialog to tell we need a file
            msg="""No file selected!\n\nYou can specify the PDF file to open on the command line if you don't want to use the "Open File" dialog."""
            dialog = Gtk.MessageDialog(type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, message_format=msg, parent=self.p_win)
            dialog.set_position(Gtk.WindowPosition.CENTER)
            dialog.run()
            sys.exit(1)

        return os.path.abspath(name)


    def menu_about(self, widget=None, event=None):
        """ Display the "About pympress" dialog.
        """
        about = Gtk.AboutDialog()
        about.set_program_name('pympress')
        about.set_version(pympress.__version__)
        about.set_copyright('(c) 2009-2016 Thomas Jost, Cimbali, Christof Rath')
        about.set_comments('pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK for the GUI.\n'
                         + 'Some preferences are saved in ' + pympress.util.path_to_config())
        about.set_website('https://github.com/Cimbali/pympress/')
        try:
            about.set_logo(pympress.util.get_icon_pixbuf('pympress-128.png'))
        except Exception:
            print('Error loading icon for about window')
        about.run()
        about.destroy()


    def page_preview(self, page_nb):
        """ Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the
        :class:`~pympress.document.Document` class.

        :param unpause: ``True`` if the page change should unpause the timer,
           ``False`` otherwise
        :type  unpause: boolean
        """
        page_cur = self.doc.page(page_nb)
        page_next = self.doc.page(page_nb+1)

        self.page_preview_nb = page_nb

        # Aspect ratios and queue redraws
        pr = page_cur.get_aspect_ratio(self.notes_mode)
        self.p_frame_cur.set_property('ratio', pr)

        if page_next is not None:
            pr = page_next.get_aspect_ratio(self.notes_mode)
            self.p_frame_next.set_property('ratio', pr)

        # queue redraws
        self.p_da_cur.queue_draw()
        self.p_da_next.queue_draw()
        self.p_da_pres.queue_draw()

        self.add_annotations(page_cur.get_annotations())


        # Prerender the 4 next pages and the 2 previous ones
        cur = page_cur.number()
        page_max = min(self.doc.pages_number(), cur + 5)
        page_min = max(0, cur - 2)
        for p in list(range(cur+1, page_max)) + list(range(cur, page_min, -1)):
            self.cache.prerender(p)


    def on_page_change(self, unpause=True):
        """ Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the
        :class:`~pympress.document.Document` class.

        :param unpause: ``True`` if the page change should unpause the timer,
           ``False`` otherwise
        :type  unpause: boolean
        """
        page_cur = self.doc.current_page()
        page_next = self.doc.next_page()

        self.add_annotations(page_cur.get_annotations())

        # Page change: resynchronize miniatures
        self.page_preview_nb = page_cur.number()

        # Aspect ratios
        pr = page_cur.get_aspect_ratio(self.notes_mode)
        self.c_frame.set_property('ratio', pr)
        self.p_frame_cur.set_property('ratio', pr)

        if page_next is not None:
            pr = page_next.get_aspect_ratio(self.notes_mode)
            self.p_frame_next.set_property('ratio', pr)

        # Queue redraws
        self.c_da.queue_draw()
        self.p_da_cur.queue_draw()
        self.p_da_next.queue_draw()
        self.p_da_pres.queue_draw()


        # Start counter if needed
        if unpause:
            self.paused = False
            if self.start_time == 0:
                self.start_time = time.time()

        # Update display
        self.update_page_numbers()

        # Prerender the 4 next pages and the 2 previous ones
        page_max = min(self.doc.pages_number(), self.page_preview_nb + 5)
        page_min = max(0, self.page_preview_nb - 2)
        for p in list(range(self.page_preview_nb+1, page_max)) + list(range(self.page_preview_nb, page_min, -1)):
            self.cache.prerender(p)

        self.replace_media_overlays()


    def replace_media_overlays(self):
        """ Remove current media overlays, add new ones if page contains media.
        """
        if not vlc_enabled:
            return

        self.c_overlay.foreach(lambda child, *ignored: child.stop_and_remove() and self.c_overlay.remove(child) if child is not self.c_da else None, None)

        page_cur = self.doc.current_page()
        pw, ph = page_cur.get_size()

        global media_overlays

        for relative_margins, filename, show_controls in page_cur.get_media():
            media_id = hash((relative_margins, filename, show_controls))

            if media_id not in media_overlays:
                v_da = pympress.vlcvideo.VLCVideo(self.c_overlay, show_controls, relative_margins)
                v_da.set_file(filename)

                media_overlays[media_id] = v_da


    @staticmethod
    def play_media(media_id):
        """ Static way of starting (playing) a media. Used by callbacks.
        """
        global media_overlays
        if media_id in media_overlays:
            media_overlays[media_id].play()


    def on_draw(self, widget, cairo_context):
        """ Manage draw events for both windows.

        This callback may be called either directly on a page change or as an
        event handler by GTK. In both cases, it determines which widget needs to
        be updated, and updates it, using the
        :class:`~pympress.surfacecache.SurfaceCache` if possible.

        :param widget: the widget to update
        :type  widget: :class:`Gtk.Widget`
        :param cairo_context: the Cairo context (or ``None`` if called directly)
        :type  cairo_context: :class:`cairo.Context`
        """

        if widget is self.c_da:
            # Current page
            if self.blanked:
                return
            page = self.doc.page(self.doc.current_page().number())
        elif widget is self.p_da_cur or widget is self.p_da_pres:
            # Current page 'preview'
            page = self.doc.page(self.page_preview_nb)
        else:
            page = self.doc.page(self.page_preview_nb+1)
            # No next page: just return so we won't draw anything
            if page is None:
                return

        # Instead of rendering the document to a Cairo surface (which is slow),
        # use a surface from the cache if possible.
        name = widget.get_name()
        nb = page.number()
        pb = self.cache.get(name, nb)
        wtype = self.cache.get_widget_type(name)

        if pb is None:
            # Cache miss: render the page, and save it to the cache
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            pb = widget.get_window().create_similar_surface(cairo.CONTENT_COLOR, ww, wh)

            cairo_prerender = cairo.Context(pb)
            page.render_cairo(cairo_prerender, ww, wh, wtype)

            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()

            self.cache.set(name, nb, pb)
        else:
            # Cache hit: draw the surface from the cache to the widget
            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()


    def on_configure_da(self, widget, event):
        """ Manage "configure" events for all drawing areas.

        In the GTK world, this event is triggered when a widget's configuration
        is modified, for example when its size changes. So, when this event is
        triggered, we tell the local :class:`~pympress.surfacecache.SurfaceCache`
        instance about it, so that it can invalidate its internal cache for the
        specified widget and pre-render next pages at a correct size.

        :param widget: the widget which has been resized
        :type  widget: :class:`Gtk.Widget`
        :param event: the GTK event, which contains the new dimensions of the
           widget
        :type  event: :class:`Gdk.Event`
        """
        self.cache.resize_widget(widget.get_name(), event.width, event.height)

        if widget is self.c_da:
            self.c_overlay.foreach(lambda child, *ignored: child.resize() if child is not self.c_da else None, None)
        elif widget is self.p_da_next:
            self.resize_annotation_list()


    def on_configure_win(self, widget, event):
        """ Manage "configure" events for both window widgets.

        :param widget: the window which has been moved or resized
        :type  widget: :class:`Gtk.Widget`
        :param event: the GTK event, which contains the new dimensions of the widget
        :type  event: :class:`Gdk.Event`
        """

        if widget is self.p_win:
            p_monitor = self.p_win.get_screen().get_monitor_at_window(self.p_frame_cur.get_parent_window())
            self.config.set('presenter', 'monitor', str(p_monitor))
        elif widget is self.c_win:
            c_monitor = self.c_win.get_screen().get_monitor_at_window(self.c_frame.get_parent_window())
            self.config.set('content', 'monitor', str(c_monitor))


    def on_navigation(self, widget, event):
        """ Manage events as mouse scroll or clicks for both windows.

        :param widget: the widget in which the event occured (ignored)
        :type  widget: :class:`Gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`Gdk.Event`
        """
        if event.type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval)
            ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

            # send all to spinner if it is active to avoid key problems
            if self.editing_cur and self.spin_cur.on_keypress(widget, event):
                return True
            # send all to entry field if it is active to avoid key problems
            if self.editing_cur_ett and self.on_label_ett_event(widget, event):
                return True

            if self.paused and name == 'space':
                self.switch_pause()
            elif name in ['Right', 'Down', 'Page_Down', 'space']:
                self.doc.goto_next()
            elif name in ['Left', 'Up', 'Page_Up', 'BackSpace']:
                self.doc.goto_prev()
            elif name == 'Home':
                self.doc.goto_home()
            elif name == 'End':
                self.doc.goto_end()
            # sic - accelerator recognizes f not F
            elif name.upper() == 'F11' or name == 'F' \
                or (name == 'Return' and event.get_state() & Gdk.ModifierType.MOD1_MASK) \
                or (name.upper() == 'L' and ctrl_pressed) \
                or (name.upper() == 'F5' and not self.c_win_fullscreen) \
                or (name == 'Escape' and self.c_win_fullscreen):
                self.switch_fullscreen(self.c_win)
            elif name.upper() == 'F' and ctrl_pressed:
                self.switch_fullscreen(self.p_win)
            elif name.upper() == 'Q':
                self.save_and_quit()
            elif name == 'Pause':
                self.switch_pause()
            elif name.upper() == 'R':
                self.reset_timer()

            # Some key events are already handled by toggle actions in the
            # presenter window, so we must handle them in the content window
            # only to prevent them from double-firing
            if widget is self.c_win:
                if name.upper() == 'P':
                    self.switch_pause()
                elif name.upper() == 'N':
                    self.switch_mode()
                elif name.upper() == 'A':
                    self.switch_annotations()
                elif name.upper() == 'S':
                    self.swap_screens()
                elif name.upper() == 'F':
                    if ctrl_pressed:
                        self.switch_fullscreen(self.p_win)
                    else:
                        self.switch_fullscreen(self.c_win)
                elif name.upper() == 'G':
                    self.on_label_event(self.eb_cur, True)
                elif name.upper() == 'T':
                    self.on_label_ett_event(self.eb_ett, True)
                elif name.upper() == 'B':
                    self.switch_blanked()
                else:
                    return False

                return True
            else:
                return False

            return True

        elif event.type == Gdk.EventType.SCROLL:

            # send all to spinner if it is active to avoid key problems
            if self.editing_cur and self.spin_cur.on_keypress(widget, event):
                return True

            elif event.direction is Gdk.ScrollDirection.SMOOTH:
                return False
            else:
                adj = self.scrollable_treelist.get_vadjustment()
                if event.direction == Gdk.ScrollDirection.UP:
                    adj.set_value(adj.get_value() - adj.get_step_increment())
                elif event.direction == Gdk.ScrollDirection.DOWN:
                    adj.set_value(adj.get_value() + adj.get_step_increment())
                else:
                    return False

            return True

        return False


    def on_link(self, widget, event):
        """ Manage events related to hyperlinks.

        :param widget: the widget in which the event occured
        :type  widget: :class:`Gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`Gdk.Event`
        """

        # Where did the event occur?
        if widget is self.p_da_next:
            page = self.doc.next_page()
            if page is None:
                return
        else:
            page = self.doc.current_page()

        # Normalize event coordinates and get link
        x, y = event.get_coords()
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        x2, y2 = x/ww, y/wh
        link = page.get_link_at(x2, y2)

        # Event type?
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if link is not None:
                link.follow()

        elif event.type == Gdk.EventType.MOTION_NOTIFY:
            if link is not None:
                cursor = Gdk.Cursor.new(Gdk.CursorType.HAND2)
                widget.get_window().set_cursor(cursor)
            else:
                widget.get_window().set_cursor(None)

        else:
            print("Unknown event {}".format(event.type))


    def on_label_event(self, *args):
        """ Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...

        :param widget: the widget in which the event occured
        :type  widget: :class:`Gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`Gdk.Event`
        """

        event = args[-1]

        # we can come manually or through a menu action as well
        alt_start_editing = (type(event) == bool and event is True or type(event) == Gtk.Action)
        event_type = None if alt_start_editing else event.type

        # Click in label-mode
        if alt_start_editing or event.type == Gdk.EventType.BUTTON_PRESS: # click
            if self.editing_cur_ett:
                self.restore_current_label_ett()

            if self.label_cur in self.hb_cur:
                # Replace label with entry
                self.hb_cur.remove(self.label_cur)
                self.spin_cur.show()
                self.hb_cur.add(self.spin_cur)
                self.hb_cur.reorder_child(self.spin_cur, 0)
                self.spin_cur.grab_focus()
                self.editing_cur = True

                self.spin_cur.set_value(self.doc.current_page().number()+1)
                self.spin_cur.select_region(0, -1)

            elif self.editing_cur:
                self.spin_cur.grab_focus()

        else:
            # Ignored event - propagate further
            return False

        return True


    def on_label_ett_event(self, *args):
        """ Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...

        :param widget: the widget in which the event occured
        :type  widget: :class:`gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`gtk.gdk.Event`
        """

        widget = self.eb_ett.get_child()
        event = args[-1]

        # we can come manually or through a menu action as well
        alt_start_editing = (type(event) == bool and event is True or type(event) == Gtk.Action)
        event_type = None if alt_start_editing else event.type

        # Click on the label
        if widget is self.label_ett and (alt_start_editing or event_type == Gdk.EventType.BUTTON_PRESS):
            if self.editing_cur:
                self.spin_cur.cancel()

            # Set entry text
            self.entry_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
            self.entry_ett.select_region(0, -1)

            # Replace label with entry
            self.eb_ett.remove(self.label_ett)
            self.eb_ett.add(self.entry_ett)
            self.entry_ett.show()
            self.entry_ett.grab_focus()
            self.editing_cur_ett = True

        # Key pressed in the entry
        elif widget is self.entry_ett and event_type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval)

            # Return key --> restore label and goto page
            if name == "Return" or name == "KP_Enter":
                text = self.entry_ett.get_text()
                self.restore_current_label_ett()

                t = ["0" + n.strip() for n in text.split(':')]
                try:
                    m = int(t[0])
                    s = int(t[1])
                except ValueError:
                    print("Invalid time (mm or mm:ss expected), got \"{}\"".format(text))
                    return True
                except IndexError:
                    s = 0

                self.est_time = m * 60 + s;
                self.label_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
                self.label_time.override_color(Gtk.StateType.NORMAL, self.label_color_default)
                return True

            # Escape key --> just restore the label
            elif name == "Escape":
                self.restore_current_label_ett()
                return True
            else:
                Gtk.Entry.do_key_press_event(widget, event)

        return True


    def resize_annotation_list(self):
        """ Readjust the annotation list's scroll window
        so it won't compete for space with the next slide frame
        """
        r = self.p_frame_next.props.ratio
        w = self.p_frame_next.props.parent.get_allocated_width()
        h = self.p_frame_next.props.parent.props.parent.get_allocated_height() - 30
        self.annotation_renderer.props.wrap_width = w - 10
        self.scrollable_treelist.set_size_request(-1, max(h - w / r, 100))
        self.scrolled_window.get_column(0).queue_resize()
        self.scrollable_treelist.queue_resize()


    def restore_current_label(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        if self.label_cur not in self.hb_cur:
            self.hb_cur.remove(self.spin_cur)
            self.hb_cur.pack_start(self.label_cur, True, True, 0)
            self.hb_cur.reorder_child(self.label_cur, 0)

        self.editing_cur = False



    def restore_current_label_ett(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        child = self.eb_ett.get_child()
        if child is not self.label_ett:
            self.eb_ett.remove(child)
            self.eb_ett.add(self.label_ett)

        self.editing_cur_ett = False


    def update_page_numbers(self):
        """ Update the displayed page numbers.
        """

        cur_nb = self.doc.current_page().number()
        cur = str(cur_nb+1)

        self.label_cur.set_text(cur)
        self.restore_current_label()


    def update_time(self):
        """ Update the timer and clock labels.

        :return: ``True`` (to prevent the timer from stopping)
        :rtype: boolean
        """

        # Current time
        clock = time.strftime("%H:%M") #"%H:%M:%S"

        # Time elapsed since the beginning of the presentation
        if not self.paused:
            self.delta = time.time() - self.start_time
        elapsed = "{:02}:{:02}".format(*divmod(int(self.delta), 60))
        if self.paused:
            elapsed += " (paused)"

        self.label_time.set_text(elapsed)
        self.label_clock.set_text(clock)

        self.update_color()

        return True


    def calc_color(self, from_color, to_color, position):
        """ Compute the interpolation between two colors.

        :param from_color: the color when position = 0
        :type  from_color: :class:`Gdk.RGBA`
        :param to_color: the color when position = 1
        :type  to_color: :class:`Gdk.RGBA`
        :param position: A floating point value in the interval [0.0, 1.0]
        :type  position: float
        :return: The color that is between from_color and to_color
        :rtype: :class:`Gdk.RGBA`
        """
        color_tuple = lambda color: ( color.red, color.green, color.blue, color.alpha )
        interpolate = lambda start, end: start + (end - start) * position

        return Gdk.RGBA(*map(interpolate, color_tuple(from_color), color_tuple(to_color)))


    def update_color(self):
        """ Update the color of the time label based on how much time is remaining.
        """
        if not self.est_time == 0:
            # Set up colors between which to fade, based on how much time remains (<0 has run out of time).
            # Times are given in seconds, in between two of those timestamps the color will interpolated linearly.
            # Outside of the intervals the closest color will be used.
            colors = {
                 300:self.label_color_default,
                   0:self.label_color_ett_reached,
                -150:self.label_color_ett_info,
                -300:self.label_color_ett_warn
            }
            bounds=list(sorted(colors, reverse=True)[:-1])

            remaining = self.est_time - self.delta
            if remaining >= bounds[0]:
                color = colors[bounds[0]]
            elif remaining <= bounds[-1]:
                color = colors[bounds[-1]]
            else:
                c=1
                while bounds[c] >= remaining:
                    c += 1
                position = (remaining - bounds[c-1]) / (bounds[c] - bounds[c-1])
                color = self.calc_color(colors[bounds[c-1]], colors[bounds[c]], position)

            if color:
                self.label_time.override_color(Gtk.StateType.NORMAL, color)

            if (remaining <= 0 and remaining > -5) or (remaining <= -300 and remaining > -310):
                self.label_time.get_style_context().add_class("time-warn")
            else:
                self.label_time.get_style_context().remove_class("time-warn")


    def switch_pause(self, widget=None, event=None):
        """ Switch the timer between paused mode and running (normal) mode.
        """
        if self.paused:
            self.start_time = time.time() - self.delta
            self.paused = False
        else:
            self.paused = True
        self.update_time()


    def reset_timer(self, widget=None, event=None):
        """ Reset the timer.
        """
        self.start_time = time.time()
        self.delta = 0
        self.update_time()


    def set_screensaver(self, must_disable):
        """ Enable or disable the screensaver.

        :param must_disable: if ``True``, indicates that the screensaver must be
           disabled; otherwise it will be enabled
        :type  must_disable: boolean
        """
        if IS_MAC_OS:
            # On Mac OS X we can use caffeinate to prevent the display from sleeping
            if must_disable:
                if self.dpms_was_enabled == None or self.dpms_was_enabled.poll():
                    self.dpms_was_enabled = subprocess.Popen(['caffeinate', '-d', '-w', str(os.getpid())])
            else:
                if self.dpms_was_enabled and not self.dpms_was_enabled.poll():
                    self.dpms_was_enabled.kill()
                    self.dpms_was_enabled.poll()
                    self.dpms_was_enabled = None

        elif IS_POSIX:
            # On Linux, set screensaver with xdg-screensaver
            # (compatible with xscreensaver, gnome-screensaver and ksaver or whatever)
            cmd = "suspend" if must_disable else "resume"
            status = os.system("xdg-screensaver {} {}".format(cmd, self.c_win.get_window().get_xid()))
            if status != 0:
                print("Warning: Could not set screensaver status: got status "+str(status), file=sys.stderr)

            # Also manage screen blanking via DPMS
            if must_disable:
                # Get current DPMS status
                pipe = os.popen("xset q") # TODO: check if this works on all locales
                dpms_status = "Disabled"
                for line in pipe.readlines():
                    if line.count("DPMS is") > 0:
                        dpms_status = line.split()[-1]
                        break
                pipe.close()

                # Set the new value correctly
                if dpms_status == "Enabled":
                    self.dpms_was_enabled = True
                    status = os.system("xset -dpms")
                    if status != 0:
                        print("Warning: Could not disable DPMS screen blanking: got status "+str(status), file=sys.stderr)
                else:
                    self.dpms_was_enabled = False

            elif self.dpms_was_enabled:
                # Re-enable DPMS
                status = os.system("xset +dpms")
                if status != 0:
                    print("Warning: Could not enable DPMS screen blanking: got status "+str(status), file=sys.stderr)

        elif IS_WINDOWS:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Control Panel\Desktop', 0, winreg.KEY_QUERY_VALUE|winreg.KEY_SET_VALUE) as key:
                    if must_disable:
                        (value,type) = winreg.QueryValueEx(key, "ScreenSaveActive")
                        assert(type == winreg.REG_SZ)
                        self.dpms_was_enabled = (value == "1")
                        if self.dpms_was_enabled:
                            winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "0")
                    elif self.dpms_was_enabled:
                        winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "1")
            except (OSError, PermissionError):
                print("Error: access denied when trying to access screen saver settings in registry!")
        else:
            print("Warning: Unsupported OS: can't enable/disable screensaver", file=sys.stderr)


    def switch_fullscreen(self, widget=None, event=None):
        """ Switch the Content window to fullscreen (if in normal mode)
        or to normal mode (if fullscreen).

        Screensaver will be disabled when entering fullscreen mode, and enabled
        when leaving fullscreen mode.
        """
        if isinstance(widget, Gtk.Action):
            # Called from menu -> use c_win
            widget = self.c_win
            fullscreen = self.c_win_fullscreen
        elif widget == self.c_win:
            fullscreen = self.c_win_fullscreen
        elif widget == self.p_win:
            fullscreen = self.p_win_fullscreen
        else:
            print ("Unknow widget " + str(widget) + " to be fullscreened, aborting.", file=sys.stderr)
            return

        if fullscreen:
            widget.unfullscreen()
        else:
            widget.fullscreen()


    def on_window_state_event(self, widget, event, user_data=None):
        """ Track whether the preview window is maximized.
        """
        if widget.get_name() == self.p_win.get_name():
            self.p_win_maximized = (Gdk.WindowState.MAXIMIZED & event.new_window_state) != 0
            self.p_win_fullscreen = (Gdk.WindowState.FULLSCREEN & event.new_window_state) != 0
        elif widget.get_name() == self.c_win.get_name():
            self.c_win_fullscreen = (Gdk.WindowState.FULLSCREEN & event.new_window_state) != 0
            self.set_screensaver(self.c_win_fullscreen)


    def update_frame_position(self, widget=None, user_data=None):
        """ Callback to preview the frame alignement, called from the spinbutton.
        """
        if widget and user_data:
            self.c_frame.set_property(user_data, widget.get_value())


    def adjust_frame_position(self, widget=None, event=None):
        """ Select how to align the frame on screen.
        """
        win_aspect_ratio = float(self.c_win.get_allocated_width()) / self.c_win.get_allocated_height()

        if win_aspect_ratio <= float(self.c_frame.get_property("ratio")):
            prop = "yalign"
        else:
            prop = "xalign"

        val = self.c_frame.get_property(prop)

        button = Gtk.SpinButton()
        button.set_adjustment(Gtk.Adjustment(lower=0.0, upper=1.0, step_incr=0.01))
        button.set_digits(2)
        button.set_value(val)
        button.connect("value-changed", self.update_frame_position, prop)

        popup = Gtk.Dialog("Adjust alignment of slides in projector screen", self.p_win, 0,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 Gtk.STOCK_OK, Gtk.ResponseType.OK))

        box = popup.get_content_area()
        box.add(button)
        popup.show_all()
        response = popup.run()
        popup.destroy()

        # revert if we cancelled
        if response == Gtk.ResponseType.CANCEL:
            self.c_frame.set_property(prop, val)
        else:
            self.config.set('content', prop, str(button.get_value()))


    def swap_screens(self, widget=None, event=None):
        """ Swap the monitors on which each window is displayed (if there are 2 monitors at least).
        """
        c_win_was_fullscreen = self.c_win_fullscreen
        p_win_was_fullscreen = self.p_win_fullscreen
        p_win_was_maximized  = self.p_win_maximized
        if c_win_was_fullscreen:
            self.c_win.unfullscreen()
        if p_win_was_fullscreen:
            self.p_win.unfullscreen()
        if p_win_was_maximized:
            self.p_win.unmaximize()

        screen = self.p_win.get_screen()
        if screen.get_n_monitors() > 1:
            # temporarily remove the annotations' list size so it won't hinder p_frame_next size adjustment
            self.scrollable_treelist.set_size_request(-1,  100)

            # Though Gtk.Window is a Gtk.Widget get_parent_window() actually returns None on self.{c,p}_win
            p_monitor = screen.get_monitor_at_window(self.p_frame_cur.get_parent_window())
            c_monitor = screen.get_monitor_at_window(self.c_frame.get_parent_window())

            if p_monitor == c_monitor:
                return

            p_monitor, c_monitor = (c_monitor, p_monitor)

            cx, cy, cw, ch = self.c_win.get_position() + self.c_win.get_size()
            px, py, pw, ph = self.p_win.get_position() + self.p_win.get_size()

            c_bounds = screen.get_monitor_geometry(c_monitor)
            p_bounds = screen.get_monitor_geometry(p_monitor)
            self.c_win.move(c_bounds.x + (c_bounds.width - cw) / 2, c_bounds.y + (c_bounds.height - ch) / 2)
            self.p_win.move(p_bounds.x + (p_bounds.width - pw) / 2, p_bounds.y + (p_bounds.height - ph) / 2)

            if p_win_was_fullscreen:
                self.p_win.fullscreen()
            elif p_win_was_maximized:
                self.p_win.maximize()

            if c_win_was_fullscreen:
                self.c_win.fullscreen()



    def switch_blanked(self, widget=None, event=None):
        """ Switch the blanked mode of the main screen.
        """
        self.blanked = not self.blanked
        self.c_da.queue_draw()


    def switch_start_blanked(self, widget=None, event=None):
        """ Switch the blanked mode of the main screen.
        """
        if self.config.getboolean('content', 'start_blanked'):
            self.config.set('content', 'start_blanked', 'off')
        else:
            self.config.set('content', 'start_blanked', 'on')


    def switch_start_fullscreen(self, widget=None):
        """ Switch the blanked mode of the main screen.
        """
        name_words=widget.get_name().lower().split()
        if 'content' in name_words:
            target = 'content'
        elif 'presenter' in name_words:
            target = 'presenter'
        else:
            print("ERROR Unknown widget to start fullscreen: {}".format(widget.get_name()))
            return

        if self.config.getboolean(target, 'start_fullscreen'):
            self.config.set(target, 'start_fullscreen', 'off')
        else:
            self.config.set(target, 'start_fullscreen', 'on')


    def switch_mode(self, widget=None, event=None):
        """ Switch the display mode to "Notes mode" or "Normal mode" (without notes).
        """
        if self.notes_mode:
            self.notes_mode = False
            self.cache.set_widget_type("c_da", PDF_REGULAR)
            self.cache.set_widget_type("p_da_cur", PDF_REGULAR)
            self.cache.set_widget_type("p_da_next", PDF_REGULAR)
            self.p_frame_pres.set_visible(False)
        else:
            self.notes_mode = True
            self.cache.set_widget_type("c_da", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_cur", PDF_NOTES_PAGE)
            self.cache.set_widget_type("p_da_next", PDF_CONTENT_PAGE)
            self.p_frame_pres.set_visible(True)

        self.on_page_change(False)


    def switch_annotations(self, widget=None, event=None):
        """ Switch the display to show annotations or to hide them.
        """
        if self.annotation_mode:
            self.annotation_mode = False
            self.p_frame_annot.set_visible(False)
        else:
            self.annotation_mode = True
            self.p_frame_annot.set_visible(True)

        self.on_page_change(False)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
