"""Генерация скриншотов для README на вымышленных данных.

Запуск:  python tools/make_docs_screenshots.py
Результат — PNG-файлы в docs/. Сеть не используется (кроме локальной папки
демо-сайта), персональных путей и данных в кадрах нет.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
DEMO_DIR = Path(
    os.environ.get("PRIREX_DEMO_DIR", str(Path(tempfile.gettempdir()) / "demo-site" / "lutik"))
)

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.models import (  # noqa: E402
    CheckResult,
    CheckStatus,
    Evidence,
    Report,
    Severity,
)
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from app.version import __version__  # noqa: E402

PRIVACY_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Политика обработки персональных данных</title></head><body>
<h1>Политика обработки персональных данных</h1>
<p>Оператор персональных данных — ООО «Лютик», ИНН 7707083893.</p>
<h2>Цели обработки</h2><p>Исполнение заказов и поддержка клиентов.</p>
<h2>Срок хранения</h2><p>3 года с момента последнего обращения.</p>
<h2>Права субъекта</h2><p>Права субъекта персональных данных по ст. 14 152-ФЗ.</p>
<h2>Отзыв согласия</h2><p>Отозвать согласие можно письмом на privacy@lutik.ru.</p>
<h2>Cookie</h2><p>Сайт использует файлы cookie для аналитики.</p>
</body></html>
"""

CONTACTS_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Контакты</title></head><body>
<h1>Контакты</h1><p>ООО «Лютик», ОГРН 1027700132195, адрес: г. Москва.</p>
<p>Телефон: +7 (495) 000-00-00, e-mail: privacy@lutik.ru</p>
</body></html>
"""

INDEX_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Магазин техники «Лютик»</title>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-DEMO"></script>
</head><body>
<header><nav><a href="/catalog/">Каталог</a><a href="contacts/index.html">Контакты</a></nav></header>
<main>
<h1>Телевизоры</h1>
<div class="product"><span>59 990 ₽</span><button>Купить</button><a href="/cart/">Корзина</a></div>
<div class="ad-block"><span>Реклама</span>
<a href="https://partner.example.ru/promo?erid=2VtzqwXyZabc123">Партнёрский баннер</a></div>
<form action="/order" method="post">
<input type="text" name="name" placeholder="Имя">
<label><input type="checkbox" name="agree"> Согласен на обработку персональных данных</label>
<button>Оформить заказ</button></form>
<form action="/subscribe" method="post">
<input type="email" name="email" placeholder="E-mail">
<label><input type="checkbox" name="news"> Согласен получать рекламные рассылки</label>
<button>Подписаться</button></form>
<div class="cookie-banner"><p>Мы используем файлы cookie.</p>
<button>Принять все</button><button>Только необходимые</button><button>Настройки</button></div>
</main>
<footer><p>ООО «Лютик», ОГРН 1027700132195, ИНН 7707083893, адрес: г. Москва</p>
<a href="privacy/index.html">Политика конфиденциальности</a>
<a href="mailto:privacy@lutik.ru">privacy@lutik.ru</a></footer>
</body></html>
"""


def ev(label: str, value: str, selector: str | None = None) -> Evidence:
    return Evidence(kind="selector" if selector else "text", label=label, value=value, selector=selector)


def check(
    check_id: str,
    title: str,
    category: str,
    status: CheckStatus,
    message: str,
    *,
    severity: Severity = Severity.IMPORTANT,
    recommendation: str = "",
    evidence: list[Evidence] | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        title=title,
        category=category,
        status=status,
        severity=severity,
        message=message,
        recommendation=recommendation,
        evidence=evidence or [],
    )


def demo_report() -> Report:
    """Вымышленный магазин: смесь пройденных, замечаний, нарушений и N/A."""
    results = [
        check(
            "a01_https", "HTTPS и TLS", "152fz", CheckStatus.PASS,
            "Сайт открывается по HTTPS, сертификат действителен, используется TLSv1.3. "
            "HTTP перенаправляется на HTTPS.",
            severity=Severity.INFO,
            evidence=[ev("Финальный адрес", "https://lutik.ru/"), ev("Версия TLS", "TLSv1.3")],
        ),
        check(
            "a02_privacy_link", "Политика конфиденциальности — наличие", "152fz",
            CheckStatus.PASS,
            "Ссылка на политику обработки персональных данных найдена в футере, "
            "страница открывается без авторизации.",
            severity=Severity.INFO,
            evidence=[
                ev("Ссылка на политику", "https://lutik.ru/privacy/"),
                ev("Селектор ссылки", "footer a", "footer a"),
            ],
        ),
        check(
            "a03_privacy_access", "Политика — доступность без регистрации", "152fz",
            CheckStatus.PASS,
            "Страница политики открывается без авторизации и cookie-стены.",
            severity=Severity.INFO,
        ),
        check(
            "a04_privacy_content", "Политика — содержание", "152fz", CheckStatus.WARN,
            "В политике найдено 6 из 7 ключевых разделов. Отсутствует: срок хранения.",
            severity=Severity.IMPORTANT,
            recommendation="Добавьте в политику раздел о сроках хранения персональных данных.",
            evidence=[ev("Найденные разделы", "оператор, персональные данные, цели обработки, права субъекта, отзыв согласия, cookie")],
        ),
        check(
            "a05_forms_consent", "Формы сбора данных и чекбокс согласия", "152fz",
            CheckStatus.FAIL,
            "В форме подписки собирается e-mail без отдельного согласия на обработку "
            "персональных данных: 1 из 2 форм.",
            severity=Severity.CRITICAL,
            recommendation="Добавьте в форму подписки обязательный чекбокс «Согласен на обработку "
            "персональных данных» со ссылкой на политику.",
            evidence=[
                ev("Форма без согласия", "form[action='/subscribe']", "form[action='/subscribe']"),
                ev("Поле", "email (input[type=email])"),
            ],
        ),
        check(
            "a06_consent_prechecked", "Чекбокс не предзаполнен", "152fz", CheckStatus.PASS,
            "Чекбоксы согласия не предзаполнены (1 шт.).",
            severity=Severity.INFO,
        ),
        check(
            "a07_separate_consent", "Отдельное согласие (не вшито в договор)", "152fz",
            CheckStatus.PASS,
            "Согласие на обработку ПДн оформлено отдельно от принятия оферты.",
            severity=Severity.INFO,
        ),
        check(
            "a08_cookie_banner", "Cookie-баннер", "152fz", CheckStatus.PASS,
            "Cookie-баннер обнаружен: информирует о cookie и запрашивает согласие.",
            severity=Severity.INFO,
            evidence=[ev("Текст баннера", "Мы используем файлы cookie.")],
        ),
        check(
            "a09_cookie_categories", "Категории cookie и кнопка отказа", "152fz",
            CheckStatus.WARN,
            "В баннере есть только кнопка «Принять все»: отказаться от необязательных "
            "cookie нельзя.",
            severity=Severity.IMPORTANT,
            recommendation="Добавьте кнопку «Только необходимые» и настройки категорий cookie.",
        ),
        check(
            "a10_foreign_trackers", "Зарубежные трекеры (риск локализации)", "152fz",
            CheckStatus.WARN,
            "Обнаружены зарубежные трекеры (2): googletagmanager.com (аналитика), "
            "facebook.net (соцсеть). Возможен риск по ч. 5 ст. 18 152-ФЗ.",
            severity=Severity.IMPORTANT,
            recommendation="Откажитесь от зарубежных трекеров в пользу российских "
            "(Яндекс.Метрика, VK Pixel) или исключите передачу персональных данных за границу.",
        ),
        check(
            "a11_pdn_contact", "Контакт для обращений субъектов ПДн", "152fz",
            CheckStatus.PASS,
            "Найдены способы обращения: e-mail privacy@lutik.ru, страница «Контакты».",
            severity=Severity.INFO,
        ),
        check(
            "a12_rkn_notice", "Признаки уведомления в РКН", "152fz", CheckStatus.PASS,
            "Найдены признаки уведомления: упоминание оператора персональных данных.",
            severity=Severity.INFO,
        ),
        check(
            "b13_seller_details", "Реквизиты продавца", "zozpp", CheckStatus.NOT_APPLICABLE,
            "На сайте не обнаружены признаки дистанционной продажи товаров/услуг. "
            "Проверка реквизитов не требуется.",
            severity=Severity.INFO,
        ),
        check(
            "c14_erid", "Маркировка интернет-рекламы (ERID)", "ad",
            CheckStatus.NOT_APPLICABLE,
            "На странице не обнаружены рекламные блоки. Маркировка ERID не требуется.",
            severity=Severity.INFO,
        ),
        check(
            "c15_ad_consent", "Согласие на рекламную рассылку", "ad",
            CheckStatus.NOT_APPLICABLE,
            "На сайте не обнаружены формы подписки на рассылку. Отдельное согласие "
            "на рекламу не требуется.",
            severity=Severity.INFO,
        ),
        check(
            "d16_robots_sitemap", "robots.txt и sitemap.xml", "tech", CheckStatus.PASS,
            "robots.txt доступен. sitemap.xml доступен, адресов в карте: 18.",
            severity=Severity.INFO,
        ),
        check(
            "d17_security_headers", "Заголовки безопасности", "tech", CheckStatus.WARN,
            "Настроены не все заголовки: отсутствует Referrer-Policy.",
            severity=Severity.RECOMMENDATION,
            recommendation="Добавьте заголовок Referrer-Policy: strict-origin-when-cross-origin.",
        ),
    ]
    return Report(
        url="https://lutik.ru/",
        final_url="https://lutik.ru/",
        scanned_at=datetime.now(timezone.utc),
        score=77,
        results=results,
        deep_analysis=True,
        app_version=__version__,
        duration_ms=8420,
        notes=[],
    )


def pump(app: QApplication, count: int = 8) -> None:
    for _ in range(count):
        app.processEvents()


def save(widget, name: str) -> None:
    path = DOCS / name
    widget.grab().save(str(path), "PNG")
    print(f"  {name} — {path.stat().st_size // 1024} КБ")


def build_demo_folder() -> None:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR, ignore_errors=True)
    DEMO_DIR.mkdir(parents=True)
    (DEMO_DIR / "index.html").write_text(INDEX_PAGE, encoding="utf-8")
    (DEMO_DIR / "privacy").mkdir()
    (DEMO_DIR / "privacy" / "index.html").write_text(PRIVACY_PAGE, encoding="utf-8")
    (DEMO_DIR / "contacts").mkdir()
    (DEMO_DIR / "contacts" / "index.html").write_text(CONTACTS_PAGE, encoding="utf-8")
    (DEMO_DIR / "robots.txt").write_text("User-agent: *\nDisallow: /admin\n", encoding="utf-8")
    (DEMO_DIR / "sitemap.xml").write_text(
        "<?xml version='1.0' encoding='UTF-8'?><urlset>"
        "<url><loc>index.html</loc></url>"
        "<url><loc>privacy/index.html</loc></url></urlset>",
        encoding="utf-8",
    )


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(["prirex-docs-screenshots"])
    apply_theme(app)

    # Скриншоты не должны содержать личных путей из локального конфига.
    from app.config import get_config_manager

    config_manager = get_config_manager()
    config_manager.config = config_manager.config.model_copy(
        update={"last_url": "https://lutik.ru/"}
    )

    print("Главное окно и детали…")
    window = MainWindow()
    window._update_timer.stop()
    window.resize(1280, 900)
    window.show()
    pump(app)
    report = demo_report()
    window.show_report(report, None)
    window.url_input.setText("https://lutik.ru/")
    window.show_na_check.setChecked(True)
    window.results_view.set_na_visible(True)
    warning = next(item for item in report.results if item.check_id == "a01_https")
    window.details_panel.show_result(warning)
    pump(app, 12)
    save(window, "screenshot-main.png")

    failing = next(item for item in report.results if item.check_id == "a05_forms_consent")
    window.resize(1280, 980)
    window.details_panel.show_result(failing)
    pump(app, 12)
    scrollbar = window.details_panel.scroll.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    pump(app, 10)
    save(window, "screenshot-detail.png")

    save(window.results_view.na_section, "screenshot-na.png")
    window.close()
    pump(app)

    print("Заключение…")
    from app.ui.conclusion_dialog import ConclusionDialog

    conclusion = ConclusionDialog(report)
    conclusion.show()
    pump(app, 12)
    save(conclusion, "screenshot-conclusion.png")
    conclusion.close()
    pump(app)

    print("Критерии проверок…")
    from app.ui.methodology_window import open_methodology_window

    methodology = open_methodology_window(None, "b13_seller_details")
    methodology.resize(900, 700)
    methodology.show()
    pump(app, 12)
    save(methodology, "screenshot-methodology.png")
    methodology.close()
    pump(app)

    print("Как работает приложение…")
    from app.ui.how_it_works_window import open_how_it_works_window

    how = open_how_it_works_window(None, "how_scan_works")
    how.resize(820, 650)
    how.show()
    pump(app, 12)
    save(how, "screenshot-how-it-works.png")
    how.close()
    pump(app)

    print("Локальная папка…")
    build_demo_folder()
    local_window = MainWindow()
    local_window._update_timer.stop()
    local_window.resize(1280, 800)
    local_window.show()
    local_window.url_input.setText(str(DEMO_DIR))
    local_window.start_scan()
    deadline = time.time() + 120
    while time.time() < deadline:
        app.processEvents()
        if getattr(local_window, "_report", None) is not None:
            break
        time.sleep(0.05)
    settle = time.time() + 1.0
    while time.time() < settle:
        app.processEvents()
        time.sleep(0.03)
    if getattr(local_window, "_report", None) is not None:
        save(local_window, "screenshot-local.png")
    else:
        print("  ЛОКАЛЬНАЯ ПРОВЕРКА НЕ ЗАВЕРШИЛАСЬ:", local_window.progress_label.text())
    local_window.close()
    pump(app)
    shutil.rmtree(DEMO_DIR, ignore_errors=True)

    print("Отчёт PDF…")
    import subprocess

    subprocess.run([sys.executable, str(ROOT / "tools" / "make_preview.py")], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
