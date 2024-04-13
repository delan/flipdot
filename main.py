#!/usr/bin/env python3
# pyright: strict
import argparse
import sys
import time
from types import NoneType
from typing import Callable, TypeAlias

import serial.rs485


Applet: TypeAlias = Callable[[int, "SevenSegment"], NoneType]
applets: dict[str, Applet] = {}
def applet(fun: Applet):
    applets[fun.__name__] = fun


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port")
    parser.add_argument("addr")
    parser.add_argument("applet", nargs="?")
    args = parser.parse_args()

    addr = int(args.addr, base=0)
    applet = applets.get(args.applet)
    if applet is None:
        print(f"available applets: {applets.keys()}")
        sys.exit(1)

    with SevenSegment(args.port) as ser:
        time.sleep(0)
        applet(addr, ser)


@applet
def hello(addr: int, ser: "SevenSegment"):
    s = "   hello world   "
    for i in range(len(s) - 2):
        ser.write_str(addr, s[i : i + 3])
        time.sleep(1.5)


@applet
def cycle_agd(addr: int, ser: "SevenSegment"):
    l = SevenSegment.A
    m = SevenSegment.G
    r = SevenSegment.D
    while True:
        ser.write_segments(addr, l, m, r)
        time.sleep(1.5)
        l, m, r = m, r, l


@applet
def counter(addr: int, ser: "SevenSegment"):
    for i in range(1000):
        ser.write_str(addr, str(i))
        time.sleep(1.5)


class MobitecRS485(serial.rs485.RS485):
    def __init__(self, port: str):
        super().__init__(port, baudrate=4800, timeout=0.1)

        #                   for...
        # MAX485 pins       RX  TX
        # ========================
        # RE (active-low)    0   1
        # DE (active-high)   0   1
        #
        # the CH430 seems to invert RTS, so even though we want RTS to be low during RX and high
        # during TX, we need to pre-invert them here
        self.rs485_mode = serial.rs485.RS485Settings(
            rts_level_for_rx=True,
            rts_level_for_tx=False,
            delay_before_rx=0.25,
            delay_before_tx=0.25,
        )

        self.start_time = time.monotonic()

    def write_packet(self, addr: int, b: bytes):
        # TODO: may need to calculate checksum after escaping, unclear
        data = bytes([addr, *b])
        payload = bytes([*data, (sum(data) & 0xFF)])

        payload_escaped = bytearray()
        for byte in payload:
            if byte == 0xFE:
                payload_escaped.extend([0xFE, 0x00])
            elif byte == 0xFF:
                payload_escaped.extend([0xFE, 0x01])
            else:
                payload_escaped.append(byte)

        # wrapping the data in empty messages on either side, then doubling that
        # in our tx, seems to trigger display updates much more reliably.
        packet = bytes([0xFF, addr, addr, 0xFF, 0xFF, *payload_escaped, 0xFF, 0xFF, addr, addr, 0xFF] * 2)
        t = time.monotonic() - self.start_time
        print(f"@{t} write to {addr=:02x}: {better_hex(b)} (packet: {better_hex(packet)})")
        self.write(packet)


class SevenSegment(MobitecRS485):
    A = 1 << 0
    B = 1 << 1
    C = 1 << 2
    D = 1 << 3
    E = 1 << 4
    F = 1 << 5
    G = 1 << 6

    FONT_RANGE_0 = [
        A | B | C | D | E | F,  # 0 = 0x30
        B | C,  # 1 = 0x31
        A | B | D | E | G,  # 2 = 0x32
        A | B | C | D | G,  # 3 = 0x33
        B | C | F | G,  # 4 = 0x34
        A | C | D | F | G,  # 5 = 0x35
        A | C | D | E | F | G,  # 6 = 0x36
        A | B | C,  # 7 = 0x37
        A | B | C | D | E | F | G,  # 8 = 0x38
        A | B | C | F | G,  # 9 = 0x39
    ]

    FONT_RANGE_1 = [
        A | B | C | E | F | G,  # A = 0x41
        C | D | E | F | G,  # B = 0x42
        A | D | E | F,  # C = 0x43
        B | C | D | E | G,  # D = 0x44
        A | D | E | F | G,  # E = 0x45
        A | E | F | G,  # F = 0x46
        A | C | D | E | F,  # G = 0x47
        B | C | E | F | G,  # H = 0x48
        C,  # I = 0x49
        B | C | D | E,  # J = 0x4a
        A | C | E | F | G,  # K = 0x4b
        D | E | F,  # L = 0x4c
        A | C | E | G,  # M = 0x4d
        C | E | G,  # N = 0x4e
        C | D | E | G,  # O = 0x4f
        A | B | E | F | G,  # P = 0x50
        A | B | C | F | G,  # Q = 0x51
        E | G,  # R = 0x52
        A | C | D | F | G,  # S = 0x53
        D | E | F | G,  # T = 0x54
        B | C | D | E | F,  # U = 0x55
        C | D | E,  # V = 0x56
        B | D | F | G,  # W = 0x57
        B | C | E | F | G,  # X = 0x58
        B | C | D | F | G,  # Y = 0x59
        A | B | D | E | G,  # Z = 0x5a
    ]

    def _font(self, c: str):
        if len(c) != 1:
            raise ValueError(f"can't look up multi-character string {c!r} in font")

        cc = ord(c)
        if cc >= 0x61 and cc <= 0x7A:
            cc -= 0x61
            cc += 0x41

        if cc == 0x20:
            return 0
        elif cc >= 0x30 and cc <= 0x39:
            return self.FONT_RANGE_0[cc - 0x30]
        elif cc >= 0x41 and cc <= 0x5A:
            return self.FONT_RANGE_1[cc - 0x41]
        else:
            raise ValueError(f"char {c!r} not in font")

    def write_segments(self, addr: int, l: int, m: int, r: int):
        if l < 0 or l >= 0x80:
            raise ValueError("value {l:#04x} out of range")
        if m < 0 or m >= 0x80:
            raise ValueError("value {m:#04x} out of range")
        if r < 0 or r >= 0x80:
            raise ValueError("value {r:#04x} out of range")

        self.write_packet(addr, bytes([0xAE, r, m, l, 0x00]))

    def write_digits(self, addr: int, l: int, m: int, r: int):
        if l < 0 or l >= 0xF:
            raise ValueError("value {l:#04x} out of range")
        if m < 0 or m >= 0xF:
            raise ValueError("value {m:#04x} out of range")
        if r < 0 or r >= 0xF:
            raise ValueError("value {r:#04x} out of range")

        self.write_segments(
            addr, self._font(f"{l:x}"), self._font(f"{m:x}"), self._font(f"{r:x}")
        )

    def write_str(self, addr: int, s: str):
        print(f"write_str {s!r}")
        if len(s) > 3:
            raise ValueError("string {s!r} must have length 3 or less")

        s = s.ljust(3)
        self.write_segments(addr, self._font(s[0]), self._font(s[1]), self._font(s[2]))


def better_hex(b: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in b)


if __name__ == "__main__":
    main()
