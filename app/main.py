from __future__ import annotations

import os
import pathlib
import shutil
import uuid
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.request import urlopen
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from .db import init_db, get_session
from .models import Person, Pet, Child, Note
from .utils import calc_age, compose_address, yandex_maps_url

# === Приложение ===
app = FastAPI(title="People Notebook")

# Папка загрузок (персистентная)
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
UPLOAD_DIR = pathlib.Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Отдаём загруженные файлы
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Шаблоны
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Telegram конфиг из ENV
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # токен бота
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")      # ваш чат/канал/группа (куда слать напоминания)


def require_auth() -> bool:
    return True


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Пускаем фонового «наблюдателя» ДР, если задан токен/чат
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        asyncio.create_task(_birthday_watcher())
    else:
        # Просто инфо в лог — напоминалки выключены
        print("Telegram reminders disabled: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")


def _safe_remove_file(path: Optional[str]) -> None:
    if not path:
        return
    if path.startswith("/uploads/"):
        fs_path = UPLOAD_DIR / path.split("/uploads/", 1)[-1]
        if fs_path.exists():
            try:
                fs_path.unlink()
            except Exception:
                pass


# ===== Телеграм уведомления

def _send_telegram(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    try:
        with urlopen(api, data=data, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print("Telegram send error:", e)


def _safe_date(year: int, month: int, day: int) -> date:
    # Корректируем невалидные даты (напр. 30.02 -> 28.02)
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
            if day <= 0:
                # fallback
                return date(year, month, 1)


async def _birthday_watcher():
    # Простая проверка каждые 12 часов
    await asyncio.sleep(3)  # небольшая задержка после старта
    while True:
        try:
            async for _ in _check_birthdays_and_notify():
                pass
        except Exception as e:
            print("Birthday watcher error:", e)
        await asyncio.sleep(60 * 60 * 12)  # 12 часов


async def _check_birthdays_and_notify():
    # Отдельная функция — удобнее тестировать
    from .db import get_session  # локальный импорт, чтобы не зацикливать
    from fastapi import Depends

    # Открываем синхронную сессию в текущем треде
    for session in get_session():
        today = date.today()
        people = session.exec(select(Person)).all()
        for p in people:
            if not (p.birth_day and p.birth_month):
                continue

            # Определяем ближайший ДР
            year = today.year
            bday = _safe_date(year, p.birth_month, p.birth_day)
            if bday < today:
                bday = _safe_date(year + 1, p.birth_month, p.birth_day)

            days_left = (bday - today).days

            # 7 дней
            if days_left == 7 and p.notify_year_7d != today.year:
                text = f"🎉 Через 7 дней День Рождения у {p.first_name or ''} {p.last_name or ''} — {p.birth_day:02d}.{p.birth_month:02d}{'.'+str(p.birth_year) if p.birth_year else ''}"
                _send_telegram(text)
                p.notify_year_7d = today.year
                session.add(p)

            # 1 день
            if days_left == 1 and p.notify_year_1d != today.year:
                text = f"🎂 Завтра ДР у {p.first_name or ''} {p.last_name or ''}! {p.birth_day:02d}.{p.birth_month:02d}{'.'+str(p.birth_year) if p.birth_year else ''}"
                _send_telegram(text)
                p.notify_year_1d = today.year
                session.add(p)

        session.commit()
        yield True


# ===== Главная (список людей)

@app.get("/")
def people_list(request: Request, session=Depends(get_session)):
    people = session.exec(select(Person)).all()
    people_sorted = sorted(
        people, key=lambda p: ((p.last_name or "").lower(), (p.first_name or "").lower())
    )
    resp = templates.TemplateResponse(
        "list.html",
        {"request": request, "people": people_sorted, "calc_age": calc_age},
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ===== Статические маршруты раньше динамики

@app.get("/person/new")
def person_new(request: Request):
    return templates.TemplateResponse("form.html", {"request": request, "p": None})


@app.post("/person/create")
def create_person(
    # базовые
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    apartment: Optional[str] = Form(None),
    birth_day: Optional[int] = Form(None),
    birth_month: Optional[int] = Form(None),
    birth_year: Optional[int] = Form(None),
    # любимое/личное
    favorite_movies: Optional[str] = Form(None),
    favorite_color: Optional[str] = Form(None),
    favorite_flowers: Optional[str] = Form(None),
    marital_status: Optional[str] = Form(None),
    partner_name: Optional[str] = Form(None),
    handedness: Optional[str] = Form(None),
    smokes: Optional[str] = Form(None),
    # аватар
    avatar: UploadFile | None = File(None),
    # новые поля
    food_prefs: Optional[str] = Form(None),
    alcohol_prefs: Optional[str] = Form(None),
    places_to_go: Optional[str] = Form(None),
    traits_positive: Optional[str] = Form(None),
    traits_negative: Optional[str] = Form(None),
    workplace: Optional[str] = Form(None),
    job_title: Optional[str] = Form(None),
    wishlist: Optional[str] = Form(None),
    telegram_username: Optional[str] = Form(None),
    instagram_username: Optional[str] = Form(None),
    vk_username: Optional[str] = Form(None),

    auth_ok: bool = Depends(require_auth),
    session=Depends(get_session),
):
    avatar_path = None
    if avatar and avatar.filename:
        ext = pathlib.Path(avatar.filename).suffix.lower()
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / filename
        with dest.open("wb") as f:
            shutil.copyfileobj(avatar.file, f)
        avatar_path = f"/uploads/{filename}"

    p = Person(
        first_name=first_name or None,
        last_name=last_name or None,
        phone=phone or None,
        email=email or None,
        city=city or None,
        address=address or None,
        apartment=apartment or None,
        birth_day=birth_day or None,
        birth_month=birth_month or None,
        birth_year=birth_year or None,
        favorite_movies=favorite_movies or None,
        favorite_color=favorite_color or None,
        favorite_flowers=favorite_flowers or None,
        marital_status=marital_status or None,
        partner_name=partner_name or None,
        handedness=handedness or None,
        smokes=(smokes == "1") if smokes is not None else None,
        avatar_path=avatar_path,
        food_prefs=food_prefs or None,
        alcohol_prefs=alcohol_prefs or None,
        places_to_go=places_to_go or None,
        traits_positive=traits_positive or None,
        traits_negative=traits_negative or None,
        workplace=workplace or None,
        job_title=job_title or None,
        wishlist=wishlist or None,
        telegram_username=(telegram_username or "").lstrip("@") or None,
        instagram_username=(instagram_username or "").lstrip("@") or None,
        vk_username=(vk_username or "").lstrip("@") or None,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return RedirectResponse(url=f"/person/{p.id}", status_code=302)


@app.get("/person/{pid}/edit")
def person_edit(pid: int, request: Request, session=Depends(get_session)):
    p = session.get(Person, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    return templates.TemplateResponse("form.html", {"request": request, "p": p})


@app.post("/person/{pid}/update")
def update_person(
    pid: int,
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    apartment: Optional[str] = Form(None),
    birth_day: Optional[int] = Form(None),
    birth_month: Optional[int] = Form(None),
    birth_year: Optional[int] = Form(None),
    favorite_movies: Optional[str] = Form(None),
    favorite_color: Optional[str] = Form(None),
    favorite_flowers: Optional[str] = Form(None),
    marital_status: Optional[str] = Form(None),
    partner_name: Optional[str] = Form(None),
    handedness: Optional[str] = Form(None),
    smokes: Optional[str] = Form(None),
    avatar: UploadFile | None = File(None),

    food_prefs: Optional[str] = Form(None),
    alcohol_prefs: Optional[str] = Form(None),
    places_to_go: Optional[str] = Form(None),
    traits_positive: Optional[str] = Form(None),
    traits_negative: Optional[str] = Form(None),
    workplace: Optional[str] = Form(None),
    job_title: Optional[str] = Form(None),
    wishlist: Optional[str] = Form(None),
    telegram_username: Optional[str] = Form(None),
    instagram_username: Optional[str] = Form(None),
    vk_username: Optional[str] = Form(None),

    auth_ok: bool = Depends(require_auth),
    session=Depends(get_session),
):
    p = session.get(Person, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")

    p.first_name = first_name or None
    p.last_name = last_name or None
    p.phone = phone or None
    p.email = email or None
    p.city = city or None
    p.address = address or None
    p.apartment = apartment or None
    p.birth_day = birth_day or None
    p.birth_month = birth_month or None
    p.birth_year = birth_year or None

    p.favorite_movies = favorite_movies or None
    p.favorite_color = favorite_color or None
    p.favorite_flowers = favorite_flowers or None
    p.marital_status = marital_status or None
    p.partner_name = partner_name or None
    p.handedness = handedness or None
    p.smokes = (smokes == "1") if smokes is not None else None

    if avatar and avatar.filename:
        _safe_remove_file(p.avatar_path)
        ext = pathlib.Path(avatar.filename).suffix.lower()
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / filename
        with dest.open("wb") as f:
            shutil.copyfileobj(avatar.file, f)
        p.avatar_path = f"/uploads/{filename}"

    p.food_prefs = food_prefs or None
    p.alcohol_prefs = alcohol_prefs or None
    p.places_to_go = places_to_go or None
    p.traits_positive = traits_positive or None
    p.traits_negative = traits_negative or None
    p.workplace = workplace or None
    p.job_title = job_title or None
    p.wishlist = wishlist or None
    p.telegram_username = (telegram_username or "").lstrip("@") or None
    p.instagram_username = (instagram_username or "").lstrip("@") or None
    p.vk_username = (vk_username or "").lstrip("@") or None

    session.add(p)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


# ===== Каскадное удаление

@app.post("/person/{pid}/delete")
def person_delete(pid: int, auth_ok: bool = Depends(require_auth), session=Depends(get_session)):
    p = session.get(Person, pid)
    if not p:
        return RedirectResponse(url="/", status_code=302)

    pets = session.exec(select(Pet).where(Pet.person_id == pid)).all()
    for pet in pets:
        _safe_remove_file(pet.photo_path)
        session.delete(pet)

    children = session.exec(select(Child).where(Child.person_id == pid)).all()
    for c in children:
        session.delete(c)

    notes = session.exec(select(Note).where(Note.person_id == pid)).all()
    for n in notes:
        session.delete(n)

    _safe_remove_file(p.avatar_path)

    session.delete(p)
    session.commit()
    return RedirectResponse(url="/", status_code=302)


# ===== Питомцы

@app.post("/person/{pid}/pets/new")
def pet_create(
    pid: int,
    name: str = Form(...),
    species: str = Form(...),
    breed: Optional[str] = Form(None),
    age: Optional[str] = Form(None),
    sex: Optional[str] = Form(None),
    feeding: Optional[str] = Form(None),
    care: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    photo: UploadFile | None = File(None),
    auth_ok: bool = Depends(require_auth),
    session=Depends(get_session),
):
    if not session.get(Person, pid):
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Человек не найден", status_code=404)

    photo_path = None
    if photo and photo.filename:
        ext = pathlib.Path(photo.filename).suffix.lower()
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / filename
        with dest.open("wb") as f:
            shutil.copyfileobj(photo.file, f)
        photo_path = f"/uploads/{filename}"

    pet = Pet(
        person_id=pid,
        name=name.strip(),
        species=species.strip(),
        breed=breed or None,
        age=age or None,
        sex=sex or None,
        feeding=feeding or None,
        care=care or None,
        notes=notes or None,
        photo_path=photo_path,
    )
    session.add(pet)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


@app.post("/pets/{pet_id}/edit")
def pet_edit(
    pet_id: int,
    name: str = Form(...),
    species: str = Form(...),
    breed: Optional[str] = Form(None),
    age: Optional[str] = Form(None),
    sex: Optional[str] = Form(None),
    feeding: Optional[str] = Form(None),
    care: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    photo: UploadFile | None = File(None),
    auth_ok: bool = Depends(require_auth),
    session=Depends(get_session),
):
    pet = session.get(Pet, pet_id)
    if not pet:
        return RedirectResponse(url="/", status_code=302)
    pid = pet.person_id

    pet.name = name.strip()
    pet.species = species.strip()
    pet.breed = breed or None
    pet.age = age or None
    pet.sex = sex or None
    pet.feeding = feeding or None
    pet.care = care or None
    pet.notes = notes or None

    if photo and photo.filename:
        _safe_remove_file(pet.photo_path)
        ext = pathlib.Path(photo.filename).suffix.lower()
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / filename
        with dest.open("wb") as f:
            shutil.copyfileobj(photo.file, f)
        pet.photo_path = f"/uploads/{filename}"

    session.add(pet)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


@app.post("/pets/{pet_id}/delete")
def pet_delete(pet_id: int, auth_ok: bool = Depends(require_auth), session=Depends(get_session)):
    pet = session.get(Pet, pet_id)
    if not pet:
        return RedirectResponse(url="/", status_code=302)
    pid = pet.person_id
    _safe_remove_file(pet.photo_path)
    session.delete(pet)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


# ===== Дети

@app.post("/person/{pid}/children/new")
def child_create(
    pid: int,
    name: str = Form(...),
    birth_day: Optional[int] = Form(None),
    birth_month: Optional[int] = Form(None),
    birth_year: Optional[int] = Form(None),
    sex: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    auth_ok: bool = Depends(require_auth),
    session=Depends(get_session),
):
    if not session.get(Person, pid):
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Человек не найден", status_code=404)
    c = Child(
        person_id=pid,
        name=name.strip(),
        birth_day=birth_day or None,
        birth_month=birth_month or None,
        birth_year=birth_year or None,
        sex=sex or None,
        notes=notes or None,
    )
    session.add(c)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


@app.post("/children/{child_id}/edit")
def child_edit(
    child_id: int,
    name: str = Form(...),
    birth_day: Optional[int] = Form(None),
    birth_month: Optional[int] = Form(None),
    birth_year: Optional[int] = Form(None),
    sex: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    auth_ok: bool = Depends(require_auth),
    session=Depends(get_session),
):
    c = session.get(Child, child_id)
    if not c:
        return RedirectResponse(url="/", status_code=302)
    pid = c.person_id

    c.name = name.strip()
    c.birth_day = birth_day or None
    c.birth_month = birth_month or None
    c.birth_year = birth_year or None
    c.sex = sex or None
    c.notes = notes or None

    session.add(c)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


@app.post("/children/{child_id}/delete")
def child_delete(child_id: int, auth_ok: bool = Depends(require_auth), session=Depends(get_session)):
    c = session.get(Child, child_id)
    if not c:
        return RedirectResponse(url="/", status_code=302)
    pid = c.person_id
    session.delete(c)
    session.commit()
    return RedirectResponse(url=f"/person/{pid}", status_code=302)


# ===== Карточка

@app.get("/person/{pid}")
def person_detail(pid: int, request: Request, session=Depends(get_session)):
    p = session.get(Person, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")

    pets = session.exec(select(Pet).where(Pet.person_id == pid)).all()
    children = session.exec(select(Child).where(Child.person_id == pid)).all()
    notes = session.exec(select(Note).where(Note.person_id == pid)).all()

    pets_sorted = sorted(pets, key=lambda x: (x.species or "", x.name or ""))
    children_sorted = sorted(children, key=lambda c: (c.birth_year or 9999, c.birth_month or 12, c.birth_day or 31))
    notes_sorted = sorted(notes, key=lambda n: n.created_at or 0, reverse=True)

    address_full = compose_address(p.city, p.address, p.apartment)

    resp = templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "p": p,
            "pets": pets_sorted,
            "children": children_sorted,
            "notes": notes_sorted,
            "calc_age": calc_age,
            "address_full": address_full,
            "yandex_maps_url": yandex_maps_url,
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp
