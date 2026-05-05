"""会员主表生成"""

from datetime import date, datetime, timedelta
import numpy as np
from faker import Faker

from helpers.db import bulk_insert
from helpers.biz_calendar import daterange

faker = Faker("zh_CN")

REGISTER_CHANNELS = ["门店", "小程序", "APP", "外卖平台"]
REGISTER_CHANNEL_P = [0.40, 0.35, 0.15, 0.10]


def gen_fact_member(conn, num_members: int, stores_meta, date_start: date, date_end: date,
                    rng: np.random.Generator):
    """
    生成会员主表。
    - 70% 在区间前注册 (老会员), 30% 在区间内注册 (新会员)
    - 等级按金字塔分布
    - 累计消费/订单数后续在订单生成时回写
    """
    rows = []
    members_meta = []  # 供订单生成快速选取
    store_ids = [s["store_id"] for s in stores_meta]
    cols = ["member_id", "member_code", "name", "gender", "phone", "birth_date",
            "register_date", "register_channel", "register_store_id", "level_id",
            "total_consumption", "total_orders", "current_points", "wallet_balance",
            "last_order_date", "status"]

    for mid in range(1, num_members + 1):
        gender = rng.choice(["男", "女"], p=[0.45, 0.55])
        name = faker.name_male() if gender == "男" else faker.name_female()
        phone = f"1{rng.choice(['3','5','7','8','9'])}{int(rng.integers(0, 10**9)):09d}"
        age = int(rng.integers(18, 55))
        birth = date(date_start.year - age, int(rng.integers(1, 13)), int(rng.integers(1, 28)))

        # 注册日期
        if rng.random() < 0.70:
            reg_offset = -int(rng.integers(30, 1000))
        else:
            reg_offset = int(rng.integers(0, (date_end - date_start).days))
        reg_date = date_start + timedelta(days=reg_offset)

        ch = rng.choice(REGISTER_CHANNELS, p=REGISTER_CHANNEL_P)
        reg_store = int(rng.choice(store_ids)) if ch == "门店" else None

        # 等级金字塔
        r = rng.random()
        if r < 0.65:
            level = 1
        elif r < 0.90:
            level = 2
        elif r < 0.985:
            level = 3
        else:
            level = 4

        # 钱包余额: 钻石/金卡更可能有余额
        wallet = 0.0
        if level >= 2 and rng.random() < 0.35:
            wallet = round(float(rng.uniform(20, 500)), 2)
        if level >= 3 and rng.random() < 0.20:
            wallet = round(float(rng.uniform(200, 2000)), 2)

        rows.append((
            mid, f"M{mid:08d}", name, gender, phone, birth,
            reg_date, ch, reg_store, level,
            0, 0, 0, wallet, None, "ACTIVE",
        ))
        members_meta.append({
            "member_id": mid, "level_id": level, "register_date": reg_date,
            "wallet_balance": wallet,
        })

        if len(rows) >= 5000:
            bulk_insert(conn, "fact_member", cols, rows)
            rows = []
    if rows:
        bulk_insert(conn, "fact_member", cols, rows)
    return members_meta


def update_member_stats(conn, member_stats: dict):
    """订单生成完毕后,把每个会员的累计消费/订单数/最后下单日期/积分批量写回。
    member_stats[member_id] = {'total_consumption': x, 'total_orders': n,
                               'last_order_date': d, 'current_points': p, 'wallet_used': w}
    """
    if not member_stats:
        return
    sql = ("UPDATE fact_member SET total_consumption=%s, total_orders=%s, "
           "last_order_date=%s, current_points=%s, "
           "wallet_balance = GREATEST(0, wallet_balance - %s) "
           "WHERE member_id=%s")
    rows = [
        (round(s["total_consumption"], 2), s["total_orders"], s["last_order_date"],
         s["current_points"], round(s.get("wallet_used", 0), 2), mid)
        for mid, s in member_stats.items()
    ]
    with conn.cursor() as cur:
        for i in range(0, len(rows), 5000):
            cur.executemany(sql, rows[i:i + 5000])
            conn.commit()
