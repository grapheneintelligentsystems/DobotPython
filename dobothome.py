#!/usr/bin/env  python3.5
# -*- coding: utf-8 -*-

import time
from glob import glob

import struct
import threading
import time
import ctypes
import serial

MODE_PTP_JUMP_XYZ = 0x00
MODE_PTP_MOVJ_XYZ = 0x01
MODE_PTP_MOVL_XYZ = 0x02
MODE_PTP_JUMP_ANGLE = 0x03
MODE_PTP_MOVJ_ANGLE = 0x04
MODE_PTP_MOVL_ANGLE = 0x05
MODE_PTP_MOVJ_INC = 0x06
MODE_PTP_MOVL_INC = 0x07
MODE_PTP_MOVJ_XYZ_INC = 0x08
MODE_PTP_JUMP_MOVL_XYZ = 0x09


class Message:

    def __init__(self, b=None):
        if b is None:
            self.header = bytes([0xAA, 0xAA])
            self.len = 0x00
            self.ctrl = 0x00
            self.params = bytes([])
            self.checksum = None
        else:
            self.header = b[0:2]
            self.len = b[2]
            self.id = b[3]
            self.ctrl = b[4]
            self.params = b[5:-1]
            self.checksum = b[-1:][0]

    def __repr__(self):
        return "Message()"

    def __str__(self):
        self.refresh()
        ret = "%s:%d:%d:%d:%s:%s" % (self.header, self.len, ord(self.id), self.ctrl, self.params, ord(self.checksum))
        return ret.upper()

    def refresh(self):
        if self.checksum is None:
            self.checksum = self.id + self.ctrl
            for i in range(len(self.params)):
                if isinstance(self.params[i], int):
                    self.checksum += self.params[i]
                else:
                    self.checksum += int(self.params[i].encode('hex'), 16)
            self.checksum = self.checksum % 256
            self.checksum = 2 ** 8 - self.checksum
            self.checksum = self.checksum % 256
            self.len = 0x02 + len(self.params)

    def bytes(self):
        self.refresh()
        if len(self.params) > 0:
            command = bytearray([0xAA, 0xAA, self.len, self.id, self.ctrl])
            command.extend(self.params)
            command.append(self.checksum)
        else:
            command = bytes([0xAA, 0xAA, self.len, self.id, self.ctrl, self.checksum])
        return command


class Dobot2(threading.Thread):
    on = True
    x = 0.0
    y = 0.0
    z = 0.0
    r = 0.0
    j1 = 0.0
    j2 = 0.0
    j3 = 0.0
    j4 = 0.0

    # joint_angles = [4]

    def __init__(self, port, verbose=False):
        threading.Thread.__init__(self)
        self.verbose = verbose
        self.lock = threading.Lock()
        self.ser = serial.Serial(port,
                                 baudrate=115200,
                                 parity=serial.PARITY_NONE,
                                 stopbits=serial.STOPBITS_ONE,
                                 bytesize=serial.EIGHTBITS)
        is_open = self.ser.isOpen()
        if self.verbose:
            print('pydobot: %s open' % self.ser.name if is_open else 'failed to open serial port')
        self._set_ptp_coordinate_params(velocity=200.0, acceleration=200.0)
        self._set_ptp_common_params(velocity=200.0, acceleration=200.0)
        self.start()

    def run(self):
        while self.on:
            self._get_pose()
            time.sleep(0.2)

    def close(self):
        self.on = False
        self.lock.acquire()
        self.ser.close()
        if self.verbose:
            print('pydobot: %s closed' % self.ser.name)
        self.lock.release()

    def _send_command(self, msg):
        self.lock.acquire()
        self.ser.reset_input_buffer()
        self._send_message(msg)
        response = self._read_message()
        self.lock.release()
        return response

    def _send_message(self, msg):
        time.sleep(0.1)
        if self.verbose:
            print('pydobot: >>', msg.bytes())
        self.ser.write(msg.bytes())

    def __read_message(self):
        time.sleep(0.1)
        b = self.ser.read_all()
        if len(b) > 0:
            msg = Message(b)
            if self.verbose:
                print('pydobot: <<', msg)
                return msg
            return

    def _read_message(self):
        # time.sleep(0.1)
        # Search for begin
        begin_found = False
        last_byte = None
        tries = 5
        while not begin_found and tries > 0:
                current_byte = ord(self.ser.read(1))
                if current_byte == 170:
                    if last_byte == 170:
                        begin_found = True
                last_byte = current_byte
                tries = tries - 1
        if begin_found:
            payload_length = ord(self.ser.read(1))
            payload_checksum = self.ser.read(payload_length + 1)
            if len(payload_checksum) == payload_length + 1:
                b = bytearray([0xAA, 0xAA])
                b.extend(bytearray([payload_length]))
                b.extend(payload_checksum)
                msg = Message(b)
                if self.verbose:
                    print('Lenght', payload_length)
                    print('MessageID:', ord(chr(payload_checksum[0])))
                    print('pydobot: <<', ":".join('{:02x}'.format(x) for x in b))
                return msg
        return

    def _get_pose(self):
        msg = Message()
        msg.id = 10
        response = self._send_command(msg)
        if response and response.id == 10:
            self.x = struct.unpack_from('f', response.params, 0)[0]
            self.y = struct.unpack_from('f', response.params, 4)[0]
            self.z = struct.unpack_from('f', response.params, 8)[0]
            self.r = struct.unpack_from('f', response.params, 12)[0]
            self.j1 = struct.unpack_from('f', response.params, 16)[0]
            self.j2 = struct.unpack_from('f', response.params, 20)[0]
            self.j3 = struct.unpack_from('f', response.params, 24)[0]
            self.j4 = struct.unpack_from('f', response.params, 28)[0]
            if self.verbose:
                print("pydobot: x:%03.1f y:%03.1f z:%03.1f r:%03.1f j1:%03.1f j2:%03.1f j3:%03.1f j4:%03.1f" % 
                      (self.x, self.y, self.z, self.r, self.j1, self.j2, self.j3, self.j4))
        else:
            if self.verbose:
                print("GetPose: empty response")
        return response

    def _get_queued_cmd_current_index(self):
        msg = Message()
        msg.id = 246
        response = self._send_command(msg)
        if response and response.id == 246:
            return self._extract_cmd_index(response)
        else:
            return -1

    def _extract_cmd_index(self, response):
        return struct.unpack_from('I', response.params, 0)[0]

    def wait_for_cmd(self, cmd_id):
        current_cmd_id = self._get_queued_cmd_current_index()
        while cmd_id > current_cmd_id:
            if self.verbose:
                print("Current-ID", current_cmd_id)
                print("Waiting for", cmd_id)
            time.sleep(0.5)
            current_cmd_id = self._get_queued_cmd_current_index()
            
    def _set_home_cmd(self):
        msg = Message()
        msg.id = 31
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.append(0x00)
        return self._send_command(msg)
    
    def _set_home_coordinate(self, x, y, z, r):
        msg = Message()
        msg.id = 30
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray(struct.pack('f', x)))
        msg.params.extend(bytearray(struct.pack('f', y)))
        msg.params.extend(bytearray(struct.pack('f', z)))
        msg.params.extend(bytearray(struct.pack('f', r)))
        return self._send_command(msg)

    def _set_cp_cmd(self, x, y, z):
        msg = Message()
        msg.id = 91
        msg.ctrl = 0x03
        msg.params = bytearray(bytes([0x01]))
        msg.params.extend(bytearray(struct.pack('f', x)))
        msg.params.extend(bytearray(struct.pack('f', y)))
        msg.params.extend(bytearray(struct.pack('f', z)))
        msg.params.append(0x00)
        return self._send_command(msg)

    def _set_ptp_coordinate_params(self, velocity, acceleration):
        msg = Message()
        msg.id = 81
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray(struct.pack('f', velocity)))
        msg.params.extend(bytearray(struct.pack('f', velocity)))
        msg.params.extend(bytearray(struct.pack('f', acceleration)))
        msg.params.extend(bytearray(struct.pack('f', acceleration)))
        return self._send_command(msg)

    def _set_ptp_common_params(self, velocity, acceleration):
        msg = Message()
        msg.id = 83
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray(struct.pack('f', velocity)))
        msg.params.extend(bytearray(struct.pack('f', acceleration)))
        return self._send_command(msg)

    def _set_ptp_cmd(self, x, y, z, r, mode):
        msg = Message()
        msg.id = 84
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray([mode]))
        msg.params.extend(bytearray(struct.pack('f', x)))
        msg.params.extend(bytearray(struct.pack('f', y)))
        msg.params.extend(bytearray(struct.pack('f', z)))
        msg.params.extend(bytearray(struct.pack('f', r)))
        return self._send_command(msg)
    
    def _set_arc_cmd(self, x, y, z, r, cir_x, cir_y, cir_z, cir_r):
        msg = Message()
        msg.id = 101
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray(struct.pack('f', cir_x)))
        msg.params.extend(bytearray(struct.pack('f', cir_y)))
        msg.params.extend(bytearray(struct.pack('f', cir_z)))
        msg.params.extend(bytearray(struct.pack('f', cir_r)))
        msg.params.extend(bytearray(struct.pack('f', x)))
        msg.params.extend(bytearray(struct.pack('f', y)))
        msg.params.extend(bytearray(struct.pack('f', z)))
        msg.params.extend(bytearray(struct.pack('f', r)))
        return self._send_command(msg)

    def _set_end_effector_suction_cup(self, suck=False):
        msg = Message()
        msg.id = 62
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray([0x01]))
        if suck is True:
            msg.params.extend(bytearray([0x01]))
        else:
            msg.params.extend(bytearray([0x00]))
        return self._send_command(msg)

    def go(self, x, y, z, r=0., mode=MODE_PTP_MOVJ_XYZ):
        return self._extract_cmd_index(self._set_ptp_cmd(x, y, z, r, mode))

    def go_lin(self, x, y, z, r=0., mode=MODE_PTP_MOVL_XYZ):
        return self._extract_cmd_index(self._set_ptp_cmd(x, y, z, r, mode))
    
    def go_arc(self, x, y, z, r, cir_x, cir_y, cir_z, cir_r):
        return self._extract_cmd_index(self._set_arc_cmd(x, y, z, r, cir_x, cir_y, cir_z, cir_r))

    def suck(self, suck):
        return self._extract_cmd_index(self._set_end_effector_suction_cup(suck))
    
    def set_home(self, x, y, z, r=0.):
        self._set_home_coordinate(x, y, z, r)
    
    def home(self):
        return self._extract_cmd_index(self._set_home_cmd())

    def speed(self, velocity=100., acceleration=100.):
        self._set_ptp_common_params(velocity, acceleration)
        self._set_ptp_coordinate_params(velocity, acceleration)

    def conveyor_belt(self, speed , direction=1, interface=0):
        if 0.0 <= speed <= 100.0 and (direction == 1 or direction == -1):
            STEP_PER_CRICLE = 360.0 / 1.8 * 10.0 * 16.0
            MM_PER_CRICLE = 3.1415926535898 * 36.0
            motor_speed = 70 * speed * STEP_PER_CRICLE / MM_PER_CRICLE * direction
            self._set_stepper_motor(motor_speed, interface)
        else:
            print("Wrong Parameter")

    def _set_stepper_motor(self, speed, interface=0, motor_control=True):
        msg = Message()
        msg.id = 0x87
        msg.ctrl = 0x03
        msg.params = bytearray([8])
        if interface == 1:
            msg.params.extend(bytearray([0x01]))
        else:
            msg.params.extend(bytearray([0x00]))
        if motor_control is True:
            msg.params.extend(bytearray([0x01]))
        else:
            msg.params.extend(bytearray([0x00]))
            
        msg.params.extend(bytearray(struct.pack('f', speed)))

        result = self._send_command(msg)

        return result

    def conveyor_belt_distance(self, speed , distance, direction=1, interface=0):
        if 0.0 <= speed <= 100.0 and (direction == 1 or direction == -1):
            STEP_PER_CRICLE = 360.0 / 1.8 * 10.0 * 16.0
            MM_PER_CRICLE = 3.1415926535898 * 36.0
            motor_speed = speed * STEP_PER_CRICLE / MM_PER_CRICLE * direction
            self._set_stepper_motor_distance(motor_speed, distance, interface)
        else:
            print("Wrong Parameter")

    def _set_stepper_motor_distance(self, speed, distance, interface=0, motor_control=True):
        msg = Message()
        msg.id = 0x88
        msg.ctrl = 0x03
        msg.params = bytearray([])
        if interface == 1:
            msg.params.extend(bytearray([0x01]))
        else:
            msg.params.extend(bytearray([0x00]))
        if motor_control is True:
            msg.params.extend(bytearray([0x01]))
        else:
            msg.params.extend(bytearray([0x00]))
        msg.params.extend(bytearray(struct.pack('i', speed)))
        msg.params.extend(bytearray(struct.pack('I', distance)))
        return self._send_command(msg)

    def _set_end_effector_gripper(self, grip=False):
        msg = Message()
        msg.id = 63
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray([0x01]))
        if grip is True:
            msg.params.extend(bytearray([0x01]))
        else:
            msg.params.extend(bytearray([0x00]))
        return self._send_command(msg)
    def startConveyor(self):
        msg = Message()
        msg.id = 135
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray([0x00]))
        msg.params.extend(bytearray([0x01]))
        msg.params.extend(bytearray([0x20]))
        msg.params.extend(bytearray([0x4e]))
        msg.params.extend(bytearray([0x00]))
        msg.params.extend(bytearray([0x00]))
        return self._send_command(msg)
    def stopConveyor(self):
        msg = Message()
        msg.id = 135
        msg.ctrl = 0x03
        msg.params = bytearray([])
        msg.params.extend(bytearray([0x00]))
        msg.params.extend(bytearray([0x00]))
        msg.params.extend(bytearray([0x20]))
        msg.params.extend(bytearray([0x4e]))
        msg.params.extend(bytearray([0x00]))
        msg.params.extend(bytearray([0x00]))
        return self._send_command(msg)
    def grip(self, grip):
        self._set_end_effector_gripper(grip)

    
available_ports = glob('/dev/ttyUSB0')  # mask for Dobot port
if len(available_ports) == 0:
    print('no port found for Dobot Magician')
    exit(1)
    
device = Dobot2(port=available_ports[0], verbose=False) 
time.sleep(0.5)

# home
device.home();
time.sleep(10)

device.close()
