import asyncio
import sys

import websockets
from loguru import logger

logger.remove()
logger.add(sys.stderr, backtrace=True, diagnose=True)


async def aio_readline(loop_, websocket: websockets.WebSocketCommonProtocol):
    while True:
        line = await loop_.run_in_executor(None, sys.stdin.readline)

        try:
            await websocket.send(line.replace('\n', ''))
        except websockets.ConnectionClosed:
            break


async def aio_print(websocket: websockets.WebSocketCommonProtocol):
    print(f'Welcome! Commands:\n'
          f'\t1. /join [room_name]\tjoin room room_name. If room does not exit, creates it.\n'
          f'\t2. /nick [nick_name]\tset nick to nick_name.\n',
          f'\t3. /msg [hello world]\tsent message to current room.\n',
          f'\t4. /rooms \tlist rooms.\n',
          f'\t5. /quite',
          )
    while True:
        try:
            msg = await websocket.recv()
        except websockets.ConnectionClosed:
            break

        print(f'< {msg}')


async def main(loop_):
    uri = 'ws://localhost:8765'
    async with websockets.connect(uri) as websocket:
        await asyncio.gather(
            asyncio.create_task(aio_readline(loop_, websocket)),
            asyncio.create_task(aio_print(websocket)),
        )


async def shutdown(loop_):
    tasks = [t for t in asyncio.all_tasks() if t is not
             asyncio.current_task()]

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    loop_.stop()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main(loop))
    finally:
        loop.close()
