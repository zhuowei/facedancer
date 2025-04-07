#!/usr/bin/env python3
#
# This file is part of FaceDancer.
#
""" USB 'Rubber Ducky' example; enters some text via the keyboard module. """

import asyncio
import logging
from typing      import Tuple, Iterable
from dataclasses import dataclass

from facedancer import main
from facedancer.devices.keyboard     import USBKeyboardDevice
from facedancer.classes.hid.keyboard import KeyboardModifiers
from facedancer.classes.hid.descriptor import HIDReportDescriptor
from facedancer.future import USBDevice, USBConfiguration, USBInterface, USBEndpoint, USBDirection, USBTransferType, use_inner_classes_automatically, USBClassDescriptor, vendor_request_handler, USBDescriptorTypeNumber, class_request_handler, USBStandardRequests, to_this_interface, use_automatically
from facedancer.classes import USBDeviceClass

#@use_inner_classes_automatically
class SprayInterface(USBInterface):
    def __init__(self, parent, number):
        super().__init__(parent=parent)
        self.number = number
        self.interface_string = "A"*15

@use_inner_classes_automatically
class USBSprayDevice(USBDevice):
    """ Simple USB keyboard device. """

    name           : str = "USB keyboard device"
    product_string : str = "Non-suspicious Keyboard"

    @use_automatically
    class KeyboardConfiguration(USBConfiguration):
        """ Primary USB configuration: act as a keyboard. """
        def __init__(self, parent):
            super().__init__(parent=parent)
            # max of 32 interfaces allowed on Linux
            for i in range(32):
                self.add_interface(SprayInterface(parent=self, number=i))


device = USBSprayDevice()

async def type_letters():
    pass

main(device, type_letters())
