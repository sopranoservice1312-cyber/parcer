import asyncio
from typing import Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

async def build_client_from_account_data(api_id: int, api_hash: str, string_session: Optional[str] = None) -> TelegramClient:
    if string_session:
        client = TelegramClient(StringSession(string_session), api_id, api_hash)
    else:
        client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    return client

async def build_client_from_account(account) -> TelegramClient:
    return await build_client_from_account_data(account.api_id, account.api_hash, account.string_session)

async def start_login(client: TelegramClient, phone: str) -> str:
    sent = await client.send_code_request(phone)
    return sent.phone_code_hash

async def finish_login(client: TelegramClient, phone: str, phone_code_hash: str, code: str, password: Optional[str] = None):
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not password:
            raise
        await client.sign_in(password=password)
    string_session = client.session.save()
    return string_session
