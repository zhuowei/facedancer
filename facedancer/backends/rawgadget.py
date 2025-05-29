# Raw Gadget-based Facedancer backend.
#
# See https://github.com/xairy/raw-gadget for details about Raw Gadget.
#
# Authors:
#   Andrey Konovalov <andreyknvl@gmail.com>
#   Kirill Zhirovsky <me@kirill9617.win>

import errno
import fcntl
import logging
import os
import struct

from construct import *

from ..core import *
from ..USB import *
from ..USBEndpoint import USBEndpoint

class TrailingBytes(Bytes):
    def _sizeof(self, context, path):
        return 0

usb_endpoint_descriptor = Struct(
    'bLength' / Int8ul,
    'bDescriptorType' / Int8ul,
    'bEndpointAddress' / Int8ul,
    'bmAttributes' / Int8ul,
    'wMaxPacketSize' / Int16ul,
    'bInternal' / Int8ul,
    'bRefresh' / Int8ul,
    'bSynchAddress' / Int8ul,
)

usb_ctrlrequest = Struct(
    'bRequestType' / Int8ul,
    'bRequest' / Int8ul,
    'wValue' / Int16ul,
    'wIndex' / Int16ul,
    'wLength' / Int16ul
)

UDC_NAME_LENGTH_MAX = 128

usb_speed = Enum(Int8un,
    USB_SPEED_UNKNOWN = 0,
    USB_SPEED_LOW = 1,
    USB_SPEED_FULL = 2,
    USB_SPEED_HIGH = 3,
    USB_SPEED_WIRELESS = 4,
    USB_SPEED_SUPER = 5,
    USB_SPEED_SUPER_PLUS = 6
)

usb_raw_init = Struct(
    'driver_name' / PaddedString(UDC_NAME_LENGTH_MAX, 'ascii'),
    'device_name' / PaddedString(UDC_NAME_LENGTH_MAX, 'ascii'),
    'speed' / usb_speed
)

usb_raw_event_type = Enum(Int32un,
    USB_RAW_EVENT_INVALID = 0,
    USB_RAW_EVENT_CONNECT = 1,
    USB_RAW_EVENT_CONTROL = 2,
    USB_RAW_EVENT_SUSPEND = 3,
    USB_RAW_EVENT_RESUME = 4,
    USB_RAW_EVENT_RESET = 5,
    USB_RAW_EVENT_DISCONNECT = 6
)

usb_raw_event = Struct(
    'type' / usb_raw_event_type,
    'length' / Int32un,
    'data' / TrailingBytes(this.length)
)

usb_raw_ep_io = Struct(
    'ep' / Int16un,
    'flags' / Int16un,
    'length' / Int32un,
    'data' / TrailingBytes(this.length)
)

usb_raw_ep_caps = BitsSwapped(BitStruct(
    'type_control' / Bit,
    'type_iso' / Bit,
    'type_bulk' / Bit,
    'type_int' / Bit,
    'dir_in' / Bit,
    'dir_out' / Bit,
    Padding(26),
))

usb_raw_ep_limits = Struct(
    'maxpacket_limit' / Int16un,
    'max_streams' / Int16un,
    'reserved' / Int32un
)

USB_RAW_EPS_NUM_MAX = 30
USB_RAW_EP_NAME_MAX = 16

usb_raw_ep_info = Struct(
    'name' / PaddedString(USB_RAW_EP_NAME_MAX, 'ascii'),
    'addr' / Int32un,
    'caps' / usb_raw_ep_caps,
    'limits' / usb_raw_ep_limits,
)

usb_raw_eps_info = Struct(
    'eps' / usb_raw_ep_info[USB_RAW_EPS_NUM_MAX]
)

usb_raw_timeout_type = Enum(Int32un,
    USB_RAW_TIMEOUT_INVALID = 0,
    USB_RAW_TIMEOUT_EVENT_FETCH = 1,
    USB_RAW_TIMEOUT_EP0_IO = 2,
    USB_RAW_TIMEOUT_EP_IO = 3
)

usb_raw_timeout = Struct(
    'type' / usb_raw_timeout_type,
    'param' / Int32un,
    'timeout' / Int32un
)

class IOCTLRequest:
    IOC_NONE = 0
    IOC_WRITE = 1
    IOC_READ = 2

    IOC_NRBITS = 8
    IOC_TYPEBITS = 8
    IOC_SIZEBITS = 14
    IOC_DIRBITS = 2

    IOC_NRSHIFT = 0
    IOC_TYPESHIFT = (IOC_NRSHIFT + IOC_NRBITS)
    IOC_SIZESHIFT = (IOC_TYPESHIFT + IOC_TYPEBITS)
    IOC_DIRSHIFT = (IOC_SIZESHIFT + IOC_SIZEBITS)

    @staticmethod
    def IOC(dir, typ, nr, size):
        if size == None:
            size = 0
        else:
            size = size.sizeof()
        if isinstance(typ, str):
            typ = ord(typ[0])
        if isinstance(dir, str):
            dir = {'' : IOCTLRequest.IOC_NONE, 'R' : IOCTLRequest.IOC_READ, 'W' : IOCTLRequest.IOC_WRITE,
                   'WR' : IOCTLRequest.IOC_WRITE | IOCTLRequest.IOC_READ}[dir]
        return dir << IOCTLRequest.IOC_DIRSHIFT | typ << IOCTLRequest.IOC_TYPESHIFT | \
                nr << IOCTLRequest.IOC_NRSHIFT | size << IOCTLRequest.IOC_SIZESHIFT

    @staticmethod
    def ioc(dir, typ, nr, size):

        def fn(fd, arg=0):
            req = IOCTLRequest.IOC(dir, typ, nr, size)
            if isinstance(arg, bytes):
                arg = bytearray(arg)
            try:
                rv = fcntl.ioctl(fd, req, arg, True)
            except OSError as e:
                if e.errno == errno.ETIME:
                    raise TimeoutError
                raise
            return rv, arg

        return fn

class RawGadgetRequests(IOCTLRequest):
    USB_RAW_IOCTL_INIT = IOCTLRequest.ioc('W', 'U', 0, usb_raw_init)
    USB_RAW_IOCTL_RUN = IOCTLRequest.ioc('', 'U', 1, None)
    USB_RAW_IOCTL_EVENT_FETCH = IOCTLRequest.ioc('R', 'U', 2, usb_raw_event)
    USB_RAW_IOCTL_EP0_WRITE = IOCTLRequest.ioc('W', 'U', 3, usb_raw_ep_io)
    USB_RAW_IOCTL_EP0_READ = IOCTLRequest.ioc('WR', 'U', 4, usb_raw_ep_io)
    USB_RAW_IOCTL_EP_ENABLE = IOCTLRequest.ioc('W', 'U', 5, usb_endpoint_descriptor)
    USB_RAW_IOCTL_EP_DISABLE = IOCTLRequest.ioc('W', 'U', 6, Int32un)
    USB_RAW_IOCTL_EP_WRITE = IOCTLRequest.ioc('W', 'U', 7, usb_raw_ep_io)
    USB_RAW_IOCTL_EP_READ = IOCTLRequest.ioc('WR', 'U', 8, usb_raw_ep_io)
    USB_RAW_IOCTL_CONFIGURE = IOCTLRequest.ioc('', 'U', 9, None)
    USB_RAW_IOCTL_VBUS_DRAW = IOCTLRequest.ioc('W', 'U', 10, Int32un)
    USB_RAW_IOCTL_EPS_INFO = IOCTLRequest.ioc('R', 'U', 11, usb_raw_eps_info)
    USB_RAW_IOCTL_EP0_STALL = IOCTLRequest.ioc('', 'U', 12, None)
    USB_RAW_IOCTL_EP_SET_HALT = IOCTLRequest.ioc('W', 'U', 13, Int32un)
    USB_RAW_IOCTL_EP_CLEAR_HALT = IOCTLRequest.ioc('W', 'U', 14, Int32un)
    USB_RAW_IOCTL_EP_SET_WEDGE = IOCTLRequest.ioc('W', 'U', 15, Int32un)
    USB_RAW_IOCTL_SET_TIMEOUT = IOCTLRequest.ioc('W', 'U', 16, usb_raw_timeout)

class RawGadget:
    def __init__(self):
        self.fd = None
        self.last_ep_addr = 0

    def open(self):
        self.fd = open('/dev/raw-gadget', 'bw')

    def close(self):
        self.fd.close()

    def init(self, driver, device, speed):
        arg = usb_raw_init.build({ 'driver_name' : driver, 'device_name' : device, 'speed' : speed })
        RawGadgetRequests.USB_RAW_IOCTL_INIT(self.fd, arg)

    def run(self):
        RawGadgetRequests.USB_RAW_IOCTL_RUN(self.fd)

    def event_fetch(self, data):
        arg = usb_raw_event.build({ 'type' : 0, 'length' : len(data), 'data' : data })
        try:
            _, data = RawGadgetRequests.USB_RAW_IOCTL_EVENT_FETCH(self.fd, arg)
        except TimeoutError:
            return None
        return usb_raw_event.parse(data)

    def ep0_write(self, data, flags=0):
        arg = usb_raw_ep_io.build({ 'ep' : 0, 'flags' : flags, 'length' : len(data), 'data' : data })
        try:
            RawGadgetRequests.USB_RAW_IOCTL_EP0_WRITE(self.fd, arg)
        except TimeoutError:
            pass

    def ep0_read(self, data, flags=0):
        arg = usb_raw_ep_io.build({ 'ep' : 0, 'flags' : flags, 'length' : len(data), 'data' : data })
        try:
            rv, data = RawGadgetRequests.USB_RAW_IOCTL_EP0_READ(self.fd, arg)
        except TimeoutError:
            return None, None
        return rv, data

    def ep_enable(self, ep_desc):
        rv, _ = RawGadgetRequests.USB_RAW_IOCTL_EP_ENABLE(self.fd, ep_desc)
        logging.info(f'ep_enable: {rv=}')
        return rv

    def ep_disable(self, ep_num):
        RawGadgetRequests.USB_RAW_IOCTL_EP_DISABLE(self.fd, ep_num)
        logging.info(f'ep_disable: {ep_num=}')

    def ep_write(self, ep_num, data, flags=0):
        arg = usb_raw_ep_io.build({ 'ep' : ep_num, 'flags' : flags, 'length' : len(data), 'data' : data })
        try:
            RawGadgetRequests.USB_RAW_IOCTL_EP_WRITE(self.fd, arg)
        except TimeoutError:
            pass

    def ep_read(self, ep_num, data, flags=0):
        arg = usb_raw_ep_io.build({ 'ep' : ep_num, 'flags' : flags, 'length' : len(data), 'data' : data })
        try:
            rv, data = RawGadgetRequests.USB_RAW_IOCTL_EP_READ(self.fd, arg)
        except TimeoutError:
            return None, None
        return rv, data

    def configure(self):
        RawGadgetRequests.USB_RAW_IOCTL_CONFIGURE(self.fd)

    def vbus_draw(self, power):
        RawGadgetRequests.USB_RAW_IOCTL_VBUS_DRAW(self.fd, power)

    def eps_info(self):
        eps_info = bytes(usb_raw_eps_info.sizeof())
        num, resp = RawGadgetRequests.USB_RAW_IOCTL_EPS_INFO(self.fd, eps_info)
        return usb_raw_eps_info.parse(resp)

    def ep0_stall(self):
        RawGadgetRequests.USB_RAW_IOCTL_EP0_STALL(self.fd)

    def set_timeout(self, typ, param, timeout):
        arg = usb_raw_timeout.build({ 'type' : typ, 'param' : param, 'timeout' : timeout})
        RawGadgetRequests.USB_RAW_IOCTL_SET_TIMEOUT(self.fd, arg)

class RawGadgetApp(FacedancerApp):
    app_name = 'Raw Gadget'

    HOST_TO_DEVICE = 0
    DEVICE_TO_HOST = 1

    @staticmethod
    def _endpoint_address(ep_num, direction):
        if direction:
            return ep_num | 0x80
        else:
            return ep_num

    @staticmethod
    def _endpoint_number(ep_addr):
        return ep_addr & 0x7f

    @staticmethod
    def _endpoint_direction(ep_addr):
        return ep_addr >> 7

    @classmethod
    def appropriate_for_environment(cls, backend_name):
        if backend_name and backend_name != 'rawgadget':
            return False

        try:
            rg = open('/dev/raw-gadget')
            rg.close()
            return True
        except ImportError:
            logging.info('Skipping Raw Gadget, as could not open /dev/raw-gadget .')
            return False
        except:
            logging.exception('Raw Gadget check fail', exc_info=True, stack_info=True)
            return False

    def __init__(self, device=None, verbose=0, quirks=None):
        if 'RG_UDC_DRIVER' in os.environ:
            self.udc_driver = os.environ['RG_UDC_DRIVER'].lower()
        else:
            self.udc_driver = 'dummy_udc'

        if 'RG_UDC_DEVICE' in os.environ:
            self.udc_device = os.environ['RG_UDC_DEVICE'].lower()
        else:
            self.udc_device = 'dummy_udc.0'

        # Since Facedancer does not provide the device speed,
        # get it from an environment variable.
        if 'RG_USB_SPEED' in os.environ:
            self.speed = int(os.environ['RG_USB_SPEED'])
        else:
            self.speed = usb_speed.USB_SPEED_HIGH

        self.api = RawGadget()
        self.enabled_eps = {}
        self.eps_info = None
        self.connected_device = None
        self.is_configured = False
        self.is_suspended = False

        super().__init__(device, verbose)

    def init_commands(self):
        self.api.open()
        self.api.init(self.udc_driver, self.udc_device, self.speed)
        # Set a small timeout for event fetching, as it only checks a Raw Gadget
        # internal queue for events and does no USB communication.
        self.api.set_timeout(usb_raw_timeout_type.USB_RAW_TIMEOUT_EVENT_FETCH, 0, 20)
        # Set a larger timeout for endpoint operations here and in configured,
        # as these operations do USB communication.
        self.api.set_timeout(usb_raw_timeout_type.USB_RAW_TIMEOUT_EP0_IO, 0, 100)

    def connect(self, device, maxp_ep0):
        self.connected_device = device
        self.api.run()

    def disconnect(self):
        self.api.close()

    def ack_status_stage(self, direction=HOST_TO_DEVICE, endpoint_number=0, blocking=False):
        logging.info(f'ack_status_stage: {direction=} {endpoint_number=} {blocking=}')
        if endpoint_number != 0:
            raise NotImplementedError()
        if direction == self.HOST_TO_DEVICE:
            self.api.ep0_read(bytes([]))
        else:
            self.api.ep0_write(bytes([]))

    def send_on_endpoint(self, ep_num, data, blocking=False):
        # Here and in ack_status_stage, Raw Gadget backend ignores the blocking
        # argument, as it does not support non-blocking transfers. Instead,
        # this backend relies on timeouts.
        logging.info(f'send_on_endpoint: {ep_num=} {len(data)=:0x} {blocking=}')
        if ep_num == 0:
            if self.last_control_direction == self.HOST_TO_DEVICE:
                # zhuowei - hack: copy data back...
                rv, return_data = self.api.ep0_read(bytes(data))
                if rv > 0 and isinstance(data, bytearray):
                    data[0:rv] = return_data[0:rv]
            else:
                self.api.ep0_write(bytes(data))
        else:
            ep_addr = self._endpoint_address(ep_num, self.DEVICE_TO_HOST)
            self.api.ep_write(self.enabled_eps[ep_addr], bytes(data))

    def _read_from_endpoint(self, ep_addr, data):
        rv, data = self.api.ep_read(self.enabled_eps[ep_addr], bytes(data))
        if rv == None:
            return None
        return usb_raw_ep_io.parse(data).data

    def configured(self, configuration):
        for ep in self.enabled_eps:
            self.api.ep_disable(self.enabled_eps[ep])
        self.enabled_eps = {}

        for interface in configuration.get_interfaces():
            for ep in interface.get_endpoints():
                # We could validate the endpoint descriptor against the UDC
                # endpoint capabilities and the selected USB device speed.
                # This will, however, limit the ability to emulate devices
                # that do not strictly follow the USB specifications;
                # some UDCs unofficially support this. As having this ability
                # might be useful for fuzzing, use the endpoint descriptor as
                # is. As a trade off, this might lead to unpredictable errors
                # during the device emulation.
                ep_handle = self.api.ep_enable(ep.get_descriptor())
                self.api.set_timeout(usb_raw_timeout_type.USB_RAW_TIMEOUT_EP_IO, ep_handle, 100)
                self.enabled_eps[ep.get_address()] = ep_handle

        self.api.vbus_draw(configuration.max_power // 2)
        self.api.configure()

        self.configuration = configuration
        self.is_configured = True

        logging.info(f'configured')

    def stall_ep0(self):
        self.api.ep0_stall()

    def stall_endpoint(self, ep_num, direction):
        if ep_num == 0:
            self.stall_ep0()
        else:
            # Raw Gadget does support stalling non-control endpoints, but none
            # of the Facedancer examples do this. Thus, testing this feature is
            # hard, so leave this as not implemented.
            raise NotImplementedError()

    def set_address(self, address, defer):
        # Raw Gadget backend cannot receive a SET_ADDRESS request, as this
        # request is handled by the UDC driver.
        raise NotImplementedError()

    def reset(self):
        # Raw Gadget does not yet support resetting the device.
        raise NotImplementedError()

    def _get_endpoint(self, ep_addr):
        try:
            # Try future API.
            ep_num = self._endpoint_number(ep_addr)
            ep_dir = self._endpoint_direction(ep_addr)
            return self.connected_device.get_endpoint(ep_num, ep_dir)
        except AttributeError:
            # Fall back to legacy API.
            for interface in self.connected_device.configuration.get_interfaces():
                for ep in interface.get_endpoints():
                    if ep.get_address() == ep_addr:
                        return ep
        return None

    def service_irqs(self):
        event = self.api.event_fetch(bytes(usb_ctrlrequest.sizeof()))
        if event != None:
            if event.type == usb_raw_event_type.USB_RAW_EVENT_CONNECT:
                # UDC endpoint information is only obtained for reference:
                # this backend does use it in any way. In the future, this
                # backend can be extended to validate UDC endpoints
                # capabilities against the device endpoint descriptors.
                self.eps_info = self.api.eps_info()
            elif event.type == usb_raw_event_type.USB_RAW_EVENT_CONTROL:
                request = self.connected_device.create_request(event.data)
                self.last_control_direction = request.get_direction()
                self.connected_device.handle_request(request)
            elif event.type == usb_raw_event_type.USB_RAW_EVENT_DISCONNECT:
                # For an unclear reason, some UDC drivers issue a disconnect
                # event when the device is being reconfigured. Thus, treat
                # disconnect as reset.
                self.is_configured = False
                logging.info(f'gadget disconnected')
            elif event.type == usb_raw_event_type.USB_RAW_EVENT_SUSPEND:
                self.is_suspended = True
                logging.info(f'gadget suspended')
            elif event.type == usb_raw_event_type.USB_RAW_EVENT_RESET:
                self.is_configured = False
                logging.info(f'gadget reset')
            elif event.type == usb_raw_event_type.USB_RAW_EVENT_RESUME:
                self.is_suspended = False
                logging.info(f'gadget resumed')
            else:
                # Raw Gadget might be extended and start reporting other kinds
                # of events. Instead of ignoring these events, raise an
                # exception to hint that this backend must be extended as well.
                raise NotImplementedError()

        if not(self.is_configured) or self.is_suspended:
            return

        for ep_addr in self.enabled_eps:
            ep_dir = self._endpoint_direction(ep_addr)
            ep_num = self._endpoint_number(ep_addr)
            ep = self._get_endpoint(ep_addr)

            if ep_dir == self.DEVICE_TO_HOST:
                try:
                    # Try future API.
                    self.connected_device.handle_data_requested(ep)
                except AttributeError:
                    # Fall back to legacy API.
                    self.connected_device.handle_buffer_available(ep_num)
            else:
                data = self._read_from_endpoint(ep_addr, bytes(ep.max_packet_size))
                if data != None:
                    try:
                        # Try future API.
                        self.connected_device.handle_data_received(ep, data)
                    except AttributeError:
                        # Fall back to legacy API.
                        self.connected_device.handle_data_available(ep_addr, data)
