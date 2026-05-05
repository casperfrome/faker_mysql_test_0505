"""维度表生成器"""

from datetime import date, datetime, timedelta
import random
import numpy as np
from faker import Faker

from helpers.db import bulk_insert
from helpers.biz_calendar import daterange, is_weekend, is_holiday, get_holiday_name, get_season

faker = Faker("zh_CN")


# ============================================================
# dim_date
# ============================================================
def gen_dim_date(conn, start: date, end: date):
    rows = []
    for d in daterange(start, end):
        date_key = int(d.strftime("%Y%m%d"))
        holiday_name = get_holiday_name(d)
        rows.append((
            date_key, d, d.year, (d.month - 1) // 3 + 1, d.month, d.day,
            d.isocalendar()[1], d.isoweekday(),
            1 if is_weekend(d) else 0,
            1 if is_holiday(d) else 0,
            holiday_name or None,
            get_season(d),
        ))
    cols = ["date_key", "full_date", "year", "quarter", "month", "day",
            "week_of_year", "weekday", "is_weekend", "is_holiday",
            "holiday_name", "season"]
    return bulk_insert(conn, "dim_date", cols, rows)


# ============================================================
# dim_city
# ============================================================
CITIES = [
    # (id, name, province, tier, region)
    (1,  "北京", "北京市",   "一线",   "华北"),
    (2,  "上海", "上海市",   "一线",   "华东"),
    (3,  "广州", "广东省",   "一线",   "华南"),
    (4,  "深圳", "广东省",   "一线",   "华南"),
    (5,  "杭州", "浙江省", "新一线", "华东"),
    (6,  "成都", "四川省", "新一线", "西南"),
    (7,  "武汉", "湖北省", "新一线", "华中"),
    (8,  "南京", "江苏省", "新一线", "华东"),
    (9,  "苏州", "江苏省", "新一线", "华东"),
    (10, "西安", "陕西省", "新一线", "西北"),
    (11, "天津", "天津市", "新一线", "华北"),
    (12, "重庆", "重庆市", "新一线", "西南"),
]


def gen_dim_city(conn):
    cols = ["city_id", "city_name", "province", "tier", "region"]
    return bulk_insert(conn, "dim_city", cols, CITIES)


# ============================================================
# dim_store
# ============================================================
BIZ_DISTRICTS = ["CBD", "社区", "校园", "交通枢纽", "旅游区", "商场"]
# 城市的店数权重 (北上广深多, 二线少)
CITY_STORE_DIST = {
    1: 8, 2: 9, 3: 5, 4: 5, 5: 4, 6: 4, 7: 3, 8: 3, 9: 3, 10: 2, 11: 2, 12: 2,
}  # sum=50

DISTRICTS_BY_CITY = {
    1:  ["朝阳区", "海淀区", "西城区", "东城区", "丰台区", "通州区"],
    2:  ["浦东新区", "黄浦区", "徐汇区", "静安区", "长宁区", "闵行区"],
    3:  ["天河区", "越秀区", "海珠区", "白云区", "番禺区"],
    4:  ["南山区", "福田区", "罗湖区", "宝安区", "龙华区"],
    5:  ["西湖区", "拱墅区", "上城区", "余杭区", "滨江区"],
    6:  ["锦江区", "武侯区", "高新区", "青羊区", "成华区"],
    7:  ["江汉区", "武昌区", "洪山区", "硚口区"],
    8:  ["鼓楼区", "建邺区", "玄武区", "秦淮区"],
    9:  ["姑苏区", "工业园区", "高新区", "吴中区"],
    10: ["雁塔区", "碑林区", "新城区"],
    11: ["和平区", "南开区", "河西区"],
    12: ["渝中区", "江北区", "南岸区"],
}


def gen_dim_store(conn, num_stores: int, date_start: date, date_end: date, rng: np.random.Generator):
    rows = []
    sid = 1
    stores_meta = []   # 返回供 orders 使用
    for city_id, n in CITY_STORE_DIST.items():
        for _ in range(n):
            district = rng.choice(DISTRICTS_BY_CITY[city_id])
            biz = rng.choice(BIZ_DISTRICTS, p=[0.25, 0.30, 0.10, 0.10, 0.10, 0.15])
            area = round(float(rng.uniform(80, 350)), 1)
            seats = int(rng.integers(20, 80))

            # 大约 30% 的店在区间内开业(新店), 4% 在区间内关店
            r = rng.random()
            if r < 0.30:
                # 新店: 在区间前 70% 内某天开业
                offset = int(rng.integers(0, int((date_end - date_start).days * 0.7)))
                open_date = date_start + timedelta(days=offset)
                close_date = None
                status = "OPEN"
            elif r < 0.34:
                # 在区间内关店: 以前开的, 区间内某天关
                open_date = date_start - timedelta(days=int(rng.integers(180, 1500)))
                close_offset = int(rng.integers(60, (date_end - date_start).days - 30))
                close_date = date_start + timedelta(days=close_offset)
                status = "CLOSED"
            else:
                # 老店
                open_date = date_start - timedelta(days=int(rng.integers(180, 2000)))
                close_date = None
                status = "OPEN"

            store_code = f"SH{sid:04d}"
            store_name = f"CasPerFect-{district}{biz}店"
            address = faker.street_address()
            manager = faker.name()
            phone = faker.phone_number()

            rows.append((
                sid, store_code, store_name, city_id, district, address,
                biz, area, seats, open_date, close_date, status, manager, phone,
            ))
            stores_meta.append({
                "store_id": sid, "city_id": city_id, "biz_district": biz,
                "open_date": open_date, "close_date": close_date,
                "is_delivery_zone": biz in ("CBD", "社区", "商场", "校园"),
            })
            sid += 1

    cols = ["store_id", "store_code", "store_name", "city_id", "district", "address",
            "biz_district", "area_sqm", "seats", "open_date", "close_date", "status",
            "manager_name", "phone"]
    bulk_insert(conn, "dim_store", cols, rows)
    return stores_meta


# ============================================================
# dim_channel / dim_payment_method / dim_category / dim_member_level / dim_position
# ============================================================
CHANNELS = [
    (1, "DINE_IN",  "堂食",        0, 0.0),
    (2, "TAKEOUT",  "自取",        0, 0.0),
    (3, "MEITUAN",  "美团外卖",   1, 0.18),
    (4, "ELEME",    "饿了么外卖", 1, 0.16),
]
PAYMENT_METHODS = [
    (1, "WECHAT", "微信支付", 1),
    (2, "ALIPAY", "支付宝",   1),
    (3, "MEMBER", "会员储值", 0),
    (4, "CARD",   "银行卡",   1),
    (5, "CASH",   "现金",     0),
]
CATEGORIES = [
    (1, "BURGER",   "汉堡",   1),
    (2, "CHICKEN",  "鸡肉",   2),
    (3, "SIDE",     "小食",   3),
    (4, "DRINK",    "饮料",   4),
    (5, "COMBO",    "套餐",   5),
    (6, "BREAKFAST", "早餐",  6),
    (7, "DESSERT",  "甜品",   7),
    (8, "KIDS",     "儿童餐", 8),
]
MEMBER_LEVELS = [
    (1, "REGULAR", "普通会员", 1.0,    1.0,     0),
    (2, "SILVER",  "银卡会员", 0.95,   1.5,  1000),
    (3, "GOLD",    "金卡会员", 0.90,   2.0,  5000),
    (4, "DIAMOND", "钻石会员", 0.85,   3.0, 20000),
]
POSITIONS = [
    (1, "MANAGER",     "店长",     8000, 15000, 1),
    (2, "ASS_MANAGER", "副店长",   6000, 10000, 1),
    (3, "CASHIER",     "收银员",   4000,  6500, 0),
    (4, "KITCHEN",     "后厨员",   4500,  7500, 0),
    (5, "WAITER",      "服务员",   3800,  5800, 0),
    (6, "RIDER",       "配送员",   5000,  9000, 0),
]


def gen_static_dims(conn):
    bulk_insert(conn, "dim_channel",
                ["channel_id", "channel_code", "channel_name", "is_delivery", "commission_rate"], CHANNELS)
    bulk_insert(conn, "dim_payment_method",
                ["payment_id", "payment_code", "payment_name", "is_third_party"], PAYMENT_METHODS)
    bulk_insert(conn, "dim_category",
                ["category_id", "category_code", "category_name", "sort_order"], CATEGORIES)
    bulk_insert(conn, "dim_member_level",
                ["level_id", "level_code", "level_name", "discount_rate", "point_rate", "upgrade_amount"],
                MEMBER_LEVELS)
    bulk_insert(conn, "dim_position",
                ["position_id", "position_code", "position_name", "salary_min", "salary_max", "is_management"],
                POSITIONS)


# ============================================================
# dim_product
# ============================================================
PRODUCT_SEEDS = [
    # (cat_id, name, price, cost, is_combo, is_cold, is_hot, is_signature)
    (1, "经典芝士汉堡",   28.00, 8.50, 0, 0, 0, 1),
    (1, "双层牛肉堡",     35.00, 11.0, 0, 0, 0, 1),
    (1, "培根鸡腿堡",     32.00, 10.0, 0, 0, 0, 0),
    (1, "深海鳕鱼堡",     30.00, 9.50, 0, 0, 0, 0),
    (1, "辣翅炸鸡堡",     31.00, 10.0, 0, 0, 0, 0),
    (1, "黑椒安格斯堡",   42.00, 14.0, 0, 0, 0, 1),
    (1, "BBQ 烟熏堡",     36.00, 11.5, 0, 0, 0, 0),
    (1, "蔬菜素汉堡",     22.00, 6.50, 0, 0, 0, 0),
    (1, "经典原味汉堡",   25.00, 7.50, 0, 0, 0, 0),
    (2, "黄金炸鸡(2 块)", 22.00, 6.50, 0, 0, 0, 1),
    (2, "辣味炸鸡(2 块)", 23.00, 6.50, 0, 0, 0, 0),
    (2, "全家桶(8 块)",   88.00, 26.0, 0, 0, 0, 1),
    (2, "鸡米花(中)",     16.00, 4.50, 0, 0, 0, 0),
    (2, "奥尔良烤翅",     18.00, 5.50, 0, 0, 0, 0),
    (2, "脆皮鸡腿",       15.00, 4.50, 0, 0, 0, 0),
    (3, "黄金薯条(中)",   12.00, 2.50, 0, 0, 0, 1),
    (3, "黄金薯条(大)",   16.00, 3.50, 0, 0, 0, 0),
    (3, "薯格",           14.00, 3.20, 0, 0, 0, 0),
    (3, "洋葱圈",         15.00, 3.50, 0, 0, 0, 0),
    (3, "鸡块(6 块)",     18.00, 4.50, 0, 0, 0, 0),
    (3, "玉米浓汤",       10.00, 2.00, 0, 0, 1, 0),
    (3, "蔬菜沙拉",       14.00, 3.50, 0, 0, 0, 0),
    (3, "凯撒沙拉",       18.00, 4.50, 0, 0, 0, 0),
    (4, "可口可乐(中)",    9.00, 1.50, 0, 1, 0, 0),
    (4, "可口可乐(大)",   12.00, 2.00, 0, 1, 0, 0),
    (4, "雪碧(中)",        9.00, 1.50, 0, 1, 0, 0),
    (4, "美年达(中)",      9.00, 1.50, 0, 1, 0, 0),
    (4, "冰红茶",          9.00, 1.30, 0, 1, 0, 0),
    (4, "鲜榨橙汁",       16.00, 4.50, 0, 1, 0, 0),
    (4, "美式咖啡(热)",   16.00, 3.50, 0, 0, 1, 1),
    (4, "美式咖啡(冰)",   16.00, 3.50, 0, 1, 0, 0),
    (4, "拿铁(热)",       20.00, 4.50, 0, 0, 1, 1),
    (4, "拿铁(冰)",       22.00, 4.50, 0, 1, 0, 0),
    (4, "卡布奇诺",       20.00, 4.50, 0, 0, 1, 0),
    (4, "热巧克力",       18.00, 4.00, 0, 0, 1, 0),
    (4, "原味奶昔",       18.00, 4.50, 0, 1, 0, 0),
    (4, "草莓奶昔",       20.00, 5.00, 0, 1, 0, 0),
    (4, "矿泉水",          5.00, 0.80, 0, 0, 0, 0),
    (4, "豆浆(热)",        7.00, 1.20, 0, 0, 1, 0),
    (5, "经典单人套餐",    38.00, 12.0, 1, 0, 0, 1),
    (5, "双层牛肉套餐",    45.00, 15.0, 1, 0, 0, 0),
    (5, "炸鸡双人套餐",    78.00, 25.0, 1, 0, 0, 1),
    (5, "全家欢享套餐",   158.00, 50.0, 1, 0, 0, 1),
    (5, "学生超值套餐",    25.00, 8.00, 1, 0, 0, 0),
    (5, "工作日午市套餐",  32.00, 11.0, 1, 0, 0, 0),
    (5, "深夜小食套餐",    36.00, 11.5, 1, 0, 0, 0),
    (5, "三人聚餐套餐",   118.00, 38.0, 1, 0, 0, 0),
    (6, "早餐火腿堡套餐",  18.00, 5.50, 1, 0, 0, 1),
    (6, "早餐培根堡",      14.00, 4.50, 0, 0, 0, 0),
    (6, "饭团套餐",        16.00, 4.80, 1, 0, 0, 0),
    (6, "中式皮蛋瘦肉粥",  10.00, 2.50, 0, 0, 1, 0),
    (6, "豆浆油条套餐",    12.00, 3.20, 1, 0, 1, 0),
    (6, "蛋堡套餐",        15.00, 4.20, 1, 0, 0, 0),
    (6, "鸡蛋三明治",      11.00, 3.00, 0, 0, 0, 0),
    (7, "焦糖布丁",        12.00, 3.50, 0, 0, 0, 0),
    (7, "提拉米苏",        18.00, 5.50, 0, 0, 0, 0),
    (7, "巧克力布朗尼",    14.00, 4.20, 0, 0, 0, 0),
    (7, "草莓圣代",        12.00, 3.20, 0, 1, 0, 0),
    (7, "巧克力圣代",      12.00, 3.20, 0, 1, 0, 0),
    (7, "原味甜筒",         5.00, 1.20, 0, 1, 0, 0),
    (7, "蛋挞",             8.00, 1.80, 0, 0, 1, 1),
    (7, "焦糖玛奇朵蛋糕",  16.00, 4.80, 0, 0, 0, 0),
    (8, "儿童欢乐套餐 A",  35.00, 11.0, 1, 0, 0, 1),
    (8, "儿童欢乐套餐 B",  38.00, 12.0, 1, 0, 0, 0),
    (8, "儿童鸡块餐",      22.00, 7.00, 1, 0, 0, 0),
    (8, "儿童牛奶套餐",    18.00, 5.50, 1, 0, 0, 0),
]


def gen_dim_product(conn, date_start: date, date_end: date, rng: np.random.Generator):
    rows = []
    products_meta = []
    for i, p in enumerate(PRODUCT_SEEDS, start=1):
        cat, name, price, cost, is_combo, is_cold, is_hot, is_sig = p
        # 每个产品在区间前 1-3 年的某天上架, 少数在区间内上架
        avail_from = date_start - timedelta(days=int(rng.integers(60, 1000)))
        if rng.random() < 0.10:
            avail_from = date_start + timedelta(days=int(rng.integers(0, 200)))
        avail_to = None
        status = "ON_SHELF"
        if rng.random() < 0.05:
            avail_to = date_start + timedelta(days=int(rng.integers(50, 320)))
            status = "OFF_SHELF"
        code = f"P{i:04d}"
        rows.append((
            i, code, name, cat, price, cost, is_combo, is_cold, is_hot, is_sig,
            avail_from, avail_to, status,
        ))
        products_meta.append({
            "product_id": i, "name": name, "category_id": cat,
            "price": price, "cost": cost, "is_combo": is_combo,
            "is_cold": is_cold, "is_hot": is_hot, "is_signature": is_sig,
            "available_from": avail_from, "available_to": avail_to,
        })
    cols = ["product_id", "product_code", "product_name", "category_id", "price", "cost",
            "is_combo", "is_cold", "is_hot", "is_signature",
            "available_from", "available_to", "status"]
    bulk_insert(conn, "dim_product", cols, rows)
    return products_meta


# ============================================================
# dim_coupon_template
# ============================================================
COUPON_TEMPLATES = [
    # (code, name, type, face_value, discount_rate, min_amount, valid_days)
    ("NEW_USER_15",  "新人立减 15 元",        "NEW_USER",   15, None,  30, 30),
    ("CASH_5_30",    "满 30 减 5",            "CASH",        5, None,  30, 60),
    ("CASH_10_50",   "满 50 减 10",           "CASH",       10, None,  50, 60),
    ("CASH_20_100",  "满 100 减 20",          "CASH",       20, None, 100, 30),
    ("CASH_30_150",  "满 150 减 30",          "CASH",       30, None, 150, 30),
    ("DISC_88",      "8.8 折券",              "DISCOUNT",    0, 0.88,  30, 60),
    ("DISC_75",      "7.5 折券",              "DISCOUNT",    0, 0.75,  50, 30),
    ("FREE_FRIES",   "免费薯条(中)券",        "FREE_ITEM",  12, None,   0, 60),
    ("FREE_DRINK",   "免费可乐(中)券",        "FREE_ITEM",   9, None,   0, 60),
    ("BIRTHDAY_30",  "生日专享 30 元",        "CASH",       30, None,  60, 30),
    ("WEEKEND_8",    "周末专享 8 元",         "CASH",        8, None,  40, 14),
    ("BREAKFAST_5",  "早餐专享 5 元",         "CASH",        5, None,  15,  7),
    ("RECALL_20",    "流失召回 20 元",        "CASH",       20, None,  40, 14),
    ("VIP_DAY_50",   "会员日满 100 减 50",   "CASH",       50, None, 100,  3),
    ("INVITE_10",    "邀请好友 10 元",        "CASH",       10, None,  30, 30),
]


def gen_dim_coupon_template(conn):
    rows = []
    for i, t in enumerate(COUPON_TEMPLATES, start=1):
        code, name, ctype, face, disc, min_amt, valid = t
        desc = name
        rows.append((i, code, name, ctype, face, disc, min_amt, valid, desc))
    cols = ["template_id", "template_code", "template_name", "coupon_type",
            "face_value", "discount_rate", "min_order_amount", "valid_days", "description"]
    bulk_insert(conn, "dim_coupon_template", cols, rows)
    return rows


# ============================================================
# dim_supplier / dim_warehouse / dim_ingredient
# ============================================================
SUPPLIER_SEEDS = [
    ("肉类", "正大食品", "华北中央"),
    ("肉类", "双汇集团", "华中"),
    ("肉类", "雨润食品", "华东"),
    ("肉类", "凤祥食品", "山东"),
    ("面包", "曼可顿烘焙", "华东"),
    ("面包", "桃李面包", "全国"),
    ("面包", "宾堡烘焙", "华南"),
    ("蔬菜", "本地蔬菜联盟", "区域"),
    ("蔬菜", "山姆生鲜直供", "华东"),
    ("饮料", "可口可乐(中国)", "全国"),
    ("饮料", "百事可乐(中国)", "全国"),
    ("饮料", "蒙牛乳业", "全国"),
    ("饮料", "伊利股份", "全国"),
    ("调味", "李锦记", "华南"),
    ("调味", "海天味业", "华南"),
    ("包材", "美包包装", "华东"),
    ("包材", "环球纸业", "华东"),
    ("油料", "金龙鱼粮油", "全国"),
    ("冷冻", "圣农冷链", "福建"),
    ("综合", "美菜网食材", "全国"),
]


def gen_dim_supplier(conn, date_start: date, rng: np.random.Generator):
    rows = []
    for i, s in enumerate(SUPPLIER_SEEDS, start=1):
        cat, name, region = s
        code = f"SUP{i:03d}"
        contact = faker.name()
        phone = faker.phone_number()
        addr = faker.address().replace("\n", " ")
        coop = date_start - timedelta(days=int(rng.integers(180, 2000)))
        rows.append((i, code, name, cat, contact, phone, addr, coop))
    cols = ["supplier_id", "supplier_code", "supplier_name", "category",
            "contact_name", "phone", "address", "cooperation_since"]
    bulk_insert(conn, "dim_supplier", cols, rows)
    return rows


def gen_dim_warehouse(conn):
    rows = [
        (1, "WH_CENTRAL", "全国总仓(上海)",  2, 1),
        (2, "WH_NORTH",   "华北区域仓(北京)", 1, 0),
        (3, "WH_SOUTH",   "华南区域仓(广州)", 3, 0),
        (4, "WH_WEST",    "西部区域仓(成都)", 6, 0),
        (5, "WH_CENTRAL2","华中区域仓(武汉)", 7, 0),
        (6, "WH_EAST",    "华东区域仓(杭州)", 5, 0),
    ]
    cols = ["warehouse_id", "warehouse_code", "warehouse_name", "city_id", "is_central"]
    bulk_insert(conn, "dim_warehouse", cols, rows)
    return rows


INGREDIENT_SEEDS = [
    # (name, unit, category, unit_cost, shelf_days)
    ("牛肉饼 (90g)",      "片",  "肉类", 3.20,   3),
    ("鸡腿肉",             "kg",  "肉类", 28.0,   2),
    ("鸡胸肉",             "kg",  "肉类", 32.0,   2),
    ("鸡翅",               "kg",  "肉类", 35.0,   2),
    ("培根",               "kg",  "肉类", 45.0,   7),
    ("火腿片",             "kg",  "肉类", 38.0,   7),
    ("鳕鱼柳",             "kg",  "肉类", 55.0,   3),
    ("汉堡胚 (大)",        "个",  "面包", 1.20,   2),
    ("汉堡胚 (小)",        "个",  "面包", 0.90,   2),
    ("芝麻汉堡胚",         "个",  "面包", 1.40,   2),
    ("热狗胚",             "个",  "面包", 1.10,   2),
    ("帕尼尼面包",         "个",  "面包", 1.80,   3),
    ("生菜",               "kg",  "蔬菜", 6.00,   3),
    ("番茄",               "kg",  "蔬菜", 5.00,   5),
    ("洋葱",               "kg",  "蔬菜", 3.00,  14),
    ("酸黄瓜",             "kg",  "蔬菜", 12.0,  60),
    ("土豆",               "kg",  "蔬菜", 2.50,  30),
    ("玉米粒",             "kg",  "蔬菜", 8.50,  60),
    ("沙拉混合菜",         "kg",  "蔬菜", 18.0,   3),
    ("可口可乐糖浆",       "L",   "饮料", 12.0, 180),
    ("雪碧糖浆",           "L",   "饮料", 12.0, 180),
    ("鲜橙汁原液",         "L",   "饮料", 22.0,  30),
    ("咖啡豆 (阿拉比卡)",  "kg",  "饮料", 95.0, 180),
    ("浓缩咖啡液",         "L",   "饮料", 35.0,  30),
    ("纯牛奶",             "L",   "饮料",  6.50,  7),
    ("淡奶油",             "L",   "饮料", 28.0,  30),
    ("矿泉水 (550ml)",     "瓶",  "饮料",  1.20, 360),
    ("冰红茶浓缩液",       "L",   "饮料", 18.0, 180),
    ("番茄酱 (小包)",      "包",  "调味", 0.18, 360),
    ("沙拉酱",             "L",   "调味", 22.0,  60),
    ("黑胡椒",             "kg",  "调味", 60.0, 360),
    ("食盐",               "kg",  "调味", 4.50, 720),
    ("食用油",             "L",   "油料", 9.00, 360),
    ("白砂糖",             "kg",  "调味", 6.50, 360),
    ("奶油 (烘焙)",        "kg",  "调味", 35.0,  30),
    ("芝士片",             "kg",  "调味", 65.0,  30),
    ("巧克力酱",           "L",   "调味", 28.0, 180),
    ("草莓酱",             "L",   "调味", 26.0,  90),
    ("纸杯 (中)",          "个",  "包材", 0.15, 999),
    ("纸杯 (大)",          "个",  "包材", 0.22, 999),
    ("打包盒 (汉堡)",      "个",  "包材", 0.30, 999),
    ("打包袋 (大)",        "个",  "包材", 0.18, 999),
    ("吸管",               "个",  "包材", 0.05, 999),
    ("纸巾",               "包",  "包材", 0.08, 999),
    ("一次性餐具",         "套",  "包材", 0.25, 999),
    ("打包袋 (小)",        "个",  "包材", 0.12, 999),
    ("饭团米饭",           "kg",  "面包", 6.50,   2),
    ("油条原料",           "kg",  "面包", 5.50,   3),
    ("豆浆粉",             "kg",  "饮料", 22.0, 360),
    ("速冻薯条 (粗)",      "kg",  "冷冻", 16.0, 180),
    ("速冻鸡块",           "kg",  "冷冻", 22.0, 180),
    ("速冻洋葱圈",         "kg",  "冷冻", 18.0, 180),
    ("速冻薯格",           "kg",  "冷冻", 17.0, 180),
    ("冰淇淋液",           "L",   "冷冻", 28.0, 180),
    ("巧克力豆",           "kg",  "冷冻", 32.0, 180),
    ("草莓 (冷冻)",        "kg",  "冷冻", 24.0, 180),
    ("布丁粉",             "kg",  "调味", 28.0, 360),
    ("蛋挞皮",             "个",  "面包", 0.55,  60),
    ("提拉米苏底料",       "kg",  "面包", 38.0,  30),
    ("面粉",               "kg",  "面包",  4.50, 180),
    ("酵母",               "kg",  "调味", 32.0, 360),
    ("芝麻",               "kg",  "调味", 28.0, 360),
    ("饮料杯盖",           "个",  "包材", 0.06, 999),
    ("外卖封口贴",         "张",  "包材", 0.04, 999),
    ("玉米脆筒",           "个",  "面包", 0.80,  60),
    ("炸鸡裹粉",           "kg",  "调味", 14.0, 360),
    ("鸡蛋",               "个",  "肉类", 0.90,  30),
    ("豆腐",               "kg",  "蔬菜",  6.0,   5),
    ("胡椒粉",             "kg",  "调味", 80.0, 360),
    ("酱油",               "L",   "调味", 18.0, 360),
    ("蚝油",               "L",   "调味", 22.0, 360),
    ("辣椒粉",             "kg",  "调味", 35.0, 360),
    ("孜然粉",             "kg",  "调味", 50.0, 360),
    ("奥尔良腌料",         "kg",  "调味", 30.0, 360),
    ("BBQ 酱",             "L",   "调味", 28.0, 180),
    ("蜂蜜芥末酱",         "L",   "调味", 32.0, 180),
    ("番茄火锅底",         "kg",  "调味", 15.0, 180),
    ("速冻鸡米花",         "kg",  "冷冻", 25.0, 180),
    ("速冻鳕鱼柳",         "kg",  "冷冻", 48.0, 180),
    ("生菜叶 (洗净)",       "kg",  "蔬菜", 9.00,  3),
    ("黄瓜",               "kg",  "蔬菜",  4.50, 7),
]


def gen_dim_ingredient(conn, supplier_count: int, rng: np.random.Generator):
    rows = []
    for i, ing in enumerate(INGREDIENT_SEEDS, start=1):
        name, unit, cat, cost, shelf = ing
        code = f"ING{i:04d}"
        sup_id = int(rng.integers(1, supplier_count + 1))
        rows.append((i, code, name, unit, cat, cost, shelf, sup_id))
    cols = ["ingredient_id", "ingredient_code", "ingredient_name", "unit",
            "category", "unit_cost", "shelf_life_days", "default_supplier_id"]
    bulk_insert(conn, "dim_ingredient", cols, rows)
    return rows
