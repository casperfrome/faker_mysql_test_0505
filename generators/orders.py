"""订单 / 订单明细 / 支付 / 优惠券核销 / 积分流水

最复杂模块。流式生成,按 day×store 节奏,定期 flush 到 MySQL。
"""

import bisect
from datetime import date, datetime, timedelta
import numpy as np

from helpers.db import bulk_insert, BATCH_SIZE
from helpers.biz_calendar import daterange, is_weekend, is_holiday, is_spring_festival_period, get_season
from helpers.distributions import (
    HOUR_WEIGHT, weekday_factor, holiday_factor, seasonal_factor,
    store_lifecycle_factor, daily_orders_for_store,
)
from generators.dimensions import CITIES


# ============================================================
# 类目基础权重
# ============================================================
CATEGORY_BASE_WEIGHT = {
    1: 0.30,   # 汉堡
    2: 0.12,   # 鸡肉
    3: 0.15,   # 小食
    4: 0.25,   # 饮料
    5: 0.08,   # 套餐
    6: 0.05,   # 早餐
    7: 0.04,   # 甜品
    8: 0.01,   # 儿童餐
}


def store_base_daily(store, city_tier_lookup):
    """根据门店属性返回日均订单基线"""
    base = 130.0
    tier = city_tier_lookup.get(store["city_id"], "二线")
    if tier == "一线":
        base *= 1.18
    elif tier == "新一线":
        base *= 0.95
    biz = store["biz_district"]
    biz_mult = {
        "CBD": 1.18, "旅游区": 1.20, "商场": 1.10, "交通枢纽": 1.12,
        "社区": 1.00, "校园": 0.90,
    }.get(biz, 1.0)
    base *= biz_mult
    base *= store.get("popularity", 1.0)
    return base


def order_size_distribution(rng) -> int:
    r = rng.random()
    if r < 0.05:
        return 1
    if r < 0.65:
        return 2
    if r < 0.90:
        return 3
    if r < 0.97:
        return 4
    return 5


def quantity_distribution(rng) -> int:
    r = rng.random()
    if r < 0.90:
        return 1
    if r < 0.98:
        return 2
    return 3


def gen_orders(conn, stores_meta, products_meta, members_meta, coupon_templates,
               date_start: date, date_end: date, rng: np.random.Generator,
               channel_ratio: dict, payment_ratio: dict,
               member_order_ratio: float, coupon_use_ratio: float,
               batch_size: int = BATCH_SIZE):
    """
    返回 (order_count, item_count, payment_count, coupon_count, point_count, member_stats)
    member_stats 用于订单结束后回写到 fact_member。
    """
    # ---- 准备 lookup ----
    city_tier_lookup = {c[0]: c[3] for c in CITIES}
    # 给每店随机一个 popularity (0.75-1.30)
    for s in stores_meta:
        if "popularity" not in s:
            s["popularity"] = float(rng.uniform(0.75, 1.30))

    # 产品按类目分桶,用于按类目权重抽样
    products_by_cat = {cid: [] for cid in CATEGORY_BASE_WEIGHT}
    for p in products_meta:
        products_by_cat[p["category_id"]].append(p)

    # 会员按注册日期排序 → 给每天找出"截止当日已注册"的会员数
    members_sorted = sorted(members_meta, key=lambda m: m["register_date"])
    member_reg_dates = [m["register_date"] for m in members_sorted]

    # 渠道与支付方式的 id 映射 (与 dimensions.py 中一致)
    CHANNEL_IDS = {"DINE_IN": 1, "TAKEOUT": 2, "MEITUAN": 3, "ELEME": 4}
    DINE_TYPE_OF_CHANNEL = {1: "DINE_IN", 2: "TAKEAWAY", 3: "DELIVERY", 4: "DELIVERY"}
    PAYMENT_IDS = {"WECHAT": 1, "ALIPAY": 2, "MEMBER": 3, "CARD": 4, "CASH": 5}
    MEMBER_DISCOUNT = {1: 1.0, 2: 0.95, 3: 0.90, 4: 0.85}
    POINT_RATE = {1: 1.0, 2: 1.5, 3: 2.0, 4: 3.0}
    COMMISSION = {1: 0.0, 2: 0.0, 3: 0.18, 4: 0.16}

    channel_codes = list(channel_ratio.keys())
    channel_probs = np.array([channel_ratio[c] for c in channel_codes])
    channel_probs = channel_probs / channel_probs.sum()
    payment_codes = list(payment_ratio.keys())
    payment_probs = np.array([payment_ratio[c] for c in payment_codes])
    payment_probs = payment_probs / payment_probs.sum()

    # ---- 状态 ----
    order_id_counter = 0
    coupon_id_counter = 0
    member_stats = {}     # member_id -> {...}

    order_buf, item_buf, pay_buf = [], [], []
    issued_buf, redeemed_buf, point_buf = [], [], []

    order_cols = ["order_id", "order_no", "store_id", "date_key", "order_time",
                  "channel_id", "member_id", "cashier_id", "dine_type", "table_no",
                  "headcount", "item_count", "original_amount", "discount_amount",
                  "coupon_amount", "delivery_fee", "platform_fee", "actual_amount",
                  "points_used", "points_earned", "status", "prep_minutes"]
    item_cols = ["order_id", "product_id", "quantity", "unit_price", "discount_amount", "subtotal"]
    pay_cols = ["order_id", "payment_id", "pay_amount", "pay_time", "transaction_no", "status"]
    issued_cols = ["coupon_id", "coupon_code", "template_id", "member_id", "issue_time",
                   "expire_time", "source", "status"]
    redeemed_cols = ["coupon_id", "order_id", "member_id", "redeem_time", "discount_amount"]
    point_cols = ["member_id", "txn_time", "txn_type", "points", "balance_after",
                  "related_order_id", "remark"]

    counts = {"orders": 0, "items": 0, "payments": 0, "issued": 0, "redeemed": 0, "points": 0}

    def flush(force=False):
        nonlocal counts
        if force or len(order_buf) >= batch_size:
            if order_buf:
                bulk_insert(conn, "fact_order", order_cols, order_buf, batch_size)
                counts["orders"] += len(order_buf)
                order_buf.clear()
        if force or len(item_buf) >= batch_size:
            if item_buf:
                bulk_insert(conn, "fact_order_item", item_cols, item_buf, batch_size)
                counts["items"] += len(item_buf)
                item_buf.clear()
        if force or len(pay_buf) >= batch_size:
            if pay_buf:
                bulk_insert(conn, "fact_payment", pay_cols, pay_buf, batch_size)
                counts["payments"] += len(pay_buf)
                pay_buf.clear()
        if force or len(issued_buf) >= batch_size:
            if issued_buf:
                bulk_insert(conn, "fact_coupon_issued", issued_cols, issued_buf, batch_size)
                counts["issued"] += len(issued_buf)
                issued_buf.clear()
        if force or len(redeemed_buf) >= batch_size:
            if redeemed_buf:
                bulk_insert(conn, "fact_coupon_redeemed", redeemed_cols, redeemed_buf, batch_size)
                counts["redeemed"] += len(redeemed_buf)
                redeemed_buf.clear()
        if force or len(point_buf) >= batch_size:
            if point_buf:
                bulk_insert(conn, "fact_point_txn", point_cols, point_buf, batch_size)
                counts["points"] += len(point_buf)
                point_buf.clear()

    coupon_templates_arr = coupon_templates  # list of tuples per dimensions.gen_dim_coupon_template

    # ---- 主循环 ----
    from tqdm import tqdm
    days = list(daterange(date_start, date_end))
    for d in tqdm(days, desc="生成订单"):
        date_key = int(d.strftime("%Y%m%d"))
        eligible_member_count = bisect.bisect_right(member_reg_dates, d)

        # 当日类目权重 (季节调整)
        season = get_season(d)
        for s in stores_meta:
            n = daily_orders_for_store(
                d, store_base_daily(s, city_tier_lookup), s["biz_district"],
                s["open_date"], s["close_date"], rng,
            )
            if n <= 0:
                continue

            hours = rng.choice(24, size=n, p=HOUR_WEIGHT)
            # 每店收银员候选 (后续从 employees_meta 拿;这里随机一个员工 id 占位)

            for hh in hours:
                order_id_counter += 1
                order_id = order_id_counter
                mm = int(rng.integers(0, 60))
                ss = int(rng.integers(0, 60))
                order_dt = datetime(d.year, d.month, d.day, int(hh), mm, ss)

                # 渠道
                ch_code = rng.choice(channel_codes, p=channel_probs)
                channel_id = CHANNEL_IDS[ch_code]
                dine_type = DINE_TYPE_OF_CHANNEL[channel_id]

                # 是否会员
                member_id = None
                level_id = 1
                if eligible_member_count > 0 and rng.random() < member_order_ratio:
                    midx = int(rng.integers(0, eligible_member_count))
                    member = members_sorted[midx]
                    member_id = member["member_id"]
                    level_id = member["level_id"]

                # 选 items
                size = order_size_distribution(rng)
                items_in_order = []
                original_amount = 0.0
                # 类目权重 (套餐/早餐 时段限制)
                cat_w = dict(CATEGORY_BASE_WEIGHT)
                if hh < 6 or hh > 10:
                    cat_w[6] = 0.005    # 早餐非时段
                if hh < 11:
                    cat_w[5] *= 0.4     # 午餐前套餐少
                # 归一化
                cat_ids = list(cat_w.keys())
                cat_p_raw = np.array([cat_w[c] for c in cat_ids])
                cat_p = cat_p_raw / cat_p_raw.sum()

                for _ in range(size):
                    cat = int(rng.choice(cat_ids, p=cat_p))
                    pool = products_by_cat[cat]
                    if not pool:
                        continue
                    # 季节调整: 冷热饮重新加权
                    if cat == 4:
                        weights = []
                        for p in pool:
                            w = 1.0
                            if p["is_cold"]:
                                w *= seasonal_factor(d, True, False)
                            elif p["is_hot"]:
                                w *= seasonal_factor(d, False, True)
                            # 招牌+30%
                            if p["is_signature"]:
                                w *= 1.3
                            # 上下架日期检查
                            if d < p["available_from"]:
                                w = 0
                            if p["available_to"] and d > p["available_to"]:
                                w = 0
                            weights.append(w)
                        wsum = sum(weights)
                        if wsum <= 0:
                            continue
                        wn = [w / wsum for w in weights]
                        product = pool[int(rng.choice(len(pool), p=wn))]
                    else:
                        # 招牌权重
                        weights = []
                        for p in pool:
                            w = 1.0
                            if p["is_signature"]:
                                w *= 1.4
                            if d < p["available_from"]:
                                w = 0
                            if p["available_to"] and d > p["available_to"]:
                                w = 0
                            weights.append(w)
                        wsum = sum(weights)
                        if wsum <= 0:
                            continue
                        wn = [w / wsum for w in weights]
                        product = pool[int(rng.choice(len(pool), p=wn))]

                    qty = quantity_distribution(rng)
                    unit_price = product["price"]
                    subtotal = unit_price * qty
                    items_in_order.append({"product": product, "qty": qty, "unit_price": unit_price, "subtotal": subtotal})
                    original_amount += subtotal

                if not items_in_order:
                    order_id_counter -= 1
                    continue

                # 会员折扣
                discount_rate = MEMBER_DISCOUNT[level_id]
                discount_amount = round(original_amount * (1 - discount_rate), 2) if member_id else 0.0
                amount_after_discount = original_amount - discount_amount

                # 优惠券 (仅会员且满足总体核销概率 ~50%)
                coupon_amount = 0.0
                use_coupon = (
                    member_id is not None and
                    rng.random() < (coupon_use_ratio / max(member_order_ratio, 0.01))
                )
                redeem_record = None
                if use_coupon:
                    # 选一个适用的券模板
                    valid_templates = [t for t in coupon_templates_arr
                                       if t[6] <= amount_after_discount]   # min_order_amount
                    if valid_templates:
                        tpl = valid_templates[int(rng.integers(0, len(valid_templates)))]
                        ctype = tpl[3]
                        face = float(tpl[4]) if tpl[4] else 0.0
                        disc = float(tpl[5]) if tpl[5] else None
                        if ctype == "DISCOUNT" and disc:
                            coupon_amount = round(amount_after_discount * (1 - disc), 2)
                        else:
                            coupon_amount = min(face, amount_after_discount * 0.5)

                        coupon_id_counter += 1
                        coupon_id = coupon_id_counter
                        issue_time = order_dt - timedelta(days=int(rng.integers(0, max(1, tpl[7]))))
                        expire_time = issue_time + timedelta(days=tpl[7])
                        coupon_code = f"C{coupon_id:010d}"
                        issued_buf.append((
                            coupon_id, coupon_code, tpl[0], member_id,
                            issue_time, expire_time, "活动发放", "USED",
                        ))
                        redeem_record = (coupon_id, order_id, member_id, order_dt, coupon_amount)

                amount_after_coupon = amount_after_discount - coupon_amount

                # 配送费 + 平台佣金 (仅外卖)
                delivery_fee = 0.0
                platform_fee = 0.0
                if channel_id in (3, 4):
                    delivery_fee = round(float(rng.choice([3, 4, 5, 6, 7, 8])), 2)
                    platform_fee = round(amount_after_coupon * COMMISSION[channel_id], 2)

                actual_amount = round(amount_after_coupon + delivery_fee, 2)

                # 积分赚取
                points_earned = 0
                points_used = 0
                if member_id:
                    points_earned = int(amount_after_coupon * POINT_RATE[level_id])
                    state = member_stats.setdefault(member_id, {
                        "total_consumption": 0.0, "total_orders": 0,
                        "current_points": 0, "last_order_date": None,
                        "wallet_used": 0.0,
                    })
                    state["total_consumption"] += amount_after_coupon
                    state["total_orders"] += 1
                    state["last_order_date"] = d
                    state["current_points"] += points_earned

                    # 积分赚取 txn
                    point_buf.append((
                        member_id, order_dt, "EARN", points_earned,
                        state["current_points"], order_id, "消费返积分",
                    ))
                    # 5% 概率消耗积分 (100 分抵 1 元)
                    if state["current_points"] >= 200 and rng.random() < 0.05:
                        used = min(state["current_points"], int(actual_amount * 100 * 0.3))
                        used = (used // 100) * 100
                        if used >= 100:
                            points_used = used
                            state["current_points"] -= used
                            point_buf.append((
                                member_id, order_dt, "REDEEM", -used,
                                state["current_points"], order_id, "积分抵现",
                            ))

                # 桌号/人数 (仅堂食)
                table_no = None
                headcount = None
                if channel_id == 1:
                    table_no = f"T{int(rng.integers(1, 30)):02d}"
                    headcount = int(rng.choice([1, 1, 2, 2, 2, 3, 3, 4, 4, 5, 6], p=[0.18, 0.10, 0.20, 0.12, 0.08, 0.10, 0.06, 0.06, 0.04, 0.04, 0.02]))

                # 出餐时长
                if channel_id == 1:
                    prep = int(rng.integers(5, 18))
                else:
                    prep = int(rng.integers(8, 25))

                # 状态: 1.5% 退款, 0.5% 取消
                r2 = rng.random()
                if r2 < 0.005:
                    status = "CANCELLED"
                elif r2 < 0.020:
                    status = "REFUNDED"
                else:
                    status = "PAID"

                # 构造订单行
                order_no = f"O{d.strftime('%Y%m%d')}{s['store_id']:04d}{order_id_counter % 100000:05d}"
                # 收银员: 简化为 None (位置占用)
                order_buf.append((
                    order_id, order_no, s["store_id"], date_key, order_dt,
                    channel_id, member_id, None, dine_type, table_no, headcount,
                    sum(it["qty"] for it in items_in_order),
                    round(original_amount, 2), discount_amount, coupon_amount,
                    delivery_fee, platform_fee, actual_amount,
                    points_used, points_earned, status, prep,
                ))
                for it in items_in_order:
                    item_buf.append((
                        order_id, it["product"]["product_id"], it["qty"],
                        round(it["unit_price"], 2),
                        round(it["subtotal"] * (1 - discount_rate), 2) if member_id else 0,
                        round(it["subtotal"] * discount_rate if member_id else it["subtotal"], 2),
                    ))

                # 支付 (95% 单一, 5% 拆分)
                if status != "CANCELLED":
                    if member_id and member_stats.get(member_id, {}).get("wallet_used", -1) >= 0:
                        # 会员订单 30% 概率使用储值
                        pass  # 简化保留下方逻辑
                    if rng.random() < 0.05 and actual_amount > 30:
                        # 拆分支付
                        amt1 = round(actual_amount * float(rng.uniform(0.3, 0.7)), 2)
                        amt2 = round(actual_amount - amt1, 2)
                        p1 = rng.choice(payment_codes, p=payment_probs)
                        p2 = rng.choice(payment_codes, p=payment_probs)
                        pay_buf.append((order_id, PAYMENT_IDS[p1], amt1, order_dt,
                                        f"TX{order_id:012d}A", "SUCCESS"))
                        pay_buf.append((order_id, PAYMENT_IDS[p2], amt2, order_dt,
                                        f"TX{order_id:012d}B", "SUCCESS"))
                    else:
                        # 会员储值优先
                        if member_id and rng.random() < 0.30:
                            p_code = "MEMBER"
                        else:
                            p_code = rng.choice(payment_codes, p=payment_probs)
                        pay_buf.append((order_id, PAYMENT_IDS[p_code], actual_amount,
                                        order_dt, f"TX{order_id:012d}", "SUCCESS"))

                if redeem_record:
                    redeemed_buf.append(redeem_record)

                flush()

        # 每天结束尝试 flush
        flush()

    flush(force=True)

    return counts, member_stats


# ============================================================
# 额外发券 (注册赠送 / 未使用 / 过期) — 让 fact_coupon_issued 更丰富
# ============================================================
def gen_extra_issued_coupons(conn, members_meta, coupon_templates, date_start, date_end,
                              rng, batch_size: int = BATCH_SIZE):
    """补充约 15-20 万张未使用/已过期的券,提高真实度"""
    rows = []
    cols = ["coupon_id", "coupon_code", "template_id", "member_id", "issue_time",
            "expire_time", "source", "status"]

    # 当前 fact_coupon_issued 中最大 coupon_id
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(coupon_id), 0) FROM fact_coupon_issued")
        next_id = cur.fetchone()[0] + 1

    target = int(len(members_meta) * 1.8)   # 每会员平均 1.8 张
    sources = ["注册赠送", "活动发放", "生日福利", "邀请奖励", "流失召回"]
    src_p = [0.30, 0.35, 0.10, 0.15, 0.10]

    for _ in range(target):
        m = members_meta[int(rng.integers(0, len(members_meta)))]
        tpl = coupon_templates[int(rng.integers(0, len(coupon_templates)))]
        valid_days = tpl[7]
        # issue_time 在会员注册后到 date_end 之间
        max_issue = (date_end - max(m["register_date"], date_start)).days
        if max_issue < 1:
            continue
        offset = int(rng.integers(0, max_issue))
        issue_dt = datetime.combine(max(m["register_date"], date_start), datetime.min.time()) + timedelta(days=offset, hours=int(rng.integers(8, 22)))
        expire_dt = issue_dt + timedelta(days=valid_days)
        # 状态: 80% UNUSED, 20% EXPIRED (取决于 expire 是否过去)
        if expire_dt < datetime.combine(date_end, datetime.min.time()):
            status = "EXPIRED" if rng.random() < 0.7 else "UNUSED"
        else:
            status = "UNUSED"
        src = rng.choice(sources, p=src_p)

        rows.append((
            next_id, f"C{next_id:010d}", tpl[0], m["member_id"],
            issue_dt, expire_dt, src, status,
        ))
        next_id += 1
        if len(rows) >= batch_size:
            bulk_insert(conn, "fact_coupon_issued", cols, rows, batch_size)
            rows = []

    if rows:
        bulk_insert(conn, "fact_coupon_issued", cols, rows, batch_size)
