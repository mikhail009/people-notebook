from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Person(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Базовые поля
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    apartment: Optional[str] = None  # Квартира

    # Дата рождения
    birth_day: Optional[int] = None
    birth_month: Optional[int] = None
    birth_year: Optional[int] = None

    # Любимое
    favorite_movies: Optional[str] = None
    favorite_color: Optional[str] = None
    favorite_flowers: Optional[str] = None

    # Личное/семья
    marital_status: Optional[str] = None  # single | married | partnered
    partner_name: Optional[str] = None
    handedness: Optional[str] = None      # right | left | ambi
    smokes: Optional[bool] = None

    # Аватар
    avatar_path: Optional[str] = None

    # Предпочтения
    food_prefs: Optional[str] = None
    alcohol_prefs: Optional[str] = None
    places_to_go: Optional[str] = None

    # Характер
    traits_positive: Optional[str] = None
    traits_negative: Optional[str] = None

    # Работа
    workplace: Optional[str] = None       # Где работает
    job_title: Optional[str] = None       # Должность
    # (Для совместимости старая occupation не используется в UI)
    occupation: Optional[str] = None

    # Пожелания на ДР
    wishlist: Optional[str] = None

    # Соцсети (по нику)
    telegram_username: Optional[str] = None
    instagram_username: Optional[str] = None
    vk_username: Optional[str] = None

    # Маркеры отправленных уведомлений о ДР в текущем году
    notify_year_7d: Optional[int] = None
    notify_year_1d: Optional[int] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Pet(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(index=True, foreign_key="person.id")

    name: str
    species: str
    breed: Optional[str] = None
    age: Optional[str] = None
    sex: Optional[str] = None
    feeding: Optional[str] = None
    care: Optional[str] = None
    notes: Optional[str] = None
    photo_path: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Child(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(index=True, foreign_key="person.id")

    name: str
    birth_day: Optional[int] = None
    birth_month: Optional[int] = None
    birth_year: Optional[int] = None
    sex: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(index=True, foreign_key="person.id")
    body: str

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
