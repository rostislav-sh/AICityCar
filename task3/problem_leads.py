"""Пункт 3: сделки amoCRM без открытых задач или с просроченными задачами."""

import time

import aiohttp

from task3.client import fetch_all
from task3.schemas import Lead, ProblemLeads, Task

# Системные статусы, одинаковые во всех воронках: «успешно реализовано» / «закрыто и не реализовано»
CLOSED_STATUSES = frozenset({142, 143})
# Только незавершённые задачи, привязанные к сделкам
OPEN_LEAD_TASKS = {"filter[is_completed]": 0, "filter[entity_type]": "leads"}


def classify(leads: list[Lead], tasks: list[Task], now: int) -> ProblemLeads:
    """Чистая функция без сети и времени внутри — тестируется на обычных списках."""
    active = [lead for lead in leads if lead.status_id not in CLOSED_STATUSES]
    with_tasks = {task.entity_id for task in tasks}
    with_overdue = {task.entity_id for task in tasks if task.complete_till < now}
    return ProblemLeads(
        no_tasks=[lead for lead in active if lead.id not in with_tasks],
        overdue=[lead for lead in active if lead.id in with_overdue],
    )


async def find_problem_leads(session: aiohttp.ClientSession) -> ProblemLeads:
    # Для примера грузим все сделки; в рабочей системе — инкрементальный синк в БД (см. п. 1 README)
    leads = [lead async for lead in fetch_all(session, "/api/v4/leads", Lead)]
    tasks = [task async for task in fetch_all(session, "/api/v4/tasks", Task, OPEN_LEAD_TASKS)]
    return classify(leads, tasks, now=int(time.time()))

