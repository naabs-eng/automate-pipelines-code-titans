import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.config_manager import ConfigManager

st.set_page_config(page_title="Data Pipeline", page_icon="🔧", layout="wide")

st.title("Data Pipeline Dashboard")
st.caption("Medallion Architecture — Bronze → Silver → Gold")

config = ConfigManager()

st.divider()

col1, col2, col3 = st.columns(3)

# SQL Server stats
ss_tables = config.get("tables.source", [])
with col1:
    st.metric("SQL Server Tables", len(ss_tables))
    st.caption(f"DB: {config.get('sql_server.database', 'N/A')}")

# PostgreSQL stats
pg_tables = config.get("tables.pg_source", [])
with col2:
    st.metric("PostgreSQL Tables", len(pg_tables))
    st.caption(f"DB: {config.get('postgresql.database', 'N/A')}")

# Bronze tables on disk
bronze_path = Path(config.get("paths.bronze", "./data/bronze"))
bronze_on_disk = [d.name for d in bronze_path.iterdir() if d.is_dir()] if bronze_path.exists() else []
with col3:
    st.metric("Bronze Tables on Disk", len(bronze_on_disk))
    st.caption(", ".join(bronze_on_disk) if bronze_on_disk else "None yet")

st.divider()

st.subheader("Configured Sources")

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.markdown("**PostgreSQL**")
        st.write(f"Host: `{config.get('postgresql.host', 'N/A')}`")
        st.write(f"Port: `{config.get('postgresql.port', 5432)}`")
        st.write(f"Database: `{config.get('postgresql.database', 'N/A')}`")
        if pg_tables:
            st.write("Tables: " + ", ".join(f"`{t['bronze_table']}`" for t in pg_tables))

with c2:
    with st.container(border=True):
        st.markdown("**SQL Server**")
        st.write(f"Server: `{config.get('sql_server.server', 'N/A')}`")
        st.write(f"Database: `{config.get('sql_server.database', 'N/A')}`")
        if ss_tables:
            st.write("Tables: " + ", ".join(f"`{t['bronze_table']}`" for t in ss_tables))

st.divider()
st.info("Use **Source Manager** to add/edit DB connections  |  Use **Pipeline Runner** to validate tables and run Bronze ingestion")
