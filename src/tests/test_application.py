import asyncio
import threading
import unittest
from typing import Tuple

from src.application import EmailAddress, EmailBody, EmailSubject, PC_app, Port_app
from src.entities.app_events import (
    EmailReceived,
    EmailSent,
    PCConnected,
    PCDisconnected,
)
from src.simulation import (
    get_pcs,
    start_network,
    stop_network,
)


# set error probability to 0 for testing
class TestPort_app(unittest.IsolatedAsyncioTestCase):
    async def test_ports_uplink_linkactive_downlink_bidirectionally(self):
        port1 = Port_app("port 1", 0)
        port2 = Port_app("port 2", 0)
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
        port1 = Port_app("port 1", 0)
        port2 = Port_app("port 2", 0)
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


class AsyncBackground:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_func(self, func):
        return self.loop.call_soon_threadsafe(func)

    def run_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


# set error probability to 0 for testing
class TestPC_app(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addresses = tuple(EmailAddress(a) for a in ("Mark", "Anna", "Carl"))
        # event loop will be running during all tests, with shared pcs
        cls.bg = AsyncBackground()
        ready = asyncio.Event()

        async def run_init():
            await TestPC_app.__get_network_connected_on_phy_cha_app_levels(
                cls.addresses
            )
            ready.set()

        cls.bg.run_coro(run_init()).result()
        cls.bg.run_coro(ready.wait()).result()

    @classmethod
    def tearDownClass(cls):
        cls.bg.run_func(stop_network)

    def setUp(self):
        self.pcs = get_pcs()

    def test_1_network_pcs_connect_and_add_to_internal_network_addresses(self):
        async def test():
            for pc, address in zip(self.pcs, self.addresses):
                other_addresses = set([a for a in self.addresses if a != address])
                self.assertEqual(
                    set(pc.network_addresses),
                    other_addresses,
                    f"{pc.name} should have network_addresses {other_addresses}",
                )
                self.assertEqual(
                    (type(await pc.get_event()), type(await pc.get_event())),
                    (PCConnected, PCConnected),
                    f"{pc.name} should have 2 PCConnected events",
                )

        self.bg.run_coro(test()).result()

    def test_2_network_pcs_send_and_receive_emails(self):
        async def test():
            subject = EmailSubject("Hi")
            body1 = EmailBody("Is this working?")
            body2 = EmailBody("All's set up!")

            await self.pcs[0].send_email(self.addresses[2], subject, body1)
            await self.pcs[2].send_email(EmailAddress("*"), subject, body2)

            pc1_emails = self.pcs[0].received_emails
            pc2_emails = self.pcs[1].received_emails
            pc3_emails = self.pcs[2].received_emails

            async def pcs_received_emails():
                max_iters = 20
                for _ in range(max_iters):
                    if (
                        len(pc1_emails) == 1
                        and len(pc2_emails) == 1
                        and len(pc3_emails) == 1
                    ):
                        return
                    await asyncio.sleep(1)

            await pcs_received_emails()

            self.assertEqual(
                len(self.pcs[0].sent_emails),
                1,
                f"{self.addresses[0]} should have 1 sent email",
            )
            self.assertEqual(
                len(self.pcs[1].sent_emails),
                0,
                f"{self.addresses[1]} should have 0 sent emails",
            )
            self.assertEqual(
                len(self.pcs[2].sent_emails),
                1,
                f"{self.addresses[2]} should have 1 sent email",
            )

            self.assertEqual(
                (pc1_emails[0].From, pc1_emails[0].subject, pc1_emails[0].body),
                (self.addresses[2], subject, body2),
                f"{self.addresses[0]} should receive email from {self.addresses[2]} with subject '{subject}' body '{body2}'",
            )
            self.assertEqual(
                (pc2_emails[0].From, pc2_emails[0].subject, pc2_emails[0].body),
                (self.addresses[2], subject, body2),
                f"{self.addresses[1]} should receive email from {self.addresses[2]} with subject '{subject}' body '{body2}'",
            )
            self.assertEqual(
                (pc3_emails[0].From, pc3_emails[0].subject, pc3_emails[0].body),
                (self.addresses[0], subject, body1),
                f"{self.addresses[2]} should receive email from {self.addresses[0]} with subject '{subject}' body '{body1}'",
            )

            self.assertEqual(
                type(await self.pcs[0].get_event()),
                EmailSent,
                f"{self.addresses[0]} should have EmailSent event",
            )
            self.assertEqual(
                type(await self.pcs[2].get_event()),
                EmailSent,
                f"{self.addresses[2]} should have EmailSent event",
            )

            self.assertEqual(
                type(await self.pcs[0].get_event()),
                EmailReceived,
                f"{self.addresses[0]} should have EmailReceived event",
            )
            self.assertEqual(
                type(await self.pcs[1].get_event()),
                EmailReceived,
                f"{self.addresses[1]} should have EmailReceived event",
            )
            self.assertEqual(
                type(await self.pcs[2].get_event()),
                EmailReceived,
                f"{self.addresses[2]} should have EmailReceived event",
            )

        self.bg.run_coro(test()).result()

    def test_3_network_pcs_disconnect_and_remove_from_internal_network_addresses(
        self,
    ):
        async def test():
            for pc in self.pcs:
                await pc.email_disconnect()

            async def pcs_addresses_cleared():
                max_iters = 20
                for _ in range(max_iters):
                    if all(len(pc.network_addresses) == 0 for pc in self.pcs):
                        return
                    await asyncio.sleep(1)

            await pcs_addresses_cleared()

            for pc in self.pcs:
                self.assertEqual(
                    pc.network_addresses,
                    [],
                    f"{pc.name} should have empty network_addresses",
                )
                self.assertEqual(
                    type(await pc.get_event()),
                    PCDisconnected,
                    f"{pc.name} should have PCDisconnected event",
                )

        self.bg.run_coro(test()).result()

    @staticmethod
    async def __get_network_connected_on_phy_cha_app_levels(
        addresses: Tuple[EmailAddress, ...],
    ) -> Tuple[PC_app, ...]:
        start_network(len(addresses), 0)
        pcs = get_pcs()

        for pc in pcs:
            pc.connect_out_port()
            await pc.channel_uplink("out_port")

        for pc, address in zip(pcs, addresses):
            await pc.email_connect(address)

        async def pcs_addresses_filled():
            neighbor_cnt = len(pcs) - 1
            max_iters = 20
            for _ in range(max_iters):
                if all(len(pc.network_addresses) == neighbor_cnt for pc in pcs):
                    return
                await asyncio.sleep(1)

        await pcs_addresses_filled()

        return pcs


if __name__ == "__main__":
    unittest.main()
