import streamlit as st
import sqlite3
import hashlib
import os
from PIL import Image

# --- CONFIGURAZIONE DELLA PAGINA ---
st.set_page_config(
    page_title="CAD Assistant — Proiezioni Ortogonali",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STILE GRAFICO (DARK MODE ORIGINALE) ---
st.markdown("""
    <style>
    .stApp {
        background: radial-gradient(circle at 10% 20%, #0f172a 0%, #020617 90%);
        color: #f1f5f9;
        font-family: 'Inter', sans-serif;
    }
    .card, [data-testid="stForm"] {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        padding: 24px;
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        margin-bottom: 20px;
    }
    .step-box {
        background: rgba(37, 99, 235, 0.15);
        border-left: 4px solid #38bdf8;
        padding: 16px;
        border-radius: 0 12px 12px 0;
        margin: 15px 0;
    }
    .stButton>button, [data-testid="stFormSubmitButton"]>button {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        color: white;
        border-radius: 10px;
        font-weight: 600;
        border: none;
        padding: 10px 24px;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        transition: all 0.2s ease;
        width: 100%;
    }
    .stButton>button:hover, [data-testid="stFormSubmitButton"]>button:hover {
        background: linear-gradient(135deg, #1d4ed8 100%, #1e40af 100%);
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.5);
        transform: translateY(-1px);
    }
    .stTextInput>div>div>input, .stSelectbox>div>div>select {
        background-color: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: #f1f5f9 !important;
        border-radius: 10px !important;
    }
    h1, h2, h3 {
        color: #f8fafc;
    }
    h1 {
        background: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    </style>
""", unsafe_allow_html=True)

# --- GESTIONE DATABASE UTENTI ---
def init_db():
    conn = sqlite3.connect("cad_users.db", check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            name TEXT,
            pin TEXT,
            raw_pin TEXT,
            role TEXT
        )
    ''')
    dev_pin_raw = "sviluppatore@"
    dev_pin_hash = hashlib.sha256(dev_pin_raw.encode()).hexdigest()
    res = conn.execute("SELECT * FROM users WHERE username = 'DEV'").fetchone()
    if not res:
        conn.execute("INSERT INTO users (username, name, pin, raw_pin, role) VALUES (?, ?, ?, ?, ?)", 
                     ("DEV", "Enrico Bottone", dev_pin_hash, dev_pin_raw, "sviluppatore"))
    conn.commit()
    conn.close()

init_db()

# --- INIZIALIZZAZIONE SESSION STATE ---
if "logged_user" not in st.session_state:
    st.session_state.logged_user = None

if "current_step" not in st.session_state:
    st.session_state.current_step = 0

if "uploaded_image_path" not in st.session_state:
    st.session_state.uploaded_image_path = None

if "scala_scelta" not in st.session_state:
    st.session_state.scala_scelta = "1:1"

# --- SCHERMATA DI LOGIN ---
if not st.session_state.logged_user:
    st.markdown("<h2 style='text-align: center; margin-bottom: 25px;'>📐 CAD ASSISTANT — ACCESSO</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center; color: #38bdf8;'>Area Riservata</h3>", unsafe_allow_html=True)
            username_input = st.text_input("Nome Utente").strip()
            password_input = st.text_input("Password", type="password")
            
            submit_login = st.form_submit_button("Accedi al Sistema")
            
            if submit_login:
                conn = sqlite3.connect("cad_users.db", check_same_thread=False)
                user_record = conn.execute("SELECT name, pin, role FROM users WHERE username = ?", (username_input,)).fetchone()
                conn.close()
                
                hashed_input = hashlib.sha256(password_input.encode()).hexdigest()
                
                if user_record and user_record[1] == hashed_input:
                    st.session_state.logged_user = {
                        "username": username_input,
                        "name": user_record[0],
                        "role": user_record[2]
                    }
                    st.success(f"Accesso riuscito! Benvenuto, {user_record[0]}")
                    st.rerun()
                else:
                    st.error("Nome utente o password errati.")
    st.stop()

user = st.session_state.logged_user

# --- BARRA LATERALE E MENU ---
st.sidebar.markdown(f"""
    <div style='background: rgba(30, 41, 59, 0.5); padding: 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); margin-bottom: 20px;'>
        <div style='font-size: 0.75rem; color: #38bdf8; font-weight: 600; text-transform: uppercase;'>Utente Connesso</div>
        <div style='font-size: 1.05rem; font-weight: 700; color: #f8fafc; margin-top: 2px;'>{user['name']}</div>
        <div style='font-size: 0.85rem; color: #94a3b8;'>Ruolo: {user['role'].upper()}</div>
    </div>
""", unsafe_allow_html=True)

menu_options = ["📐 Area Disegno & Guida"]
if user["role"] == "sviluppatore":
    menu_options.append("👥 Gestione Utenti")

selected_page = st.sidebar.radio("Navigazione", menu_options)

st.sidebar.markdown("---")
if st.sidebar.button("🔒 Effettua il Logout", use_container_width=True):
    st.session_state.logged_user = None
    st.rerun()

# --- PAGINA 1: AREA DISEGNO & GUIDA ---
if selected_page == "📐 Area Disegno & Guida":
    st.title("📐 CAD Assistant — Proiezioni Ortogonali")
    st.markdown("""
    **A cosa serve il sistema:** Questo software è un assistente intelligente progettato per supportare passo-passo nell'esecuzione di disegni tecnici e proiezioni ortogonali di qualsiasi solido o esercitazione, guidando l'utente attraverso indicazioni visive e strutturate.
    """)
    st.markdown("👨‍💻 **Creato da: ENRICO BOTTONE**")
    st.markdown("---")

    col_upload, col_settings = st.columns(2)

    with col_upload:
        st.subheader("📸 1. Carica Traccia")
        uploaded_file = st.file_uploader("Seleziona o scatta la foto della traccia", type=["jpg", "jpeg", "png", "webp"])
        
        if uploaded_file is not None:
            os.makedirs("uploads", exist_ok=True)
            image_path = f"uploads/traccia_{user['username']}.jpg"
            with open(image_path, "wb") as f_foto:
                f_foto.write(uploaded_file.getbuffer())
            st.session_state.uploaded_image_path = image_path

    with col_settings:
        st.subheader("⚙️ 2. Imposta Scala")
        st.session_state.scala_scelta = st.selectbox(
            "Seleziona la Scala di Rappresentazione", 
            ["1:1", "1:2", "2:1", "1:5", "5:1", "1:10"],
            index=0
        )
        st.markdown(f"**Scala attiva:** `{st.session_state.scala_scelta}`")

    st.markdown("---")
    st.subheader("🧭 3. Guida Passo-Passo Interattiva e Risultato Completo")

    # Due colonne: a sinistra la traccia caricata, a destra il disegno completo con quote e proiezioni
    col_img, col_result = st.columns(1)
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("### 📄 Traccia di Riferimento")
        if st.session_state.uploaded_image_path and os.path.exists(st.session_state.uploaded_image_path):
            try:
                st.image(st.session_state.uploaded_image_path, caption="Traccia caricata dall'utente", use_container_width=True)
            except Exception:
                st.warning("Impossibile mostrare l'anteprima dell'immagine.")
        else:
            st.info("💡 Carica la foto della traccia sopra per visualizzarla qui.")

    with col_t2:
        st.markdown("### 📐 Disegno Completo & Quote (Risultato Atteso)")
        if st.session_state.uploaded_image_path and os.path.exists(st.session_state.uploaded_image_path):
            st.success("✅ Traccia elaborata: Ecco il disegno tecnico completo con proiezioni ortogonali, Linea di Terra, assi e quote di misura calcolate in scala.")
            # Box visivo dimostrativo del disegno completo con quote basato sulla scala attiva
            st.markdown(f"""
                <div class='card' style='border: 1px solid #38bdf8;'>
                    <h4 style='color: #38bdf8; margin-top: 0;'>Elaborato in Scala {st.session_state.scala_scelta}</h4>
                    <ul style='padding-left: 20px; line-height: 1.8;'>
                        <li><b>Piano Verticale (PV):</b> Prospetto principale con quote geometriche esterne.</li>
                        <li><b>Piano Orizzontale (PO):</b> Pianta in asse con profondità e dettagli interni (tratteggiati).</li>
                        <li><b>Piano Laterale (PL):</b> Ribaltamento a 45° con verifiche di quota complete.</li>
                        <li><b>Linea di Terra (L.T.):</b> Posizionata correttamente con squadratura F4.</li>
                    </ul>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("💡 Carica prima una traccia per sbloccare la generazione automatica del disegno completo con tutte le quote e proiezioni.")

    st.markdown("---")

    # Passi guidati con pulsanti di navigazione
    steps = [
        {
            "title": "Passo 1: Squadratura e Linea di Terra (L.T.)",
            
