from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import Database
from ai_parser import TaskParser
from config import TIMEZONE
from datetime import datetime

router = Router()

# ── Приоритеты ────────────────────────────────────────────────
PRIORITY_LABELS = {
    "urgent":  "🔴 Срочно",
    "high":    "🟠 Высокий",
    "normal":  "🟢 Обычный",
    "low":     "⚪ Низкий",
}


def setup(db: Database, parser: TaskParser):
    router.db = db
    router.parser = parser


# ── /start ────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    await message.answer(
        f"*Привет, {message.from_user.first_name}!* 👋\n\n"
        f"Я — бот-календарь. Сейчас *{now}* по МСК.\n\n"
        f"Просто напиши задачу — я пойму:\n"
        f"• _встреча завтра в 15:00_\n"
        f"• _через 2 часа футбол_\n"
        f"• _тренировка каждый понедельник в 18:00_\n\n"
        f"Нажми / чтобы выбрать команду 👇",
        parse_mode="Markdown"
    )


# ── /help ─────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "*📖 Как пользоваться:*\n\n"
        "*Добавление задач:*\n"
        "Просто напиши что нужно сделать — я пойму!\n"
        "• _встреча завтра в 15:00_\n"
        "• _через 30 минут созвон_\n"
        "• _купить продукты_\n"
        "• _тренировка каждый понедельник в 18:00_\n\n"
        "*Приоритеты:*\n"
        "Добавь в начало: *срочно*, *важно*, *ненадо*\n"
        "• _срочно сдать отчёт завтра_\n"
        "• _важно позвонить врачу_\n\n"
        "*Выполнение задач:*\n"
        "• _выполнил задачу встреча с другом_\n"
        "• _сделал тренировку_\n\n"
        "*Удаление задач:*\n"
        "• _удали задачу купить продукты_\n\n"
        "*Просмотр:*\n"
        "• _покажи задачи на сегодня_\n"
        "• Или команды /today, /week\n\n"
        "*Команды:*\n"
        "/today — задачи на сегодня\n"
        "/week — задачи на неделю\n"
        "/stats — статистика\n"
        "/done <номер> — отметить выполненной\n"
        "/del <номер> — удалить задачу",
        parse_mode="Markdown"
    )


# ── /today ────────────────────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: types.Message):
    tasks = router.db.get_today_tasks(message.from_user.id)
    now = datetime.now(TIMEZONE).strftime("%H:%M")

    if not tasks:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Добавить задачу", callback_data="quick_add")
        ]])
        await message.answer(
            f"📋 *Задачи на сегодня* ({now} МСК)\n\n"
            f"✅ На сегодня задач нет!\n"
            f"Можешь отдыхать 🎉",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    lines = []
    for t in tasks:
        time_str = t['deadline'].split(" ")[1][:5]
        pri = PRIORITY_LABELS.get(t.get('priority', 'normal'), '')
        repeat_tag = " 🔁" if t.get('repeat') and t['repeat'] != 'none' else ""
        lines.append(f"#{t['id']} {pri} *{t['title']}* — {time_str} ({t['category']}){repeat_tag}")

    await message.answer(
        f"📋 *Задачи на сегодня* ({now} МСК)\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


# ── /week ─────────────────────────────────────────────────────

@router.message(Command("week"))
async def cmd_week(message: types.Message):
    tasks = router.db.get_upcoming_tasks(message.from_user.id, days=7)
    if not tasks:
        await message.answer("📅 На ближайшую неделю задач нет!")
        return

    lines = []
    for t in tasks:
        dt, tm = t['deadline'].split(" ")
        pri = PRIORITY_LABELS.get(t.get('priority', 'normal'), '')
        repeat_tag = " 🔁" if t.get('repeat') and t['repeat'] != 'none' else ""
        lines.append(f"#{t['id']} {pri} {dt} {tm[:5]} — *{t['title']}* ({t['category']}){repeat_tag}")

    await message.answer(
        "*📅 Задачи на неделю:*\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


# ── /done <id> ────────────────────────────────────────────────

@router.message(Command("done"))
async def cmd_done(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Использование: `/done 12` — отметить задачу #12 выполненной\n"
            "Или напиши: _выполнил задачу встреча с другом_",
            parse_mode="Markdown"
        )
        return
    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("Номер задачи должен быть числом")
        return

    task = router.db.get_task_by_id(task_id)
    if not task or task['user_id'] != message.from_user.id:
        await message.answer(f"❌ Задача #{task_id} не найдена")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_complete:{task_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
        ]
    ])

    await message.answer(
        f"*Задача: {task['title']}*\n"
        f"📅 {task['deadline']}\n\n"
        f"Отметить выполненной? ✅",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# ── /del <id> ─────────────────────────────────────────────────

@router.message(Command("del"))
async def cmd_del(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Использование: `/del 12` — удалить задачу #12\n"
            "Или напиши: _удали задачу купить продукты_",
            parse_mode="Markdown"
        )
        return
    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("Номер задачи должен быть числом")
        return

    task = router.db.get_task_by_id(task_id)
    if not task or task['user_id'] != message.from_user.id:
        await message.answer(f"❌ Задача #{task_id} не найдена")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirm_delete:{task_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
        ]
    ])

    await message.answer(
        f"*Задача: {task['title']}*\n"
        f"📅 {task['deadline']}\n\n"
        f"Удалить? 🗑",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# ── /stats ────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    stats = router.db.get_stats(message.from_user.id)
    completed_today = router.db.get_completed_today(message.from_user.id)
    now = datetime.now(TIMEZONE).strftime("%d.%m.%Y %H:%M")

    # Эмодзи по категориям
    cat_emoji = {
        "работа": "💼", "здоровье": "💪", "учёба": "📚",
        "личное": "🏠", "финансы": "💰", "общее": "📌",
    }

    cat_lines = []
    for cat, cnt in stats['categories'].items():
        emoji = cat_emoji.get(cat, "📌")
        cat_lines.append(f"  {emoji} {cat}: {cnt}")

    pri_lines = []
    for pri, cnt in stats['priorities'].items():
        label = PRIORITY_LABELS.get(pri, pri)
        pri_lines.append(f"  {label}: {cnt}")

    completion_rate = 0
    if stats['total'] > 0:
        completion_rate = int(stats['completed'] / stats['total'] * 100)

    # Прогресс-бар
    bar_len = 10
    filled = int(completion_rate / 100 * bar_len)
    bar = "🟩" * filled + "⬜" * (bar_len - filled)

    text = (
        f"📊 *Статистика*\n"
        f"_{now} МСК_\n\n"
        f"📋 Всего задач: *{stats['total']}*\n"
        f"⏳ Активных: *{stats['active']}*\n"
        f"✅ Выполнено: *{stats['completed']}*\n"
        f"🔁 Повторяющихся: *{stats['repeating']}*\n\n"
        f"*Прогресс:* {bar} {completion_rate}%\n"
        f"✅ Сегодня выполнено: *{completed_today}*\n"
    )

    if cat_lines:
        text += "\n*По категориям:*\n" + "\n".join(cat_lines)
    if pri_lines:
        text += "\n\n*По приоритетам:*\n" + "\n".join(pri_lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мои задачи", callback_data="view_my_tasks")]
    ])

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


# ── Inline: быстрое добавление ────────────────────────────────

@router.callback_query(lambda c: c.data == "quick_add")
async def callback_quick_add(callback: CallbackQuery):
    await callback.message.edit_text(
        "✏️ *Просто напиши задачу:*\n\n"
        "• _встреча завтра в 15:00_\n"
        "• _через 2 часа футбол_\n"
        "• _срочно сдать отчёт_\n"
        "• _тренировка каждый понедельник_\n\n"
        "Или команды: /today, /week, /stats",
        parse_mode="Markdown"
    )
    await callback.answer()


# ── Inline: просмотр задач ────────────────────────────────────

@router.callback_query(lambda c: c.data == "view_my_tasks")
async def callback_view_my_tasks(callback: CallbackQuery):
    tasks = router.db.get_today_tasks(callback.from_user.id)
    if not tasks:
        await callback.message.edit_text("✅ На сегодня задач нет!")
        await callback.answer()
        return

    lines = []
    for t in tasks:
        time_str = t['deadline'].split(" ")[1][:5]
        pri = PRIORITY_LABELS.get(t.get('priority', 'normal'), '')
        lines.append(f"#{t['id']} {pri} *{t['title']}* — {time_str}")

    await callback.message.edit_text(
        "*📋 Задачи на сегодня:*\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )
    await callback.answer()


# ── Inline: подтверждение выполнения ──────────────────────────

@router.callback_query(lambda c: c.data.startswith("confirm_complete:"))
async def callback_confirm_complete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    success = router.db.complete_task(task_id, callback.from_user.id)
    if success:
        task = router.db.get_task_by_id(task_id)
        title = task['title'] if task else f"#{task_id}"
        await callback.message.edit_text(
            f"✅ *{title}* — выполнена!\n\n"
            f"Молодец! 💪",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("❌ Задача не найдена")
    await callback.answer()


# ── Inline: подтверждение удаления ────────────────────────────

@router.callback_query(lambda c: c.data.startswith("confirm_delete:"))
async def callback_confirm_delete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = router.db.get_task_by_id(task_id)
    success = router.db.delete_task(task_id, callback.from_user.id)
    if success:
        title = task['title'] if task else f"#{task_id}"
        await callback.message.edit_text(
            f"🗑 *{title}* — удалена",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("❌ Задача не найдена")
    await callback.answer()


# ── Inline: выбор задачи для завершения ───────────────────────

@router.callback_query(lambda c: c.data.startswith("select_complete:"))
async def callback_select_complete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = router.db.get_task_by_id(task_id)
    if not task:
        await callback.message.edit_text("❌ Задача не найдена")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, выполнена", callback_data=f"confirm_complete:{task_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
        ]
    ])

    await callback.message.edit_text(
        f"*Задача: {task['title']}*\n"
        f"📅 {task['deadline']}\n\n"
        f"Отметить выполненной?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


# ── Inline: выбор задачи для удаления ─────────────────────────

@router.callback_query(lambda c: c.data.startswith("select_delete:"))
async def callback_select_delete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = router.db.get_task_by_id(task_id)
    if not task:
        await callback.message.edit_text("❌ Задача не найдена")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirm_delete:{task_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
        ]
    ])

    await callback.message.edit_text(
        f"*Задача: {task['title']}*\n"
        f"📅 {task['deadline']}\n\n"
        f"Удалить?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


# ── Inline: отмена ────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "cancel_action")
async def callback_cancel(callback: CallbackQuery):
    await callback.message.edit_text("👌 Отмена")
    await callback.answer()


# ── Обработка любого текста ───────────────────────────────────

@router.message()
async def handle_text(message: types.Message):
    if not message.text:
        return
    if message.text.startswith("/"):
        return

    try:
        parsed = router.parser.parse(message.text)
    except Exception as e:
        await message.answer("⚠️ Ошибка парсинга. Попробуй ещё раз.")
        return

    # --- Чат ---
    if parsed.intent == "chat" or (parsed.title == "NONE" and not parsed.search_query):
        responses = [
            "👋 Привет! Я — бот-календарь. Напиши задачу!",
            "📝 Хочешь добавить задачу? Просто напиши что нужно сделать.",
            "📅 Я календарь-бот. Напиши — например, 'встреча завтра в 15:00'",
            "💡 Подсказка: напиши задачу или нажми /help",
        ]
        await message.answer(
            responses[hash(message.text) % len(responses)],
            parse_mode="Markdown"
        )
        return

    # --- Просмотр задач ---
    if parsed.intent == "view_tasks":
        tasks = router.db.get_today_tasks(message.from_user.id)
        if not tasks:
            await message.answer("✅ На сегодня задач нет!")
        else:
            lines = []
            for t in tasks:
                time_str = t['deadline'].split(" ")[1][:5]
                pri = PRIORITY_LABELS.get(t.get('priority', 'normal'), '')
                repeat_tag = " 🔁" if t.get('repeat') and t['repeat'] != 'none' else ""
                lines.append(f"#{t['id']} {pri} *{t['title']}* — {time_str} ({t['category']}){repeat_tag}")
            await message.answer(
                "*📋 Задачи на сегодня:*\n\n" + "\n".join(lines),
                parse_mode="Markdown"
            )
        return

    # --- Завершение задачи по названию ---
    if parsed.intent == "complete_task":
        query = parsed.search_query.strip()
        if not query:
            task = router.db.find_last_active_task(message.from_user.id)
            if not task:
                await message.answer("✅ У тебя нет активных задач!")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_complete:{task['id']}"),
                    InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
                ]
            ])
            await message.answer(
                f"Может, ты имел в виду задачу?\n\n"
                f"*{task['title']}*\n"
                f"📅 {task['deadline']}\n\n"
                f"Отметить выполненной?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return

        tasks = router.db.find_tasks_by_title(message.from_user.id, query)

        if not tasks:
            await message.answer(
                f"❌ Не нашёл задачу '{query}'.\n"
                f"Попробуй /today или /week чтобы посмотреть список."
            )
            return

        if len(tasks) == 1:
            task = tasks[0]
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_complete:{task['id']}"),
                    InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
                ]
            ])
            await message.answer(
                f"*Задача: {task['title']}*\n"
                f"📅 {task['deadline']}\n\n"
                f"Отметить выполненной? ✅",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            buttons = []
            for t in tasks[:5]:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{t['title']} — {t['deadline']}",
                        callback_data=f"select_complete:{t['id']}"
                    )
                ])
            buttons.append([
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")
            ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await message.answer(
                f"🔍 Нашёл несколько задач по '{query}':\nВыбери какую:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return

    # --- Удаление задачи по названию ---
    if parsed.intent == "delete_task":
        query = parsed.search_query.strip()
        if not query:
            await message.answer("Какую задачу удалить? Укажи название или /del <номер>")
            return

        tasks = router.db.find_tasks_by_title(message.from_user.id, query)

        if not tasks:
            await message.answer(
                f"❌ Не нашёл задачу '{query}'.\n"
                f"Попробуй /del <номер>."
            )
            return

        if len(tasks) == 1:
            task = tasks[0]
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirm_delete:{task['id']}"),
                    InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
                ]
            ])
            await message.answer(
                f"*Задача: {task['title']}*\n"
                f"📅 {task['deadline']}\n\n"
                f"Удалить? 🗑",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            buttons = []
            for t in tasks[:5]:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{t['title']} — {t['deadline']}",
                        callback_data=f"select_delete:{t['id']}"
                    )
                ])
            buttons.append([
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")
            ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await message.answer(
                f"🔍 Нашёл несколько задач по '{query}':\nВыбери какую:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return

    # --- Добавление задачи ---
    if parsed.intent == "add_task":
        if not parsed.deadline:
            await message.answer(
                "🤔 Не совсем понял когда это.\n"
                "Укажи время — например, 'завтра в 15:00' или 'через 2 часа'"
            )
            return

        # Форматируем время для отображения
        try:
            dt_parts = parsed.deadline.split(" ")
            time_display = dt_parts[1][:5] if len(dt_parts) > 1 else "09:00"
            date_display = dt_parts[0] if dt_parts else ""
        except Exception:
            time_display = parsed.deadline
            date_display = ""

        # Сохраняем в БД
        task_id = router.db.add_task(
            user_id=message.from_user.id,
            title=parsed.title,
            deadline=parsed.deadline,
            description=parsed.description,
            category=parsed.category,
            repeat=parsed.repeat,
            repeat_days=parsed.repeat_days,
            priority=parsed.priority
        )

        # Формируем ответ
        pri_label = PRIORITY_LABELS.get(parsed.priority, "🟢 Обычный")

        repeat_text = ""
        if parsed.repeat == "daily":
            repeat_text = "\n🔁 Повтор: каждый день"
        elif parsed.repeat == "weekly":
            if parsed.repeat_days:
                days_ru = {
                    'monday': 'понедельник', 'tuesday': 'вторник', 'wednesday': 'среда',
                    'thursday': 'четверг', 'friday': 'пятница', 'saturday': 'суббота', 'sunday': 'воскресенье'
                }
                days = [days_ru.get(d, d) for d in parsed.repeat_days]
                repeat_text = f"\n🔁 Повтор: каждую {', '.join(days)}"
            else:
                repeat_text = "\n🔁 Повтор: еженедельно"
        elif parsed.repeat == "monthly":
            repeat_text = "\n🔁 Повтор: ежемесячно"

        response = (
            f"*Задача добавлена!* ✅ (#{task_id})\n\n"
            f"*{parsed.title}*\n"
            f"📅 {date_display} {time_display}\n"
            f"🏷 {parsed.category} | {pri_label}"
            f"{repeat_text}\n"
            f"⏰ Напомню за час до дедлайна"
        )
        if parsed.description:
            response += f"\n📝 {parsed.description}"

        # Inline кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнена", callback_data=f"confirm_complete:{task_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"confirm_delete:{task_id}")
            ]
        ])

        await message.answer(response, parse_mode="Markdown", reply_markup=keyboard)
        return

    # --- Фоллбэк ---
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Как пользоваться?", callback_data="show_help")]
    ])
    await message.answer(
        "🤔 Не совсем понял. Ты хочешь добавить задачу?\n\n"
        "Просто напиши что нужно сделать:\n"
        "• _встреча завтра в 15:00_\n"
        "• _через 2 часа футбол_\n"
        "• _купить продукты_\n\n"
        "Или нажми / для списка команд",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# ── Inline: показать помощь ──────────────────────────────────

@router.callback_query(lambda c: c.data == "show_help")
async def callback_show_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "📖 *Как пользоваться:*\n\n"
        "Просто напиши задачу — я пойму!\n"
        "• _встреча завтра в 15:00_\n"
        "• _через 2 часа футбол_\n"
        "• _тренировка каждый понедельник_\n\n"
        "Команды: /today, /week, /stats, /help",
        parse_mode="Markdown"
    )
    await callback.answer()
