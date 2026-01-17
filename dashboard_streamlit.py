import os
import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime

# Configuración para Streamlit Cloud
IS_STREAMLIT_CLOUD = os.getenv('STREAMLIT_CLOUD', 'False').lower() == 'true'

def get_db_path():
    """Base de datos local o remota según configuración"""
    if IS_STREAMLIT_CLOUD:
        # En Streamlit Cloud, usamos archivos locales
        return os.path.join(os.path.dirname(__file__), "txt_data.db")
    else:
        return os.path.join(os.path.dirname(__file__), "txt_data.db")

def get_record_tables(conn):
    """Obtener tablas disponibles"""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name DESC")
    rows = [r[0] for r in cur.fetchall()]
    return rows

def load_table(conn, table):
    """Cargar datos de tabla específica"""
    df = pd.read_sql_query(f'SELECT username, damage FROM "{table}"', conn)
    df["damage"] = pd.to_numeric(df["damage"], errors="coerce").fillna(0).astype("int64")
    df["name"] = df["username"].astype(str).str.upper()
    return df

def aggregate(df):
    """Agrupar datos por jugador"""
    agg = df.groupby("name", as_index=False)["damage"].sum()
    return agg

def compute_comparison(prev_df, last_df):
    """Calcular comparación entre raids"""
    a = aggregate(prev_df).rename(columns={"damage": "prev_damage"})
    b = aggregate(last_df).rename(columns={"damage": "last_damage"})
    merged = pd.merge(a, b, on="name", how="outer").fillna(0)
    merged["prev_damage"] = merged["prev_damage"].astype("int64")
    merged["last_damage"] = merged["last_damage"].astype("int64")

    def pct_row(row):
        pv = row["prev_damage"]
        ls = row["last_damage"]
        if pv > 0:
            return (ls - pv) / pv * 100.0
        if pv == 0 and ls > 0:
            return np.inf
        return 0.0

    merged["pct_change"] = merged.apply(pct_row, axis=1)
    
    def label_row(r):
        if r["pct_change"] == np.inf:
            return "new"
        if r["pct_change"] > 0:
            return "up"
        if r["pct_change"] < 0:
            return "down"
        return "same"
    
    merged["change"] = merged.apply(label_row, axis=1)
    merged = merged.sort_values(by=["pct_change"], ascending=False, key=lambda s: s.replace(np.inf, 1e18) if isinstance(s, pd.Series) else s)
    return merged

def fmt_pct(v):
    """Formatear porcentaje"""
    if v == np.inf:
        return "∞"
    return f"{v:+.2f}%"

def main():
    # Configuración de página optimizada para Streamlit Cloud
    st.set_page_config(
        page_title="⚔️ Guild Raid Dashboard", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # CSS personalizado
    st.markdown("""
    <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: bold;
            background: linear-gradient(90deg, #FF6B6B, #4ECDC4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            margin-bottom: 2rem;
            color: white;
            text-shadow: none;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1rem;
            border-radius: 10px;
            color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .stDataFrame {
            border-radius: 10px;
            overflow: hidden;
        }
        .plot-container {
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .cloud-badge {
            background: linear-gradient(135deg, #ff6b6b, #4ecdc4);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: bold;
            display: inline-block;
            margin-bottom: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Indicador de Streamlit Cloud
    if IS_STREAMLIT_CLOUD:
        st.markdown('<div class="cloud-badge">🌐 Streamlit Cloud</div>', unsafe_allow_html=True)
    
    # Título principal
    st.markdown('<h1 class="main-header">⚔️ Guild Raid Dashboard</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    db_path = get_db_path()
    if not os.path.exists(db_path):
        st.error(f"❌ No se encontró la BD: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    tables = get_record_tables(conn)
    conn.close()
    
    if not tables:
        st.info("📊 No hay tablas disponibles")
        return
    
    # Sidebar con configuración
    st.sidebar.header("⚙️ Configuración")
    
    # Selector de tablas
    sel_last = st.sidebar.selectbox("Tabla Actual", tables, index=len(tables)-1)
    sel_prev = st.sidebar.selectbox("Tabla Anterior", tables, index=max(0, len(tables)-2) if len(tables) >= 2 else 0)
    top_n = st.sidebar.number_input("Top N jugadores", min_value=0, value=10, step=1)
    
    # Cargar datos
    conn = sqlite3.connect(db_path)
    last_df = load_table(conn, sel_last)
    prev_df = load_table(conn, sel_prev)
    conn.close()
    
    if last_df.empty or prev_df.empty:
        st.error("❌ No se pudieron cargar los datos")
        return
    
    # Participación actual
    total = last_df["damage"].sum()
    agg_last = aggregate(last_df).sort_values("damage", ascending=False).reset_index(drop=True)
    agg_last["pct"] = agg_last["damage"] / total * 100.0 if total > 0 else 0.0
    
    # Métricas principales
    st.markdown("### 📈 Resumen General")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3 style="margin: 0; color: white;">⚔️ Total Damage</h3>
            <p style="font-size: 1.5rem; margin: 0; color: white;">{total:,}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3 style="margin: 0; color: white;">👥 Jugadores</h3>
            <p style="font-size: 1.5rem; margin: 0; color: white;">{len(agg_last)}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        avg_damage = total // len(agg_last) if len(agg_last) > 0 else 0
        st.markdown(f"""
        <div class="metric-card">
            <h3 style="margin: 0; color: white;">📊 Promedio</h3>
            <p style="font-size: 1.5rem; margin: 0; color: white;">{avg_damage:,}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <h3 style="margin: 0; color: white;">🎯 Top Player</h3>
            <p style="font-size: 1.2rem; margin: 0; color: white;">{agg_last.iloc[0]['name'] if len(agg_last) > 0 else 'N/A'}</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Tabla de participación con rounds
    display = agg_last.head(top_n) if top_n > 0 else agg_last
    display = display.copy()
    display["pct"] = display["pct"].map(lambda v: f"{v:.2f}%")
    
    # Obtener rounds de cada jugador
    rounds_data = pd.read_sql_query(f'SELECT username, rounds FROM "{sel_last}"', conn)
    rounds_data['rounds'] = rounds_data['rounds'].fillna('N/A')
    rounds_data['name'] = rounds_data['username'].astype(str).str.upper()
    
    display = display.merge(rounds_data[['name', 'rounds']], on='name', how='left')
    display['rounds'] = display['rounds'].fillna('N/A')
    
    st.subheader("📋 Participación por Jugador")
    st.dataframe(display.rename(columns={
        "name": "Jugador", 
        "damage": "Daño", 
        "pct": "% Participación",
        "rounds": "Rounds"
    }), use_container_width=True)
    
    # Gráficos de distribución
    st.markdown("### 🎯 Distribución del Daño")
    col1, col2 = st.columns(2)
    
    with col1:
        fig_pie = px.pie(
            agg_last.head(10), 
            values='damage', 
            names='name',
            title='Top 10 Players - Distribución de Daño',
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(showlegend=True, height=400)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        fig_bar = px.bar(
            agg_last.head(10).sort_values('damage', ascending=True),
            x='damage', 
            y='name',
            title='Top 10 Players - Daño Total',
            orientation='h',
            color='damage',
            color_continuous_scale='viridis'
        )
        fig_bar.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("---")
    
    # Comparación de daño
    st.markdown("### 📈 Comparación de Daño: Raid Anterior vs Actual")
    st.write(f"📊 Comparando: `{sel_prev}` → `{sel_last}`")
    comp = compute_comparison(prev_df, last_df)
    
    # Resumen rápido
    increased = (comp["change"] == "up").sum()
    decreased = (comp["change"] == "down").sum()
    new_players = (comp["change"] == "new").sum()
    st.write(f"🔼 {increased} incrementos — 🔽 {decreased} decrementos — 🆕 {new_players} nuevos")
    
    # Tabla de comparación con iconos
    comp_display = comp.copy()
    comp_display["pct_change"] = comp_display["pct_change"].map(fmt_pct)
    
    icon_map = {
        "up": "🔼",
        "down": "🔽", 
        "new": "🆕",
        "same": "⏺"
    }
    comp_display["Tipo"] = comp_display["change"].map(icon_map)
    comp_display = comp_display.rename(columns={
        "name": "Jugador", 
        "prev_damage": "Anterior", 
        "last_damage": "Actual", 
        "pct_change": "% Cambio"
    })
    comp_display_show = comp_display.head(top_n) if top_n > 0 else comp_display
    
    columns_order = ["Tipo", "Jugador", "Anterior", "Actual", "% Cambio"]
    st.dataframe(
        comp_display_show[columns_order], 
        use_container_width=True,
        column_config={
            "Tipo": st.column_config.TextColumn("Tendencia", width=None)
        }
    )
    
    # Gráficos de tendencias
    st.markdown("### 📈 Análisis de Tendencias")
    col1, col2 = st.columns(2)
    
    top_up = comp[comp["change"] == "up"].nlargest(10, "pct_change")
    top_down = comp[comp["change"] == "down"].nsmallest(10, "pct_change")
    
    with col1:
        if not top_up.empty:
            fig_up = go.Figure(data=[
                go.Bar(
                    x=top_up['name'],
                    y=top_up['pct_change'],
                    marker_color='lightgreen',
                    text=top_up['pct_change'].apply(lambda x: f"{x:+.1f}%"),
                    textposition='auto',
                )
            ])
            fig_up.update_layout(
                title='🚀 Top 10 Mayores Incrementos (%)',
                xaxis_title='Jugador',
                yaxis_title='Cambio Porcentual',
                height=400,
                showlegend=False
            )
            st.plotly_chart(fig_up, use_container_width=True)
        else:
            st.info("🚀 No hay incrementos detectados.")
    
    with col2:
        if not top_down.empty:
            fig_down = go.Figure(data=[
                go.Bar(
                    x=top_down['name'],
                    y=top_down['pct_change'],
                    marker_color='lightcoral',
                    text=top_down['pct_change'].apply(lambda x: f"{x:+.1f}%"),
                    textposition='auto',
                )
            ])
            fig_down.update_layout(
                title='📉 Top 10 Mayores Decrementos (%)',
                xaxis_title='Jugador',
                yaxis_title='Cambio Porcentual',
                height=400,
                showlegend=False
            )
            st.plotly_chart(fig_down, use_container_width=True)
        else:
            st.info("📉 No hay decrementos detectados.")
    
    # Nota explicativa
    st.markdown("""
    <div style="background: #667eea; padding: 1rem; border-radius: 10px; color: white; margin-top: 1rem; width: 100%;">
        <p style="margin: 0; font-size: 0.9rem;">💡 <strong>Nota:</strong> Esta comparación muestra la diferencia del daño de cada jugador entre la raid anterior y la pasada.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sección de jugadores más activos (21/21 rounds)
    st.markdown("### 🏆 Jugadores Más Activos (21/21 Rounds)")
    
    # Obtener datos de rounds
    rounds_data = pd.read_sql_query(f'SELECT username, rounds, damage FROM "{sel_last}"', conn)
    rounds_data['rounds'] = rounds_data['rounds'].fillna('N/A')
    active_players = rounds_data[rounds_data['rounds'] == '21/21'].copy()
    
    if not active_players.empty:
        # Ordenar por damage
        active_players = active_players.sort_values('damage', ascending=False)
        active_players['formatted_damage'] = active_players['damage'].apply(lambda x: f"{x:,}")
        
        # Métricas de jugadores activos
        total_active = len(active_players)
        total_active_damage = active_players['damage'].sum()
        avg_active_damage = total_active_damage // total_active if total_active > 0 else 0
        
        # Mostrar métricas
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 1rem; border-radius: 10px; color: white; text-align: center;">
                <h4 style="margin: 0;">🎯 Jugadores 21/21</h4>
                <p style="font-size: 1.8rem; margin: 0;">{total_active}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 1rem; border-radius: 10px; color: white; text-align: center;">
                <h4 style="margin: 0;">⚡ Damage Total</h4>
                <p style="font-size: 1.8rem; margin: 0;">{total_active_damage:,}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); padding: 1rem; border-radius: 10px; color: white; text-align: center;">
                <h4 style="margin: 0;">📊 Promedio</h4>
                <p style="font-size: 1.8rem; margin: 0;">{avg_active_damage:,}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Tabla de jugadores activos
        st.markdown("#### 🏅 Ranking de Jugadores Activos")
        
        display_active = active_players[['username', 'formatted_damage']].copy()
        display_active.columns = ['Jugador', 'Damage Formateado']
        
        display_active['Posición'] = range(1, len(display_active) + 1)
        display_active = display_active[['Posición', 'Jugador', 'Damage Formateado']]
        
        st.dataframe(
            display_active,
            column_config={
                "Posición": st.column_config.NumberColumn(format="%d"),
                "Damage Formateado": st.column_config.TextColumn("Damage")
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Gráfico de barras para jugadores activos
        fig_active = px.bar(
            active_players.head(15).sort_values('damage', ascending=True),
            x='damage',
            y='username',
            orientation='h',
            title='🏆 Top 15 Jugadores Activos (21/21)',
            color='damage',
            color_continuous_scale='plasma',
            labels={'damage': 'Damage', 'username': 'Jugador'}
        )
        fig_active.update_layout(height=600, showlegend=False)
        st.plotly_chart(fig_active, use_container_width=True)
        
        # Porcentaje de participación
        active_participation = (total_active / len(agg_last)) * 100
        st.markdown(f"""
        #### 📈 Participación
        **{active_participation:.1f}%** de los jugadores completaron todos sus ataques (21/21)
        """)
    else:
        st.info("🔍 No se encontraron jugadores con 21/21 rounds en esta raid.")

if __name__ == "__main__":
    main()
