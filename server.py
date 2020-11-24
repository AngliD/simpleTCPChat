import asyncio
from sys import stderr
from typing import Optional, Callable, Awaitable

import websockets
from loguru import logger

from models import Command, Commands, Client, Room, MessagePrefix

logger.remove()
logger.add(stderr, backtrace=True, diagnose=True)


ROOMS: dict[str, Room] = {}


async def process_quite(command: Command) -> None:
    logger.info(
        f'User {command.sender.nick} with addr {command.sender.websocket.remote_address} '
        f'has exited.',
    )

    await leave_room(command.sender)
    await send_message_to_user(command.sender, 'Connection closed.', prefix=MessagePrefix.SYS)
    await command.sender.websocket.close()


async def process_join(command: Command) -> None:
    if len(command.body.split(' ')) > 1:
        await send_message_to_user(command.sender, 'Room name should not contain spaces', MessagePrefix.SYS)
        return

    existing_room = ROOMS.get(command.body)
    if existing_room is None:
        existing_room = Room(name=command.body, clients={command.sender.websocket.remote_address: command.sender})
        ROOMS[existing_room.name] = existing_room
        logger.info(f'Room {command.body} created.')

    await leave_room(sender=command.sender)

    command.sender.current_room = existing_room
    ROOMS[existing_room.name].clients[command.sender.websocket.remote_address] = command.sender

    logger.info(
        f'User {command.sender.nick} with addr {command.sender.websocket.remote_address} '
        f'has joint the room {existing_room.name}',
    )

    await broadcast(
        command.sender,
        room_name=existing_room.name,
        message=f'{command.sender.nick} has joint the room!',
        prefix=MessagePrefix.ROOM,
        prefix_value=existing_room.name,
    )
    await send_message_to_user(
        command.sender,
        f'You have successfully joined room {existing_room.name}.',
        prefix=MessagePrefix.SYS,
    )


async def process_set_nick(command: Command) -> None:
    if len(command.body.split(' ')) > 1:
        await send_message_to_user(command.sender, 'Name should not contain spaces', prefix=MessagePrefix.SYS)
        return

    command.sender.nick = command.body
    logger.info(f'User with addr {command.sender.websocket.remote_address} has set nick to {command.body}')

    await send_message_to_user(command.sender, f'Your nick set to {command.body}', prefix=MessagePrefix.SYS)


async def process_msg(command: Command) -> None:
    if command.sender.current_room is None:
        await send_message_to_user(
            receiver=command.sender,
            msg='Join the room at first!',
            prefix=MessagePrefix.SYS,
        )
        return

    await broadcast(
        sender=command.sender,
        room_name=command.sender.current_room.name,
        message=command.body,
        prefix=MessagePrefix.USER,
        prefix_value=command.sender.nick,
    )


async def process_rooms(command: Command) -> None:
    message = 'Rooms list:\n' + '\n'.join(ROOMS.keys())
    await send_message_to_user(
        receiver=command.sender,
        msg=message,
    )


COMMAND_PROCESSORS: dict[Commands, Callable[[Command], Awaitable[None]]] = {
    Commands.QUITE: process_quite,
    Commands.JOIN: process_join,
    Commands.SET_NICK: process_set_nick,
    Commands.MSG: process_msg,
    Commands.ROOMS: process_rooms,
}


async def broadcast(
        sender: Client,
        room_name: str,
        message: str,
        prefix: Optional[MessagePrefix] = None,
        prefix_value: Optional[str] = None,
) -> None:
    room = ROOMS.get(room_name)
    if room is None:
        return

    for address, client in room.clients.items():
        if sender.websocket.remote_address != address:
            await send_message_to_user(client, message, prefix, prefix_value)


async def leave_room(sender: Client) -> None:
    prev_room = sender.current_room
    if prev_room is None:
        return

    del prev_room.clients[sender.websocket.remote_address]
    await broadcast(
        sender=sender,
        room_name=prev_room.name,
        message=f'{sender.nick} has left.',
        prefix=MessagePrefix.ROOM,
        prefix_value=prev_room.name,
    )
    sender.current_room = None

    logger.info(f'User {sender.nick} with addr {sender.websocket.remote_address} has left the room {prev_room.name}.')

    if len(prev_room.clients.keys()) == 0:
        logger.info(f'Room {prev_room.name} has been deleted due to absence of people.')
        del ROOMS[prev_room.name]

    await send_message_to_user(sender, f'You have left the room {prev_room.name}.', prefix=MessagePrefix.SYS)


async def send_message_to_user(
        receiver: Client,
        msg: str,
        prefix: Optional[MessagePrefix] = None,
        prefix_value: Optional[str] = None,
) -> None:
    if prefix:
        msg = prefix.format(prefix_value) + ': ' + msg

    await receiver.websocket.send(msg)


def parse_client_input(message: str, client: Client) -> tuple[Optional[Command], str]:
    if not message.startswith('/'):
        return None, 'Enter command'

    split_command = message[1:].split(' ')

    if len(split_command) == 0:
        return None, 'No such command'

    if len(split_command) == 1:
        if split_command[0] == Commands.QUITE:
            command = Command(sender=client, command=Commands.QUITE)
            return command, ''
        elif split_command[0] == Commands.ROOMS:
            command = Command(sender=client, command=Commands.ROOMS)
            return command, ''
        else:
            return None, f'Command {split_command[0]} requires more then 0 params.'

    try:
        command_name = Commands(split_command[0])
    except ValueError:
        return None, 'No such command'

    command = Command(sender=client, command=command_name, body=' '.join(split_command[1:]))
    return command, ''


async def chat(websocket: websockets.WebSocketServerProtocol, _):
    logger.info(f'New connection: [{websocket.remote_address}]')

    new_client = Client(nick='anon', websocket=websocket)

    while True:
        try:
            client_raw_msg = await websocket.recv()
            command, error_msg = parse_client_input(client_raw_msg, new_client)

            if command is None:
                await websocket.send(error_msg)
                continue

            await COMMAND_PROCESSORS[command.command](command)
            new_client = command.sender

        except websockets.ConnectionClosed:
            await websocket.close()
            logger.info(f'Close connection with : {new_client.websocket.remote_address}')
            break


if __name__ == '__main__':
    host = '127.0.0.1'
    port = 8765

    start_server = websockets.serve(chat, host, port)
    logger.info(f'Start server at {host}:{port}')

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
