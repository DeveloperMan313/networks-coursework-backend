import unittest

from src.channel import MsgRes, PFrameH, Port_cha


# set error probability to 0 for testing
class TestPort_cha(unittest.TestCase):
    def test_ports_connecting_disconnecting_bidirectionally(self):
        port1 = Port_cha("port 1", 0)
        port2 = Port_cha("port 2", 0)
        port1.connect(port2)
        port1._enqueue_request(PFrameH.UPLINK)
        while not port1._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1._get_response(),
            MsgRes(PFrameH.UPLINK, True),
            "Port1 should return successful UPLINK response",
        )

        port2._enqueue_request(PFrameH.DOWNLINK)
        while not port2._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2._get_response(),
            MsgRes(PFrameH.DOWNLINK, True),
            "Port2 should return successful DOWNLINK response",
        )

    def test_linkactive_bidirectionally(self):
        port1 = Port_cha("port 1", 0)
        port2 = Port_cha("port 2", 0)
        port1.connect(port2)
        port1._enqueue_request(PFrameH.UPLINK)
        while not port1._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1._get_response(),
            MsgRes(PFrameH.UPLINK, True),
            "Port1 should return successful UPLINK response",
        )

        port2._enqueue_request(PFrameH.LINKACTIVE)
        while not port2._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2._get_response(),
            MsgRes(PFrameH.LINKACTIVE, True),
            "Port2 should return successful LINKACTIVE response",
        )

        port1._enqueue_request(PFrameH.LINKACTIVE)
        while not port1._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1._get_response(),
            MsgRes(PFrameH.LINKACTIVE, True),
            "Port1 should return successful LINKACTIVE response",
        )

    def test_send_str_linkactive_send_str_bidirectionally(self):
        port1 = Port_cha("port 1", 0)
        port2 = Port_cha("port 2", 0)
        port1.connect(port2)
        port1._enqueue_request(PFrameH.UPLINK)
        while not port1._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1._get_response(),
            MsgRes(PFrameH.UPLINK, True),
            "Port1 should return successful UPLINK response",
        )

        string = "Hello world!"

        port1._enqueue_send_str(string)
        while not port1._has_response() or not port2.has_received_str():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port1._get_response(),
            MsgRes(PFrameH.DATA, True),
            "Port1 should return successful DATA response",
        )
        self.assertEqual(
            port2.get_received_str(),
            string,
            "Received string should be equal to sent string",
        )

        port2._enqueue_request(PFrameH.LINKACTIVE)
        while not port2._has_response():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2._get_response(),
            MsgRes(PFrameH.LINKACTIVE, True),
            "Port2 should return successful LINKACTIVE response",
        )

        string = "How are you?"

        port2._enqueue_send_str(string)
        while not port2._has_response() or not port1.has_received_str():
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2._get_response(),
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
