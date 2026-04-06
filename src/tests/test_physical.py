import unittest

from src.physical import TIMER_MAX_ERROR, TPB, Port


class TestPort(unittest.TestCase):
    def test_connect_sets_pins_up(self):
        port1 = Port("port 1")
        port2 = Port("port 2")
        port1.connect(port2)
        self.assertTrue(
            port1._get_pin("DTR")
            and port1._get_pin("DCD")
            and port2._get_pin("DTR")
            and port2._get_pin("DCD"),
            "Pins DTR and DCD should be up",
        )

    def test_connect_fails_when_already_connected(self):
        port1 = Port("port 1")
        port2 = Port("port 2")
        port3 = Port("port 3")
        port1.connect(port2)
        with self.assertRaisesRegex(RuntimeError, "already connected to port"):
            port1.connect(port3)

    def test_connect_fails_when_other_already_connected(self):
        port1 = Port("port 1")
        port2 = Port("port 2")
        port3 = Port("port 3")
        port2.connect(port3)
        with self.assertRaisesRegex(
            RuntimeError, "other port already connected to port"
        ):
            port1.connect(port3)

    def test_connect_fails_when_connecting_to_self(self):
        port1 = Port("port 1")
        with self.assertRaisesRegex(RuntimeError, "cannot connect to self"):
            port1.connect(port1)

    def test_disconnect_sets_pins_down(self):
        port1 = Port("port 1")
        port2 = Port("port 2")
        port1.connect(port2)
        port1.disconnect()
        self.assertTrue(
            not port1._get_pin("DTR")
            and not port1._get_pin("DCD")
            and not port2._get_pin("DTR")
            and not port2._get_pin("DCD"),
            "Pins DTR and DCD should be down",
        )

    def test_disconnect_fails_when_not_connected(self):
        port1 = Port("port 1")
        with self.assertRaisesRegex(RuntimeError, "not connected to port"):
            port1.disconnect()

    def test_sent_byte_is_received(self):
        port1 = Port("port 1")
        port2 = Port("port 2")
        port1.connect(port2)
        byte = 0b01110100
        port1.enqueue_send_byte(byte)
        for _ in range((TPB + TIMER_MAX_ERROR) * 15):
            port1.do_tick()
            port2.do_tick()
        self.assertEqual(
            port2.get_received_byte(),
            byte,
            "Received byte should be equal to sent byte",
        )


if __name__ == "__main__":
    unittest.main()
