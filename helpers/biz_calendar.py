"""日期/节假日工具"""

from datetime import date, timedelta
import chinese_calendar as cc


def daterange(start: date, end: date):
    """[start, end] 闭区间"""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def is_holiday(d: date) -> bool:
    try:
        return cc.is_holiday(d) and not cc.is_workday(d)
    except NotImplementedError:
        return d.weekday() >= 5


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun


def get_holiday_name(d: date) -> str:
    """返回节假日名称(中文),非节假日返回空串"""
    try:
        h = cc.get_holiday_detail(d)  # (is_holiday, holiday_name_or_None)
        if h and h[0] and h[1]:
            return _translate_holiday(h[1])
    except (NotImplementedError, AttributeError):
        pass
    return ""


_HOLIDAY_CN = {
    "New Year's Day": "元旦",
    "Spring Festival": "春节",
    "Tomb-sweeping Day": "清明",
    "Labour Day": "劳动节",
    "Dragon Boat Festival": "端午",
    "National Day": "国庆",
    "Mid-autumn Festival": "中秋",
    "Anti-Fascist 70th Day": "抗战胜利纪念日",
}


def _translate_holiday(name) -> str:
    if hasattr(name, "value"):
        name = name.value
    return _HOLIDAY_CN.get(str(name), str(name))


def is_spring_festival_period(d: date) -> bool:
    """春节连放 7 天判断 (粗略) — 用于判断是否门店歇业"""
    name = get_holiday_name(d)
    return name == "春节"


def get_season(d: date) -> str:
    m = d.month
    if 3 <= m <= 5:
        return "SPRING"
    if 6 <= m <= 8:
        return "SUMMER"
    if 9 <= m <= 11:
        return "AUTUMN"
    return "WINTER"
