-- ============================================================
-- CasPerFect 西式快餐连锁 数据仓库 DDL
-- 字符集: utf8mb4 / 引擎: InnoDB
-- 命名: dim_*  维度表 / fact_*  事实表
-- 加载策略: 加载时关闭外键检查;此处保留外键定义供数据校验和文档作用
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------------------------------------------
-- 维度表
-- ----------------------------------------------------------------

DROP TABLE IF EXISTS `dim_date`;
CREATE TABLE `dim_date` (
  `date_key`     INT          NOT NULL COMMENT 'YYYYMMDD',
  `full_date`    DATE         NOT NULL,
  `year`         SMALLINT     NOT NULL,
  `quarter`      TINYINT      NOT NULL,
  `month`        TINYINT      NOT NULL,
  `day`          TINYINT      NOT NULL,
  `week_of_year` TINYINT      NOT NULL,
  `weekday`      TINYINT      NOT NULL COMMENT '1=Mon..7=Sun',
  `is_weekend`   TINYINT      NOT NULL,
  `is_holiday`   TINYINT      NOT NULL,
  `holiday_name` VARCHAR(32)           DEFAULT NULL,
  `season`       VARCHAR(8)   NOT NULL COMMENT 'SPRING/SUMMER/AUTUMN/WINTER',
  PRIMARY KEY (`date_key`),
  UNIQUE KEY `uk_full_date` (`full_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='日期维度';

DROP TABLE IF EXISTS `dim_city`;
CREATE TABLE `dim_city` (
  `city_id`    INT           NOT NULL,
  `city_name`  VARCHAR(32)   NOT NULL,
  `province`   VARCHAR(32)   NOT NULL,
  `tier`       VARCHAR(16)   NOT NULL COMMENT '一线/新一线/二线',
  `region`     VARCHAR(16)   NOT NULL COMMENT '华北/华东/华南/华中/西南/西北/东北',
  PRIMARY KEY (`city_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='城市维度';

DROP TABLE IF EXISTS `dim_store`;
CREATE TABLE `dim_store` (
  `store_id`     INT          NOT NULL,
  `store_code`   VARCHAR(16)  NOT NULL,
  `store_name`   VARCHAR(64)  NOT NULL,
  `city_id`      INT          NOT NULL,
  `district`     VARCHAR(32)  NOT NULL,
  `address`      VARCHAR(128) NOT NULL,
  `biz_district` VARCHAR(16)  NOT NULL COMMENT 'CBD/社区/校园/交通枢纽/旅游区/商场',
  `area_sqm`     DECIMAL(6,1) NOT NULL,
  `seats`        INT          NOT NULL,
  `open_date`    DATE         NOT NULL,
  `close_date`   DATE         DEFAULT NULL,
  `status`       VARCHAR(16)  NOT NULL COMMENT 'OPEN/CLOSED/SUSPENDED',
  `manager_name` VARCHAR(32)  NOT NULL,
  `phone`        VARCHAR(20)  NOT NULL,
  PRIMARY KEY (`store_id`),
  UNIQUE KEY `uk_store_code` (`store_code`),
  KEY `idx_city` (`city_id`),
  CONSTRAINT `fk_store_city` FOREIGN KEY (`city_id`) REFERENCES `dim_city`(`city_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='门店维度';

DROP TABLE IF EXISTS `dim_channel`;
CREATE TABLE `dim_channel` (
  `channel_id`   INT          NOT NULL,
  `channel_code` VARCHAR(16)  NOT NULL,
  `channel_name` VARCHAR(32)  NOT NULL,
  `is_delivery`  TINYINT      NOT NULL,
  `commission_rate` DECIMAL(5,4) NOT NULL DEFAULT 0,
  PRIMARY KEY (`channel_id`),
  UNIQUE KEY `uk_channel_code` (`channel_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道维度';

DROP TABLE IF EXISTS `dim_payment_method`;
CREATE TABLE `dim_payment_method` (
  `payment_id`    INT          NOT NULL,
  `payment_code`  VARCHAR(16)  NOT NULL,
  `payment_name`  VARCHAR(32)  NOT NULL,
  `is_third_party` TINYINT     NOT NULL,
  PRIMARY KEY (`payment_id`),
  UNIQUE KEY `uk_payment_code` (`payment_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付方式维度';

DROP TABLE IF EXISTS `dim_category`;
CREATE TABLE `dim_category` (
  `category_id`   INT          NOT NULL,
  `category_code` VARCHAR(16)  NOT NULL,
  `category_name` VARCHAR(32)  NOT NULL,
  `sort_order`    INT          NOT NULL,
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `uk_category_code` (`category_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='菜品分类';

DROP TABLE IF EXISTS `dim_product`;
CREATE TABLE `dim_product` (
  `product_id`     INT          NOT NULL,
  `product_code`   VARCHAR(16)  NOT NULL,
  `product_name`   VARCHAR(64)  NOT NULL,
  `category_id`    INT          NOT NULL,
  `price`          DECIMAL(8,2) NOT NULL,
  `cost`           DECIMAL(8,2) NOT NULL,
  `is_combo`       TINYINT      NOT NULL DEFAULT 0,
  `is_cold`        TINYINT      NOT NULL DEFAULT 0 COMMENT '冷饮(夏季权重高)',
  `is_hot`         TINYINT      NOT NULL DEFAULT 0 COMMENT '热饮(冬季权重高)',
  `is_signature`   TINYINT      NOT NULL DEFAULT 0 COMMENT '主推招牌',
  `available_from` DATE         NOT NULL,
  `available_to`   DATE         DEFAULT NULL,
  `status`         VARCHAR(16)  NOT NULL DEFAULT 'ON_SHELF',
  PRIMARY KEY (`product_id`),
  UNIQUE KEY `uk_product_code` (`product_code`),
  KEY `idx_category` (`category_id`),
  CONSTRAINT `fk_product_category` FOREIGN KEY (`category_id`) REFERENCES `dim_category`(`category_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='菜品SKU';

DROP TABLE IF EXISTS `dim_member_level`;
CREATE TABLE `dim_member_level` (
  `level_id`        INT          NOT NULL,
  `level_code`      VARCHAR(16)  NOT NULL,
  `level_name`      VARCHAR(32)  NOT NULL,
  `discount_rate`   DECIMAL(5,4) NOT NULL COMMENT '0.95=95折',
  `point_rate`      DECIMAL(4,2) NOT NULL COMMENT '积分倍率',
  `upgrade_amount`  DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (`level_id`),
  UNIQUE KEY `uk_level_code` (`level_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员等级';

DROP TABLE IF EXISTS `dim_coupon_template`;
CREATE TABLE `dim_coupon_template` (
  `template_id`    INT           NOT NULL,
  `template_code`  VARCHAR(32)   NOT NULL,
  `template_name`  VARCHAR(64)   NOT NULL,
  `coupon_type`    VARCHAR(16)   NOT NULL COMMENT 'CASH/DISCOUNT/FREE_ITEM/NEW_USER',
  `face_value`     DECIMAL(8,2)  NOT NULL DEFAULT 0,
  `discount_rate`  DECIMAL(5,4)  DEFAULT NULL,
  `min_order_amount` DECIMAL(8,2) NOT NULL DEFAULT 0,
  `valid_days`     INT           NOT NULL DEFAULT 30,
  `description`    VARCHAR(128)  DEFAULT NULL,
  PRIMARY KEY (`template_id`),
  UNIQUE KEY `uk_template_code` (`template_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='优惠券模板';

DROP TABLE IF EXISTS `dim_position`;
CREATE TABLE `dim_position` (
  `position_id`    INT          NOT NULL,
  `position_code`  VARCHAR(16)  NOT NULL,
  `position_name`  VARCHAR(32)  NOT NULL,
  `salary_min`     DECIMAL(8,2) NOT NULL,
  `salary_max`     DECIMAL(8,2) NOT NULL,
  `is_management`  TINYINT      NOT NULL DEFAULT 0,
  PRIMARY KEY (`position_id`),
  UNIQUE KEY `uk_position_code` (`position_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='岗位维度';

DROP TABLE IF EXISTS `dim_employee`;
CREATE TABLE `dim_employee` (
  `employee_id`   INT           NOT NULL,
  `employee_code` VARCHAR(16)   NOT NULL,
  `name`          VARCHAR(32)   NOT NULL,
  `gender`        VARCHAR(8)    NOT NULL,
  `birth_date`    DATE          NOT NULL,
  `id_card_masked` VARCHAR(20)  NOT NULL,
  `phone`         VARCHAR(20)   NOT NULL,
  `store_id`      INT           NOT NULL,
  `position_id`   INT           NOT NULL,
  `hire_date`     DATE          NOT NULL,
  `leave_date`    DATE          DEFAULT NULL,
  `salary`        DECIMAL(8,2)  NOT NULL,
  `status`        VARCHAR(16)   NOT NULL,
  PRIMARY KEY (`employee_id`),
  UNIQUE KEY `uk_employee_code` (`employee_code`),
  KEY `idx_store` (`store_id`),
  KEY `idx_position` (`position_id`),
  CONSTRAINT `fk_emp_store`    FOREIGN KEY (`store_id`)    REFERENCES `dim_store`(`store_id`),
  CONSTRAINT `fk_emp_position` FOREIGN KEY (`position_id`) REFERENCES `dim_position`(`position_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='员工维度';

DROP TABLE IF EXISTS `dim_supplier`;
CREATE TABLE `dim_supplier` (
  `supplier_id`   INT          NOT NULL,
  `supplier_code` VARCHAR(16)  NOT NULL,
  `supplier_name` VARCHAR(64)  NOT NULL,
  `category`      VARCHAR(16)  NOT NULL COMMENT '肉类/面包/蔬菜/饮料/包材/其他',
  `contact_name`  VARCHAR(32)  NOT NULL,
  `phone`         VARCHAR(20)  NOT NULL,
  `address`       VARCHAR(128) NOT NULL,
  `cooperation_since` DATE     NOT NULL,
  PRIMARY KEY (`supplier_id`),
  UNIQUE KEY `uk_supplier_code` (`supplier_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='供应商维度';

DROP TABLE IF EXISTS `dim_warehouse`;
CREATE TABLE `dim_warehouse` (
  `warehouse_id`   INT          NOT NULL,
  `warehouse_code` VARCHAR(16)  NOT NULL,
  `warehouse_name` VARCHAR(64)  NOT NULL,
  `city_id`        INT          NOT NULL,
  `is_central`     TINYINT      NOT NULL DEFAULT 0,
  PRIMARY KEY (`warehouse_id`),
  UNIQUE KEY `uk_warehouse_code` (`warehouse_code`),
  CONSTRAINT `fk_wh_city` FOREIGN KEY (`city_id`) REFERENCES `dim_city`(`city_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库维度';

DROP TABLE IF EXISTS `dim_ingredient`;
CREATE TABLE `dim_ingredient` (
  `ingredient_id`   INT          NOT NULL,
  `ingredient_code` VARCHAR(16)  NOT NULL,
  `ingredient_name` VARCHAR(64)  NOT NULL,
  `unit`            VARCHAR(8)   NOT NULL COMMENT 'kg/L/个/包',
  `category`        VARCHAR(16)  NOT NULL,
  `unit_cost`       DECIMAL(8,4) NOT NULL,
  `shelf_life_days` INT          NOT NULL,
  `default_supplier_id` INT      DEFAULT NULL,
  PRIMARY KEY (`ingredient_id`),
  UNIQUE KEY `uk_ingredient_code` (`ingredient_code`),
  CONSTRAINT `fk_ing_supplier` FOREIGN KEY (`default_supplier_id`) REFERENCES `dim_supplier`(`supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食材SKU';

-- ----------------------------------------------------------------
-- 事实表
-- ----------------------------------------------------------------

DROP TABLE IF EXISTS `fact_member`;
CREATE TABLE `fact_member` (
  `member_id`         BIGINT       NOT NULL,
  `member_code`       VARCHAR(20)  NOT NULL,
  `name`              VARCHAR(32)  NOT NULL,
  `gender`            VARCHAR(8)   NOT NULL,
  `phone`             VARCHAR(20)  NOT NULL,
  `birth_date`        DATE         DEFAULT NULL,
  `register_date`     DATE         NOT NULL,
  `register_channel`  VARCHAR(16)  NOT NULL COMMENT '门店/小程序/APP/外卖平台',
  `register_store_id` INT          DEFAULT NULL,
  `level_id`          INT          NOT NULL,
  `total_consumption` DECIMAL(12,2) NOT NULL DEFAULT 0,
  `total_orders`      INT          NOT NULL DEFAULT 0,
  `current_points`    INT          NOT NULL DEFAULT 0,
  `wallet_balance`    DECIMAL(10,2) NOT NULL DEFAULT 0,
  `last_order_date`   DATE         DEFAULT NULL,
  `status`            VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  PRIMARY KEY (`member_id`),
  UNIQUE KEY `uk_member_code` (`member_code`),
  KEY `idx_phone` (`phone`),
  KEY `idx_level` (`level_id`),
  CONSTRAINT `fk_member_level` FOREIGN KEY (`level_id`) REFERENCES `dim_member_level`(`level_id`),
  CONSTRAINT `fk_member_store` FOREIGN KEY (`register_store_id`) REFERENCES `dim_store`(`store_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员主表';

DROP TABLE IF EXISTS `fact_order`;
CREATE TABLE `fact_order` (
  `order_id`         BIGINT       NOT NULL,
  `order_no`         VARCHAR(32)  NOT NULL,
  `store_id`         INT          NOT NULL,
  `date_key`         INT          NOT NULL,
  `order_time`       DATETIME     NOT NULL,
  `channel_id`       INT          NOT NULL,
  `member_id`        BIGINT       DEFAULT NULL,
  `cashier_id`       INT          DEFAULT NULL COMMENT '收银员/接单员',
  `dine_type`        VARCHAR(16)  NOT NULL COMMENT 'DINE_IN/TAKEAWAY/DELIVERY',
  `table_no`         VARCHAR(8)   DEFAULT NULL,
  `headcount`        TINYINT      DEFAULT NULL,
  `item_count`       INT          NOT NULL,
  `original_amount`  DECIMAL(10,2) NOT NULL,
  `discount_amount`  DECIMAL(10,2) NOT NULL DEFAULT 0,
  `coupon_amount`    DECIMAL(10,2) NOT NULL DEFAULT 0,
  `delivery_fee`     DECIMAL(8,2) NOT NULL DEFAULT 0,
  `platform_fee`     DECIMAL(8,2) NOT NULL DEFAULT 0,
  `actual_amount`    DECIMAL(10,2) NOT NULL,
  `points_used`      INT          NOT NULL DEFAULT 0,
  `points_earned`    INT          NOT NULL DEFAULT 0,
  `status`           VARCHAR(16)  NOT NULL COMMENT 'PAID/REFUNDED/CANCELLED',
  `prep_minutes`     SMALLINT     DEFAULT NULL,
  PRIMARY KEY (`order_id`),
  UNIQUE KEY `uk_order_no` (`order_no`),
  KEY `idx_store_date` (`store_id`, `date_key`),
  KEY `idx_date` (`date_key`),
  KEY `idx_member` (`member_id`),
  KEY `idx_channel` (`channel_id`),
  CONSTRAINT `fk_order_store`   FOREIGN KEY (`store_id`)   REFERENCES `dim_store`(`store_id`),
  CONSTRAINT `fk_order_date`    FOREIGN KEY (`date_key`)   REFERENCES `dim_date`(`date_key`),
  CONSTRAINT `fk_order_channel` FOREIGN KEY (`channel_id`) REFERENCES `dim_channel`(`channel_id`),
  CONSTRAINT `fk_order_member`  FOREIGN KEY (`member_id`)  REFERENCES `fact_member`(`member_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单头';

DROP TABLE IF EXISTS `fact_order_item`;
CREATE TABLE `fact_order_item` (
  `item_id`         BIGINT       NOT NULL AUTO_INCREMENT,
  `order_id`        BIGINT       NOT NULL,
  `product_id`      INT          NOT NULL,
  `quantity`        SMALLINT     NOT NULL,
  `unit_price`      DECIMAL(8,2) NOT NULL,
  `discount_amount` DECIMAL(8,2) NOT NULL DEFAULT 0,
  `subtotal`        DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (`item_id`),
  KEY `idx_order` (`order_id`),
  KEY `idx_product` (`product_id`),
  CONSTRAINT `fk_item_order`   FOREIGN KEY (`order_id`)   REFERENCES `fact_order`(`order_id`),
  CONSTRAINT `fk_item_product` FOREIGN KEY (`product_id`) REFERENCES `dim_product`(`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细';

DROP TABLE IF EXISTS `fact_payment`;
CREATE TABLE `fact_payment` (
  `payment_seq`    BIGINT       NOT NULL AUTO_INCREMENT,
  `order_id`       BIGINT       NOT NULL,
  `payment_id`     INT          NOT NULL,
  `pay_amount`     DECIMAL(10,2) NOT NULL,
  `pay_time`       DATETIME     NOT NULL,
  `transaction_no` VARCHAR(64)  NOT NULL,
  `status`         VARCHAR(16)  NOT NULL DEFAULT 'SUCCESS',
  PRIMARY KEY (`payment_seq`),
  KEY `idx_order` (`order_id`),
  KEY `idx_method` (`payment_id`),
  CONSTRAINT `fk_pay_order`  FOREIGN KEY (`order_id`)   REFERENCES `fact_order`(`order_id`),
  CONSTRAINT `fk_pay_method` FOREIGN KEY (`payment_id`) REFERENCES `dim_payment_method`(`payment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付流水';

DROP TABLE IF EXISTS `fact_coupon_issued`;
CREATE TABLE `fact_coupon_issued` (
  `coupon_id`     BIGINT       NOT NULL,
  `coupon_code`   VARCHAR(32)  NOT NULL,
  `template_id`   INT          NOT NULL,
  `member_id`     BIGINT       NOT NULL,
  `issue_time`    DATETIME     NOT NULL,
  `expire_time`   DATETIME     NOT NULL,
  `source`        VARCHAR(32)  NOT NULL COMMENT '注册赠送/活动/补偿/裂变',
  `status`        VARCHAR(16)  NOT NULL COMMENT 'UNUSED/USED/EXPIRED',
  PRIMARY KEY (`coupon_id`),
  UNIQUE KEY `uk_coupon_code` (`coupon_code`),
  KEY `idx_member` (`member_id`),
  KEY `idx_template` (`template_id`),
  CONSTRAINT `fk_iss_template` FOREIGN KEY (`template_id`) REFERENCES `dim_coupon_template`(`template_id`),
  CONSTRAINT `fk_iss_member`   FOREIGN KEY (`member_id`)   REFERENCES `fact_member`(`member_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='优惠券发放';

DROP TABLE IF EXISTS `fact_coupon_redeemed`;
CREATE TABLE `fact_coupon_redeemed` (
  `redeem_id`    BIGINT       NOT NULL AUTO_INCREMENT,
  `coupon_id`    BIGINT       NOT NULL,
  `order_id`     BIGINT       NOT NULL,
  `member_id`    BIGINT       NOT NULL,
  `redeem_time`  DATETIME     NOT NULL,
  `discount_amount` DECIMAL(8,2) NOT NULL,
  PRIMARY KEY (`redeem_id`),
  UNIQUE KEY `uk_coupon` (`coupon_id`),
  KEY `idx_order` (`order_id`),
  KEY `idx_member` (`member_id`),
  CONSTRAINT `fk_red_coupon` FOREIGN KEY (`coupon_id`) REFERENCES `fact_coupon_issued`(`coupon_id`),
  CONSTRAINT `fk_red_order`  FOREIGN KEY (`order_id`)  REFERENCES `fact_order`(`order_id`),
  CONSTRAINT `fk_red_member` FOREIGN KEY (`member_id`) REFERENCES `fact_member`(`member_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='优惠券核销';

DROP TABLE IF EXISTS `fact_point_txn`;
CREATE TABLE `fact_point_txn` (
  `txn_id`      BIGINT       NOT NULL AUTO_INCREMENT,
  `member_id`   BIGINT       NOT NULL,
  `txn_time`    DATETIME     NOT NULL,
  `txn_type`    VARCHAR(16)  NOT NULL COMMENT 'EARN/REDEEM/EXPIRE/ADJUST',
  `points`      INT          NOT NULL COMMENT '正负',
  `balance_after` INT        NOT NULL,
  `related_order_id` BIGINT  DEFAULT NULL,
  `remark`      VARCHAR(64)  DEFAULT NULL,
  PRIMARY KEY (`txn_id`),
  KEY `idx_member` (`member_id`),
  KEY `idx_order`  (`related_order_id`),
  CONSTRAINT `fk_pt_member` FOREIGN KEY (`member_id`)        REFERENCES `fact_member`(`member_id`),
  CONSTRAINT `fk_pt_order`  FOREIGN KEY (`related_order_id`) REFERENCES `fact_order`(`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='积分流水';

DROP TABLE IF EXISTS `fact_schedule`;
CREATE TABLE `fact_schedule` (
  `schedule_id` BIGINT       NOT NULL AUTO_INCREMENT,
  `employee_id` INT          NOT NULL,
  `store_id`    INT          NOT NULL,
  `date_key`    INT          NOT NULL,
  `shift`       VARCHAR(16)  NOT NULL COMMENT '早班/中班/晚班/休息',
  `start_time`  DATETIME     DEFAULT NULL,
  `end_time`    DATETIME     DEFAULT NULL,
  PRIMARY KEY (`schedule_id`),
  KEY `idx_emp_date`    (`employee_id`, `date_key`),
  KEY `idx_store_date`  (`store_id`, `date_key`),
  CONSTRAINT `fk_sch_emp`   FOREIGN KEY (`employee_id`) REFERENCES `dim_employee`(`employee_id`),
  CONSTRAINT `fk_sch_store` FOREIGN KEY (`store_id`)    REFERENCES `dim_store`(`store_id`),
  CONSTRAINT `fk_sch_date`  FOREIGN KEY (`date_key`)    REFERENCES `dim_date`(`date_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='员工排班';

DROP TABLE IF EXISTS `fact_attendance`;
CREATE TABLE `fact_attendance` (
  `attendance_id` BIGINT       NOT NULL AUTO_INCREMENT,
  `employee_id`   INT          NOT NULL,
  `store_id`      INT          NOT NULL,
  `date_key`      INT          NOT NULL,
  `clock_in`      DATETIME     DEFAULT NULL,
  `clock_out`     DATETIME     DEFAULT NULL,
  `status`        VARCHAR(16)  NOT NULL COMMENT 'NORMAL/LATE/EARLY_LEAVE/ABSENT/LEAVE',
  `work_hours`    DECIMAL(4,2) DEFAULT NULL,
  PRIMARY KEY (`attendance_id`),
  KEY `idx_emp_date` (`employee_id`, `date_key`),
  CONSTRAINT `fk_att_emp`   FOREIGN KEY (`employee_id`) REFERENCES `dim_employee`(`employee_id`),
  CONSTRAINT `fk_att_store` FOREIGN KEY (`store_id`)    REFERENCES `dim_store`(`store_id`),
  CONSTRAINT `fk_att_date`  FOREIGN KEY (`date_key`)    REFERENCES `dim_date`(`date_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤';

DROP TABLE IF EXISTS `fact_inventory_io`;
CREATE TABLE `fact_inventory_io` (
  `io_id`         BIGINT       NOT NULL AUTO_INCREMENT,
  `store_id`      INT          NOT NULL,
  `ingredient_id` INT          NOT NULL,
  `date_key`      INT          NOT NULL,
  `io_time`       DATETIME     NOT NULL,
  `io_type`       VARCHAR(16)  NOT NULL COMMENT 'IN_PURCHASE/IN_TRANSFER/OUT_SALE/OUT_LOSS/OUT_TRANSFER',
  `quantity`      DECIMAL(10,3) NOT NULL,
  `unit_cost`     DECIMAL(8,4) NOT NULL,
  `total_cost`    DECIMAL(10,2) NOT NULL,
  `supplier_id`   INT          DEFAULT NULL,
  `warehouse_id`  INT          DEFAULT NULL,
  `remark`        VARCHAR(64)  DEFAULT NULL,
  PRIMARY KEY (`io_id`),
  KEY `idx_store_date` (`store_id`, `date_key`),
  KEY `idx_ingredient` (`ingredient_id`),
  CONSTRAINT `fk_io_store`      FOREIGN KEY (`store_id`)      REFERENCES `dim_store`(`store_id`),
  CONSTRAINT `fk_io_ingredient` FOREIGN KEY (`ingredient_id`) REFERENCES `dim_ingredient`(`ingredient_id`),
  CONSTRAINT `fk_io_date`       FOREIGN KEY (`date_key`)      REFERENCES `dim_date`(`date_key`),
  CONSTRAINT `fk_io_supplier`   FOREIGN KEY (`supplier_id`)   REFERENCES `dim_supplier`(`supplier_id`),
  CONSTRAINT `fk_io_warehouse`  FOREIGN KEY (`warehouse_id`)  REFERENCES `dim_warehouse`(`warehouse_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存出入流水';

DROP TABLE IF EXISTS `fact_inventory_check`;
CREATE TABLE `fact_inventory_check` (
  `check_id`      BIGINT       NOT NULL AUTO_INCREMENT,
  `store_id`      INT          NOT NULL,
  `ingredient_id` INT          NOT NULL,
  `date_key`      INT          NOT NULL,
  `book_qty`      DECIMAL(10,3) NOT NULL COMMENT '账面数量',
  `actual_qty`    DECIMAL(10,3) NOT NULL COMMENT '实盘数量',
  `diff_qty`      DECIMAL(10,3) NOT NULL,
  `loss_amount`   DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (`check_id`),
  KEY `idx_store_date` (`store_id`, `date_key`),
  CONSTRAINT `fk_chk_store`      FOREIGN KEY (`store_id`)      REFERENCES `dim_store`(`store_id`),
  CONSTRAINT `fk_chk_ingredient` FOREIGN KEY (`ingredient_id`) REFERENCES `dim_ingredient`(`ingredient_id`),
  CONSTRAINT `fk_chk_date`       FOREIGN KEY (`date_key`)      REFERENCES `dim_date`(`date_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='盘点';

-- 注意: 加载数据期间外键检查由调用方控制,这里不恢复 FK_CHECKS
