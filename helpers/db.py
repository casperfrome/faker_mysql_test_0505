"""数据库工具：连接 / 重建库 / 批量写入 / DDL 执行"""

import re
import pymysql
from config import MYSQL, DB_NAME, BATCH_SIZE


def get_connection(use_db: bool = True):
    kwargs = dict(MYSQL)
    if use_db:
        kwargs["database"] = DB_NAME
    kwargs["autocommit"] = False
    return pymysql.connect(**kwargs)


def recreate_database():
    """DROP IF EXISTS + CREATE DATABASE utf8mb4"""
    conn = get_connection(use_db=False)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
            cur.execute(
                f"CREATE DATABASE `{DB_NAME}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def exec_ddl_file(conn, sql_path: str):
    """逐条执行 DDL 文件中的语句"""
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_text = f.read()

    # 移除 -- 行注释,按 ; 拆分
    cleaned_lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)

    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def bulk_insert(conn, table: str, columns: list, rows: list, batch_size: int = BATCH_SIZE):
    """批量插入。rows 为 tuple 列表。返回插入行数。"""
    if not rows:
        return 0
    cols_sql = ",".join(f"`{c}`" for c in columns)
    placeholders = ",".join(["%s"] * len(columns))
    sql = f"INSERT INTO `{table}` ({cols_sql}) VALUES ({placeholders})"

    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            cur.executemany(sql, chunk)
            inserted += len(chunk)
            conn.commit()
    return inserted


def disable_fk_checks(conn):
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        cur.execute("SET UNIQUE_CHECKS=0")
        cur.execute("SET sql_log_bin=0")
    conn.commit()


def enable_fk_checks(conn):
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        cur.execute("SET UNIQUE_CHECKS=1")
    conn.commit()


def table_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        return cur.fetchone()[0]
