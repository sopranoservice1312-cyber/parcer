import asyncio
from typing import AsyncGenerator, Tuple
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import InputPeerChannel

async def ensure_join(client, group_link_or_username: str):
    link = group_link_or_username.strip()
    try:
        if "+" in link and (link.startswith("http") or link.startswith("https") or link.startswith("t.me")):
            invite = link.rsplit("/", 1)[-1]
            res = await client(ImportChatInviteRequest(invite))
            # res may contain chats[0]
            return res.chats[0]
        else:
            if link.startswith("http") or link.startswith("https") or link.startswith("t.me"):
                username = link.split("/")[-1]
            else:
                username = link.lstrip('@')
            entity = await client.get_entity(username)
            try:
                await client(JoinChannelRequest(entity))
            except Exception:
                pass
            return entity
    except Exception as e:
        raise RuntimeError(f"Не удалось получить чат: {e}")

async def iter_members(client, entity) -> AsyncGenerator[Tuple, None]:
    async for u in client.iter_participants(entity):
        yield (
            u.id,
            getattr(u, "username", None),
            getattr(u, "first_name", None),
            getattr(u, "last_name", None),
            getattr(u, "bot", False),
            getattr(u, "verified", False),
        )

async def safe_parse_members(client, entity, on_progress=None):
    handled = 0
    async for row in iter_members(client, entity):
        handled += 1
        if on_progress and handled % 100 == 0:
            try:
                await on_progress(handled)
            except Exception:
                pass
        yield row
