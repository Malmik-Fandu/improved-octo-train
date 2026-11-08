# color_parser_auto.py
# Плагин для exteraGram: автоматическая перекраска имён из тега <details_color>

import re
from base_plugin import BasePlugin, MethodHook
from hook_utils import find_class
from android.text import SpannableStringBuilder, Spanned
from android.text.style import ForegroundColorSpan
from android.graphics import Color

# ========== МЕТАДАННЫЕ ПЛАГИНА ==========
__id__ = "color_parser_auto"
__name__ = "Color Parser Auto"
__description__ = "Автоматически перекрашивает имена, извлекая цвета из тега details_color"
__author__ = "Your Name"
__version__ = "4.0.0"
__min_version__ = "13.1.1"  # Минимальная версия exteraGram

# ========== ОСНОВНОЙ КЛАСС ПЛАГИНА ==========
class ColorParserAutoPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        # Регулярное выражение для поиска блока details_color
        self.color_block_re = re.compile(
            r'<details_color>(.*?)</details_color>', re.DOTALL
        )
        # Регулярное выражение для извлечения пар "Имя — #HEX"
        self.color_pair_re = re.compile(
            r'([^\n—]+?)\s*—\s*(#[0-9A-Fa-f]{6})'
        )
        self.chat_message_cell = None
        self.message_object_class = None

    def on_plugin_load(self):
        """Вызывается при загрузке плагина."""
        try:
            # 1. Находим класс ChatMessageCell (отрисовка сообщений)
            self.chat_message_cell = find_class(
                "org.telegram.ui.Cells.ChatMessageCell"
            )
            if not self.chat_message_cell:
                self.logger.error("ChatMessageCell не найден")
                return

            # 2. Находим класс MessageObject (обёртка над сообщением)
            self.message_object_class = find_class(
                "org.telegram.messenger.MessageObject"
            )
            if not self.message_object_class:
                self.logger.error("MessageObject не найден")
                return

            # 3. Ищем метод setMessageText или аналогичный для перехвата
            target_method = None
            for method_name in ["setMessageText", "setMessageContent", "updateText"]:
                try:
                    # Пытаемся найти метод с одним параметром MessageObject
                    target_method = self.chat_message_cell.getDeclaredMethod(
                        method_name, self.message_object_class
                    )
                    if target_method:
                        self.logger.info(f"Найден метод: {method_name}")
                        break
                except Exception:
                    continue

            if not target_method:
                self.logger.error(
                    "Не удалось найти подходящий метод для перехвата. "
                    "Проверьте версию exteraGram."
                )
                return

            # 4. Вешаем хук на найденный метод
            self.hook_method(target_method, MessageTextHook(self))
            self.logger.info("Color Parser Auto успешно загружен")

        except Exception as e:
            self.logger.error(f"Ошибка при загрузке плагина: {e}")

    def parse_colors(self, text: str) -> dict:
        """
        Извлекает словарь {имя: цвет} из блока details_color.
        Возвращает пустой словарь, если блок не найден.
        """
        block_match = self.color_block_re.search(text)
        if not block_match:
            return {}

        block = block_match.group(1)
        colors = {}
        for name, hex_color in self.color_pair_re.findall(block):
            colors[name.strip()] = hex_color.strip()
        return colors

    def apply_colors_to_text(self, original_text: str, colors: dict) -> SpannableStringBuilder:
        """
        Создаёт SpannableStringBuilder и применяет ForegroundColorSpan
        к каждому вхождению имени из словаря colors.
        """
        spannable = SpannableStringBuilder(original_text)

        for name, hex_color in colors.items():
            # Преобразуем HEX-цвет в int (ARGB)
            color_int = Color.parseColor(hex_color)
            # Ищем все вхождения имени в тексте
            start = 0
            while True:
                start = original_text.find(name, start)
                if start == -1:
                    break
                end = start + len(name)
                # Применяем цвет к найденному диапазону
                spannable.setSpan(
                    ForegroundColorSpan(color_int),
                    start,
                    end,
                    Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
                )
                start = end

        return spannable

# ========== КЛАСС ХУКА ==========
class MessageTextHook(MethodHook):
    def __init__(self, plugin: ColorParserAutoPlugin):
        self.plugin = plugin

    def after_hooked_method(self, param):
        """
        Вызывается ПОСЛЕ выполнения оригинального метода setMessageText.
        Мы получаем доступ к аргументам и можем заменить текст сообщения
        на перекрашенный Spannable.
        """
        try:
            # Ищем аргумент, который является MessageObject
            message_object = None
            for arg in param.args:
                if arg and self.plugin.message_object_class.isInstance(arg):
                    message_object = arg
                    break

            if not message_object:
                return

            # Получаем текст сообщения (messageText или caption)
            original_text = None
            if message_object.messageText is not None:
                original_text = str(message_object.messageText)
            elif message_object.caption is not None:
                original_text = str(message_object.caption)

            if not original_text:
                return

            # Извлекаем цвета из блока details_color
            colors = self.plugin.parse_colors(original_text)
            if not colors:
                # Если блока нет — ничего не меняем
                return

            # Создаём перекрашенный Spannable
            spannable_text = self.plugin.apply_colors_to_text(
                original_text, colors
            )

            # Заменяем текст в MessageObject на перекрашенный
            if message_object.messageText is not None:
                message_object.messageText = spannable_text
            elif message_object.caption is not None:
                message_object.caption = spannable_text

            self.plugin.logger.info(
                f"Перекрашены имена: {list(colors.keys())}"
            )

        except Exception as e:
            self.plugin.logger.error(f"Ошибка в хуке: {e}")