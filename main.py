"""Пункт 3: сделки amoCRM без открытых задач или с просроченными задачами.

Запуск (результат печатается в JSON):
  bash:       AMO_SUBDOMAIN=... AMO_TOKEN=... python main.py
  PowerShell: $env:AMO_SUBDOMAIN = "..."; $env:AMO_TOKEN = "..."; python main.py

Почему несколько файлов, а не один до 50 строк: в одном файле HTTP, пагинация, повторы, схемы ответа
и бизнес-правило читаются тяжело. Поэтому код разделён по ответственности:
  - main.py                — точка входа: открыть сессию, запустить, напечатать результат;
  - task3/problem_leads.py — бизнес-логика: само правило (classify) и сбор данных (32 строки);
  - task3/client.py        — HTTP-клиент amoCRM: сессия, повторы при сбоях, пагинация;
  - task3/schemas.py       — pydantic-схемы: весь ответ amoCRM проверяется, а не разбирается как dict.
Правило можно протестировать без сети, а клиент и схемы — переиспользовать для других запросов к amoCRM.
"""

import asyncio
import os

from task3.client import amo_session
from task3.problem_leads import find_problem_leads


async def main() -> None:
    async with amo_session(os.environ["AMO_SUBDOMAIN"], os.environ["AMO_TOKEN"]) as session:
        result = await find_problem_leads(session)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
