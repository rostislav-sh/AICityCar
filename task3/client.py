"""Тонкий HTTP-клиент amoCRM API v4: сессия, повторы при временных ошибках, пагинация."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from itertools import count
from typing import Any

import aiohttp
from pydantic import ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from task3.schemas import AmoModel, AmoPage

PAGE_LIMIT = 250  # максимум, который разрешает API v4


class AmoResponseError(Exception):
    """Ответ amoCRM не совпал с ожидаемой схемой."""


@asynccontextmanager
async def amo_session(subdomain: str, token: str) -> AsyncIterator[aiohttp.ClientSession]:
    """Сессия — это пул соединений: открываем её один раз на приложение и передаём в функции."""
    async with aiohttp.ClientSession(
        base_url=f"https://{subdomain}.amocrm.ru",
        headers={"Authorization": f"Bearer {token}"},
        timeout=aiohttp.ClientTimeout(total=30),  # запрос целиком, иначе TimeoutError → повтор
    ) as session:
        yield session


def _is_retryable(error: BaseException) -> bool:
    """Повторяем только временные сбои: 429, 5xx, сеть, таймаут. Прочие 4xx — ошибка в запросе."""
    if isinstance(error, aiohttp.ClientResponseError):
        return error.status == 429 or error.status >= 500
    return isinstance(error, aiohttp.ClientError | TimeoutError)


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=1, max=30),
    reraise=True,
)
async def _get_page[T: AmoModel](
    session: aiohttp.ClientSession, path: str, params: dict[str, Any], item_type: type[T]
) -> AmoPage[T] | None:
    async with session.get(path, params=params) as response:
        if response.status == 204:  # пустой результат amoCRM отдаёт как 204 без тела
            return None
        response.raise_for_status()
        body = await response.read()
    try:
        # Парсим байты сразу pydantic: не зависим от Content-Type (amoCRM отдаёт application/hal+json)
        return AmoPage[item_type].model_validate_json(body)
    except ValidationError as e:
        raise AmoResponseError(f"{path}: неожиданный формат ответа amoCRM\n{e}") from e


async def fetch_all[T: AmoModel](
    session: aiohttp.ClientSession, path: str, item_type: type[T], params: dict[str, Any] | None = None
) -> AsyncIterator[T]:
    """Все элементы со всех страниц.

    Запросы идут последовательно — так укладываемся в лимит amoCRM (~7 запросов/с).
    """
    for page in count(1):
        page_params = {**(params or {}), "page": page, "limit": PAGE_LIMIT}
        result = await _get_page(session, path, page_params, item_type)
        if result is None:
            return
        for item in result.items:
            yield item
        if not result.has_next:
            return
