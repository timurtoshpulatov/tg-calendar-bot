"""
Парсит текст задачи через OpenRouter (прямой HTTP-запрос).
Определяет намерение пользователя и поддерживает повторяющиеся задачи.
"""

import json
import re
import httpx
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional


class ParsedTask(BaseModel):
    title: str
    deadline: str = ""
    description: str = ""
    category: str = "общее"
    confidence: float = 1.0
    intent: str = "add_task"
    repeat: str = "none"
    repeat_days: Optional[list] = None
    search_query: str = ""


# ── Простой regex-парсер как fallback ──────────────────────────

def simple_parse(text: str) -> ParsedTask:
    """Простой парсер без AI - для случаев когда API недоступен."""
    today = datetime.now()
    lower = text.lower().strip()

    # ── Чат ──────────────────────────────────────────────────
    chat_words = ["привет", "здравствуй", "хай", "хей", "спасибо", "пока", "как дела", "кто ты", "что умеешь"]
    if any(w in lower for w in chat_words):
        return ParsedTask(title="NONE", intent="chat")

    # ── Просмотр задач ───────────────────────────────────────
    view_words = ["покажи задачи", "список задач", "что на сегодня", "мои задачи", "задачи на сегодня", "задачи на неделю"]
    if any(w in lower for w in view_words):
        return ParsedTask(title="NONE", intent="view_tasks")

    # ── Завершение задачи ────────────────────────────────────
    complete_words = ["выполнил", "сделал", "готово", "завершил", "выполнена", "сделано", "закончил"]
    if any(w in lower for w in complete_words):
        query = lower
        for w in complete_words:
            query = query.replace(w, "")
        query = re.sub(r'задач[уае]?\s*', '', query).strip()
        return ParsedTask(title="NONE", intent="complete_task", search_query=query)

    # ── Удаление задачи ──────────────────────────────────────
    delete_words = ["удали", "убери", "удалить", "убрать"]
    if any(w in lower for w in delete_words):
        query = lower
        for w in delete_words:
            query = query.replace(w, "")
        query = re.sub(r'задач[уае]?\s*', '', query).strip()
        return ParsedTask(title="NONE", intent="delete_task", search_query=query)

    # ── Определяем повтор ────────────────────────────────────
    repeat = "none"
    repeat_days = None
    if "каждый день" in lower or "ежедневно" in lower:
        repeat = "daily"
    elif "по понедельникам" in lower or "каждый понедельник" in lower:
        repeat = "weekly"
        repeat_days = ["monday"]
    elif "по вторникам" in lower or "каждый вторник" in lower:
        repeat = "weekly"
        repeat_days = ["tuesday"]
    elif "по средам" in lower or "каждую среду" in lower:
        repeat = "weekly"
        repeat_days = ["wednesday"]
    elif "по четвергам" in lower or "каждый четверг" in lower:
        repeat = "weekly"
        repeat_days = ["thursday"]
    elif "по пятницам" in lower or "каждую пятницу" in lower:
        repeat = "weekly"
        repeat_days = ["friday"]
    elif "по субботам" in lower or "каждую субботу" in lower:
        repeat = "weekly"
        repeat_days = ["saturday"]
    elif "по воскресеньям" in lower or "каждое воскресенье" in lower:
        repeat = "weekly"
        repeat_days = ["sunday"]
    elif "еженедельно" in lower:
        repeat = "weekly"
    elif "ежемесячно" in lower or "каждый месяц" in lower:
        repeat = "monthly"

    # ── Определяем дату ──────────────────────────────────────
    deadline = ""
    if "завтра" in lower:
        deadline_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "послезавтра" in lower:
        deadline_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    elif "сегодня" in lower:
        deadline_date = today.strftime("%Y-%m-%d")
    else:
        # Пытаемся найти дату в тексте
        date_match = re.search(r'(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?', lower)
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else today.year
            if year < 100:
                year += 2000
            try:
                deadline_date = f"{year}-{month:02d}-{day:02d}"
            except:
                deadline_date = today.strftime("%Y-%m-%d")
        else:
            deadline_date = today.strftime("%Y-%m-%d")

    # ── Определяем время ─────────────────────────────────────
    time_match = re.search(r'(\d{1,2})\s*[:\.]\s*(\d{2})', lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            deadline = f"{deadline_date} {hour:02d}:{minute:02d}"
        else:
            deadline = f"{deadline_date} 09:00"
    else:
        # Пытаемся найти время без двоеточия
        time_match2 = re.search(r'в\s+(\d{1,2})\s*(утра|вечера|дн|ут|веч)?', lower)
        if time_match2:
            hour = int(time_match2.group(1))
            period = time_match2.group(2) or ""
            if period in ["вечера", "веч"] and hour < 12:
                hour += 12
            elif period in ["утра", "ут"] and hour == 12:
                hour = 0
            if 0 <= hour <= 23:
                deadline = f"{deadline_date} {hour:02d}:00"
            else:
                deadline = f"{deadline_date} 09:00"
        else:
            deadline = f"{deadline_date} 09:00"

    # ── Извлекаем название задачи ────────────────────────────
    title = text.strip()
    # Убираем временные маркеры
    for word in ["завтра", "послезавтра", "сегодня", "утром", "днём", "вечером", "в ",
                  "каждый день", "ежедневно", "по понедельникам", "еженедельно",
                  "ежемесячно", "каждый месяц", "каждую неделю"]:
        title = title.replace(word, "")
    title = re.sub(r'\d{1,2}\s*[:\.]\s*\d{2}', '', title)
    title = re.sub(r'\d{1,2}[.\-/]\d{1,2}', '', title)
    title = title.strip(" ,.-")
    if not title:
        title = "Новая задача"

    # ── Определяем категорию ─────────────────────────────────
    category = "общее"
    work_words = ["встреча", "созвон", "проект", "задача", "работа", "дедлайн", "презентация", "совещание"]
    health_words = ["тренировка", "спортзал", "зал", "бег", "пробежка", "йога", "врач", "больница"]
    study_words = ["учёба", "лекция", "семинар", "экзамен", "дз", "домашка", "пара"]
    if any(w in lower for w in work_words):
        category = "работа"
    elif any(w in lower for w in health_words):
        category = "здоровье"
    elif any(w in lower for w in study_words):
        category = "учёба"

    return ParsedTask(
        title=title,
        deadline=deadline,
        category=category,
        intent="add_task",
        repeat=repeat,
        repeat_days=repeat_days
    )


# ── AI парсер ────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты - AI-ассистент календаря задач. Определи намерение пользователя и извлеки данные.

## Намерения (intent):
- **add_task** - пользователь хочет добавить задачу: "добавь встречу", "напомни купить", "созвон завтра"
- **complete_task** - пользователь хочет отметить задачу выполненной: "выполнил задачу", "сделал", "задача готова", "завершил встречу"
- **delete_task** - пользователь хочет удалить задачу: "удали задачу", "убери встречу"
- **view_tasks** - пользователь хочет посмотреть задачи: "покажи задачи", "что на сегодня", "список задач"
- **chat** - обычное сообщение: "привет", "как дела", "спасибо", "кто ты"

## Повтор (repeat):
- **none** - одноразовая задача (по умолчанию)
- **daily** - "каждый день", "ежедневно"
- **weekly** - "по понедельникам", "каждую среду", "по пятницам"
- **monthly** - "1 числа каждого месяца", "каждое 15-е"

Если указаны конкретные дни недели - заполни repeat_days списком на английском (monday, tuesday, wednesday, thursday, friday, saturday, sunday).

## Правила:
1. Преобразуй относительные даты в абсолютные (смотри текущую дату в сообщении)
2. Время в формате YYYY-MM-DD HH:MM (24-часовой)
3. Если время не указано - 09:00
4. Если дата не указана - сегодня
5. Категорию определи: работа, личное, здоровье, финансы, учёба, общее
6. Для complete_task и delete_task - в search_query запиши ключевые слова из сообщения для поиска задачи
7. Возвращай ТОЛЬКО JSON без markdown-обёрток

## Примеры:
"добавь встречу с друзьями завтра в 15:00"
-> {"title": "Встреча с друзьями", "deadline": "2026-07-16 15:00", "description": "", "category": "личное", "intent": "add_task", "repeat": "none", "repeat_days": null, "search_query": ""}

"купить продукты на завтра"
-> {"title": "Купить продукты", "deadline": "2026-07-16 09:00", "description": "", "category": "личное", "intent": "add_task", "repeat": "none", "repeat_days": null, "search_query": ""}

"тренировка каждый понедельник в 18:00"
-> {"title": "Тренировка", "deadline": "2026-07-20 18:00", "description": "", "category": "здоровье", "intent": "add_task", "repeat": "weekly", "repeat_days": ["monday"], "search_query": ""}

"встреча завтра в 15:30"
-> {"title": "Встреча", "deadline": "2026-07-16 15:30", "description": "", "category": "общее", "intent": "add_task", "repeat": "none", "repeat_days": null, "search_query": ""}

"привет"
-> {"title": "NONE", "intent": "chat", "repeat": "none", "repeat_days": null, "search_query": ""}

"выполнил задачу встреча с другом"
-> {"title": "NONE", "intent": "complete_task", "repeat": "none", "repeat_days": null, "search_query": "встреча с другом"}

"задача готова"
-> {"title": "NONE", "intent": "complete_task", "repeat": "none", "repeat_days": null, "search_query": ""}

"покажи задачи на сегодня"
-> {"title": "NONE", "intent": "view_tasks", "repeat": "none", "repeat_days": null, "search_query": ""}

Сегодня {today_date}."""


class TaskParser:
    def __init__(self, api_key: str, model: str, base_url: str = None, max_tokens: int = 300):
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.max_tokens = max_tokens

    def parse(self, text: str) -> ParsedTask:
        # Сначала пробуем AI
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            system_msg = SYSTEM_PROMPT.format(today_date=today_date)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t.me/tg_calendar_bot",
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
                timeout=30.0,
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
            if result.title != "NONE" or result.intent != "add_task":
                return result
            # Если AI вернул add_task но без названия - fallback
            if result.intent == "add_task" and not result.title:
                return simple_parse(text)
            return result

        except Exception as e:
            print(f"[AI_PARSER] Ошибка AI, используем fallback: {e}")
            return simple_parse(text)
