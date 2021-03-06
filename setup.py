#!/usr/bin/env python
#
#       setup.py
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
#       Copyright 2015 Cimbali <me@cimba.li>
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

from setuptools import setup
import glob, sys, os.path, importlib

#get version
pkg_meta = importlib.import_module('pympress.__init__')
for pattern in [os.path.join('share', 'css', '*.css'), os.path.join('share', 'pixmaps', '*.png')]:
    print(glob.glob(os.path.join('pympress', pattern)))
setup(name='pympress',
      version=pkg_meta.__version__,
      description='A simple dual-screen PDF reader designed for presentations',
      author='Thomas Jost, Cimbali, Christof Rath',
      author_email='me@cimba.li',
      url='https://github.com/Cimbali/pympress/',
      download_url='https://github.com/Cimbali/pympress/releases/latest',
      classifiers=[
          'Development Status :: 4 - Beta',
          'Environment :: X11 Applications :: GTK',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Information Technology',
          'Intended Audience :: Science/Research',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Natural Language :: English',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Topic :: Multimedia :: Graphics :: Presentation',
          'Topic :: Multimedia :: Graphics :: Viewers',
      ],
      packages=['pympress'],
      entry_points={
        'gui_scripts': [
            'pympress = pympress.__main__:main',
            'pympress{} = pympress.__main__:main'.format(sys.version_info.major),
        ]
      },
      license='GPLv2',
      install_requires=[
          'python-vlc',
      ],
      package_data={
        'pympress': [os.path.join('share', 'css', '*.css'), os.path.join('share', 'pixmaps', '*.png')]
      },
)

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
