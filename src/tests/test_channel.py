import unittest

from src.channel import T_MULT, MsgRX, MsgTX, PFrameH, Port_cha
from src.physical import TIMER_MAX_ERROR, TPB


class TestPort_cha(unittest.TestCase):
    def test_ports_connecting_disconnecting_bidirectionally(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_send_msg(MsgTX(PFrameH.UPLINK))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_received_msg(),
            MsgRX(PFrameH.UPLINK, 1),
            "Port1 should return successful UPLINK message",
        )

        port2.enqueue_send_msg(MsgTX(PFrameH.DOWNLINK))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_received_msg(),
            MsgRX(PFrameH.DOWNLINK, 1),
            "Port2 should return successful DOWNLINK message",
        )

    def test_linkactive_bidirectionally(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_send_msg(MsgTX(PFrameH.UPLINK))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_received_msg(),
            MsgRX(PFrameH.UPLINK, 1),
            "Port1 should return successful UPLINK message",
        )

        port2.enqueue_send_msg(MsgTX(PFrameH.LINKACTIVE))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_received_msg(),
            MsgRX(PFrameH.LINKACTIVE, 1),
            "Port2 should return successful LINKACTIVE message",
        )

        port1.enqueue_send_msg(MsgTX(PFrameH.LINKACTIVE))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_received_msg(),
            MsgRX(PFrameH.LINKACTIVE, 1),
            "Port1 should return successful LINKACTIVE message",
        )

    def test_send_str_linkactive_send_str_bidirectionally(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_send_msg(MsgTX(PFrameH.UPLINK))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_received_msg(),
            MsgRX(PFrameH.UPLINK, 1),
            "Port1 should return successful UPLINK message",
        )

        string = "Hello world!"

        port1.enqueue_send_str(string)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 200):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_received_msg(),
            MsgRX(PFrameH.DATA, 1),
            "Port1 should return successful DATA message",
        )
        self.assertEqual(
            port2.get_received_str(),
            string,
            "Received string should be equal to sent string",
        )

        port2.enqueue_send_msg(MsgTX(PFrameH.LINKACTIVE))
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_received_msg(),
            MsgRX(PFrameH.LINKACTIVE, 1),
            "Port2 should return successful LINKACTIVE message",
        )

        string = "How are you?"

        port2.enqueue_send_str(string)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 200):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_received_msg(),
            MsgRX(PFrameH.DATA, 1),
            "Port2 should return successful DATA message",
        )
        self.assertEqual(
            port1.get_received_str(),
            string,
            "Received string should be equal to sent string",
        )


if __name__ == "__main__":
    unittest.main()
