from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import Database
from ai_parser import TaskParser

router = Router()


def setup(db: Database, parser: TaskParser):
    router.db = db
    router.parser = parser


# --- Команда /start ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "*Бот-календарь*\n\n"
        "Я понимаю обычный язык! Просто напиши мне задачу:\n"
        "- _встреча с друзьями завтра в 15:00_\n"
        "- _купить продукты на завтра_\n"
        "- _тренировка каждый понедельник в 18:00_\n\n"
        "Можно также:\n"
        "- _выполнил задачу встреча с другом_ - отмечу выполненной\n"
        "- _покажи задачи на сегодня_ - покажу список\n\n"
        "Команды:\n"
        "/today - задачи на сегодня\n"
        "/week - задачи на неделю\n"
        "/done 12 - отметить задачу #12 выполненной\n"
        "/del 12 - удалить задачу #12",
        parse_mode="Markdown"
    )


# --- Команда /today ---
@router.message(Command("today"))
async def cmd_today(message: types.Message):
    tasks = router.db.get_today_tasks(message.from_user.id)
    if not tasks:
        await message.answer("На сегодня задач нет!")
        return

    lines = []
    for t in tasks:
        time_str = t['deadline'].split(" ")[1][:5]
        repeat_tag = " [R]" if t.get('repeat') and t['repeat'] != 'none' else ""
        lines.append(f"#{t['id']} . *{t['title']}* - {time_str} ({t['category']}){repeat_tag}")

    await message.answer(
        "*Задачи на сегодня:*\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


# --- Команда /week ---
@router.message(Command("week"))
async def cmd_week(message: types.Message):
    tasks = router.db.get_upcoming_tasks(message.from_user.id, days=7)
    if not tasks:
        await message.answer("На ближайшую неделю задач нет!")
        return

    lines = []
    for t in tasks:
        dt, tm = t['deadline'].split(" ")
        repeat_tag = " [R]" if t.get('repeat') and t['repeat'] != 'none' else ""
        lines.append(f"#{t['id']} . {dt} {tm[:5]} - *{t['title']}* ({t['category']}){repeat_tag}")

    await message.answer(
        "*Задачи на неделю:*\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


# --- Команда /done ---
@router.message(Command("done"))
async def cmd_done(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: `/done 12` - отметить задачу #12 выполненной",
                             parse_mode="Markdown")
        return
    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("Номер задачи должен быть числом")
        return

    task = router.db.get_task_by_id(task_id)
    if not task or task['user_id'] != message.from_user.id:
        await message.answer(f"Задача #{task_id} не найдена")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=f"confirm_complete:{task_id}"),
            InlineKeyboardButton(text="Нет", callback_data="cancel_action")
        ]
    ])

    await message.answer(
        f"*Задача: {task['title']}*\n\nОтметить выполненной?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# --- Команда /del ---
@router.message(Command("del"))
async def cmd_del(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: `/del 12` - удалить задачу #12",
                             parse_mode="Markdown")
        return
    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("Номер задачи должен быть числом")
        return

    task = router.db.get_task_by_id(task_id)
    if not task or task['user_id'] != message.from_user.id:
        await message.answer(f"Задача #{task_id} не найдена")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, удалить", callback_data=f"confirm_delete:{task_id}"),
            InlineKeyboardButton(text="Нет", callback_data="cancel_action")
        ]
    ])

    await message.answer(
        f"*Задача: {task['title']}*\n\nУдалить?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# --- Inline: подтверждение выполнения ---
@router.callback_query(lambda c: c.data.startswith("confirm_complete:"))
async def callback_confirm_complete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    success = router.db.complete_task(task_id, callback.from_user.id)
    if success:
        task = router.db.get_task_by_id(task_id)
        title = task['title'] if task else f"#{task_id}"
        await callback.message.edit_text(
            f"*{title}* - выполнена! Молодец",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("Задача не найдена")
    await callback.answer()


# --- Inline: подтверждение удаления ---
@router.callback_query(lambda c: c.data.startswith("confirm_delete:"))
async def callback_confirm_delete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = router.db.get_task_by_id(task_id)
    success = router.db.delete_task(task_id, callback.from_user.id)
    if success:
        title = task['title'] if task else f"#{task_id}"
        await callback.message.edit_text(
            f"*{title}* - удалена",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("Задача не найдена")
    await callback.answer()


# --- Inline: выбор задачи для завершения ---
@router.callback_query(lambda c: c.data.startswith("select_complete:"))
async def callback_select_complete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = router.db.get_task_by_id(task_id)
    if not task:
        await callback.message.edit_text("Задача не найдена")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, выполнена", callback_data=f"confirm_complete:{task_id}"),
            InlineKeyboardButton(text="Нет", callback_data="cancel_action")
        ]
    ])

    await callback.message.edit_text(
        f"*Задача: {task['title']}*\n"
        f"{task['deadline']}\n\n"
        f"Отметить выполненной?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


# --- Inline: выбор задачи для удаления ---
@router.callback_query(lambda c: c.data.startswith("select_delete:"))
async def callback_select_delete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = router.db.get_task_by_id(task_id)
    if not task:
        await callback.message.edit_text("Задача не найдена")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, удалить", callback_data=f"confirm_delete:{task_id}"),
            InlineKeyboardButton(text="Нет", callback_data="cancel_action")
        ]
    ])

    await callback.message.edit_text(
        f"*Задача: {task['title']}*\n"
        f"{task['deadline']}\n\n"
        f"Удалить?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


# --- Inline: отмена ---
@router.callback_query(lambda c: c.data == "cancel_action")
async def callback_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Ок, отмена")
    await callback.answer()


# --- Обработка любого текста (через нейросеть) ---
@router.message()
async def handle_text(message: types.Message):
    if not message.text:
        return

    # Пропускаем команды
    if message.text.startswith("/"):
        return

    # Парсим через нейросеть
    parsed = router.parser.parse(message.text)

    # --- Чат ---
    if parsed.intent == "chat" or parsed.title == "NONE" and not parsed.search_query:
        responses = [
            "Привет! Я - бот-календарь. Напиши задачу, и я добавлю её в расписание!",
            "Привет! Хочешь добавить задачу? Просто напиши что нужно сделать.",
            "Я календарь-бот. Напиши задачу - например, 'встреча завтра в 15:00'",
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
            await message.answer("На сегодня задач нет!")
        else:
            lines = []
            for t in tasks:
                time_str = t['deadline'].split(" ")[1][:5]
                repeat_tag = " [R]" if t.get('repeat') and t['repeat'] != 'none' else ""
                lines.append(f"#{t['id']} . *{t['title']}* - {time_str} ({t['category']}){repeat_tag}")
            await message.answer(
                "*Задачи на сегодня:*\n\n" + "\n".join(lines),
                parse_mode="Markdown"
            )
        return

    # --- Завершение задачи по названию ---
    if parsed.intent == "complete_task":
        query = parsed.search_query.strip()
        if not query:
            task = router.db.find_last_active_task(message.from_user.id)
            if not task:
                await message.answer("У тебя нет активных задач. Добавь новую!")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data=f"confirm_complete:{task['id']}"),
                    InlineKeyboardButton(text="Нет", callback_data="cancel_action")
                ]
            ])
            await message.answer(
                f"Может, ты имел в виду задачу?\n\n"
                f"*{task['title']}*\n"
                f"{task['deadline']}\n\n"
                f"Отметить выполненной?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return

        tasks = router.db.find_tasks_by_title(message.from_user.id, query)

        if not tasks:
            await message.answer(
                f"Не нашёл задачу '{query}'. Попробуй ещё раз или посмотри список командами /today, /week"
            )
            return

        if len(tasks) == 1:
            task = tasks[0]
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data=f"confirm_complete:{task['id']}"),
                    InlineKeyboardButton(text="Нет", callback_data="cancel_action")
                ]
            ])
            await message.answer(
                f"*Задача: {task['title']}*\n"
                f"{task['deadline']}\n\n"
                f"Отметить выполненной?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            buttons = []
            for t in tasks[:5]:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{t['title']} - {t['deadline']}",
                        callback_data=f"select_complete:{t['id']}"
                    )
                ])
            buttons.append([
                InlineKeyboardButton(text="Отмена", callback_data="cancel_action")
            ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await message.answer(
                f"Нашёл несколько задач по запросу '{query}':\nВыбери какую:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return

    # --- Удаление задачи по названию ---
    if parsed.intent == "delete_task":
        query = parsed.search_query.strip()
        if not query:
            await message.answer("Какую задачу удалить? Укажи название или используй /del <номер>")
            return

        tasks = router.db.find_tasks_by_title(message.from_user.id, query)

        if not tasks:
            await message.answer(
                f"Не нашёл задачу '{query}'. Попробуй ещё раз или используй /del <номер>"
            )
            return

        if len(tasks) == 1:
            task = tasks[0]
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да, удалить", callback_data=f"confirm_delete:{task['id']}"),
                    InlineKeyboardButton(text="Нет", callback_data="cancel_action")
                ]
            ])
            await message.answer(
                f"*Задача: {task['title']}*\n"
                f"{task['deadline']}\n\n"
                f"Удалить?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            buttons = []
            for t in tasks[:5]:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{t['title']} - {t['deadline']}",
                        callback_data=f"select_delete:{t['id']}"
                    )
                ])
            buttons.append([
                InlineKeyboardButton(text="Отмена", callback_data="cancel_action")
            ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await message.answer(
                f"Нашёл несколько задач по запросу '{query}':\nВыбери какую:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return

    # --- Добавление задачи ---
    if parsed.intent == "add_task":
        if not parsed.deadline:
            await message.answer("Не совсем понял когда это. Укажи дату и время - например, 'завтра в 15:00'")
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
            repeat_days=parsed.repeat_days
        )

        # Формируем ответ
        repeat_text = ""
        if parsed.repeat == "daily":
            repeat_text = "\nПовтор: каждый день"
        elif parsed.repeat == "weekly":
            if parsed.repeat_days:
                days_ru = {
                    'monday': 'понедельник', 'tuesday': 'вторник', 'wednesday': 'среда',
                    'thursday': 'четверг', 'friday': 'пятница', 'saturday': 'суббота', 'sunday': 'воскресенье'
                }
                days = [days_ru.get(d, d) for d in parsed.repeat_days]
                repeat_text = f"\nПовтор: каждую {', '.join(days)}"
            else:
                repeat_text = "\nПовтор: еженедельно"
        elif parsed.repeat == "monthly":
            repeat_text = "\nПовтор: ежемесячно"

        response = (
            f"*Задача добавлена!* (#{task_id})\n\n"
            f"*{parsed.title}*\n"
            f"{date_display} {time_display}\n"
            f"{parsed.category}"
            f"{repeat_text}\n"
            f"Напомню за час до дедлайна"
        )
        if parsed.description:
            response += f"\n{parsed.description}"

        await message.answer(response, parse_mode="Markdown")
        return

    # --- Фоллбэк ---
    await message.answer(
        "Не совсем понял. Ты хочешь добавить задачу?\n\n"
        "Просто напиши что нужно сделать - например:\n"
        "- _встреча завтра в 15:00_\n"
        "- _купить продукты_\n"
        "- _тренировка каждый понедельник в 18:00_\n\n"
        "Или команды: /today, /week, /done, /del",
        parse_mode="Markdown"
    )
