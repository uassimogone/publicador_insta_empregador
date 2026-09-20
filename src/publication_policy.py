import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BRAZIL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def first_only(items: list) -> list:
    """Mantém somente o item mais antigo de uma lista em ordem cronológica."""
    return items[:1]


def first_unpublished(posts: list):
    """Retorna somente o primeiro post, desde que ele ainda não tenha sido publicado."""
    if not posts:
        return None
    first_post = posts[0]
    return None if first_post.get("publicado") else first_post


def publication_day(now: datetime | None = None) -> str:
    current = now or datetime.now(BRAZIL_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BRAZIL_TIMEZONE)
    return current.astimezone(BRAZIL_TIMEZONE).date().isoformat()


def already_published_today(state_file: Path, now: datetime | None = None) -> bool:
    if not state_file.exists():
        return False
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return state.get("ultima_publicacao_em") == publication_day(now)


def already_selected_today(data_file: Path, now: datetime | None = None) -> bool:
    if not data_file.exists():
        return False
    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("data_selecao") == publication_day(now)


def mark_published_today(state_file: Path, now: datetime | None = None) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {"ultima_publicacao_em": publication_day(now)},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
