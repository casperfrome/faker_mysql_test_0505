"""CasPerFect 西式快餐连锁 模拟数据生成器 — 主入口

运行命令:
  "D:\\PythonVenv\\Scripts\\python.exe" gen_fake_data.py

可选参数:
  --orders N   覆盖 config.TARGET_ORDERS (用于小批量冒烟测试)
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime

# Windows 控制台默认 GBK,这里强制 UTF-8 以正常显示中文/特殊符号
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
from faker import Faker

import config
from helpers import db
from generators import dimensions, employees, members, orders, inventory


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--orders", type=int, default=None,
                   help="目标订单数 (覆盖 config.TARGET_ORDERS)")
    p.add_argument("--members", type=int, default=None,
                   help="会员数 (覆盖 config.MEMBER_BASE_COUNT)")
    p.add_argument("--skip-inventory", action="store_true",
                   help="跳过库存生成 (调试用)")
    return p.parse_args()


def main():
    args = parse_args()
    target_orders = args.orders or config.TARGET_ORDERS
    target_members = args.members or config.MEMBER_BASE_COUNT

    # 随机种子
    rng = np.random.default_rng(config.RANDOM_SEED)
    random.seed(config.RANDOM_SEED)
    Faker.seed(config.RANDOM_SEED)

    date_start = datetime.strptime(config.DATE_START, "%Y-%m-%d").date()
    date_end   = datetime.strptime(config.DATE_END,   "%Y-%m-%d").date()
    num_days = (date_end - date_start).days + 1

    print("=" * 64)
    print("CasPerFect 模拟数据生成器")
    print("=" * 64)
    print(f"目标库         : {config.DB_NAME}")
    print(f"日期范围       : {date_start} ~ {date_end} ({num_days} 天)")
    print(f"门店数         : {config.NUM_STORES}")
    print(f"会员数         : {target_members:,}")
    print(f"目标订单数     : {target_orders:,}")
    print(f"批量提交大小   : {config.BATCH_SIZE}")
    print("=" * 64)

    t0 = time.time()

    # ------------------------------------------------------------
    # Step 1: 重建数据库 + 建表
    # ------------------------------------------------------------
    print("\n[1/8] 重建数据库 + 执行 DDL …")
    db.recreate_database()
    conn = db.get_connection(use_db=True)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    db.exec_ddl_file(conn, schema_path)
    # 必须在 DDL 之后再禁用 FK 检查 (schema.sql 内部可能有 FK_CHECKS=1)
    db.disable_fk_checks(conn)
    print(f"     数据库 {config.DB_NAME} 创建完毕 ({time.time()-t0:.1f}s)")

    # ------------------------------------------------------------
    # Step 2: 维度数据
    # ------------------------------------------------------------
    print("\n[2/8] 生成维度数据 …")
    t = time.time()
    dimensions.gen_dim_date(conn, date_start, date_end)
    dimensions.gen_dim_city(conn)
    stores_meta = dimensions.gen_dim_store(conn, config.NUM_STORES, date_start, date_end, rng)
    dimensions.gen_static_dims(conn)
    products_meta = dimensions.gen_dim_product(conn, date_start, date_end, rng)
    coupon_templates = dimensions.gen_dim_coupon_template(conn)
    suppliers = dimensions.gen_dim_supplier(conn, date_start, rng)
    warehouses = dimensions.gen_dim_warehouse(conn)
    ingredients = dimensions.gen_dim_ingredient(conn, len(suppliers), rng)
    print(f"     维度表写入完毕 ({time.time()-t:.1f}s)")

    # ------------------------------------------------------------
    # Step 3: 员工 + 排班 + 考勤
    # ------------------------------------------------------------
    print("\n[3/8] 生成员工/排班/考勤 …")
    t = time.time()
    employees_meta = employees.gen_dim_employee(conn, stores_meta, date_start, rng)
    sched_n, att_n = employees.gen_schedule_and_attendance(
        conn, employees_meta, stores_meta, date_start, date_end, rng,
        batch_size=config.BATCH_SIZE,
    )
    print(f"     员工 {len(employees_meta):,} | 排班 {sched_n:,} | 考勤 {att_n:,} ({time.time()-t:.1f}s)")

    # ------------------------------------------------------------
    # Step 4: 会员主表
    # ------------------------------------------------------------
    print("\n[4/8] 生成会员主表 …")
    t = time.time()
    members_meta = members.gen_fact_member(
        conn, target_members, stores_meta, date_start, date_end, rng,
    )
    print(f"     会员 {len(members_meta):,} 行 ({time.time()-t:.1f}s)")

    # ------------------------------------------------------------
    # Step 5: 订单 + 明细 + 支付 + 券核销 + 积分
    # ------------------------------------------------------------
    print("\n[5/8] 生成订单/明细/支付/积分/券核销 (最耗时) …")
    t = time.time()
    # 根据目标订单数动态调整 base_daily 因子
    # 默认配置下,每店每日平均 ~135 → 50 × 336 × 135 ≈ 226 万
    # 目标 200 万 → 系数 0.88
    expected_default = config.NUM_STORES * num_days * 135 * 0.96  # 0.96 含爬坡/节假日折损
    scale = target_orders / expected_default
    for s in stores_meta:
        s["popularity"] = float(rng.uniform(0.75, 1.30)) * scale

    counts, member_stats = orders.gen_orders(
        conn, stores_meta, products_meta, members_meta, coupon_templates,
        date_start, date_end, rng,
        config.CHANNEL_RATIO, config.PAYMENT_RATIO,
        config.MEMBER_ORDER_RATIO, config.COUPON_USE_RATIO,
        batch_size=config.BATCH_SIZE,
    )
    print(f"     订单 {counts['orders']:,} | 明细 {counts['items']:,} | 支付 {counts['payments']:,}")
    print(f"     已用券 {counts['redeemed']:,} | 积分流水 {counts['points']:,} ({time.time()-t:.1f}s)")

    # ------------------------------------------------------------
    # Step 6: 补充未使用/过期券 + 回写会员统计
    # ------------------------------------------------------------
    print("\n[6/8] 补充券发放记录 + 回写会员累计 …")
    t = time.time()
    orders.gen_extra_issued_coupons(
        conn, members_meta, coupon_templates, date_start, date_end, rng,
        batch_size=config.BATCH_SIZE,
    )
    members.update_member_stats(conn, member_stats)
    print(f"     完毕 ({time.time()-t:.1f}s)")

    # ------------------------------------------------------------
    # Step 7: 库存 (出入库 + 月度盘点)
    # ------------------------------------------------------------
    if not args.skip_inventory:
        print("\n[7/8] 生成库存出入流水 + 月度盘点 …")
        t = time.time()
        inv_counts = inventory.gen_inventory(
            conn, stores_meta, ingredients, suppliers, warehouses,
            date_start, date_end, rng, batch_size=config.BATCH_SIZE,
        )
        print(f"     出入库 {inv_counts['io']:,} | 盘点 {inv_counts['check']:,} ({time.time()-t:.1f}s)")
    else:
        print("\n[7/8] 跳过库存生成 (--skip-inventory)")

    # ------------------------------------------------------------
    # Step 8: 自检 + 摘要
    # ------------------------------------------------------------
    print("\n[8/8] 数据自检 + 摘要 …")
    db.enable_fk_checks(conn)
    print_summary(conn)

    conn.close()
    print(f"\n✓ 全部完成,总耗时 {time.time()-t0:.1f}s")


def print_summary(conn):
    tables = [
        "dim_date", "dim_city", "dim_store", "dim_channel", "dim_payment_method",
        "dim_category", "dim_product", "dim_member_level", "dim_coupon_template",
        "dim_position", "dim_employee", "dim_supplier", "dim_warehouse", "dim_ingredient",
        "fact_member", "fact_order", "fact_order_item", "fact_payment",
        "fact_coupon_issued", "fact_coupon_redeemed", "fact_point_txn",
        "fact_schedule", "fact_attendance", "fact_inventory_io", "fact_inventory_check",
    ]
    print("\n  ┌─────────────────────────┬───────────────┐")
    print("  │ 表名                     │ 行数          │")
    print("  ├─────────────────────────┼───────────────┤")
    total = 0
    with conn.cursor() as cur:
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM `{t}`")
            n = cur.fetchone()[0]
            total += n
            print(f"  │ {t:<24}│ {n:>13,} │")
    print("  ├─────────────────────────┼───────────────┤")
    print(f"  │ 合计                     │ {total:>13,} │")
    print("  └─────────────────────────┴───────────────┘")

    print("\n  业务合理性自检:")
    with conn.cursor() as cur:
        cur.execute("SELECT SUM(actual_amount), AVG(actual_amount) FROM fact_order")
        s, a = cur.fetchone()
        print(f"    订单总流水    : ¥{float(s):,.2f}")
        print(f"    平均客单价    : ¥{float(a):,.2f}")

        cur.execute("""
            SELECT
              ROUND(AVG(CASE WHEN d.is_weekend=1 THEN cnt END), 1) AS weekend_avg,
              ROUND(AVG(CASE WHEN d.is_weekend=0 THEN cnt END), 1) AS weekday_avg
            FROM (
              SELECT date_key, COUNT(*) AS cnt FROM fact_order GROUP BY date_key
            ) o JOIN dim_date d ON d.date_key=o.date_key
        """)
        we, wd = cur.fetchone()
        if we and wd:
            print(f"    周末日均订单  : {float(we):,.0f} | 工作日: {float(wd):,.0f} | 比值 {float(we)/float(wd):.2f}")

        cur.execute("SELECT COUNT(*) FROM fact_order WHERE member_id IS NOT NULL")
        m_orders = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fact_order")
        all_orders = cur.fetchone()[0]
        if all_orders:
            print(f"    会员订单占比  : {m_orders/all_orders*100:.1f}%")

        cur.execute("SELECT COUNT(*) FROM fact_coupon_redeemed")
        used = cur.fetchone()[0]
        if all_orders:
            print(f"    券核销占比    : {used/all_orders*100:.1f}%")

        cur.execute("""
            SELECT d.season, COUNT(*) AS n FROM fact_order_item i
            JOIN fact_order o ON o.order_id=i.order_id
            JOIN dim_product p ON p.product_id=i.product_id
            JOIN dim_date d ON d.date_key=o.date_key
            WHERE p.is_cold=1
            GROUP BY d.season ORDER BY n DESC
        """)
        rows = cur.fetchall()
        print(f"    冷饮按季节销量: {dict(rows)}")


if __name__ == "__main__":
    sys.exit(main())
