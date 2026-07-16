import getpass
from pathlib import Path


def test_connection(source_type, host, port, database, username, password):
    try:
        if source_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                host=host, port=port, dbname=database,
                user=username or getpass.getuser(), password=password,
                connect_timeout=5, gssencmode='disable',
            )
            conn.close()
            return True, ""
        elif source_type == "file":
            base_dir = Path(host)
            if not base_dir.exists():
                return False, f"Directory not found: {host}"
            if not base_dir.is_dir():
                return False, f"Path is not a directory: {host}"
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
                user=username or getpass.getuser(), password=password,
                connect_timeout=5, gssencmode='disable',
            )
            cur = conn.cursor()
            for table in table_names:
                parts = table.split(".", 1)
                schema, tname = (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("public", table.strip())
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (schema, tname)
                )
                results[table] = cur.fetchone() is not None
            cur.close()
            conn.close()

        elif source_type == "file":
            base_dir = Path(host)
            for filename in table_names:
                results[filename] = (base_dir / filename).exists()

    except Exception as e:
        return results, str(e)

    return results, ""
