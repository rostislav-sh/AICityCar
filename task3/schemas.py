"""Pydantic-схемы ответов amoCRM API v4 и результата.

JSON целиком проверяется pydantic: если amoCRM пришлёт неожиданный формат, будет понятная ValidationError
с путём до поля, а не KeyError где-то в середине кода.
"""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AmoModel(BaseModel):
    # Лишние поля ответа игнорируются: описываем только то, что используем
    model_config = ConfigDict(extra="ignore", frozen=True)


class Lead(AmoModel):
    id: int
    name: str
    status_id: int
    responsible_user_id: int


class Task(AmoModel):
    id: int
    entity_id: int  # id сделки, к которой привязана задача
    complete_till: int  # срок, unix timestamp


class _Link(AmoModel):
    href: str


class _Links(AmoModel):
    next: _Link | None = None  # нет ссылки next — последняя страница


class _Embedded[T: AmoModel](AmoModel):
    # Список лежит под именем сущности: {"leads": [...]} или {"tasks": [...]}
    items: list[T] = Field(validation_alias=AliasChoices("leads", "tasks"))


class AmoPage[T: AmoModel](AmoModel):
    """Страница в формате HAL: {"_embedded": {"leads": [...]}, "_links": {"next": {"href": ...}}}."""

    embedded: _Embedded[T] = Field(alias="_embedded")
    links: _Links = Field(default_factory=_Links, alias="_links")

    @property
    def items(self) -> list[T]:
        return self.embedded.items

    @property
    def has_next(self) -> bool:
        return self.links.next is not None


class ProblemLeads(AmoModel):
    """Результат: активные сделки без открытых задач и с просроченной открытой задачей."""

    no_tasks: list[Lead]
    overdue: list[Lead]
