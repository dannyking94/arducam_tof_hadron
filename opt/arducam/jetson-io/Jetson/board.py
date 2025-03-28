# SPDX-FileCopyrightText: Copyright (c) 2019-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
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
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from Linux import dt
from Linux import extlinux
from Jetson import header
from Jetson import pmx
from Utils import dtc
from Utils import fio
from Utils import syscall
import Headers
import datetime
import glob
import os
import re
import shutil


def _board_find_overlays(dtbos, hdr_names, hdtbos, hw_addons):
    for dtbo in dtbos:
        # HW addon overlays
        header = dtc.get_prop_value(dtbo, '/', 'jetson-header-name', 0)
        if header in hdr_names:
            if header not in hw_addons.keys():
                hw_addons[header] = {}

            overlay = dtc.get_prop_value(dtbo, '/', 'overlay-name', 0)
            if overlay is None:
                error = "overlay-name not specified in %s!\n" % dtbo
                raise RuntimeError(error)
            if overlay in hw_addons[header].keys():
                error = "Multiple DT overlays for '%s' found!\n" % overlay
                error = error + "Please remove duplicate(s)"
                error = error + "\n%s\n%s" % \
                                (dtbo, hw_addons[header][overlay])
                raise RuntimeError(error)

            hw_addons[header][overlay] = dtbo
            if header not in hdtbos.keys():
                hdtbos[header] = None

            continue

        # Header overlays
        header = dtc.get_prop_value(dtbo, '/', 'overlay-name', 0)
        if header in hdtbos.keys() and hdtbos[header]:
            error = "Multiple DT overlays for '%s' found!\n" % header
            error = error + "Please remove duplicate(s)"
            error = error + "\n%s\n%s" % (dtbo, hdtbos[header])
            raise RuntimeError(error)

        if header:
            hdtbos[header] = dtbo
            if header not in hw_addons.keys():
                hw_addons[header] = {}


def _board_get_jetson_io_pinmux_pins(hdr_prefixes):
    # This tool writes the pinmux nodes for modified pins at the
    # below location in the platform DTB file. These need to be
    # read so that changes made in earlier sessions of this tool
    # (in earlier boot cycles) are retained, in case these pins
    # are not touched in the current session.
    properties = '__symbols__/jetson_io_pinmux', \
                '__symbols__/jetson_io_pinmux_aon'

    preconf_pins = dict.fromkeys(hdr_prefixes, None)

    for prop in properties:
        if not dt.prop_exists(prop):
            continue

        dt_pinmux = dt.read_prop(prop)
        path = dt_pinmux[1:]
        sub_nodes = dt.get_child_nodes(path)

        for node in sub_nodes:
            res = re.match(r'(.+)-pin([0-9]+).*', node)
            if res is None:
                continue

            prefix = str(res.groups()[0])
            if prefix not in hdr_prefixes:
                continue

            if preconf_pins[prefix] is None:
                preconf_pins[prefix] = []

            pin_name_prop = '/'.join((path, node, 'nvidia,pins'))
            if dt.prop_exists(pin_name_prop):
                pin_name = dt.read_prop(pin_name_prop)
                preconf_pins[prefix].append(pin_name)

    return preconf_pins


def _board_root_partition_is_block_device():
    dev = syscall.call_out('mountpoint -q -d /')
    if not dev or len(dev) != 1:
        raise RuntimeError("Root partition not found!")
    return os.path.exists("/dev/block/%s" % dev[0])


def _board_root_partition_get_partlabel():
    entries = syscall.call_out('lsblk -n -r -o mountpoint,partlabel')
    for entry in entries:
        mountpoint,label = entry.split(' ')
        if mountpoint == '/':
            return label
    return None


def _board_partition_exists(partlabel):
    numparts = 0
    partlabels = syscall.call_out('lsblk -n -r -o partlabel')
    for p in partlabels:
        if p == partlabel:
            numparts += 1
    return numparts


def _board_partition_is_root_mountpoint(partlabel):
    if not _board_root_partition_is_block_device():
        return False
    if _board_root_partition_get_partlabel() == partlabel:
        return True
    return False

def _board_get_dtb(compat, model, path):
    dtbs = dtc.find_compatible_dtb_files(compat, model, path)

    if dtbs is None:
        raise RuntimeError("No DTB found for %s!" % model)
    if len(dtbs) > 1:
        raise RuntimeError("Multiple DTBs found for %s!" % model)
    return dtbs[0]

def _board_partition_mount(partlabel):
    numparts = _board_partition_exists(partlabel)
    if numparts == 0:
        raise RuntimeError("No %s partition found!" % partlabel)
    elif numparts > 1:
        raise RuntimeError("Multiple %s partitions found!" % partlabel)
    path = os.path.join('/mnt', partlabel)
    if os.path.exists(path):
        raise RuntimeError("Mountpoint %s already exists!" % path)
    os.makedirs(path)
    syscall.call('mount PARTLABEL="%s" "%s"' % (partlabel, path))
    return path


def _board_partition_umount(mountpoint):
    if syscall.call('umount "%s"' % mountpoint):
        raise RuntimeError("Failed to umount %s!" % mountpoint)
    os.rmdir(mountpoint)


def _board_load_headers(hdr_defs, dtbos):
    hdtbos = {}
    hw_addons = {}
    board_headers = {}

    hdr_names_all = [hdr_def.name for hdr_def in hdr_defs]
    _board_find_overlays(dtbos, hdr_names_all, hdtbos, hw_addons)

    # Pins already set thru Jetson-IO tool
    hdr_prefixes = [hdr_def.prefix for hdr_def in hdr_defs]
    preconf_pins = _board_get_jetson_io_pinmux_pins(hdr_prefixes)

    for hdr_def in hdr_defs:
        hdr = hdr_def.name
        if hdr in hdtbos.keys():
            board_header = _BoardHeader(hdr_def, hdtbos[hdr], hw_addons[hdr],
                                        preconf_pins[hdr_def.prefix])
            board_headers[hdr] = board_header

    return board_headers


class _BoardHeader(object):
    def __init__(self, hdr_def, hdtbos, hw_addons, preconf_pins):
        self.hdr_def = hdr_def
        self.hdtbos = hdtbos
        self.hw_addons = hw_addons
        self.preconf_pins = preconf_pins
        # Below will be populated when the header is actually
        # loaded for the first time in set_active_header
        self.header = None


class Board(object):
    def __init__(self):
        self.appdir = None
        #self.bootdir = '/boot'
        self.bootdir = '/boot/arducam/dts'
        self.extlinux = '/boot/extlinux/extlinux.conf'
        dtbdir = os.path.join(self.bootdir, 'dtb')
        fio.is_rw(self.bootdir)

        #Finding the active partition in case of redundant rootfs flash.
        activepart = syscall.call_out('nvbootctrl -t rootfs get-current-slot')
        if activepart[0] == '0':
            mountpart = "APP"
        elif activepart[0] == '1':
            mountpart = "APP_b"
        else:
            raise RuntimeError("Failed to get active rootfs partition!")

        # When mounting the rootfs via NFS, the root partition is not a
        # block device. Furthermore, when booting with NFS the partition
        # that the bootloader reads to parse the extlinux.conf and load
        # the kernel DTB may not be mounted. Therefore, if the rootfs is
        # not mounted with the active partition, then it is necessary to
        # find and mount the active partition and copy the generated
        # files back to this partition.
        if not _board_partition_is_root_mountpoint(mountpart):
            self.appdir = _board_partition_mount(mountpart)
            dtbdir = os.path.join(self.appdir, 'boot/dtb')
            fio.is_rw(self.appdir)

        # Import platform specific data
        self.compat = dt.read_prop('compatible')
        self.model = dt.read_prop('model')
        self.dtb = _board_get_dtb(self.compat, self.model, dtbdir)
        dtbos = dtc.find_compatible_dtbo_files(self.compat.split(),
                                               self.bootdir)
        # Import pinmux
        self.pinmux = pmx.PinMux()

        # Load header definitions
        self.board_headers = _board_load_headers(Headers.HDRS, dtbos)

    def __del__(self):
        if self.appdir:
            _board_partition_umount(self.appdir)

    def get_board_headers(self):
        # The returned list has headers in the
        # same order as listed in Headers.HDRS
        headers = []
        for hdr_def in Headers.HDRS:
            if hdr_def.name in self.board_headers.keys():
                headers.append(hdr_def.name)
        return headers

    def set_active_header(self, hdr):
        if hdr not in self.board_headers.keys():
            raise RuntimeError("Unknown header %s!" % hdr)
        if self.board_headers[hdr].header is None:
            self.board_headers[hdr].header = \
                    header.Header(self.board_headers[hdr].hdtbos,
                                  self.board_headers[hdr].hdr_def,
                                  self.board_headers[hdr].preconf_pins,
                                  self.pinmux)
        self.hdtbo = self.board_headers[hdr].hdtbos
        self.hw_addons = self.board_headers[hdr].hw_addons
        self.header = self.board_headers[hdr].header
        self.hdr = hdr

    def preconf_pins_avail(self, hdr):
        if self.board_headers[hdr].preconf_pins:
            return True
        return False

    def hw_addon_get(self):
        return sorted(self.hw_addons.keys())

    def hw_addon_load(self, name):
        if name not in self.hw_addons.keys():
            raise RuntimeError("No overlay found for %s!" % name)

        overlay = self.hw_addons[name]
        self.header.pins_reset()

        nodes = dtc.find_nodes_with_prop(overlay, '/', 'nvidia,function')

        for node in nodes:
            pin_node = r'.*/%s-pin([0-9]+).*/' % self.header.prefix
            res = re.match(pin_node, node)
            if res is None:
                raise RuntimeError("Failed to get pin number for node %s!" %
                                   node)

            pin = int(res.groups()[0])
            function = dtc.get_prop_value(overlay, node, 'nvidia,function', 0)
            self.header.pin_set_function(pin, function)

    def _create_header_dtbo(self, name):
        dtbo = os.path.join(self.bootdir, name)
        shutil.copyfile(self.hdtbo, dtbo)
        pins = []

        for pin in self.header.pins.nodes.keys():
            # Fixed function pin
            if not self.header.pins.is_configurable(pin):
                # Such pin is deleted
                dtc.remove_node(dtbo, self.header.pin_get_node(pin))
            # Pin in default state and not listed in DT pinmux
            elif self.header.pin_is_default(pin) and \
                 not self.header.pin_configured_by_dt(pin):
                # All nodes under such pin are deleted
                nodes = self.header.pin_get_all_nodes(pin)
                for n in nodes.values():
                    dtc.remove_node(dtbo, n)
            else:
                pins.append(pin)

        if not pins:
            os.remove(dtbo)
            raise RuntimeError("Unable to generate DTBO for %s!" % self.hdr)

        # Below code ensures that changes made to the header in earlier
        # sessions of the tool (and written to DTB) are retained, even though
        # some (or all) of those pins may not be touched in the current session
        for pin in pins:
            function = self.header.pin_get_function(pin)

            # Enabled pin
            if self.header.pin_is_enabled(pin):
                # Pick the node that matches the enabled function
                node = self.header.pin_get_node(pin, function)
            # Disabled pin
            else:
                # Pick one node and set its props for disabling
                node = self.header.pin_get_default_node(pin)
                if function is not None:
                    dtc.set_prop_value(dtbo, node, 's',
                                       'nvidia,function', function)
                dtc.set_prop_value(dtbo, node, 'u',
                                   'nvidia,tristate', '1')
                dtc.set_prop_value(dtbo, node, 'u',
                                   'nvidia,enable-input', '0')

            # Custom properties are removed from the
            # pin node that will be retained
            dtc.delete_prop(dtbo, node, 'nvidia,pin-label')
            dtc.delete_prop(dtbo, node, 'nvidia,pin-group')

            # All nodes under the pin are removed, except
            # the one to be retained
            nodes = self.header.pin_get_all_nodes(pin)
            for n in nodes.values():
                if n != node:
                    dtc.remove_node(dtbo, n)

        return dtbo

    def create_dtbo_for_header(self):
        date = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        name = "User Custom [%s]" % date
        fn = "jetson-io-%s-user-custom.dtbo" % self.header.prefix
        dtbo = self._create_header_dtbo(fn)
        dtc.set_prop_value(dtbo, '/', 's', 'overlay-name', name)
        dtc.set_prop_value(dtbo, '/', 's',
                           'jetson-header-name', self.hdr)
        return dtbo

    def configure_overlays(self, dtbos):
        messages = []
        if len(dtbos) < 1:
            raise RuntimeError("No overlays to list!")
        name = "Custom Header Config:"
        overlays = ""
        for dtbo in dtbos:
            hdr = dtc.get_prop_value(dtbo, '/', 'jetson-header-name', 0)
            name += " <%s" % (self.board_headers[hdr].hdr_def.prefix.upper())
            name += " %s>" % dtc.get_prop_value(dtbo, '/', 'overlay-name', 0)
            if overlays:
                overlays += ","
            overlays += dtbo

        if self.appdir:
            appextlinux = os.path.join(self.appdir, self.extlinux[1:])
            sigextlinux = appextlinux + ".sig"
            extlinux.add_entry(appextlinux, 'JetsonIO', name, self.dtb[len(self.appdir):], overlays, True)
            messages.append("Modified " + appextlinux + " to add following DTBO entries: ")

            for dtbo in dtbos:
                shutil.copyfile(dtbo, os.path.join(self.appdir, dtbo[1:]))
                messages.append(dtbo)
            shutil.copyfile(appextlinux, self.extlinux)
            messages.append("Copied " + appextlinux + " to " + self.extlinux + ".")
        else:
            sigextlinux = self.extlinux + ".sig"
            extlinux.add_entry(self.extlinux, 'JetsonIO', name, self.dtb, overlays, True)
            messages.append("Modified " + self.extlinux + " to add following DTBO entries: ")
            for dtbo in dtbos:
                messages.append(dtbo)

        if os.path.exists(sigextlinux):
            backup_filename = sigextlinux + ".jetson-io-backup"
            os.rename(sigextlinux, backup_filename)
            messages.append("File " + sigextlinux + " has been backed up as " + backup_filename + ".")
        return messages

    def configure_dt_for_next_boot(self, dtbos):
        return self.configure_overlays(dtbos)
