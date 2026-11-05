"""Search mode keys and labels for the chatlog parser."""

# Mode keys (stable English identifiers for logic)
MODE_KEYS = [
    "Single Date",
    "From Date",
    "Date Range",
    "From Start",
    "From Registered",
    "Personal Mentions",
    "Sync Database",
]


MODE_LABELS = {
    "Single Date": ("Single Date", "Одна дата"),
    "From Date": ("From Date", "С даты"),
    "Date Range": ("Date Range", "Диапазон дат"),
    "From Start": ("From Start", "С начала"),
    "From Registered": ("From Registered", "С регистрации"),
    "Personal Mentions": ("Personal Mentions", "Личные упоминания"),
    "Sync Database": ("Sync Database", "Синхронизация базы"),
}


MENTION_SUB_KEYS = [
    "Single Date",
    "From Date",
    "Date Range",
    "From Start",
    "Last N Days",
]


MENTION_SUB_LABELS = {
    "Single Date": ("Single Date", "Одна дата"),
    "From Date": ("From Date", "С даты"),
    "Date Range": ("Date Range", "Диапазон дат"),
    "From Start": ("From Start", "С начала"),
    "Last N Days": ("Last N Days", "Последние N дней"),
}
