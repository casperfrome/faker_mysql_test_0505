# CasPerFect 模拟数据生成器

为西式快餐连锁品牌 **CasPerFect** 生成完整的业务仿真数据，写入 MySQL 数据库，供数据分析、BI 报表、数据仓库开发等场景使用。

默认配置下可生成约 **200 万订单**、**10 万会员**、**50 家门店**，覆盖 ~11 个月的经营数据。

---

## 功能特性

- **完整星型模型**：14 张维度表 + 11 张事实表，含外键约束
- **业务仿真**：节假日效应、周末效应、冷热饮季节性、新店爬坡/衰退期
- **多渠道**：堂食 / 自取 / 美团 / 饿了么，支付方式含微信、支付宝、会员储值等
- **会员体系**：等级折扣、积分流水、优惠券发放与核销
- **人力模块**：员工维度、排班表、考勤表
- **供应链模块**：食材 SKU、供应商、仓库、库存出入流水、月度盘点
- **可复现**：固定随机种子，生成结果完全一致
- **可调规模**：命令行参数覆盖订单数/会员数，支持小批量冒烟测试

---

## 数据库表结构

### 维度表

| 表名 | 说明 |
|------|------|
| `dim_date` | 日期维度（节假日、季节、周末标志） |
| `dim_city` | 城市（城市等级、所属大区） |
| `dim_store` | 门店（地址、商圈类型、营业状态） |
| `dim_channel` | 销售渠道 |
| `dim_payment_method` | 支付方式 |
| `dim_category` | 菜品分类 |
| `dim_product` | 菜品 SKU（冷饮/热饮/套餐标志） |
| `dim_member_level` | 会员等级（折扣率、积分倍率） |
| `dim_coupon_template` | 优惠券模板（满减/折扣/免单/新客） |
| `dim_position` | 员工岗位 |
| `dim_employee` | 员工维度 |
| `dim_supplier` | 供应商 |
| `dim_warehouse` | 仓库 |
| `dim_ingredient` | 食材 SKU |

### 事实表

| 表名 | 说明 |
|------|------|
| `fact_member` | 会员主表（累计消费、积分、钱包余额） |
| `fact_order` | 订单头（渠道、会员、金额、状态） |
| `fact_order_item` | 订单明细 |
| `fact_payment` | 支付流水 |
| `fact_coupon_issued` | 优惠券发放记录 |
| `fact_coupon_redeemed` | 优惠券核销记录 |
| `fact_point_txn` | 积分流水（获取/消费/过期/调整） |
| `fact_schedule` | 员工排班 |
| `fact_attendance` | 员工考勤 |
| `fact_inventory_io` | 库存出入流水 |
| `fact_inventory_check` | 月度盘点 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置数据库

```bash
cp config.example.py config.py
```

编辑 `config.py`，填入 MySQL 连接信息：

```python
MYSQL = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "your_password_here",
    "charset": "utf8mb4",
}
```

### 3. 运行生成器

```bash
python gen_fake_data.py
```

生成过程分 8 步，完整运行约需数分钟（取决于机器性能）：

```
[1/8] 重建数据库 + 执行 DDL
[2/8] 生成维度数据
[3/8] 生成员工/排班/考勤
[4/8] 生成会员主表
[5/8] 生成订单/明细/支付/积分/券核销
[6/8] 补充券发放记录 + 回写会员累计
[7/8] 生成库存出入流水 + 月度盘点
[8/8] 数据自检 + 摘要
```

---

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--orders N` | 覆盖目标订单数（冒烟测试用） | `--orders 10000` |
| `--members N` | 覆盖会员数 | `--members 1000` |
| `--skip-inventory` | 跳过库存生成（加速调试） | |

**冒烟测试示例**（约 1 万订单，秒级完成）：

```bash
python gen_fake_data.py --orders 10000 --members 500 --skip-inventory
```

---

## 默认配置参数

| 参数 | 默认值 |
|------|--------|
| 数据库名 | `CasPerFect_260505` |
| 日期范围 | 2025-06-04 ~ 2026-05-05（约 11 个月） |
| 门店数 | 50 |
| 菜品数 | 90 |
| 目标订单数 | 200 万 |
| 会员数 | 10 万 |
| 批量提交大小 | 5000 |
| 随机种子 | 20260505 |

渠道占比：堂食 45% / 自取 10% / 美团 30% / 饿了么 15%

支付方式：微信 45% / 支付宝 30% / 会员储值 12% / 银行卡 8% / 现金 5%

---

## 项目结构

```
.
├── gen_fake_data.py        # 主入口
├── config.py               # 本地配置（含数据库密码，已 gitignore）
├── config.example.py       # 配置模板
├── schema.sql              # 数据库 DDL
├── requirements.txt        # Python 依赖
├── generators/
│   ├── dimensions.py       # 维度表生成
│   ├── employees.py        # 员工/排班/考勤生成
│   ├── members.py          # 会员主表生成
│   ├── orders.py           # 订单/支付/积分/券生成
│   └── inventory.py        # 库存流水/盘点生成
└── helpers/
    ├── db.py               # 数据库工具函数
    ├── biz_calendar.py     # 节假日/工作日判断
    └── distributions.py    # 概率分布工具
```

---

## 依赖说明

| 包 | 用途 |
|----|------|
| `Faker` | 姓名、地址、手机号等仿真数据 |
| `PyMySQL` | MySQL 驱动 |
| `chinese-calendar` | 中国法定节假日判断 |
| `numpy` | 概率分布（泊松/正态/均匀）、随机数 |
| `tqdm` | 进度条 |
| `python-dateutil` | 日期计算 |

---

## 注意事项

- 运行前请确保 MySQL 服务已启动，且配置的用户有建库权限
- **每次运行会删除并重建目标数据库**，请勿在生产环境使用
- `config.py` 包含数据库密码，已加入 `.gitignore`，请勿提交到版本控制
