import streamlit as st
from PIL import Image

# Configurazione della pagina con tema chiaro
st.set_page_config(
    page_title="CAD Assistant — Proiezioni Ortogonali",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Stile CSS personalizzato con toni chiari, puliti e professionali
st.markdown("""
    <style>
    .stApp {
        background-color: #f8fafc;
        color: #1e293b;
        font-family: 'Inter', sans-serif;
    }
    .card {
        background: #ffffff;
        padding: 24px;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
    }
    .step-box {
        background: #eff6ff;
        border-left: 5px solid #2563eb;
        padding: 20px;
        border-radius: 0 12px 12px 0;
        margin: 15px 0;
        color: #1e3a8a;
    }
    h1, h2, h3 {
        color: #0f172a;
    }
    h1 {
        color: #1d4ed8;
    }
    .stTextInput>div>div>input, .stSelectbox>div>div>select {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        color: #1e293b !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Gestione dello stato dell'applicazione
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "current_step" not in st.session_state:
    st.session_state.current_step = 1

if "uploaded_image" not in st.session_state:
    st.session_state.uploaded_image = None

if "scala_scelta" not in st.session_state:
    st.session_state.scala_scelta = "1:1"

# --- SCHERMATA DI ACCESSO (SENZA RIFERIMENTI A SVILUPPATORE) ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center; margin-bottom: 25px; color: #1e293b;'>📐 CAD ASSISTANT — ACCESSO UTENTE</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center; color: #2563eb;'>Area di Lavoro</h3>", unsafe_allow_html=True)
            username_input = st.text_input("Nome Utente").strip()
            password_input = st.text_input("Password", type="password")
            
            submit_login = st.form_submit_button("Entra nell'App", use_container_width=True)
            
            if submit_login:
                # Credenziali standard richieste
                if username_input == "DEV" and password_input == "sviluppatore@":
                    st.session_state.logged_in = True
                    st.success("Accesso effettuato correttamente!")
                    st.rerun()
                else:
                    st.error("Credenziali non valide. Riprova.")
    st.stop()

# --- INTERFACCIA PRINCIPALE ---
st.sidebar.markdown("""
    <div style='background: #ffffff; padding: 14px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 20px;'>
        <div style='font-size: 0.75rem; color: #64748b; font-weight: 600; text-transform: uppercase;'>Pannello di Controllo</div>
        <div style='font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-top: 2px;'>📐 CAD Assistant</div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.markdown("👤 **Utente:** `Attivo`")
st.sidebar.markdown("---")

menu = st.sidebar.radio("Navigazione", ["📸 Carica Traccia e Scala", "🧭 Guida Passo-Passo (Frecce)", "ℹ️ Informazioni"])

if st.sidebar.button("🔒 Disconnetti", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# 1. CARICA TRACCIA E SELEZIONA SCALA
if menu == "📸 Carica Traccia e Scala":
    st.title("📸 Acquisizione Traccia e Configurazione Scala")
    st.write("Carica la foto del disegno o della consegna. La foto rimarrà memorizzata in sicurezza durante tutta la navigazione.")
    
    uploaded_file = st.file_uploader("Seleziona o scatta la foto della traccia", type=["jpg", "jpeg", "png"])
    
    # Memorizza l'immagine nello state per evitare crash o reset
    if uploaded_file is not None:
        st.session_state.uploaded_image = Image.open(uploaded_file)

    col_a, col_b = st.columns(2)
    
    with col_a:
        if st.session_state.uploaded_image is not None:
            st.image(st.session_state.uploaded_image, caption="Traccia Attualmente in Lavorazione", use_column_width=True)
        else:
            st.info("💡 Nessuna immagine caricata. Carica una foto per iniziare.")
            
    with col_b:
        st.markdown("### ⚙️ Impostazioni Grafiche")
        st.session_state.scala_scelta = st.selectbox(
            "Seleziona la Scala di Rappresentazione", 
            ["1:1 (Grandezza Naturale)", "1:2 (Riduzione)", "2:1 (Ingrandimento)", "1:5 (Riduzione)", "5:1 (Ingrandimento)"],
            index=0
        )
        
        st.markdown(f"""
        * **Scala impostata:** `{st.session_state.scala_scelta}`
        * **Stato:** Pronto per generare la sequenza di disegno.
        """)
        
        if st.button("🚀 Avvia Guida Interattiva", use_container_width=True):
            if st.session_state.uploaded_image is not None:
                st.success("Configurazione salvata! Passa alla sezione 'Guida Passo-Passo' nel menu a sinistra.")
            else:
                st.warning("Prima di avviare la guida, carica una foto della traccia.")

# 2. GUIDA PASSO-PASSO CON FRECCE E VISUALIZZAZIONE DISEGNO
elif menu == "🧭 Guida Passo-Passo (Frecce)":
    st.title("🧭 Guida Interattiva alle Proiezioni Ortogonali")
    
    # Layout a due colonne: a sinistra la foto di riferimento, a destra i passi guidati
    col_img, col_guide = st.columns([1, 1.2])
    
    with col_img:
        st.markdown("### 📄 Riferimento Traccia")
        if st.session_state.uploaded_image is not None:
            st.image(st.session_state.uploaded_image, caption=f"Scala applicata: {st.session_state.scala_scelta}", use_column_width=True)
        else:
            st.warning("Nessuna immagine caricata. Carica prima la foto nella sezione precedente.")

    with col_guide:
        steps = [
            {
                "title": "Passo 1: Squadratura e Linea di Terra (L.T.)",
                "desc": "Posiziona il foglio in verticale. Traccia la squadratura e disegna la **Linea di Terra (L.T.)** orizzontale. Riferisciti alle dimensioni della traccia per posizionare correttamente il Piano Verticale (PV) in alto e il Piano Orizzontale (PO) in basso."
            },
            {
                "title": "Passo 2: Tracciamento del Piano Verticale (PV)",
                "desc": f"Disegna la vista principale sul PV applicando la scala **{st.session_state.scala_scelta}**. Riporta con precisione le linee di Contorno e posiziona le quote geometriche principali affianco a ogni linea."
            },
            {
                "title": "Passo 3: Proiezione sul Piano Orizzontale (PO)",
                "desc": "Abbassa le linee verticali di proiezione oltre la Linea di Terra per definire la pianta (vista dall'alto). Imposta la profondità complessiva del solido basandoti sulle indicazioni della traccia."
            },
            {
                "title": "Passo 4: Dettagli Interni e Parti Nascoste",
                "desc": "Aggiungi i fori o le cavità interne tracciando le linee continue o tratteggiate necessarie, mantenendo il perfetto allineamento geometrico tra pianta e prospetto."
            },
            {
                "title": "Passo 5: Piano Laterale (PL) e Controllo Finale",
                "desc": "Riporta le larghezze e le altezze sul Piano Laterale usando linee di rimando a 45° o il compasso. Esegui la verifica finale delle linee e delle quote per completare l'elaborato."
            }
        ]
        
        # Pulsanti di controllo per scorrere i passi con le frecce
        col_prev, col_indicator, col_next = st.columns([1, 1.5, 1])
        
        with col_prev:
            if st.button("⬅️ Indietro", use_container_width=True) and st.session_state.current_step > 1:
                st.session_state.current_step -= 1
                st.rerun()
                
        with col_indicator:
            st.markdown(f"<h4 style='text-align: center; color: #1d4ed8; margin-top: 5px;'>Passo {st.session_state.current_step} / {len(steps)}</h4>", unsafe_allow_html=True)
            
        with col_next:
            if st.button("Avanti ➡️", use_container_width=True) and st.session_state.current_step < len(steps):
                st.session_state.current_step += 1
                st.rerun()
                
        # Mostra il box del passo corrente
        curr = steps[st.session_state.current_step - 1]
        st.markdown(f"""
            <div class='step-box'>
                <h3 style='color: #1e3a8a; margin-top: 0;'>{curr['title']}</h3>
                <p style='font-size: 1.05rem; line-height: 1.6; color: #1e293b;'>{curr['desc']}</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Barra di avanzamento pulita
        st.progress(st.session_state.current_step / len(steps))

# 3. INFORMAZIONI
elif menu == "ℹ️ Informazioni":
    st.title("ℹ️ Informazioni sull'Applicazione")
    st.markdown("""
    Un assistente grafico intelligente per lo studio e l'esecuzione delle **proiezioni ortogonali**:
    * **Interfaccia Chiara:** Ottimizzata per una visualizzazione pulita e senza distrazioni.
    * **Gestione della Memoria:** La foto caricata resta attiva durante tutti i passaggi della guida.
    * **Adattamento di Scala:** Seleziona la scala di disegno desiderata in modo immediato.
    """)
