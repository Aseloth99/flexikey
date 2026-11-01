"""Sistem bosta suresi (GetLastInputInfo): 32 bit tick sayaci ~49,7 gunde basa sardiginda da dogru olmali.

Gercek Win32 cagrisi yapilmaz: user32/kernel32 sahte.
"""

from __future__ import annotations

import unittest
from unittest import mock

import _support  # noqa: F401  (proje kokunu sys.path'e ekler)

from src.core import win_input


def fake_apis(ticks, last_input, ok=1):
    user32, kernel32 = mock.Mock(), mock.Mock()

    def get_last_input_info(ref):
        ref._obj.dwTime = last_input
        return ok

    user32.GetLastInputInfo.side_effect = get_last_input_info
    kernel32.GetTickCount.return_value = ticks
    return user32, kernel32


class SystemIdleSecondsTests(unittest.TestCase):
    def test_plain_difference(self):
        self.assertAlmostEqual(win_input.system_idle_seconds(*fake_apis(10_000, 4_000)), 6.0)

    def test_tick_counter_wraparound(self):
        # son girdi sayac sarmadan hemen once, simdi sardiktan sonra (eskiden ~49,7 gun cikiyordu)
        self.assertAlmostEqual(win_input.system_idle_seconds(*fake_apis(0x800, 0xFFFFF000)), 6.144)

    def test_long_uptime_uses_32_bit_counter(self):
        # 49,7 gunden uzun acik sistem: 32 bit sayac 1000, son girdi 900 -> 0,1 sn (GetTickCount64 kullanilmaz)
        user32, kernel32 = fake_apis(1000, 900)
        kernel32.GetTickCount64.return_value = 2 ** 32 + 1000
        self.assertAlmostEqual(win_input.system_idle_seconds(user32, kernel32), 0.1)
        kernel32.GetTickCount64.assert_not_called()

    def test_api_failure_counts_as_busy(self):
        self.assertEqual(win_input.system_idle_seconds(*fake_apis(10_000, 0, ok=0)), 0.0)


if __name__ == "__main__":
    unittest.main()
