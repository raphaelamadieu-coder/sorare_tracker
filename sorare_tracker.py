import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import plotly.graph_objects as go

# ==============================
# CONFIGURATION
# ==============================
SEASON = 2024
TOP_N = 50
API_URL = "https://api.sorare.com/graphql"
COINBASE_API = "https://api.coinbase.com/v2/exchange-rates?currency=ETH"

# Sur Streamlit Cloud, on stocke les CSV dans ./data pour persistance
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
HISTO_FILE = os.path.join(DATA_DIR, "historique_prices.csv")
JOUERS_FILE = os.path.join(DATA_DIR, "joueurs_suivi.csv")

# ==============================
# UTILITAIRES
# ==============================
@st.cache_data(ttl=300)
def get_eth_to_eur():
    try:
        res = requests.get(COINBASE_API)
        return float(res.json()["data"]["rates"]["EUR"])
    except:
        return 0.0

def get_top_players(limit=50):
    query = """
    query TopPlayers($first: Int!) {
      players(first: $first) {
        nodes {
          displayName
          slug
        }
      }
    }
    """
    variables = {"first": limit}
    response = requests.post(API_URL, json={"query": query, "variables": variables})
    data = response.json()
    return [(p["displayName"], p["slug"]) for p in data["data"]["players"]["nodes"]]

def get_slug_from_name(player_name):
    query = """
    query search($query: String!) {
      search(query: $query, types: [PLAYER], first: 1) {
        edges {
          node {
            ... on Player {
              displayName
              slug
            }
          }
        }
      }
    }
    """
    variables = {"query": player_name}
    response = requests.post(API_URL, json={"query": query, "variables": variables})
    data = response.json()
    try:
        edges = data["data"]["search"]["edges"]
        if not edges:
            return None
        return edges[0]["node"]["slug"]
    except:
        return None

def get_floor_price(slug, season=None):
    query = """
    query PlayerFloor($slug: String!, $season: Int) {
      player(slug: $slug) {
        displayName
        cards(rarities: [limited], seasonStartYear: $season, first: 10) {
          nodes {
            liveSingleSaleOffer {
              price
            }
          }
        }
      }
    }
    """
    variables = {"slug": slug, "season": season}
    response = requests.post(API_URL, json={"query": query, "variables": variables})
    data = response.json()
    try:
        player_name = data["data"]["player"]["displayName"]
        offers = data["data"]["player"]["cards"]["nodes"]
        prices = [float(o["liveSingleSaleOffer"]["price"]) for o in offers if o["liveSingleSaleOffer"]]
        if not prices:
            return player_name, None
        return player_name, min(prices)
    except:
        return slug, None

def update_historique(player, type_carte, price_eth):
    now = datetime.now()
    df_new = pd.DataFrame([{
        "Date": now,
        "Joueur": player,
        "Type": type_carte,
        "Prix ETH": price_eth
    }])
    if os.path.exists(HISTO_FILE):
        df_old = pd.read_csv(HISTO_FILE, parse_dates=["Date"])
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    df_all.to_csv(HISTO_FILE, index=False)
    return df_all

def get_data_7j(player, type_carte):
    if not os.path.exists(HISTO_FILE):
        return pd.DataFrame()
    df = pd.read_csv(HISTO_FILE, parse_dates=["Date"])
    limite = datetime.now() - timedelta(days=7)
    return df[(df["Joueur"]==player) & (df["Type"]==type_carte) & (df["Date"]>=limite)]

def plot_comparatif(player, eth_to_eur):
    df_in = get_data_7j(player, "In Season")
    df_classic = get_data_7j(player, "Classic")
    fig = go.Figure()
    if not df_in.empty:
        fig.add_trace(go.Scatter(
            x=df_in["Date"], y=df_in["Prix ETH"]*eth_to_eur,
            mode='lines+markers', name="In Season",
            line=dict(color="blue"), marker=dict(size=6)
        ))
        moy_in = df_in["Prix ETH"].mean()*eth_to_eur
        fig.add_trace(go.Scatter(
            x=[df_in["Date"].min(), df_in["Date"].max()],
            y=[moy_in, moy_in], mode='lines',
            name="Moyenne 7j In Season", line=dict(color="blue", width=2, dash="dash")
        ))
    if not df_classic.empty:
        fig.add_trace(go.Scatter(
            x=df_classic["Date"], y=df_classic["Prix ETH"]*eth_to_eur,
            mode='lines+markers', name="Classic",
            line=dict(color="orange"), marker=dict(size=6)
        ))
        moy_classic = df_classic["Prix ETH"].mean()*eth_to_eur
        fig.add_trace(go.Scatter(
            x=[df_classic["Date"].min(), df_classic["Date"].max()],
            y=[moy_classic, moy_classic], mode='lines',
            name="Moyenne 7j Classic", line=dict(color="orange", width=2, dash="dash")
        ))
    fig.update_layout(title=f"Evolution Floor Price – {player}",
                      xaxis_title="Date", yaxis_title="Prix (€)",
                      height=350, margin=dict(l=40,r=40,t=40,b=40))
    return fig

# ==============================
# STREAMLIT
# ==============================
st.set_page_config(page_title="Sorare Cloud Tracker", page_icon="⚽", layout="wide")
st.title("⚽ Sorare Tracker – Top + Recherche persistante")

refresh_button = st.button("🔄 Rafraîchir maintenant")
if refresh_button:
    st.cache_data.clear()

eth_to_eur = get_eth_to_eur()

# 1️⃣ Charger joueurs sauvegardés
if os.path.exists(JOUERS_FILE):
    df_joueurs = pd.read_csv(JOUERS_FILE)
    joueurs_sauvegardes = list(zip(df_joueurs["Nom"], df_joueurs["Slug"]))
else:
    joueurs_sauvegardes = []

# 2️⃣ Récupérer Top N joueurs
top_players = get_top_players(TOP_N)

# 3️⃣ Combiner Top + sauvegardés
players = top_players + [j for j in joueurs_sauvegardes if j not in top_players]

# 4️⃣ Ajouter un joueur via recherche
st.subheader("Ajouter un joueur manuellement")
new_player_name = st.text_input("Nom du joueur à ajouter")
if new_player_name:
    slug = get_slug_from_name(new_player_name)
    if slug:
        joueur = (new_player_name, slug)
        if joueur not in players:
            players.append(joueur)
            # Sauvegarde persistante sur Streamlit Cloud
            df_sauvegarde = pd.DataFrame(players, columns=["Nom", "Slug"])
            df_sauvegarde.to_csv(JOUERS_FILE, index=False)
            st.success(f"{new_player_name} ajouté et sauvegardé !")
        else:
            st.info(f"{new_player_name} est déjà suivi.")
    else:
        st.error("Joueur introuvable sur Sorare")

# 5️⃣ Récupérer prix et mise à jour historique
rows = []
for name, slug in players:
    name, price_in = get_floor_price(slug, SEASON)
    update_historique(name, "In Season", price_in if price_in else 0)
    _, price_classic = get_floor_price(slug, None)
    update_historique(name, "Classic", price_classic if price_classic else 0)
    rows.append({
        "Joueur": name,
        "Prix In Season (€)": price_in*eth_to_eur if price_in else None,
        "Prix Classic (€)": price_classic*eth_to_eur if price_classic else None,
        "Dernière mise à jour": datetime.now().strftime("%H:%M:%S")
    })

df = pd.DataFrame(rows)

# 6️⃣ Tableau résumé
st.subheader("Résumé des prix actuels")
st.dataframe(df, use_container_width=True)

# 7️⃣ Graphiques comparatifs
st.subheader("Évolution sur 7 jours")
for name, _ in players:
    fig = plot_comparatif(name, eth_to_eur)
    st.plotly_chart(fig, use_container_width=True)
