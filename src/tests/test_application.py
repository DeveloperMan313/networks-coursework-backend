import asyncio
import unittest

from src.application import Port_app


class TestPort_app(unittest.IsolatedAsyncioTestCase):
    async def test_ports_uplink_linkactive_downlink_bidirectionally(self):
        port1 = Port_app("port 1")
        port2 = Port_app("port 2")
        port1.connect(port2)

        async def do_tick():
            while not port1._has_response() and not port2._has_response():
                port1.do_tick()
                port2.do_tick()
                await asyncio.sleep(0)

        asyncio.create_task(do_tick())
        try:
            await port2.channel_uplink()
        except RuntimeError:
            self.fail("Port2 should uplink successfully")

        asyncio.create_task(do_tick())
        channel_active = await port1.channel_active()
        self.assertEqual(
            channel_active, True, "Port1 should report that channel is active"
        )

        asyncio.create_task(do_tick())
        try:
            await port2.channel_downlink()
        except RuntimeError:
            self.fail("Port2 should downlink successfully")

    async def test_ports_uplink_send_receive_string_bidirectionally(self):
        port1 = Port_app("port 1")
        port2 = Port_app("port 2")
        port1.connect(port2)

        async def do_tick():
            while not port1._has_response() and not port2._has_response():
                port1.do_tick()
                port2.do_tick()
                await asyncio.sleep(0)

        asyncio.create_task(do_tick())
        try:
            await port2.channel_uplink()
        except RuntimeError:
            self.fail("Port2 should uplink successfully")

        string = "Hello world!"

        asyncio.create_task(do_tick())
        try:
            await port1.send_str(string)
        except RuntimeError:
            self.fail("Port1 should send string successfully")

        # port2 should receive string before port1 gets success message
        self.assertEqual(
            port2.get_received_str(),
            string,
            "Received string should be equal to sent string",
        )


if __name__ == "__main__":
    unittest.main()
