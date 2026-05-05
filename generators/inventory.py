"""库存出入流水 + 月度盘点

简化模型:
- 每日按门店销量反推主要食材出库 (OUT_SALE)
- 每周一/四从供应商入库一次 (IN_PURCHASE)
- 每月末做盘点 (fact_inventory_check)
- 每店每月 ~3% 概率某 SKU 报损 (OUT_LOSS)
"""

from datetime import date, datetime, timedelta
import calendar
import numpy as np

from helpers.db import bulk_insert, BATCH_SIZE
from helpers.biz_calendar import daterange


def gen_inventory(conn, stores_meta, ingredients, suppliers, warehouses,
                  date_start: date, date_end: date, rng: np.random.Generator,
                  store_daily_orders=None, batch_size: int = BATCH_SIZE):
    """
    store_daily_orders: dict[(store_id, date_key)] -> n_orders, 用于反推用量;
                        若为 None 则均匀估算 100 单/天.
    """
    io_buf = []
    chk_buf = []
    io_cols = ["store_id", "ingredient_id", "date_key", "io_time", "io_type",
               "quantity", "unit_cost", "total_cost", "supplier_id",
               "warehouse_id", "remark"]
    chk_cols = ["store_id", "ingredient_id", "date_key", "book_qty", "actual_qty",
                "diff_qty", "loss_amount"]

    counts = {"io": 0, "check": 0}

    def flush(force=False):
        if force or len(io_buf) >= batch_size:
            if io_buf:
                bulk_insert(conn, "fact_inventory_io", io_cols, io_buf, batch_size)
                counts["io"] += len(io_buf)
                io_buf.clear()
        if force or len(chk_buf) >= batch_size:
            if chk_buf:
                bulk_insert(conn, "fact_inventory_check", chk_cols, chk_buf, batch_size)
                counts["check"] += len(chk_buf)
                chk_buf.clear()

    # 选 30 个核心食材做高频流水 (避免行数爆炸)
    core_ingredients = ingredients[:30]
    # 仓库分配: 简化按 city 分配
    wh_by_city = {w[3]: w[0] for w in warehouses}
    central_wh = next((w[0] for w in warehouses if w[4] == 1), warehouses[0][0])

    # 库存账面 (内存)
    book = {}   # (store_id, ing_id) -> qty

    for s in stores_meta:
        sid = s["store_id"]
        for ing in core_ingredients:
            book[(sid, ing[0])] = float(rng.uniform(20, 100))

    from tqdm import tqdm
    days = list(daterange(date_start, date_end))
    for d in tqdm(days, desc="生成库存"):
        date_key = int(d.strftime("%Y%m%d"))
        for s in stores_meta:
            sid = s["store_id"]
            if d < s["open_date"]:
                continue
            if s["close_date"] and d > s["close_date"]:
                continue

            # 估算今日订单量
            n_orders = 100 if store_daily_orders is None else store_daily_orders.get((sid, date_key), 0)
            if n_orders == 0:
                continue

            # 出库: 每店每日仅记录 5-10 个核心食材的出库 (而非全部 30,避免行数过多)
            sample_size = int(rng.integers(5, 11))
            sampled = rng.choice(len(core_ingredients), size=sample_size, replace=False)
            for idx in sampled:
                ing = core_ingredients[idx]
                ing_id = ing[0]
                # 用量正比订单量 + 噪声
                qty = round(n_orders * float(rng.uniform(0.02, 0.10)) + float(rng.uniform(0.5, 3)), 3)
                cost = float(ing[5])
                total = round(qty * cost, 2)
                book[(sid, ing_id)] = book.get((sid, ing_id), 0) - qty
                io_buf.append((sid, ing_id, date_key,
                               datetime.combine(d, datetime.min.time()) + timedelta(hours=int(rng.integers(11, 22))),
                               "OUT_SALE", qty, cost, total, None, None, "销售消耗"))

            # 入库 (周一/周四)
            if d.weekday() in (0, 3):
                wh_id = wh_by_city.get(s["city_id"], central_wh)
                for idx in sampled[:int(rng.integers(3, 7))]:
                    ing = core_ingredients[idx]
                    ing_id = ing[0]
                    qty_in = round(float(rng.uniform(20, 80)), 3)
                    cost = float(ing[5]) * float(rng.uniform(0.95, 1.05))
                    total = round(qty_in * cost, 2)
                    book[(sid, ing_id)] = book.get((sid, ing_id), 0) + qty_in
                    sup_id = ing[7] if ing[7] else int(rng.integers(1, len(suppliers) + 1))
                    io_buf.append((sid, ing_id, date_key,
                                   datetime.combine(d, datetime.min.time()) + timedelta(hours=int(rng.integers(7, 11))),
                                   "IN_PURCHASE", qty_in, round(cost, 4), total,
                                   sup_id, wh_id, "周期采购入库"))

            # 偶发损耗 (~3% 概率)
            if rng.random() < 0.03:
                ing = core_ingredients[int(rng.integers(0, len(core_ingredients)))]
                ing_id = ing[0]
                loss_qty = round(float(rng.uniform(0.5, 5)), 3)
                cost = float(ing[5])
                book[(sid, ing_id)] = book.get((sid, ing_id), 0) - loss_qty
                io_buf.append((sid, ing_id, date_key,
                               datetime.combine(d, datetime.min.time()) + timedelta(hours=22),
                               "OUT_LOSS", loss_qty, cost, round(loss_qty * cost, 2),
                               None, None, "过期/损耗"))

            # 月末盘点
            last_day = calendar.monthrange(d.year, d.month)[1]
            if d.day == last_day:
                for ing in core_ingredients:
                    ing_id = ing[0]
                    book_q = round(book.get((sid, ing_id), 0), 3)
                    # 实盘比账面少 0-2%
                    actual_q = round(book_q * float(rng.uniform(0.98, 1.005)), 3)
                    diff = round(actual_q - book_q, 3)
                    loss = round(abs(diff) * float(ing[5]), 2) if diff < 0 else 0.0
                    chk_buf.append((sid, ing_id, date_key, book_q, actual_q, diff, loss))
                    # 盘点后账面对齐实盘
                    book[(sid, ing_id)] = actual_q

            flush()

    flush(force=True)
    return counts
