"""员工 / 排班 / 考勤"""

from datetime import date, datetime, timedelta, time
import numpy as np
from faker import Faker

from helpers.db import bulk_insert
from helpers.biz_calendar import daterange, is_weekend

faker = Faker("zh_CN")

# 每店标准岗位配置 (position_id -> 人数区间)
POSITION_HEADCOUNT = {
    1: (1, 1),   # 店长
    2: (1, 2),   # 副店长
    3: (3, 5),   # 收银员
    4: (5, 9),   # 后厨员
    5: (5, 8),   # 服务员
    6: (4, 7),   # 配送员
}


def gen_dim_employee(conn, stores_meta, date_start: date, rng: np.random.Generator):
    """生成员工 + 返回 employees_meta 供排班/考勤使用"""
    rows = []
    employees_meta = []
    eid = 1
    for s in stores_meta:
        for pos_id, (lo, hi) in POSITION_HEADCOUNT.items():
            n = int(rng.integers(lo, hi + 1))
            # 大店多招人, 小店少招
            for _ in range(n):
                gender = rng.choice(["男", "女"], p=[0.55, 0.45]) if pos_id != 5 else rng.choice(["男", "女"], p=[0.35, 0.65])
                if gender == "男":
                    name = faker.name_male()
                else:
                    name = faker.name_female()

                # 年龄: 店长35-50, 其他19-40
                if pos_id == 1:
                    age = int(rng.integers(32, 50))
                elif pos_id == 2:
                    age = int(rng.integers(28, 45))
                else:
                    age = int(rng.integers(19, 40))
                birth = date(date_start.year - age, int(rng.integers(1, 13)), int(rng.integers(1, 28)))

                id_card = f"{int(rng.integers(110000, 660000))}{birth.strftime('%Y%m%d')}{int(rng.integers(1000, 9999))}"
                id_card_masked = id_card[:6] + "********" + id_card[-4:]
                phone = f"1{rng.choice(['3','5','7','8','9'])}{int(rng.integers(0, 10**9)):09d}"

                # 入职日期: 店长基本是开店日, 其他在开店日前后/开店后陆续招
                if pos_id == 1:
                    hire = s["open_date"]
                elif pos_id == 2:
                    hire = s["open_date"] + timedelta(days=int(rng.integers(-30, 30)))
                else:
                    # 入职在开店日前 60 天 ~ 区间结束前
                    earliest = s["open_date"] - timedelta(days=60)
                    hire = earliest + timedelta(days=int(rng.integers(0, max(1, (date_start - earliest).days + 100))))

                # 5% 已离职
                leave = None
                status = "ACTIVE"
                if rng.random() < 0.06:
                    leave = hire + timedelta(days=int(rng.integers(60, 700)))
                    if leave < date_start:
                        # 区间前就离职 — 仍记录但状态INACTIVE
                        status = "INACTIVE"
                    else:
                        status = "INACTIVE" if leave < date.today() else "ACTIVE"

                # 薪资在岗位带宽内
                from generators.dimensions import POSITIONS
                pos_def = POSITIONS[pos_id - 1]
                salary_min, salary_max = pos_def[3], pos_def[4]
                salary = round(float(rng.uniform(salary_min, salary_max)), 0)

                code = f"E{eid:06d}"
                rows.append((
                    eid, code, name, gender, birth, id_card_masked, phone,
                    s["store_id"], pos_id, hire, leave, salary, status,
                ))
                employees_meta.append({
                    "employee_id": eid, "store_id": s["store_id"],
                    "position_id": pos_id, "hire_date": hire,
                    "leave_date": leave, "status": status,
                })
                eid += 1

    cols = ["employee_id", "employee_code", "name", "gender", "birth_date",
            "id_card_masked", "phone", "store_id", "position_id", "hire_date",
            "leave_date", "salary", "status"]
    bulk_insert(conn, "dim_employee", cols, rows)
    return employees_meta


# ============================================================
# 排班 + 考勤
# ============================================================
SHIFT_DEFS = {
    "EARLY":   (time(6, 0),  time(14, 0)),
    "MIDDLE":  (time(10, 0), time(18, 0)),
    "LATE":    (time(14, 0), time(22, 30)),
    "REST":    (None, None),
}


def gen_schedule_and_attendance(conn, employees_meta, stores_meta, date_start: date, date_end: date,
                                 rng: np.random.Generator, batch_size: int = 5000):
    """按月生成排班+考勤,流式入库以节省内存"""
    # 按 store_id 索引门店生命周期
    store_idx = {s["store_id"]: s for s in stores_meta}

    sched_buf = []
    att_buf = []
    sched_count = 0
    att_count = 0

    sched_cols = ["employee_id", "store_id", "date_key", "shift", "start_time", "end_time"]
    att_cols = ["employee_id", "store_id", "date_key", "clock_in", "clock_out", "status", "work_hours"]

    for d in daterange(date_start, date_end):
        date_key = int(d.strftime("%Y%m%d"))
        for emp in employees_meta:
            if emp["status"] == "INACTIVE" and emp["leave_date"] and d > emp["leave_date"]:
                continue
            if d < emp["hire_date"]:
                continue
            store = store_idx.get(emp["store_id"])
            if store is None:
                continue
            if d < store["open_date"]:
                continue
            if store["close_date"] and d > store["close_date"]:
                continue

            # 每周 5 天班 + 2 天休 (随机)
            shift_choice = rng.choice(["EARLY", "MIDDLE", "LATE", "REST"], p=[0.28, 0.28, 0.27, 0.17])
            start_t, end_t = SHIFT_DEFS[shift_choice]
            if start_t:
                start_dt = datetime.combine(d, start_t)
                end_dt = datetime.combine(d, end_t)
            else:
                start_dt = end_dt = None

            sched_buf.append((emp["employee_id"], emp["store_id"], date_key, shift_choice, start_dt, end_dt))

            # 考勤: 休息日跳过;否则按状态生成
            if shift_choice == "REST":
                pass
            else:
                # 95% 正常, 3% 迟到, 1% 早退, 0.5% 缺勤, 0.5% 请假
                r = rng.random()
                if r < 0.005:
                    status = "ABSENT"
                    ci = co = None
                    work = None
                elif r < 0.01:
                    status = "LEAVE"
                    ci = co = None
                    work = None
                elif r < 0.04:
                    status = "LATE"
                    delay = int(rng.integers(5, 40))
                    ci = start_dt + timedelta(minutes=delay)
                    co = end_dt + timedelta(minutes=int(rng.integers(-5, 15)))
                    work = round((co - ci).total_seconds() / 3600, 2)
                elif r < 0.05:
                    status = "EARLY_LEAVE"
                    ci = start_dt - timedelta(minutes=int(rng.integers(0, 10)))
                    co = end_dt - timedelta(minutes=int(rng.integers(20, 90)))
                    work = round((co - ci).total_seconds() / 3600, 2)
                else:
                    status = "NORMAL"
                    ci = start_dt - timedelta(minutes=int(rng.integers(0, 12)))
                    co = end_dt + timedelta(minutes=int(rng.integers(-3, 15)))
                    work = round((co - ci).total_seconds() / 3600, 2)
                att_buf.append((emp["employee_id"], emp["store_id"], date_key, ci, co, status, work))

            if len(sched_buf) >= batch_size:
                bulk_insert(conn, "fact_schedule", sched_cols, sched_buf, batch_size)
                sched_count += len(sched_buf)
                sched_buf = []
            if len(att_buf) >= batch_size:
                bulk_insert(conn, "fact_attendance", att_cols, att_buf, batch_size)
                att_count += len(att_buf)
                att_buf = []

    if sched_buf:
        bulk_insert(conn, "fact_schedule", sched_cols, sched_buf, batch_size)
        sched_count += len(sched_buf)
    if att_buf:
        bulk_insert(conn, "fact_attendance", att_cols, att_buf, batch_size)
        att_count += len(att_buf)

    return sched_count, att_count
