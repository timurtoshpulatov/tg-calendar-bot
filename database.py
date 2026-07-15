import sqlite3
from datetime import datetime, timedelta


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    deadline TEXT NOT NULL,
                    remind_at TEXT,
                    notified INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    category TEXT DEFAULT 'общее',
                    repeat TEXT DEFAULT 'none',
                    repeat_days TEXT DEFAULT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_remind
                ON tasks(notified, remind_at)
            """)
            # Миграция: добавляем колонки если их нет
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN repeat TEXT DEFAULT 'none'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN repeat_days TEXT DEFAULT NULL")
            except sqlite3.OperationalError:
                pass

    def add_task(self, user_id: int, title: str, deadline: str,
                 description: str = "", category: str = "общее",
                 repeat: str = "none", repeat_days: list = None) -> int:
        remind_at = self._calc_remind_at(deadline)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        import json
        repeat_days_json = json.dumps(repeat_days) if repeat_days else None
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO tasks
                   (user_id, title, description, deadline, remind_at, created_at, category, repeat, repeat_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, title, description, deadline, remind_at, now, category, repeat, repeat_days_json)
            )
            return cur.lastrowid

    # ── Поиск задач ─────────────────────────────────────────────

    def find_task_by_title(self, user_id: int, query: str) -> dict | None:
        """Ищет первую активную задачу по частичному совпадению названия."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Ищем по названию и описанию
            row = conn.execute(
                """SELECT * FROM tasks
                   WHERE user_id = ? AND status = 'active'
                   AND (title LIKE ? OR description LIKE ?)
                   ORDER BY deadline""",
                (user_id, f"%{query}%", f"%{query}%")
            ).fetchone()
            return dict(row) if row else None

    def find_tasks_by_title(self, user_id: int, query: str) -> list[dict]:
        """Ищет все активные задачи по частичному совпадению названия."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE user_id = ? AND status = 'active'
                   AND (title LIKE ? OR description LIKE ?)
                   ORDER BY deadline""",
                (user_id, f"%{query}%", f"%{query}%")
            ).fetchall()
            return [dict(r) for r in rows]

    def find_last_active_task(self, user_id: int) -> dict | None:
        """Находит последнюю активную задачу (самый ближайший дедлайн)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM tasks
                   WHERE user_id = ? AND status = 'active'
                   ORDER BY deadline ASC LIMIT 1""",
                (user_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Напоминания ─────────────────────────────────────────────

    def get_reminders_due(self) -> list[dict]:
        """Задачи, которые пора напомнить (notified=0, remind_at <= now)."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE notified = 0 AND remind_at IS NOT NULL AND remind_at <= ?
                   AND status = 'active'""",
                (now,)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_notified(self, task_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET notified = 1 WHERE id = ?",
                (task_id,)
            )

    # ── Просмотр задач ──────────────────────────────────────────

    def get_today_tasks(self, user_id: int) -> list[dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE user_id = ? AND deadline LIKE ? AND status = 'active'
                   ORDER BY deadline""",
                (user_id, f"{today}%")
            ).fetchall()
            return [dict(r) for r in rows]

    def get_upcoming_tasks(self, user_id: int, days: int = 7) -> list[dict]:
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE user_id = ? AND deadline <= ? AND status = 'active'
                   ORDER BY deadline""",
                (user_id, f"{end} 23:59:59")
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_user_ids(self) -> list[int]:
        """Все пользователи, у которых есть активные задачи."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM tasks WHERE status = 'active'"
            ).fetchall()
            return [r[0] for r in rows]

    def get_task_by_id(self, task_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Изменение задач ─────────────────────────────────────────

    def complete_task(self, task_id: int, user_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE tasks SET status = 'completed' WHERE id = ? AND user_id = ?",
                (task_id, user_id)
            )
            return cur.rowcount > 0

    def delete_task(self, task_id: int, user_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM tasks WHERE id = ? AND user_id = ?",
                (task_id, user_id)
            )
            return cur.rowcount > 0

    # ── Повторяющиеся задачи ────────────────────────────────────

    def get_repeating_tasks(self) -> list[dict]:
        """Активные повторяющиеся задачи, у которых deadline уже прошёл."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE repeat != 'none' AND repeat IS NOT NULL
                   AND deadline <= ? AND status = 'active'""",
                (now,)
            ).fetchall()
            return [dict(r) for r in rows]

    def create_next_occurrence(self, task: dict) -> int | None:
        """Создаёт следующее вхождение повторяющейся задачи."""
        import json
        from datetime import datetime, timedelta

        try:
            dt = datetime.strptime(task['deadline'], "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                dt = datetime.strptime(task['deadline'], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

        repeat = task.get('repeat', 'none')
        repeat_days = None
        if task.get('repeat_days'):
            try:
                repeat_days = json.loads(task['repeat_days'])
            except (json.JSONDecodeError, TypeError):
                repeat_days = None

        if repeat == 'daily':
            next_dt = dt + timedelta(days=1)
        elif repeat == 'weekly':
            if repeat_days:
                # Находим следующий указанный день недели
                day_map = {
                    'monday': 0, 'tuesday': 1, 'wednesday': 2,
                    'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
                }
                target_weekdays = [day_map[d.lower()] for d in repeat_days if d.lower() in day_map]
                next_dt = dt + timedelta(days=1)
                for _ in range(14):  # ищем до 2 недель вперёд
                    if next_dt.weekday() in target_weekdays:
                        break
                    next_dt += timedelta(days=1)
                else:
                    next_dt = dt + timedelta(weeks=1)
            else:
                next_dt = dt + timedelta(weeks=1)
        elif repeat == 'monthly':
            month = dt.month + 1
            year = dt.year
            if month > 12:
                month = 1
                year += 1
            try:
                next_dt = dt.replace(year=year, month=month)
            except ValueError:
                # Если дня нет в следующем месяце (например, 31 февраля)
                next_dt = dt + timedelta(days=32)
                next_dt = next_dt.replace(day=1)
        else:
            return None

        # Создаём новую задачу
        new_deadline = next_dt.strftime("%Y-%m-%d %H:%M")
        remind_at = self._calc_remind_at(new_deadline)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO tasks
                   (user_id, title, description, deadline, remind_at, created_at, category, repeat, repeat_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task['user_id'], task['title'], task.get('description', ''),
                 new_deadline, remind_at, now, task.get('category', 'общее'),
                 task.get('repeat', 'none'), task.get('repeat_days'))
            )
            return cur.lastrowid

    # ── Вспомогательные ─────────────────────────────────────────

    @staticmethod
    def _calc_remind_at(deadline: str) -> str:
        """Отнимает REMINDER_MINUTES от дедлайна."""
        try:
            dt = datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(deadline, "%Y-%m-%d %H:%M")
            except ValueError:
                return deadline
        remind = dt - timedelta(minutes=60)
        return remind.strftime("%Y-%m-%d %H:%M:%S")
