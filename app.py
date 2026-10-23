import streamlit as st
from PIL import Image

# Configurazione della pagina
st.set_page_config(
    page_title="CAD Assistant — Proiezioni Ortogonali Universali",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Stile CSS personalizzato
st.markdown("""
    <style>
    .stApp {
        background: radial-gradient(circle at 10% 20%, #0f172a 0%, #020617 90%);
        color: #f1f5f9;
        font-family: 'Inter', sans-serif;
    }
    .card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(12px);
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

# Gestione dello stato di autenticazione e navigazione
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "current_step" not in st.session_state:
    st.session_state.current_step = 1

if "drawing_data" not in st.session_state:
    st.session_state.drawing_data = {
        "base": 24,
        "altezza": 30,
        "profondita": 20,
        "tipo": "Prisma / Solido Geometrico"
    }

# --- SCHERMATA DI LOGIN ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center; margin-bottom: 25px;'>📐 CAD ASSISTANT — PROIEZIONI ORTOGONALI</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center; color: #38bdf8;'>ACCESSO SVILUPPATORE</h3>", unsafe_allow_html=True)
            username_input = st.text_input("Nome Utente").strip()
            password_input = st.text_input("Password", type="password")
            
            submit_login = st.form_submit_button("Accedi al Sistema", use_container_width=True)
            
            if submit_login:
                if username_input == "DEV" and password_input == "sviluppatore@":
                    st.session_state.logged_in = True
                    st.success("Accesso effettuato con successo!")
                    st.rerun()
                else:
                    st.error("Credenziali errate. Usa DEV e sviluppatore@")
    st.stop()

# --- INTERFACCIA PRINCIPALE ---
st.sidebar.markdown("""
    <div style='background: rgba(30, 41, 59, 0.5); padding: 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); margin-bottom: 20px;'>
        <div style='font-size: 0.75rem; color: #38bdf8; font-weight: 600; text-transform: uppercase;'>Area Riservata</div>
        <div style='font-size: 1.05rem; font-weight: 700; color: #f8fafc; margin-top: 2px;'>📐 CAD Assistant Universal</div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.markdown("👤 **Utente:** `DEV`")
st.sidebar.markdown("Ruolo: `Sviluppatore / Tutor`")
st.sidebar.markdown("---")

menu = st.sidebar.radio("Navigazione", ["📸 Carica Qualsiasi Traccia", "🧭 Guida Passo-Passo (Frecce)", "ℹ️ Informazioni"])

if st.sidebar.button("🔒 Effettua il Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# 1. CARICA QUALSIASI TRACCIA E CONFIGURA
if menu == "📸 Carica Qualsiasi Traccia":
    st.title("📸 Acquisizione e Parametri del Disegno")
    st.write("Carica la foto di **qualsiasi nuova esercitazione** o disegno tecnico e imposta le quote principali rilevate dalla traccia.")
    
    uploaded_file = st.file_uploader("Carica immagine della nuova traccia", type=["jpg", "jpeg", "png"])
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Nuova Traccia Acquisita", use_column_width=True)
        else:
            st.info("💡 Carica qui la foto di un qualsiasi solido o esercitazione da proiettare.")
            
    with col_b:
        st.markdown("### ⚙️ Configurazione Quote per il Calcolo")
        with st.form("params_form"):
            tipo_solido = st.text_input("Descrizione / Nome Solido", value=st.session_state.drawing_data["tipo"])
            base_val = st.number_input("Larghezza / Base principale (mm)", value=st.session_state.drawing_data["base"])
            altezza_val = st.number_input("Altezza principale (mm)", value=st.session_state.drawing_data["altezza"])
            prof_val = st.number_input("Profondità / Spessore (mm)", value=st.session_state.drawing_data["profondita"])
            
            save_params = st.form_submit_button("💾 Salva e Genera Proiezioni", use_container_width=True)
            
            if save_params:
                st.session_state.drawing_data = {
                    "base": base_val,
                    "altezza": altezza_val,
                    "profondita": prof_val,
                    "tipo": tipo_solido
                }
                st.success("Parametri salvati con successo! L'assistente è pronto con le nuove misure.")

# 2. GUIDA PASSO-PASSO DINAMICA CON FRECCE
elif menu == "🧭 Guida Passo-Passo (Frecce)":
    st.title("🧭 Guida Interattiva Universale")
    data = st.session_state.drawing_data
    st.write(f"Stai lavorando sul solido: **{data['tipo']}** (Base: {data['base']}mm, Altezza: {data['altezza']}mm, Profondità: {data['profondita']}mm). Segui i passi per completare il disegno.")
    
    # Generazione dinamica dei passi basata sulle quote inserite
    steps = [
        {
            "title": "Step 1: Squadratura e Linea di Terra (L.T.)",
            "desc": "Traccia la squadratura del foglio F4. Posiziona la **Linea di Terra (L.T.)** in modo da lasciare equzio spazio per disporre il Piano Verticale (PV) in alto e il Piano Orizzontale (PO) in basso."
        },
        {
            "title": f"Step 2: Proiezione sul Piano Verticale (PV) — Base {data['base']} mm",
            "desc": f"Disegna la vista frontale principale sul PV rispettando la larghezza di **{data['base']} mm** e l'altezza proporzionata. Scrivi le quote esatte affianco a ogni linea guida."
        },
        {
            "title": f"Step 3: Riporto sul Piano Orizzontale (PO) — Profondità {data['profondita']} mm",
            "desc": f"Proietta verticalmente le linee verso il basso oltre la Linea di Terra e imposta la profondità complessiva del solido a **{data['profondita']} mm**."
        },
        {
            "title": "Step 4: Dettagli Interni, Assi e Parti Nascoste",
            "desc": "Aggiungi eventuali fori, cavità o linee tratteggiate interne richieste dalla traccia, mantenendo il perfetto allineamento tra pianta e fronte."
        },
        {
            "title": "Step 5: Completamento del Piano Laterale (PL) e Verifica Finale",
            "desc": "Ribalta le misure sul Piano Laterale tramite linee a 45° o compasso. Esegui un controllo generale di tutte le quote e del tratto di matita per ottenere il disegno finale pulito."
        }
    ]
    
    # Pulsanti di controllo passo
    col_prev, col_indicator, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("⬅️ Indietro", use_container_width=True) and st.session_state.current_step > 1:
            st.session_state.current_step -= 1
            st.rerun()
            
    with col_indicator:
        st.markdown(f"<h3 style='text-align: center; color: #38bdf8;'>Passo {st.session_state.current_step} di {len(steps)}</h3>", unsafe_allow_html=True)
        
    with col_next:
        if st.button("Avanti ➡️", use_container_width=True) and st.session_state.current_step < len(steps):
            st.session_state.current_step += 1
            st.rerun()
            
    # Mostra il box dello step corrente
    curr = steps[st.session_state.current_step - 1]
    st.markdown(f"""
        <div class='step-box'>
            <h3>{curr['title']}</h3>
            <p style='font-size: 1.1rem; line-height: 1.6;'>{curr['desc']}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Barra di avanzamento
    st.progress(st.session_state.current_step / len(steps))

# 3. INFORMAZIONI
elif menu == "ℹ️ Informazioni":
    st.title("ℹ️ Informazioni su CAD Assistant Universal")
    st.markdown("""
    Questa versione universale dell'app ti consente di affrontare **qualsiasi esercitazione di disegno geometrico**:
    * **Caricamento flessibile:** Funziona con qualsiasi foto o scansione di libri di disegno tecnico.
    * **Adattamento delle quote:** Inserisci le misure specifiche della consegna e l'app adatterà la sequenza di lavoro passo-passo.
    * **Autore / Sviluppatore:** `DEV`
    """)
