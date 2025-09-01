import os
import asyncio
import base64
from typing import Optional, Dict
from fastapi import FastAPI, Request, Depends, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Base, engine, get_db
from .models import Account, Member
from .auth import build_client_from_account, start_login, finish_login
from .parser import ensure_join, safe_parse_members
from telethon.errors.rpcerrorlist import PhoneCodeExpiredError

FLASH_KEY = "flash_message"

def set_flash(response: Response, message: str):
    # Кодируем строку в base64 для безопасного сохранения в cookie
    encoded = base64.b64encode(message.encode("utf-8")).decode("ascii")
    response.set_cookie(FLASH_KEY, encoded, max_age=30, httponly=False)

def pop_flash(request: Request):
    encoded = request.cookies.get(FLASH_KEY)
    if encoded:
        try:
            # Декодируем обратно в строку
            return base64.b64decode(encoded).decode("utf-8")
        except Exception:
            return None
    return None

app = FastAPI(title="Telegram Parser Panel")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

JOB_PROGRESS: Dict[str, Dict] = {}

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    flash = pop_flash(request)
    accounts = (await db.execute(select(Account).order_by(Account.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "accounts": accounts, "flash": flash})

@app.post("/accounts/start")
async def accounts_start(
    request: Request,
    response: Response,
    api_id: int = Form(...),
    api_hash: str = Form(...),
    phone: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    acc = (await db.execute(select(Account).where(Account.phone == phone))).scalar_one_or_none()
    if not acc:
        acc = Account(api_id=api_id, api_hash=api_hash, phone=phone)
        db.add(acc)
        await db.flush()

    acc.api_id = api_id
    acc.api_hash = api_hash
    acc.is_ready = False
    acc.string_session = None

    client = await build_client_from_account(acc)
    try:
        phone_code_hash = await start_login(client, phone)
    finally:
        await client.disconnect()

    acc.phone_code_hash = phone_code_hash
    await db.commit()
    set_flash(response, "Код отправлен в Telegram. Введите его ниже.")
    return RedirectResponse(url=f"/?verify={acc.id}", status_code=303)

@app.post("/accounts/verify")
async def accounts_verify(
    request: Request,
    response: Response,
    account_id: int = Form(...),
    code: str = Form(...),
    password: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not acc or not acc.phone_code_hash:
        set_flash(response, "Аккаунт не найден или не запущена отправка кода.")
        return RedirectResponse("/", 303)

    client = await build_client_from_account(acc)
    try:
        try:
            string_session = await finish_login(client, acc.phone, acc.phone_code_hash, code, password)
        except PhoneCodeExpiredError:
            set_flash(response, "Код подтверждения истёк. Попробуйте отправить код заново.")
            return RedirectResponse("/", 303)
    finally:
        await client.disconnect()

    acc.string_session = string_session
    acc.is_ready = True
    acc.phone_code_hash = None
    await db.commit()

    set_flash(response, "Аккаунт успешно авторизован!")
    return RedirectResponse("/", 303)

@app.post("/accounts/delete")
async def accounts_delete(
    account_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Аккаунт не найден.")
    await db.delete(acc)
    await db.commit()
    # Можно добавить flash-сообщение, если используешь их
    # set_flash(response, "Аккаунт удалён.")
    return RedirectResponse("/", status_code=303)

@app.post("/parse")
async def parse(
    response: Response,
    account_id: int = Form(...),
    group: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not acc or not acc.is_ready or not acc.string_session:
        set_flash(response, "Аккаунт не готов. Авторизуйте его.")
        return RedirectResponse("/", 303)

    job_id = os.urandom(6).hex()
    JOB_PROGRESS[job_id] = {"status": "init", "count": 0, "group": group}

    async def worker():
        client = await build_client_from_account(acc)
        try:
            entity = await ensure_join(client, group)
            title = getattr(entity, "title", getattr(entity, "username", str(entity)))

            async def on_progress(n):
                JOB_PROGRESS[job_id]["count"] = n

            async for (uid, username, first, last, is_bot, is_verified) in safe_parse_members(client, entity, on_progress=on_progress):
                # Проверяем существование, чтобы избежать дублей
                exists_q = await db.execute(select(Member).where(Member.account_id == acc.id, Member.tg_user_id == uid, Member.group_id == str(getattr(entity, 'id', 'unknown'))))
                exists = exists_q.scalar_one_or_none()
                if exists:
                    continue
                m = Member(
                    account_id=acc.id,
                    tg_user_id=uid,
                    username=username,
                    first_name=first,
                    last_name=last,
                    is_bot=is_bot,
                    is_verified=is_verified,
                    group_id=str(getattr(entity, 'id', 'unknown')),
                    group_title=title,
                )
                db.add(m)
            await db.commit()
            JOB_PROGRESS[job_id]["status"] = "done"
        except Exception as e:
            JOB_PROGRESS[job_id]["status"] = f"error: {e}"
        finally:
            await client.disconnect()

    asyncio.create_task(worker())
    return RedirectResponse(url=f"/results?job={job_id}", status_code=303)

@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    data = JOB_PROGRESS.get(job_id) or {"status": "unknown"}
    return PlainTextResponse(f"status={data.get('status')} count={data.get('count', 0)}")

@app.get("/results", response_class=HTMLResponse)
async def results(request: Request, job: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import desc
    q = await db.execute(select(Member).order_by(desc(Member.id)).limit(200))
    items = q.scalars().all()
    return templates.TemplateResponse("results.html", {"request": request, "items": items, "job": job})

@app.get("/export.csv")
async def export_csv(group_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    from io import StringIO
    import csv

    if group_id:
        rs = await db.execute(select(Member).where(Member.group_id == group_id))
    else:
        rs = await db.execute(select(Member))
    rows = rs.scalars().all()

    def iter_csv():
        sio = StringIO()
        w = csv.writer(sio)
        w.writerow(["tg_user_id", "username", "first_name", "last_name", "is_bot", "is_verified", "group_id", "group_title", "crawled_at"]) 
        yield sio.getvalue(); sio.seek(0); sio.truncate(0)
        for m in rows:
            w.writerow([m.tg_user_id, m.username or "", m.first_name or "", m.last_name or "", int(m.is_bot or 0), int(m.is_verified or 0), m.group_id or "", m.group_title or "", m.crawled_at])
            yield sio.getvalue(); sio.seek(0); sio.truncate(0)

    headers = {"Content-Disposition": "attachment; filename=members.csv"}
    return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)
