"""业务分布函数：小时权重 / 周末效应 / 节假日 / 季节性 / 门店生命周期"""

from datetime import date
import numpy as np
from helpers.biz_calendar import is_weekend, is_holiday, is_spring_festival_period, get_season


# ---- 小时权重 (西式快餐双峰: 午餐+晚餐, 加早餐小峰) ----
# 24 小时, 营业时间 06:00-23:00
HOUR_WEIGHT = np.array([
    0.001, 0.001, 0.001, 0.001, 0.001, 0.005,   # 0-5
    0.020, 0.060, 0.080, 0.040, 0.030, 0.090,   # 6-11
    0.140, 0.110, 0.040, 0.030, 0.040, 0.080,   # 12-17
    0.120, 0.090, 0.040, 0.030, 0.020, 0.005,   # 18-23
])
HOUR_WEIGHT = HOUR_WEIGHT / HOUR_WEIGHT.sum()


def sample_hours(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.choice(24, size=n, p=HOUR_WEIGHT)


def weekday_factor(d: date) -> float:
    """周末客流加成"""
    return 1.25 if is_weekend(d) else 1.0


def holiday_factor(d: date, biz_district: str) -> float:
    """节假日按商圈类型差异化"""
    if is_spring_festival_period(d):
        return 0.4
    if not is_holiday(d):
        return 1.0
    # 法定节假日 (非春节)
    boost_map = {
        "CBD":     0.85,    # 上班族放假 → CBD 反而下降
        "社区":    1.10,
        "校园":    0.70,    # 放假学生回家
        "交通枢纽": 1.50,    # 出行高峰
        "旅游区":  1.65,
        "商场":    1.35,
    }
    return boost_map.get(biz_district, 1.10)


def seasonal_factor(d: date, is_cold: bool, is_hot: bool) -> float:
    """冷饮夏季高,热饮冬季高"""
    season = get_season(d)
    if is_cold:
        return {"SUMMER": 1.8, "SPRING": 1.0, "AUTUMN": 0.8, "WINTER": 0.4}[season]
    if is_hot:
        return {"SUMMER": 0.5, "SPRING": 0.9, "AUTUMN": 1.1, "WINTER": 1.7}[season]
    return 1.0


def store_lifecycle_factor(d: date, open_date: date, close_date) -> float:
    """新店爬坡 / 衰退期"""
    if d < open_date:
        return 0.0
    if close_date and d > close_date:
        return 0.0

    days_open = (d - open_date).days
    if days_open < 30:
        # 爬坡: 30% 线性升至 100%
        return 0.30 + 0.70 * (days_open / 30.0)

    if close_date:
        days_to_close = (close_date - d).days
        if days_to_close < 60:
            # 衰退: 100% 线性降至 0
            return max(0.0, days_to_close / 60.0)

    return 1.0


def daily_orders_for_store(d: date, base_daily: float, biz_district: str,
                           open_date: date, close_date,
                           rng: np.random.Generator) -> int:
    """综合各因子,返回某店某日订单数"""
    if is_spring_festival_period(d) and rng.random() < 0.5:
        return 0    # 春节期间 50% 概率歇业
    f_lifecycle = store_lifecycle_factor(d, open_date, close_date)
    if f_lifecycle <= 0:
        return 0
    f_weekday = weekday_factor(d)
    f_holiday = holiday_factor(d, biz_district)
    expected = base_daily * f_lifecycle * f_weekday * f_holiday
    # 加 ±15% 随机噪声
    noise = rng.normal(1.0, 0.15)
    return max(0, int(expected * noise))
