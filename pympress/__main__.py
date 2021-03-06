#!/usr/bin/env python
#
#       pympress
#
#       Copyright 2009, 2010 Thomas Jost <thomas.jost@gmail.com>
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

import os.path
import sys
import getopt
import signal

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

import pympress.ui

def usage():
    print("Usage: {} [options] <presentation_file>".format(sys.argv[0]))
    print("")
    print("Options:")
    print("    -h, --help: This help")
    print("    -t xx, --talk-time=xx: The estimated (intended) talk time in minutes")
    print("")

def main(argv = sys.argv[1:]):
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        opts, args = getopt.getopt(argv, "ht:", ["help", "talk-time="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    ett = 0
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-t", "--talk-time"):
            t = ["0" + n.strip() for n in arg.split(':')]
            try:
                m = int(t[0])
                s = int(t[1])
            except ValueError:
                print("Invalid time (mm or mm:ss expected), got \"{}\"".format(text))
                usage()
                sys.exit(2)
            except IndexError:
                s = 0
            ett = m * 60 + s

    # PDF file to open passed on command line?
    name = None
    if len(args) > 0:
        name = os.path.abspath(args[0])

        # Check if the path is valid
        if not os.path.exists(name):
            msg="Could not find the file \"{}\"".format(name)
            dialog = Gtk.MessageDialog(type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, message_format=msg)
            dialog.set_position(Gtk.WindowPosition.CENTER)
            dialog.run()
            name = None

    # Create windows
    ui = pympress.ui.UI(name, ett)
    ui.run()


if __name__ == "__main__":
    main()

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
