from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import get_telegram_bot
from app.contexts.identity.dependencies import get_current_user, get_user_service
from app.contexts.identity.jwt import create_access_token
from app.contexts.identity.models import TokenResponse, User, UserPublic
from app.contexts.scheduling.telegram_bot import _LINK_TTL_S, TelegramApiError, TelegramBot
from app.web.asset_manifest import TEMPLATE_SEARCH_DIRS, asset_css, asset_js

if TYPE_CHECKING:
    from app.contexts.identity.service import UserService

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=TEMPLATE_SEARCH_DIRS)
templates.env.globals["asset_js"] = asset_js
templates.env.globals["asset_css"] = asset_css


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.post("/auth/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user_service: UserService = Depends(get_user_service),
):
    user = await user_service.authenticate(email, password)
    if user is None:
        return RedirectResponse(url="/login?error=1", status_code=status.HTTP_303_SEE_OTHER)

    token = create_access_token({"sub": user.user_id})
    user_public = UserPublic(**user.model_dump())

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        response = JSONResponse(
            content=TokenResponse(access_token=token, user=user_public).model_dump(mode="json")
        )
    else:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax",
    )
    return response


@router.post("/auth/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


@router.get("/auth/me", response_model=UserPublic)
async def me(current_user=Depends(get_current_user)):
    return UserPublic(**current_user.model_dump())


def _telegram_page(
    request: Request,
    current_user: User,
    telegram_bot: TelegramBot | None,
    **context: object,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "account/telegram.html",
        {
            "current_user": current_user,
            "bot_enabled": telegram_bot is not None,
            "link_ttl_minutes": _LINK_TTL_S // 60,
            **context,
        },
    )


@router.get("/account/telegram", response_class=HTMLResponse)
async def telegram_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    telegram_bot: TelegramBot | None = Depends(get_telegram_bot),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return _telegram_page(request, current_user, telegram_bot)


@router.post("/account/telegram/link", response_class=HTMLResponse)
async def issue_telegram_link(
    request: Request,
    current_user: User = Depends(get_current_user),
    telegram_bot: TelegramBot | None = Depends(get_telegram_bot),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if telegram_bot is None:
        return _telegram_page(request, current_user, telegram_bot)
    try:
        link = await telegram_bot.issue_link(current_user.user_id)
    except TelegramApiError:
        return _telegram_page(request, current_user, telegram_bot, issue_failed=True)
    return _telegram_page(request, current_user, telegram_bot, link=link)


@router.post("/account/telegram/unlink")
async def unlink_telegram(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
    telegram_bot: TelegramBot | None = Depends(get_telegram_bot),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if telegram_bot is not None:
        await telegram_bot.unlink_user(current_user.user_id)
    else:
        await user_service.unlink_telegram(current_user.user_id)
    return RedirectResponse(url="/account/telegram", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/account/password", response_class=HTMLResponse)
async def password_page(request: Request, current_user: User = Depends(get_current_user)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse(
        request,
        "account/password.html",
        {"current_user": current_user},
    )


@router.post("/auth/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    if new_password != new_password_confirm:
        return RedirectResponse(
            url="/account/password?error=mismatch",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await user_service.change_password(current_user.user_id, current_password, new_password)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_400_BAD_REQUEST:
            code = "wrong" if "현재" in str(exc.detail) else "weak"
            return RedirectResponse(
                url=f"/account/password?error={code}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse(content={"ok": True})

    return RedirectResponse(
        url="/account/password?success=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )
