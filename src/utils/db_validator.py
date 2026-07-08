def test_connection(source_type, host, port, database, username, password):
    try:
        if source_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                host=host, port=port, dbname=database,
                user=username, password=password, connect_timeout=5
            )
            conn.close()
            return True, ""
        elif source_type == "sqlserver":
            import pyodbc
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={host},{port};DATABASE={database};"
                f"UID={username};PWD={password};Timeout=5"
            )
            conn = pyodbc.connect(conn_str, timeout=5)
            conn.close()
            return True, ""
        else:
            return False, f"Unsupported source type: {source_type}"
    except Exception as e:
        return False, str(e)


def validate_tables(source_type, host, port, database, username, password, table_names):
    results = {t: False for t in table_names}
    try:
        if source_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                host=host, port=port, dbname=database,
                user=username, password=password, connect_timeout=5
            )
            cur = conn.cursor()
            for table in table_names:
                schema, tname = ("public", table) if "." not in table else table.split(".", 1)
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (schema, tname)
                )
                results[table] = cur.fetchone() is not None
            cur.close()
            conn.close()

        elif source_type == "sqlserver":
            import pyodbc
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={host},{port};DATABASE={database};"
                f"UID={username};PWD={password};Timeout=5"
            )
            conn = pyodbc.connect(conn_str, timeout=5)
            cur = conn.cursor()
            for table in table_names:
                schema, tname = ("dbo", table) if "." not in table else table.split(".", 1)
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = ? AND table_name = ?",
                    (schema, tname)
                )
                results[table] = cur.fetchone() is not None
            cur.close()
            conn.close()

    except Exception as e:
        return results, str(e)

    return results, ""
