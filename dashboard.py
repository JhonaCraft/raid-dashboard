import os
import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def get_db_path():
    # Detectar si estamos en Streamlit Cloud
    if os.getenv('STREAMLIT_CLOUD', 'False').lower() == 'true':
        return "txt_data.db"
    else:
        return os.path.join(os.path.dirname(__file__), "txt_data.db")

def get_record_tables(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name")
    rows = [r[0] for r in cur.fetchall()]
    return rows

def load_table(conn, table):
    df = pd.read_sql_query(f'SELECT username, damage FROM "{table}"', conn)
    df["damage"] = pd.to_numeric(df["damage"], errors="coerce").fillna(0).astype("int64")
    # normalizar nombres a mayúsculas para evitar sensibilidad en la comparación
    df["name"] = df["username"].astype(str).str.upper()
    return df

def aggregate(df):
    # agrupar por nombre (ya en mayúsculas) y sumar daño
    agg = df.groupby("name", as_index=False)["damage"].sum()
    return agg

def compute_comparison(prev_df, last_df):
    # ambas tablas ya tienen nombres normalizados en load_table
    a = aggregate(prev_df).rename(columns={"damage": "prev_damage"})
    b = aggregate(last_df).rename(columns={"damage": "last_damage"})
    merged = pd.merge(a, b, on="name", how="outer").fillna(0)
    merged["prev_damage"] = merged["prev_damage"].astype("int64")
    merged["last_damage"] = merged["last_damage"].astype("int64")

    # pct change: if prev>0 compute, if prev==0 and last>0 mark as inf/new
    def pct_row(row):
        pv = row["prev_damage"]
        ls = row["last_damage"]
        if pv > 0:
            return (ls - pv) / pv * 100.0
        if pv == 0 and ls > 0:
            return np.inf
        return 0.0

    merged["pct_change"] = merged.apply(pct_row, axis=1)
    # label change
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
    if v == np.inf:
        return "∞"
    return f"{v:+.2f}%"

def main():
    # Configuración de la página con tema personalizado
    st.set_page_config(
        page_title="⚔️ Guild Raid Dashboard", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # CSS personalizado para mejor apariencia
    st.markdown("""
    <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: bold;
            background: linear-gradient(90deg, #FF6B6B, #4ECDC4);
            -webkit-background-clip: text;
            
            text-align: center;
            margin-bottom: 2rem;
            color: white;
            text-shadow: none; /* Eliminar sombras */
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
    </style>
    """, unsafe_allow_html=True)
    
    # Título principal
    st.markdown('<h1 class="main-header">⚔️ Guild Raid Dashboard</h1>', unsafe_allow_html=True)
    st.markdown("---")

    db_path = get_db_path()
    if not os.path.exists(db_path):
        st.error(f"No se encontró la BD: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    tables = get_record_tables(conn)
    if not tables:
        st.info("No hay tablas en la BD.")
        conn.close()
        return

    # Sidebar: elegir tablas para comparar (por defecto las últimas dos)
    st.sidebar.header("Comparación / selección")
    default_last = tables[-1]
    default_prev = tables[-2] if len(tables) >= 2 else tables[-1]
    sel_last = st.sidebar.selectbox("Tabla última", tables, index=len(tables)-1)
    sel_prev = st.sidebar.selectbox("Tabla anterior", tables, index=max(0, len(tables)-2))
    top_n = st.sidebar.number_input("Top N jugadores (0 = todos)", min_value=0, value=10, step=1)

    # Cargar datos
    last_df = load_table(conn, sel_last)
    prev_df = load_table(conn, sel_prev)

    # Participación actual (última tabla)
    total = last_df["damage"].sum()
    agg_last = aggregate(last_df).sort_values("damage", ascending=False).reset_index(drop=True)
    agg_last["pct"] = agg_last["damage"] / total * 100.0 if total > 0 else 0.0

    # Métricas principales con diseño mejorado
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

    # Mostrar participación
    display = agg_last.head(top_n) if top_n > 0 else agg_last
    display = display.copy()
    display["pct"] = display["pct"].map(lambda v: f"{v:.2f}%")
    # Obtener rounds de cada jugador
    rounds_data = pd.read_sql_query(f'SELECT username, rounds FROM "{sel_last}"', conn)
    rounds_data['rounds'] = rounds_data['rounds'].fillna('N/A')
    # Normalizar nombres en rounds_data a mayúsculas
    rounds_data['name'] = rounds_data['username'].astype(str).str.upper()
    # Unir rounds con el display usando el nombre normalizado
    display = display.merge(rounds_data[['name', 'rounds']], on='name', how='left')
    display['rounds'] = display['rounds'].fillna('N/A')
    st.subheader("Participación por jugador (última tabla)")
    st.dataframe(display.rename(columns={
        "name": "Jugador", 
        "damage": "Daño", 
        "pct": "% Participación",
        "rounds": "Rounds"
    }), use_container_width=True)
    #st.bar_chart(agg_last.set_index("name")["pct"])

    # Gráfico de pastel para participación
    st.markdown("### 🎯 Distribución del Daño")
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de pastel interactivo
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
        # Gráfico de barras horizontal
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

    # Comparación / Tendencias
    st.markdown("---")
    st.subheader("Tendencias: comparación entre tablas")
    st.write(f"Comparando: `{sel_prev}` → `{sel_last}`")
    comp = compute_comparison(prev_df, last_df)

    # resumen rápido
    increased = (comp["change"] == "up").sum()
    decreased = (comp["change"] == "down").sum()
    new_players = (comp["change"] == "new").sum()
    st.write(f"↑ {increased} incrementos — ↓ {decreased} decrementos — ✨ {new_players} nuevos (prev=0)")

    # Mostrar tabla de comparación con formato
    comp_display = comp.copy()
    comp_display["pct_change"] = comp_display["pct_change"].map(fmt_pct)
    # Mapear tipos a iconos
    icon_map = {
        "up": "🔼",
        "down": "🔽", 
        "new": "🆕",
        "same": "⏺"
    }
    comp_display["Tipo"] = comp_display["change"].map(icon_map)
    comp_display = comp_display.rename(columns={
        "name": "Jugador", 
        "prev_damage": "Prev (daño)", 
        "last_damage": "Last (daño)", 
        "pct_change": "% Cambio"
    })
    comp_display_show = comp_display.head(top_n) if top_n > 0 else comp_display
    # Reordenar columnas para poner "Tipo" primero
    columns_order = ["Tipo", "Jugador", "Prev (daño)", "Last (daño)", "% Cambio"]
    st.dataframe(
        comp_display_show[columns_order], 
        use_container_width=True,
        column_config={
            "Tipo": st.column_config.TextColumn(
                "Tipo",
                width=None

            )
        }
    )

    # Obtener datos para top mejoras y empeoramientos
    top_up = comp[comp["change"] == "up"].nlargest(10, "pct_change")
    top_down = comp[comp["change"] == "down"].nsmallest(10, "pct_change")

    # Gráficos mejorados con Plotly para tendencias
    st.markdown("### 📈 Análisis de Tendencias")
    col1, col2 = st.columns(2)
    
    with col1:
        if not top_up.empty:
            # Gráfico de barras mejorado para top aumentos
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
            # Gráfico de barras mejorado para top decrementos
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
    st.markdown("""
    <div style="background: #667eea; padding: 1rem; border-radius: 10px; color: white; margin-top: 1rem; width: 100%;">
        <p style="margin: 0; font-size: 0.9rem;">💡 <strong>Nota:</strong> Esta comparación muestra la diferencia del daño de cada jugador entre la raid anterior y la pasada.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # # Gráfico de dispersión para comparación
    # st.markdown("### 🎯 Comparación Detallada")
    # if len(comp) > 0:
    #     # Usar valor absoluto del cambio porcentual para el tamaño
    #     comp['abs_pct_change'] = comp['pct_change'].abs()
    #     # Reemplazar infinitos con un valor grande para el tamaño
    #     comp['abs_pct_change'] = comp['abs_pct_change'].replace(np.inf, 100)
        
    #     fig_scatter = px.scatter(
    #         comp,
    #         x='prev_damage',
    #         y='last_damage',
    #         color='change',
    #         size='abs_pct_change',
    #         hover_data=['name', 'pct_change'],
    #         title='Comparación de Damage: Anterior vs Actual',
    #         color_discrete_map={
    #             'up': 'green',
    #             'down': 'red',
    #             'same': 'gray',
    #             'new': 'blue'
    #         },
    #         labels={
    #             'prev_damage': 'Damage Anterior',
    #             'last_damage': 'Damage Actual',
    #             'change': 'Tendencia',
    #             'pct_change': '% Cambio'
    #         }
    #     )
        
    #     # Línea de referencia (y=x)
    #     fig_scatter.add_shape(
    #         type='line',
    #         x0=0, y0=0,
    #         x1=comp['prev_damage'].max(), y1=comp['prev_damage'].max(),
    #         line=dict(color='black', dash='dash'),
    #         name='Sin cambio'
    #     )
        
    #     fig_scatter.update_layout(height=500)
    #     st.plotly_chart(fig_scatter, use_container_width=True)
    
    # Sección de jugadores más activos (21/21 rounds)
    st.markdown("### 🏆 Jugadores Más Activos (21/21 Rounds)")
    
    # Obtener datos de rounds de la tabla actual
    rounds_data = pd.read_sql_query(f'SELECT username, rounds, damage FROM "{sel_last}"', conn)
    rounds_data['rounds'] = rounds_data['rounds'].fillna('N/A')
    
    # Filtrar jugadores con 21/21
    active_players = rounds_data[rounds_data['rounds'] == '21/21'].copy()
    
    if not active_players.empty:
        # Ordenar por damage
        active_players = active_players.sort_values('damage', ascending=False)
        active_players['formatted_damage'] = active_players['damage'].apply(lambda x: f"{x:,}")
        
        # Métricas de jugadores activos
        total_active = len(active_players)
        total_active_damage = active_players['damage'].sum()
        avg_active_damage = total_active_damage // total_active
        
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
        
        # Porcentaje de participación de jugadores activos
        active_participation = (total_active / len(agg_last)) * 100
        st.markdown(f"""
        #### 📈 Participación
        **{active_participation:.1f}%** de los jugadores completaron todos sus ataques (21/21)
        """)

        # Tabla de jugadores activos
        st.markdown("#### 🏅 Ranking de Jugadores Activos")
        
        # Crear tabla formateada
        display_active = active_players[['username', 'formatted_damage']].copy()
        display_active.columns = ['Jugador', 'Damage Formateado']
        
        # Añadir posición en el ranking
        display_active['Posición'] = range(1, len(display_active) + 1)
        display_active = display_active[['Posición', 'Jugador', 'Damage Formateado']]
        

        # Aplicar estilo a la tabla
        st.dataframe(
            display_active,
            column_config={
                "Posición": st.column_config.NumberColumn(format="%d"),
                #"Damage": st.column_config.NumberColumn(format="%,d"),
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
        
        
        
    else:
        st.info("🔍 No se encontraron jugadores con 21/21 rounds en esta raid.")

    conn.close()

if __name__ == "__main__":
    main()