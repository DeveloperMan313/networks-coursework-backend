import unittest

from src.physical import Port_phy


class TestPort_phy(unittest.TestCase):
    def test_connect_sets_pins_up(self):
        port1 = Port_phy("port 1")
        port2 = Port_phy("port 2")
        port1.connect(port2)
        self.assertTrue(
            port1._get_pin("DTR")
            and port1._get_pin("DCD")
            and port2._get_pin("DTR")
            and port2._get_pin("DCD"),
            "Pins DTR and DCD should be up",
        )

    def test_connect_fails_when_already_connected(self):
        port1 = Port_phy("port 1")
        port2 = Port_phy("port 2")
        port3 = Port_phy("port 3")
        port1.connect(port2)
        with self.assertRaisesRegex(RuntimeError, "already connected to port"):
            port1.connect(port3)

    def test_connect_fails_when_other_already_connected(self):
        port1 = Port_phy("port 1")
        port2 = Port_phy("port 2")
        port3 = Port_phy("port 3")
        port2.connect(port3)
        with self.assertRaisesRegex(
            RuntimeError, "other port already connected to port"
        ):
            port1.connect(port3)

    def test_connect_fails_when_connecting_to_self(self):
        port1 = Port_phy("port 1")
        with self.assertRaisesRegex(RuntimeError, "cannot connect to self"):
            port1.connect(port1)

    def test_disconnect_sets_pins_down(self):
        port1 = Port_phy("port 1")
        port2 = Port_phy("port 2")
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
        port1 = Port_phy("port 1")
        with self.assertRaisesRegex(RuntimeError, "not connected to port"):
            port1.disconnect()

    def test_sent_byte_is_received_bidirectionally_arbitrary_order(self):
        port1 = Port_phy("port 1", 0)
        port2 = Port_phy("port 2", 0)
        port1.connect(port2)
        byte = 0b01110100
        for swap in (False, False, True, False, True, True):
            if swap:
                portA = port2
                portB = port1
            else:
                portA = port1
                portB = port2
            portA._enqueue_send_byte(byte)
            while not portB._has_received_bytes():
                portA.do_tick()
                portB.do_tick()
            self.assertEqual(
                portB._get_received_byte(),
                byte,
                "Received byte should be equal to sent byte",
            )


if __name__ == "__main__":
    unittest.main()
