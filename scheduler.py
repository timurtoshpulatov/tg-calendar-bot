"""
Планировщик:
  - раз в 30 секунд проверяет БД и отправляет напоминания
  - обрабатывает повторяющиеся задачи
  - ежедневная сводка
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from database import Database
from config import TIMEZONE


class ReminderScheduler:
    def __init__(self, bot: Bot, db: Database, digest_time: str = "09:00"):
        self.bot = bot
        self.db = db
        self.digest_time = digest_time
        self._running = False
        self._last_digest_date = ""

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._check_reminders()
                await self._check_repeating_tasks()
                await self._check_digest()
            except Exception as e:
                print(f"[SCHEDULER] Ошибка: {e}")
            await asyncio.sleep(30)

    def stop(self):
        self._running = False

    # ── Напоминания ────────────────────────────────────────────

    async def _check_reminders(self):
        tasks = self.db.get_reminders_due()
        for task in tasks:
            try:
                repeat_tag = " 🔁" if task.get('repeat') and task['repeat'] != 'none' else ""
                text = (
                    f"⏰ *Напоминание!*\n\n"
                    f"📌 *{task['title']}*\n"
                    f"📅 {task['deadline']}\n"
                    f"🏷 {task['category']}{repeat_tag}"
                )
                if task.get('description'):
                    text += f"\n\n_{task['description']}_"

                await self.bot.send_message(
                    chat_id=task['user_id'],
                    text=text,
                    parse_mode="Markdown"
                )
                self.db.mark_notified(task['id'])
                print(f"[SCHEDULER] Напоминание: {task['title']} → {task['user_id']}")
            except Exception as e:
                print(f"[SCHEDULER] Ошибка отправки #{task['id']}: {e}")

    # ── Повторяющиеся задачи ───────────────────────────────────

    async def _check_repeating_tasks(self):
        tasks = self.db.get_repeating_tasks()
        for task in tasks:
            try:
                new_id = self.db.create_next_occurrence(task)
                if new_id:
                    print(f"[SCHEDULER] 🔁 Новое вхождение: '{task['title']}' → #{new_id}")
            except Exception as e:
                print(f"[SCHEDULER] Ошибка создания повтора #{task['id']}: {e}")

    # ── Ежедневная сводка ──────────────────────────────────────

    async def _check_digest(self):
        now = datetime.now(TIMEZONE)
        today = now.strftime("%Y-%m-%d")

        if self._last_digest_date == today:
            return

        target_h, target_m = map(int, self.digest_time.split(":"))
        if now.hour < target_h or (now.hour == target_h and now.minute < target_m):
            return

        self._last_digest_date = today
        print(f"[SCHEDULER] 📋 Отправляю утреннюю сводку на {today}")

        user_ids = self.db.get_all_user_ids()
        for uid in user_ids:
            try:
                tasks = self.db.get_today_tasks(uid)
                if tasks:
                    lines = []
                    for t in tasks:
                        tm = t['deadline'].split(" ")[1][:5]
                        repeat_tag = " 🔁" if t.get('repeat') and t['repeat'] != 'none' else ""
                        lines.append(f"#{t['id']} · *{t['title']}* — {tm} ({t['category']}){repeat_tag}")

                    text = (
                        f"🌅 *Доброе утро!* ☀️\n\n"
                        f"📋 *План на сегодня:*\n" + "\n".join(lines)
                    )
                else:
                    text = (
                        f"🌅 *Доброе утро!* ☀️\n\n"
                        f"✅ На сегодня задач нет — можно отдыхать! 🎉"
                    )

                await self.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
                print(f"[SCHEDULER] Сводка отправлена пользователю {uid}")
            except Exception as e:
                print(f"[SCHEDULER] Ошибка сводки для {uid}: {e}")
