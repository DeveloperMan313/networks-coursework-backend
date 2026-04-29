import asyncio
import unittest
from typing import Tuple

from src.application import PC_app, Port_app
from src.simulation import get_pcs, init_network, start_ticks, stop_ticks


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


class TestPC_app(unittest.IsolatedAsyncioTestCase):
    async def test_network_pcs_connect_and_add_to_internal_network_addresses(self):
        pcs = await self.__get_network_connected_on_physical_channel_levels()

        start_ticks()

        addresses = ["Mark", "Anna", "Carl"]

        for pc, address in zip(pcs, addresses):
            await pc.email_connect(address)

        # sleep is needed because addresses are filled after email_connect is done
        # and knowing if the network is idle is too complicated
        time = 20
        print(f"{self._testMethodName} awaiting for {time} seconds")
        await asyncio.sleep(time)
        stop_ticks()

        for pc, address in zip(pcs, addresses):
            other_addresses = set([a for a in addresses if a != address])
            self.assertEqual(
                set(pc.network_addresses),
                other_addresses,
                f"{pc.name} should have network_addresses {other_addresses}",
            )

    async def __get_network_connected_on_physical_channel_levels(
        self,
    ) -> Tuple[PC_app, ...]:
        init_network()
        pcs = get_pcs()

        start_ticks()

        for pc in pcs:
            pc.connect_out_port()
            await pc.channel_uplink("out_port")

        stop_ticks()

        return pcs


if __name__ == "__main__":
    unittest.main()
