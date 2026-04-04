import pandas as pd
import mysql.connector
import logging
from config import DB_CONFIG

logger = logging.getLogger(__name__)

def get_connection():
    """
    Creates and returns a MySQL connection using config credentials.
    SSL disabled for local connections — not needed for localhost.
    """
    config = DB_CONFIG.copy()
    config['ssl_disabled'] = True
    return mysql.connector.connect(**config)

def load_table(df: pd.DataFrame, table_name: str, connection, chunk_size: int = 1000) -> int:
    """
    Loads a dataframe into a MySQL table in chunks.
    Uses INSERT IGNORE to skip duplicate primaryids.
    Returns number of rows inserted.
    """
    if df.empty:
        logger.warning(f"Empty dataframe for {table_name}, skipping.")
        return 0

    # Rename columns to match MySQL schema
    column_map = {
        'age_cod':      'age_unit',
        'wt':           'weight',
        'event_dt':     'report_date',
        'occr_country': 'country',
        'rept_cod':     'reporter_type',
        'drugname':     'drug_name',
        'role_cod':     'drug_role',
        'pt':           'reaction',
        'outc_cod':     'outcome_code',
        'rpsr_cod':     'reporter_source'
    }
    df = df.rename(columns=column_map)
    df = df.where(pd.notna(df), None)

    cols = ', '.join(df.columns)
    placeholders = ', '.join(['%s'] * len(df.columns))
    sql = f"INSERT IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})"

    total_inserted = 0
    total_rows = len(df)

    # Split into chunks to avoid connection timeout
    for i in range(0, total_rows, chunk_size):
        chunk = df.iloc[i:i + chunk_size]
        rows = [tuple(row) for row in chunk.itertuples(index=False)]

        # Reconnect if connection was lost
        if not connection.is_connected():
            logger.warning("Connection lost — reconnecting...")
            connection.reconnect(attempts=3, delay=2)

        cursor = connection.cursor()
        try:
            cursor.executemany(sql, rows)
            connection.commit()
            total_inserted += cursor.rowcount

            # Progress log every 100k rows
            if i % 100000 == 0:
                logger.info(f"{table_name}: {i}/{total_rows} rows processed")

        except mysql.connector.Error as e:
            logger.error(f"MySQL error at chunk {i} for {table_name}: {e}")
            connection.rollback()

        finally:
            cursor.close()

    logger.info(f"Loaded {total_inserted} rows into {table_name}")
    return total_inserted

def load_quarter(tables: dict, connection) -> None:
    """
    Loads all five parsed tables into MySQL.
    DEMO must load first — other tables have foreign keys pointing to it.
    """
    # Load order matters — DEMO first, then dimension tables
    load_order = ['demo', 'drug', 'reac', 'outc', 'rpsr']

    for table_name in load_order:
        df = tables.get(table_name, pd.DataFrame())
        load_table(df, table_name, connection)