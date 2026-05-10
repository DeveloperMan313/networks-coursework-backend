import asyncio
from asyncio.exceptions import CancelledError

from uvicorn import Config
from uvicorn.server import Server

from src.simulation import get_pcs, start_network, stop_network
from src.webserver import app

PC_CNT = 3


async def main():
    config = Config(app=app, host="127.0.0.1", port=8000, log_level="info")
    server = Server(config)

    start_network(PC_CNT)
    pcs = get_pcs()
    for pc in pcs:
        pc.connect_port("out")
        await pc.data_link_uplink("out")

    server_task = asyncio.create_task(server.serve())

    try:
        await server_task
    except CancelledError:
        stop_network()
        print("Cancelled by user, exiting")


if __name__ == "__main__":
    asyncio.run(main())
