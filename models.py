from enum import Enum
from typing import Dict, Optional, Tuple

from pydantic import BaseModel
from websockets import WebSocketServerProtocol


class Commands(str, Enum):
    SET_NICK = 'nick'
    JOIN = 'join'
    MSG = 'msg'
    QUITE = 'quite'
    ROOMS = 'rooms'


class MessagePrefix(str, Enum):
    SYS = '[ *SYS ]'
    ROOM = '[ *ROOM {0}]'
    USER = '< {0} >'


class ServerResponse(BaseModel):
    ok: bool
    body: str


class Room(BaseModel):
    name: str
    clients: Dict[Tuple[str, int], 'Client']


class Client(BaseModel):
    nick: str
    current_room: Optional[Room] = None
    websocket: WebSocketServerProtocol

    class Config:
        arbitrary_types_allowed = True


class Command(BaseModel):
    sender: Client
    command: Commands
    body: Optional[str]


class Message(BaseModel):
    sender: Client
    body: str


Room.update_forward_refs()
