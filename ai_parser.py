"""
Парсит текст задачи через OpenRouter (NVIDIA Nemotron / любая OpenAI-совместимая модель).
"""

from openai import OpenAI
from pydantic import BaseModel


class ParsedTask(BaseModel):
    title: str
    deadline: str           # YYYY-MM-DD HH:MM
    description: str = ""
    category: str = "общее"
    confidence: float = 1.0


SYSTEM_PROMPT = """Ты — AI-ассистент календаря задач.
Из сообщения пользователя извлеки задачу в структурированном виде.

Правила:
1. Преобразуй относительные даты в абсолютные (сегодня = 2026-07-15, завтра = 2026-07-16, послезавтра = 2026-07-17)
2. Время указывай в формате YYYY-MM-DD HH:MM (24-часовой формат)
3. Если время не указано — поставь 09:00 (начало дня)
4. Если дата не указана — поставь сегодня
5. Категорию определи сам: работа, личное, здоровье, финансы, учёба, общее
6. Если в сообщении нет задачи (приветствие, шутка) — верни title="NONE"
7. Возвращай ТОЛЬКО JSON, без markdown-обёрток, без лишнего текста
8. Обязательно используй двойные кавычки для ключей и строк

Примеры:
"добавь встречу с друзьями завтра в 15:00"
→ {"title": "Встреча с друзьями", "deadline": "2026-07-16 15:00", "description": "", "category": "личное"}

"купить продукты на завтра"
→ {"title": "Купить продукты", "deadline": "2026-07-16 09:00", "description": "", "category": "личное"}

"созвон по проекту сегодня в 18:30, нужно показать макеты"
→ {"title": "Созвон по проекту", "deadline": "2026-07-15 18:30", "description": "Нужно показать макеты", "category": "работа"}

"привет"
→ {"title": "NONE"}

Сегодня 2026-07-15."""


class TaskParser:
    def __init__(self, api_key: str, model: str, base_url: str = None, max_tokens: int = 300):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://t.me/tg_calendar_bot",
                "X-Title": "TG Calendar Bot",
            }
        )
        self.model = model
        self.max_tokens = max_tokens

    def parse(self, text: str) -> ParsedTask:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=self.max_tokens,
            )

            content = response.choices[0].message.content.strip()

            # Убираем возможные markdown-обёртки ```json ... ```
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0].strip()

            import json
            data = json.loads(content)
            return ParsedTask(**data)

        except Exception as e:
            return ParsedTask(
                title="NONE",
                deadline="",
                description=f"Ошибка парсинга: {e}",
                confidence=0
            )
