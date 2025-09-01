from fastapi import Request

FLASH_KEY = "_flash"

def set_flash(response, message: str):
    response.set_cookie(FLASH_KEY, message, max_age=30, httponly=False)

def pop_flash(request: Request):
    return request.cookies.get(FLASH_KEY)
