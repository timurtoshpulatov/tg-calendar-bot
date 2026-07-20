"""
Парсит текст задачи через regex (быстро) + OpenRouter (точно).
Определяет намерение пользователя и поддерживает повторяющиеся задачи.
"""

import re
import json
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field
from typing import Optional

from config import TIMEZONE
TZ = ZoneInfo(TIMEZONE)


class ParsedTask(BaseModel):
    title: str
    deadline: str = ""                          # YYYY-MM-DD HH:MM
    description: str = ""
    category: str = "общее"
    confidence: float = 1.0
    intent: str = "add_task"                    # add_task | complete_task | delete_task | view_tasks | chat
    repeat: str = "none"                        # none | daily | weekly | monthly
    repeat_days: Optional[list] = None          # ["monday", "wednesday"] и т.д.
    search_query: str = ""                      # запрос для поиска задачи (при complete/delete)


# ─── Regex-парсер (быстрый, без AI) ──────────────────────────

DAYS_RU_TO_EN = {
    'понедельник': 'monday', 'понедельникам': 'monday', 'по понедельникам': 'monday',
    'вторник': 'tuesday', 'вторникам': 'tuesday',
    'среда': 'wednesday', 'средам': 'wednesday',
    'четверг': 'thursday', 'четвергам': 'thursday',
    'пятница': 'friday', 'пятницам': 'friday',
    'суббота': 'saturday', 'субботам': 'saturday',
    'воскресенье': 'sunday', 'воскресеньям': 'sunday',
}

DAYS_NUM_TO_EN = {
    0: 'monday', 1: 'tuesday', 2: 'wednesday',
    3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday',
}


def _get_now():
    return datetime.now(TZ)


def _parse_time(text: str) -> str:
    """Извлекает время из текста (HH:MM или HH)"""
    m = re.search(r'в\s+(\d{1,2})(?::(\d{2}))?(?:\s|$)', text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
    # Без "в" — просто число в начале/середине
    m = re.search(r'\b(\d{1,2}):(\d{2})\b', text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
    return ""


def _parse_date(text: str) -> str:
    """Возвращает дату YYYY-MM-DD из относительных указаний"""
    now = _get_now()
    text_lower = text.lower()

    if 'завтра' in text_lower:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if 'послезавтра' in text_lower:
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")
    if 'сегодня' in text_lower:
        return now.strftime("%Y-%m-%d")
    if 'понедельник' in text_lower:
        target = now + timedelta(days=(7 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")
    if 'вторник' in text_lower:
        target = now + timedelta(days=(1 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")
    if 'сред' in text_lower:
        target = now + timedelta(days=(2 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")
    if 'четверг' in text_lower or 'четв' in text_lower:
        target = now + timedelta(days=(3 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")
    if 'пятниц' in text_lower:
        target = now + timedelta(days=(4 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")
    if 'суббот' in text_lower:
        target = now + timedelta(days=(5 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")
    if 'воскресен' in text_lower:
        target = now + timedelta(days=(6 - now.weekday()) % 7 or 7)
        return target.strftime("%Y-%m-%d")

    # Абсолютная дата: DD.MM или DD.MM.YYYY
    m = re.search(r'\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b', text)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"

    return now.strftime("%Y-%m-%d")


def _parse_repeat(text: str) -> tuple:
    """Определяет повтор и дни недели"""
    text_lower = text.lower()

    if any(w in text_lower for w in ['каждый день', 'ежедневно', 'каждый']):
        if 'день' in text_lower:
            return 'daily', None

    if any(w in text_lower for w in ['каждую неделю', 'еженедельно', 'по неделям']):
        return 'weekly', None

    if any(w in text_lower for w in ['ежемесячно', 'каждый месяц', 'раз в месяц']):
        return 'monthly', None

    # Дни недели: "по понедельникам", "каждую среду"
    repeat_days = []
    for ru_day, en_day in DAYS_RU_TO_EN.items():
        if ru_day in text_lower:
            repeat_days.append(en_day)

    if repeat_days:
        return 'weekly', list(set(repeat_days))

    return 'none', None


def _extract_title(text: str) -> str:
    """Извлекает название задачи, убирая служебные слова"""
    title = text
    # Убираем даты и время
    title = re.sub(r'\bзавтра\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bпослезавтра\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bсегодня\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bв\s+\d{1,2}(?::\d{2})?\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\b\d{1,2}:\d{2}\b', '', title)
    title = re.sub(r'\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b', '', title)
    title = re.sub(r'\bпо\s+\w+дам?\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bкажд\w+\s+\w+\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bежедневно\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bежемесячно\b', '', title, flags=re.IGNORECASE)
    # Убираем "встреча с друзьями" -> "Встреча с друзьями"
    title = title.strip(' \n\r\t-,.')
    if not title:
        return "Задача"
    return title.capitalize()


def regex_parse(text: str) -> Optional[ParsedTask]:
    """Быстрый regex-парсер. Возвращает None если не распознал."""
    text_lower = text.lower().strip()

    # ── view_tasks ──
    if any(w in text_lower for w in [
        'покажи задачи', 'список задач', 'что на сегодня',
        'какие задачи', 'задачи на', 'показать задачи',
        'что запланировано', 'мой расписание'
    ]):
        return ParsedTask(title="NONE", intent="view_tasks")

    # ── complete_task ──
    if any(w in text_lower for w in ['выполнил', 'сделал', 'готово', 'завершил', 'закончил']):
        query = re.sub(r'(выполнил|сделал|готово|завершил|закончил|задачу?)\s*', '', text_lower).strip()
        return ParsedTask(title="NONE", intent="complete_task", search_query=query)

    # ── delete_task ──
    if any(w in text_lower for w in ['удали', 'убери', 'удалить', 'убрать']):
        query = re.sub(r'(удали|убери|удалить|убрать|задачу?)\s*', '', text_lower).strip()
        return ParsedTask(title="NONE", intent="delete_task", search_query=query)

    # ── add_task: есть время или дата? ──
    has_time = bool(re.search(r'в\s+\d{1,2}', text_lower)) or bool(re.search(r'\d{1,2}:\d{2}', text_lower))
    has_date = any(w in text_lower for w in ['завтра', 'послезавтра', 'сегодня',
        'понедельник', 'вторник', 'сред', 'четверг', 'пятниц', 'суббот', 'воскресен'])
    has_date = has_date or bool(re.search(r'\b\d{1,2}\.\d{1,2}', text_lower))

    if has_time or has_date:
        time_str = _parse_time(text)
        if not time_str:
            time_str = "09:00"
        date_str = _parse_date(text)
        title = _extract_title(text)
        repeat, repeat_days = _parse_repeat(text)

        return ParsedTask(
            title=title,
            deadline=f"{date_str} {time_str}",
            intent="add_task",
            repeat=repeat,
            repeat_days=repeat_days,
        )

    # ── chat ──
    return None  # Не распознали — передаём в AI


# ─── AI-парсер (точный, медленный) ───────────────────────────

SYSTEM_PROMPT = """Ты - AI-ассистент календаря задач. Определи намерение и извлеки JSON.

Намерения: add_task, complete_task, delete_task, view_tasks, chat
Повтор: none, daily, weekly, monthly
Дни: monday, tuesday, wednesday, thursday, friday, saturday, sunday

Правила:
1. Даты в YYYY-MM-DD HH:MM (24ч). Если время не указано - 09:00.
2. Категория: работа, личное, здоровье, финансы, учёба, общее
3. Для complete/delete - search_query = ключевые слова для поиска
4. ТОЛЬКО JSON без markdown

Примеры:
"встреча завтра в 15:00" -> {"title":"Встреча","deadline":"2026-07-21 15:00","intent":"add_task","category":"общее"}
"тренировка каждый понедельник в 18:00" -> {"title":"Тренировка","deadline":"2026-07-20 18:00","intent":"add_task","repeat":"weekly","repeat_days":["monday"]}
"выполнил задачу встреча" -> {"title":"NONE","intent":"complete_task","search_query":"встреча"}
"покажи задачи" -> {"title":"NONE","intent":"view_tasks"}
"привет" -> {"title":"NONE","intent":"chat"}

Сегодня {today_date}."""


class TaskParser:
    def __init__(self, api_key: str, model: str, base_url: str = None, max_tokens: int = 300):
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.max_tokens = max_tokens

    def parse(self, text: str) -> ParsedTask:
        # 1) Быстрый regex
        result = regex_parse(text)
        if result:
            print(f"[REGEX] Распознал: intent={result.intent}, title={result.title}")
            return result

        # 2) AI-парсер (fallback)
        try:
            today_date = _get_now().strftime("%Y-%m-%d")
            system_msg = SYSTEM_PROMPT.format(today_date=today_date)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t.me/timhelp1_bot",
                "X-Title": "TG Calendar Bot",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": self.max_tokens,
            }

            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=15.0,
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Убираем markdown-обёртки
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0].strip()

            parsed_data = json.loads(content)
            result = ParsedTask(**parsed_data)
            print(f"[AI] Распознал: intent={result.intent}, title={result.title}")
            return result

        except Exception as e:
            print(f"[AI_PARSER] Ошибка: {e}")
            return ParsedTask(
                title="NONE",
                deadline="",
                description=f"Ошибка парсинга: {e}",
                intent="chat",
                confidence=0
            )
