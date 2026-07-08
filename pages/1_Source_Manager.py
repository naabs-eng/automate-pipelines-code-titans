import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.config_manager import ConfigManager
from utils.db_validator import test_connection

st.set_page_config(page_title="Source Manager", page_icon="🔌", layout="wide")
st.title("Source Manager")
st.caption("Add and manage database connections")

config = ConfigManager()


def _save_pg_credentials(username, password):
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = {}
    new_lines = []
    for line in lines:
        if line.startswith("PG_USERNAME="):
            new_lines.append(f"PG_USERNAME={username}")
            updated["PG_USERNAME"] = True
        elif line.startswith("PG_PASSWORD="):
            new_lines.append(f"PG_PASSWORD={password}")
            updated["PG_PASSWORD"] = True
        else:
            new_lines.append(line)
    if "PG_USERNAME" not in updated:
        new_lines.append(f"PG_USERNAME={username}")
    if "PG_PASSWORD" not in updated:
        new_lines.append(f"PG_PASSWORD={password}")
    env_path.write_text("\n".join(new_lines) + "\n")


# ── Existing Sources ──────────────────────────────────────────────────────────
st.subheader("Existing Sources")

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.markdown("**PostgreSQL**")
        pg_host = config.get("postgresql.host")
        if pg_host:
            st.write(f"Host: `{pg_host}`")
            st.write(f"Port: `{config.get('postgresql.port', 5432)}`")
            st.write(f"Database: `{config.get('postgresql.database')}`")
            st.write("Password: `••••••••`")
        else:
            st.warning("Not configured yet")

with c2:
    with st.container(border=True):
        st.markdown("**SQL Server**")
        ss_server = config.get("sql_server.server")
        if ss_server:
            st.write(f"Server: `{ss_server}`")
            st.write(f"Database: `{config.get('sql_server.database')}`")
            st.write("Auth: `Windows Integrated`")
        else:
            st.warning("Not configured yet")

st.divider()

# ── Add / Edit Source ─────────────────────────────────────────────────────────
st.subheader("Add / Edit Source")

source_type = st.selectbox("Source Type", ["PostgreSQL", "SQL Server"])

if source_type == "PostgreSQL":
    with st.form("pg_form"):
        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("Host", value=config.get("postgresql.host", "localhost"))
            port = st.number_input("Port", value=int(config.get("postgresql.port", 5432)), step=1)
        with col2:
            database = st.text_input("Database", value=config.get("postgresql.database", ""))
            username = st.text_input("Username", value=os.environ.get("PG_USERNAME", ""))
        password = st.text_input("Password", type="password")

        test_btn = st.form_submit_button("Test Connection")

    if test_btn:
        with st.spinner("Testing connection..."):
            ok, err = test_connection("postgresql", host, int(port), database, username, password)
        if ok:
            st.success("Connection successful!")
            st.session_state["pg_conn_valid"] = True
            st.session_state["pg_conn_data"] = {
                "host": host, "port": int(port), "database": database,
                "username": username, "password": password
            }
        else:
            st.error(f"Connection failed: {err}")
            st.session_state["pg_conn_valid"] = False

    if st.session_state.get("pg_conn_valid"):
        if st.button("Save Source", type="primary"):
            d = st.session_state["pg_conn_data"]
            config.set("postgresql.host", d["host"])
            config.set("postgresql.port", d["port"])
            config.set("postgresql.database", d["database"])
            config.save()
            _save_pg_credentials(d["username"], d["password"])
            st.success("Source saved to config.yaml and credentials saved to .env")
            st.session_state["pg_conn_valid"] = False
            st.rerun()

else:
    with st.form("ss_form"):
        col1, col2 = st.columns(2)
        with col1:
            server = st.text_input("Server", value=config.get("sql_server.server", "localhost\\SQLEXPRESS"))
        with col2:
            database = st.text_input("Database", value=config.get("sql_server.database", ""))
        st.info("SQL Server uses Windows Integrated Authentication — no username/password needed.")
        test_btn = st.form_submit_button("Test Connection")

    if test_btn:
        with st.spinner("Testing connection..."):
            ok, err = test_connection("sqlserver", server, 1433, database, "", "")
        if ok:
            st.success("Connection successful!")
            st.session_state["ss_conn_valid"] = True
            st.session_state["ss_conn_data"] = {"server": server, "database": database}
        else:
            st.error(f"Connection failed: {err}")
            st.session_state["ss_conn_valid"] = False

    if st.session_state.get("ss_conn_valid"):
        if st.button("Save Source", type="primary"):
            d = st.session_state["ss_conn_data"]
            config.set("sql_server.server", d["server"])
            config.set("sql_server.database", d["database"])
            config.save()
            st.success("Source saved to config.yaml")
            st.session_state["ss_conn_valid"] = False
            st.rerun()
