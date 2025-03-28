# Copyright (c) 2023, NVIDIA CORPORATION. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from Jetson import header_def


HDR = header_def.HeaderDef( \
            #name
            'Jetson M.2 Key B Slot',
            #prefix
            'm2kb',
            #pin_count
            78,
            #static_pins
            {
                #idx    :       label
                 2      :       '3.3V',
                 3      :       'GND',
                 4      :       '3.3V',
                 5      :       'GND',
                11      :       'GND',
                27      :       'GND',
                33      :       'GND',
                39      :       'GND',
                45      :       'GND',
                51      :       'GND',
                56      :       'NC',
                57      :       'GND',
                58      :       'NC',
                70      :       '3.3V',
                71      :       'GND',
                72      :       '3.3V',
                73      :       'GND',
                74      :       '3.3V',
                76      :       'GND',
                77      :       'GND',
            }
        )
