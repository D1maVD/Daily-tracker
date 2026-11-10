from config import ANTHROPIC_API_KEY


def analyze_day(sessions: list) -> str:
    if not sessions:
        return "Сегодня не было записей. Завтра начни трекать с самого утра!"

    total_minutes = sum(s[4] for s in sessions if s[4])
    h, m = divmod(total_minutes, 60)
    total_str = f"{h}ч {m}мин" if h else f"{m}мин"

    # Без AI — простая сводка
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
        lines = [f"Всего: {total_str}\n"]
        for cat, start, _, desc, dur in sessions:
            line = f"• {cat} — {dur}мин"
            if desc:
                line += f": {desc}"
            lines.append(line)
        return "\n".join(lines)

    # С AI
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    session_lines = [
        f"- {cat}: {desc or 'без описания'} ({dur} мин)"
        for cat, _, _, desc, dur in sessions if dur
    ]

    prompt = f"""Проанализируй рабочий день по сессиям трекера:

{chr(10).join(session_lines)}

Итого активного времени: {total_str}

Дай анализ в таком формате:
✅ Что сделал (топ-3 достижения одной строкой каждое)
📊 Как распределилось время (краткая таблица по категориям)
⚡ Продуктивность: X/10 — одно предложение почему
💡 Совет на завтра: одна конкретная рекомендация

Пиши кратко, по-русски, без лишних вступлений."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text
