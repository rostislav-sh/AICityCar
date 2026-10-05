import json
from collections.abc import AsyncIterator

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from pydantic import ValidationError

from task3.client import AmoResponseError, fetch_all
from task3.problem_leads import classify
from task3.schemas import AmoPage, Lead, Task

NOW = 10_000


def lead(id: int, status_id: int = 100) -> Lead:
    return Lead(id=id, name=f"Сделка {id}", status_id=status_id, responsible_user_id=1)


def page_json(ids: list[int], *, has_next: bool) -> dict:
    links = {"self": {"href": "..."}} | ({"next": {"href": "..."}} if has_next else {})
    leads = [{"id": i, "name": "x", "status_id": 1, "responsible_user_id": 1, "price": 0} for i in ids]
    return {"_page": 1, "_links": links, "_embedded": {"leads": leads}}


# --- логика ---


def test_classify_splits_active_leads():
    leads = [lead(1), lead(2), lead(3), lead(4, status_id=142)]
    tasks = [
        Task(id=10, entity_id=2, complete_till=NOW + 1),
        Task(id=11, entity_id=3, complete_till=NOW + 1),
        Task(id=12, entity_id=3, complete_till=NOW - 1),
    ]

    result = classify(leads, tasks, NOW)

    assert [x.id for x in result.no_tasks] == [1]  # сделка 4 закрыта — не проверяем
    assert [x.id for x in result.overdue] == [3]  # хотя бы одна открытая задача просрочена


# --- схемы ---


def test_page_parses_hal_and_ignores_extra_fields():
    page = AmoPage[Lead].model_validate(page_json([1, 2], has_next=True))
    assert [x.id for x in page.items] == [1, 2]
    assert page.has_next


def test_broken_item_fails_with_field_name():
    data = page_json([1], has_next=False)
    del data["_embedded"]["leads"][0]["status_id"]
    with pytest.raises(ValidationError, match="status_id"):
        AmoPage[Lead].model_validate(data)


# --- клиент на локальном HTTP-сервере вместо amoCRM ---


def hal(body: dict | None, status: int = 200) -> web.Response:
    text = None if body is None else json.dumps(body)
    return web.Response(status=status, text=text, content_type="application/hal+json")


@pytest.fixture
def responses() -> list[web.Response]:
    return []


@pytest.fixture
async def session(responses: list[web.Response]) -> AsyncIterator[aiohttp.ClientSession]:
    async def handler(_: web.Request) -> web.Response:
        return responses.pop(0)

    app = web.Application()
    app.router.add_get("/api/v4/leads", handler)
    async with TestServer(app) as server, aiohttp.ClientSession(base_url=str(server.make_url(""))) as s:
        yield s


async def test_fetch_all_walks_pages(session, responses):
    responses += [hal(page_json([1, 2], has_next=True)), hal(page_json([3], has_next=False))]
    leads = [x async for x in fetch_all(session, "/api/v4/leads", Lead)]
    assert [x.id for x in leads] == [1, 2, 3]


async def test_fetch_all_204_is_empty(session, responses):
    responses.append(hal(None, status=204))
    assert [x async for x in fetch_all(session, "/api/v4/leads", Lead)] == []


async def test_unexpected_format_raises_amo_response_error(session, responses):
    responses.append(hal({"_embedded": {"leads": [{"id": "не число"}]}}))
    with pytest.raises(AmoResponseError):
        _ = [x async for x in fetch_all(session, "/api/v4/leads", Lead)]
