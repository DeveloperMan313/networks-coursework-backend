import unittest

from src.channel import T_MULT, MsgRes, PFrameH, Port_cha
from src.physical import TIMER_MAX_ERROR, TPB


class TestPort_cha(unittest.TestCase):
    def test_ports_connecting_disconnecting_bidirectionally(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_request(PFrameH.UPLINK)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_response(),
            MsgRes(PFrameH.UPLINK, True),
            "Port1 should return successful UPLINK response",
        )

        port2.enqueue_request(PFrameH.DOWNLINK)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_response(),
            MsgRes(PFrameH.DOWNLINK, True),
            "Port2 should return successful DOWNLINK response",
        )

    def test_linkactive_bidirectionally(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_request(PFrameH.UPLINK)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_response(),
            MsgRes(PFrameH.UPLINK, True),
            "Port1 should return successful UPLINK response",
        )

        port2.enqueue_request(PFrameH.LINKACTIVE)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_response(),
            MsgRes(PFrameH.LINKACTIVE, True),
            "Port2 should return successful LINKACTIVE response",
        )

        port1.enqueue_request(PFrameH.LINKACTIVE)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_response(),
            MsgRes(PFrameH.LINKACTIVE, True),
            "Port1 should return successful LINKACTIVE response",
        )

    def test_send_str_linkactive_send_str_bidirectionally(self):
        port1 = Port_cha("port 1")
        port2 = Port_cha("port 2")
        port1.connect(port2)
        port1.enqueue_request(PFrameH.UPLINK)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_response(),
            MsgRes(PFrameH.UPLINK, True),
            "Port1 should return successful UPLINK response",
        )

        string = "Hello world!"

        port1.enqueue_send_str(string)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 200):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1.get_response(),
            MsgRes(PFrameH.DATA, True),
            "Port1 should return successful DATA response",
        )
        self.assertEqual(
            port2.get_received_str(),
            string,
            "Received string should be equal to sent string",
        )

        port2.enqueue_request(PFrameH.LINKACTIVE)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 5):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_response(),
            MsgRes(PFrameH.LINKACTIVE, True),
            "Port2 should return successful LINKACTIVE response",
        )

        string = "How are you?"

        port2.enqueue_send_str(string)
        for _ in range((TPB + TIMER_MAX_ERROR) * T_MULT * 200):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_response(),
            MsgRes(PFrameH.DATA, True),
            "Port2 should return successful DATA response",
        )
        self.assertEqual(
            port1.get_received_str(),
            string,
            "Received string should be equal to sent string",
        )


if __name__ == "__main__":
    unittest.main()
