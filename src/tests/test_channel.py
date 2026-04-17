import unittest

from src.channel import T_MULT, MsgRX, MsgTX, PFrameH, Port_cha
from src.physical import TIMER_MAX_ERROR, TPB


class TestPort_cha(unittest.TestCase):
    def test_ports_connecting(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_send_msg(MsgTX(PFrameH.UPLINK))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 10):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_received_msg(),
            MsgRX(PFrameH.UPLINK, 1),
            "Port1 should return successful UPLINK message",
        )


if __name__ == "__main__":
    unittest.main()
