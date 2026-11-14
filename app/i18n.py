"""Минимальная локализация.

Русский — язык исходных строк. Английский включается словарём переводов
(``EN``): ``tr("Проверить")`` вернёт ``"Check"``, если язык — ``en``.
Неизвестные строки остаются русскими, поэтому словарь можно пополнять
постепенно, ничего не ломая.
"""

from __future__ import annotations

_LANGUAGE = {"code": "ru"}

EN: dict[str, str] = {
    # окно
    "проверка сайта по 152-ФЗ": "website compliance check (152-FZ)",
    "Адрес сайта": "Website address",
    "Проверить": "Check",
    "Отмена": "Cancel",
    "Стоп": "Stop",
    "Экспорт": "Export",
    "Поиск": "Search",
    "Копировать ссылку на отчёт": "Copy report link",
    "Готово": "Done",
    "Проверка…": "Checking…",
    "Проверка выполнена за {seconds} с": "Checked in {seconds} s",
    "Ошибка": "Error",
    "Закрыть": "Close",
    "Открыть папку": "Open folder",
    "Сохранить": "Save",
    "Настройки": "Settings",
    "Файл": "File",
    "Справка": "Help",
    "О программе": "About",
    "Выход": "Exit",
    "Глубокий анализ (Playwright)": "Deep analysis (Playwright)",
    "Проверять сторонние трекеры": "Check third-party trackers",
    "Показывать проверки со статусом N/A": "Show N/A checks",
    "Проверки": "Checks",
    "Не применимо (N/A)": "Not applicable (N/A)",
    "Не удалось проверить": "Could not check",
    "Соответствие": "Compliance",
    "Пройдено": "Passed",
    "Замечание": "Warning",
    "Нарушение": "Violation",
    "Не проверено": "Not checked",
    "Не применимо": "Not applicable",
    "Рекомендация": "Recommendation",
    "Критично": "Critical",
    "Важно": "Important",
    "Информация": "Info",
    "Детали проверки": "Check details",
    "Выберите проверку слева": "Select a check on the left",
    "Сообщение": "Message",
    "Подтверждение": "Evidence",
    "Как исправить": "How to fix",
    "Разработано PriRex": "Made by PriRex",
    "Разработка от PriRex": "Made by PriRex",
    "Критерии проверок": "Check criteria",
    "Как работает приложение": "How the app works",
    "Поддержать автора": "Support the author",
    "Заключение": "Conclusion",
    "Проверить обновление": "Check for updates",
    "Спрашивать перед открытием Boosty": "Ask before opening Boosty",
    "Локальная папка": "Local folder",
    "Папка…": "Folder…",
    "Файл…": "File…",
    "Выберите папку с сайтом": "Choose the site folder",
    "Выберите страницу сайта": "Choose the site page",
    "HTML-страницы (*.html *.htm *.xhtml);;Все файлы (*.*)": (
        "HTML pages (*.html *.htm *.xhtml);;All files (*.*)"
    ),
    "example.com, https://example.com, путь к папке или файлу сайта": (
        "example.com, https://example.com, a folder or a site file path"
    ),
    "актуально на": "data as of",
    "Версия": "Version",
    "Таймаут запросов, сек": "Request timeout, s",
    "User-Agent": "User-Agent",
    "Папка для отчётов": "Reports folder",
    "Проверять обновления": "Check for updates",
    "Частота проверки обновлений, ч": "Update check interval, h",
    "Язык интерфейса": "Interface language",
    "Настройки сохранены": "Settings saved",
    "Версия": "Version",
    "Отчёт": "Report",
}

RU_UI = {
    "export_pdf": "Экспорт в PDF",
    "export_md": "Экспорт в Markdown",
    "export_html": "Экспорт в HTML",
    "export_json": "Экспорт в JSON",
}


def set_language(code: str) -> None:
    _LANGUAGE["code"] = code if code in {"ru", "en"} else "ru"


def get_language() -> str:
    return _LANGUAGE["code"]


def tr(text: str) -> str:
    """Перевод строки на текущий язык (русский — исходный)."""
    if _LANGUAGE["code"] == "ru":
        return text
    return EN.get(text, text)


def trf(text: str, **values: object) -> str:
    try:
        return tr(text).format(**values)
    except (KeyError, IndexError):
        return tr(text)


__all__ = ["EN", "RU_UI", "get_language", "set_language", "tr", "trf"]
