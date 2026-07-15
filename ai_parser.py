"""
Парсит текст задачи через OpenRouter (прямой HTTP-запрос).
Определяет намерение пользователя и поддерживает повторяющиеся задачи.
"""

import json
import httpx
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


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
            return ParsedTask(**parsed_data)

        except Exception as e:
            print(f"[AI_PARSER] Ошибка: {e}")
            return ParsedTask(
                title="NONE",
                deadline="",
                description=f"Ошибка парсинга: {e}",
                intent="chat",
                confidence=0
            )
