import streamlit as st
from PIL import Image
import io

# Configurazione della pagina
st.set_page_config(
    page_title="CAD Assistant — Proiezioni Ortogonali",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Stile CSS con i toni scuri originali
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

# Gestione dello stato dell'applicazione
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "current_step" not in st.session_state:
    st.session_state.current_step = 1

if "uploaded_image_bytes" not in st.session_state:
    st.session_state.uploaded_image_bytes = None

if "scala_scelta" not in st.session_state:
    st.session_state.scala_scelta = "1:1"

# --- SCHERMATA DI ACCESSO ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center; margin-bottom: 25px;'>📐 CAD ASSISTANT — ACCESSO</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center; color: #38bdf8;'>Area Riservata</h3>", unsafe_allow_html=True)
            username_input = st.text_input("Nome Utente").strip()
            password_input = st.text_input("Password", type="password")
            
            submit_login = st.form_submit_button("Accedi al Sistema", use_container_width=True)
            
            if submit_login:
                if username_input == "DEV" and password_input == "sviluppatore@":
                    st.session_state.logged_in = True
                    st.success("Accesso effettuato con successo!")
                    st.rerun()
                else:
                    st.error("Credenziali errate. Riprova.")
    st.stop()

# --- INTERFACCIA PRINCIPALE UNIFICATA ---
st.sidebar.markdown("""
    <div style='background: rgba(30, 41, 59, 0.5); padding: 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); margin-bottom: 20px;'>
        <div style='font-size: 0.75rem; color: #38bdf8; font-weight: 600; text-transform: uppercase;'>Pannello</div>
        <div style='font-size: 1.05rem; font-weight: 700; color: #f8fafc; margin-top: 2px;'>📐 CAD Assistant</div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.markdown("👤 **Utente:** `Attivo`")
st.sidebar.markdown("---")

if st.sidebar.button("🔒 Effettua il Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# Intestazione e informazioni sul sistema
st.title("📐 CAD Assistant — Proiezioni Ortogonali")
st.markdown("""
**A cosa serve il sistema:** Questo software è un assistente intelligente progettato per supportare passo-passo nell'esecuzione di disegni tecnici e proiezioni ortogonali di qualsiasi solido o esercitazione, guidando l'utente attraverso indicazioni visive e strutturate.
""")
st.markdown("👨‍💻 **Creato da: ENRICO BOTTONE**")
st.markdown("---")

# Sezione 1: Caricamento Traccia e Selezione Scala
col_upload, col_settings = st.columns(2)

with col_upload:
    st.subheader("📸 1. Carica Traccia")
    uploaded_file = st.file_uploader("Seleziona o scatta la foto della traccia", type=["jpg", "jpeg", "png", "webp"])
    
    if uploaded_file is not None:
        try:
            # Salvataggio sicuro in memoria dei byte del file
            st.session_state.uploaded_image_bytes = uploaded_file.read()
        except Exception as e:
            st.error(f"Errore nel salvataggio dell'immagine: {e}")

with col_settings:
    st.subheader("⚙️ 2. Imposta Scala")
    st.session_state.scala_scelta = st.selectbox(
        "Seleziona la Scala di Rappresentazione", 
        ["1:1", "1:2", "2:1", "1:5", "5:1", "1:10"],
        index=0
    )
    st.markdown(f"**Scala attiva:** `{st.session_state.scala_scelta}`")

st.markdown("---")
st.subheader("🧭 3. Guida Passo-Passo Interattiva")

# Sezione 2: Guida interattiva con foto affiancata e frecce di scorrimento
col_img, col_guide = st.columns([1, 1.2])

with col_img:
    st.markdown("### 📄 Riferimento Traccia")
    if st.session_state.uploaded_image_bytes is not None:
        try:
            img = Image.open(io.BytesIO(st.session_state.uploaded_image_bytes))
            st.image(img, caption=f"Scala applicata: {st.session_state.scala_scelta}", use_container_width=True)
        except Exception as e:
            st.error("Impossibile visualizzare l'immagine caricata. Riprova a caricarla.")
    else:
        st.info("💡 Carica la foto della traccia sopra per visualizzarla qui come riferimento durante il disegno.")

with col_guide:
    steps = [
        {
            "title": "Passo 1: Squadratura e Linea di Terra (L.T.)",
            "desc": "Posiziona il foglio. Traccia la squadratura e individua la **Linea di Terra (L.T.)**. Dividi lo spazio per disporre il Piano Verticale (PV) in alto e il Piano Orizzontale (PO) in basso."
        },
        {
            "title": "Passo 2: Disegno sul Piano Verticale (PV)",
            "desc": f"Inizia il disegno sul PV applicando la scala **{st.session_state.scala_scelta}**. Riporta le linee principali di contorno e scrivi le quote affianco a ogni elemento."
        },
        {
            "title": "Passo 3: Riporto sul Piano Orizzontale (PO)",
            "desc": "Proietta verticalmente le linee verso il basso superando la Linea di Terra per tracciare la vista dall'alto (pianta), rispettando la profondità del solido."
        },
        {
            "title": "Passo 4: Dettagli Interni e Parti Nascoste",
            "desc": "Aggiungi eventuali fori o dettagli interni con linee continue o tratteggiate, verificando il perfetto allineamento geometrico."
        },
        {
            "title": "Passo 5: Piano Laterale (PL) e Verifica Finale",
            "desc": "Completa il disegno ricavando il Piano Laterale tramite linee di rimando a 45° o compasso. Esegui il controllo finale delle quote."
        }
    ]
    
    col_prev, col_indicator, col_next = st.columns([1, 1.5, 1])
    
    with col_prev:
        if st.button("⬅️ Indietro", use_container_width=True) and st.session_state.current_step > 1:
            st.session_state.current_step -= 1
            st.rerun()
            
    with col_indicator:
        st.markdown(f"<h4 style='text-align: center; color: #38bdf8; margin-top: 5px;'>Passo {st.session_state.current_step} / {len(steps)}</h4>", unsafe_allow_html=True)
        
    with col_next:
        if st.button("Avanti ➡️", use_container_width=True) and st.session_state.current_step < len(steps):
            st.session_state.current_step += 1
            st.rerun()
            
    curr = steps[st.session_state.current_step - 1]
    st.markdown(f"""
        <div class='step-box'>
            <h3 style='color: #38bdf8; margin-top: 0;'>{curr['title']}</h3>
            <p style='font-size: 1.05rem; line-height: 1.6; color: #f1f5f9;'>{curr['desc']}</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.progress(st.session_state.current_step / len(steps))
