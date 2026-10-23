# -*- coding: utf-8 -*-
"""
CAD Assistant — Proiezioni Ortogonali
Creato da: ENRICO BOTTONE

Avvio:  streamlit run app.py
Requisiti: streamlit>=1.30 (Pillow è già installato come dipendenza di Streamlit)
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
import uuid
from pathlib import Path

import streamlit as st
from PIL import Image

# ----------------------------------------------------------------------------
# CONFIGURAZIONE
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="CAD Assistant — Proiezioni Ortogonali",
    page_icon="📐",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cad_users.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_MB = 15
ALLOWED_EXT = ["jpg", "jpeg", "png", "webp"]
SCALES = ["1:1", "1:2", "2:1", "1:5", "5:1", "1:10"]

ROLE_DEV = "sviluppatore"
ROLE_STUDENT = "studente"

PBKDF2_ITERATIONS = 200_000


# ----------------------------------------------------------------------------
# DATABASE E AUTENTICAZIONE
# ----------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt_hex: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return dk.hex()


def create_user(username: str, password: str, role: str) -> None:
    salt = secrets.token_hex(16)
    pwd_hash = hash_password(password, salt)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            (username, pwd_hash, salt, role),
        )


REQUIRED_COLUMNS = {"id", "username", "password_hash", "salt", "role", "created_at"}


def migrate_legacy_table() -> None:
    """Se esiste una vecchia tabella 'users' con schema diverso, la mette da parte."""
    with get_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if cols and not REQUIRED_COLUMNS.issubset(cols):
            conn.execute("DROP TABLE IF EXISTS users_legacy")
            conn.execute("ALTER TABLE users RENAME TO users_legacy")


def init_db() -> None:
    migrate_legacy_table()
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('sviluppatore', 'studente')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = 'DEV'"
        ).fetchone()
    if not exists:
        create_user("DEV", "sviluppatore@", ROLE_DEV)


def authenticate(username: str, password: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        return None
    candidate = hash_password(password, row["salt"])
    if hmac.compare_digest(candidate, row["password_hash"]):
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def list_students():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, created_at FROM users WHERE role = ? ORDER BY username",
            (ROLE_STUDENT,),
        ).fetchall()


def delete_student(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM users WHERE id = ? AND role = ?", (user_id, ROLE_STUDENT)
        )


def reset_student_password(user_id: int, new_password: str) -> None:
    salt = secrets.token_hex(16)
    pwd_hash = hash_password(new_password, salt)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ? AND role = ?",
            (pwd_hash, salt, user_id, ROLE_STUDENT),
        )


# ----------------------------------------------------------------------------
# STILE (DARK MODE)
# ----------------------------------------------------------------------------
CSS = """
<style>
.stApp {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0f172a 100%);
    color: #e2e8f0;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1224 0%, #111c3a 100%);
    border-right: 1px solid rgba(148, 163, 184, 0.15);
}
h1, h2, h3, h4 { color: #f8fafc !important; letter-spacing: 0.2px; }

.hero {
    background: linear-gradient(120deg, rgba(56,189,248,0.15), rgba(139,92,246,0.18));
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 20px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.4rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}
.hero h1 { margin: 0 0 0.4rem 0; font-size: 2rem; }
.hero p { margin: 0.2rem 0; color: #cbd5e1; font-size: 1rem; line-height: 1.5; }
.hero .author {
    display: inline-block; margin-top: 0.7rem; padding: 0.25rem 0.8rem;
    border-radius: 999px; background: rgba(56,189,248,0.18);
    color: #7dd3fc; font-weight: 600; font-size: 0.85rem; letter-spacing: 0.5px;
}

.card {
    background: rgba(30, 41, 59, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
}
.card h3 { margin-top: 0; color: #7dd3fc !important; }
.card ul { margin: 0.4rem 0 0 1.1rem; }
.card li { margin-bottom: 0.3rem; color: #e2e8f0; }
.step-badge {
    display: inline-block; padding: 0.15rem 0.7rem; border-radius: 999px;
    background: rgba(139,92,246,0.25); color: #c4b5fd;
    font-size: 0.8rem; font-weight: 600; margin-bottom: 0.5rem;
}
.tip {
    border-left: 4px solid #38bdf8; background: rgba(56,189,248,0.08);
    padding: 0.6rem 0.9rem; border-radius: 8px; margin-top: 0.7rem; color: #bae6fd;
}

.stButton > button, .stFormSubmitButton > button {
    background: linear-gradient(90deg, #0ea5e9, #6366f1);
    color: white; border: none; border-radius: 12px;
    padding: 0.55rem 1.3rem; font-weight: 600;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(99, 102, 241, 0.45);
    color: white; border: none;
}
.stButton > button:disabled {
    background: #334155; color: #94a3b8; box-shadow: none; transform: none;
}
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #38bdf8, #8b5cf6);
}
[data-testid="stFileUploader"] section {
    background: rgba(30, 41, 59, 0.6);
    border: 1.5px dashed rgba(125, 211, 252, 0.5);
    border-radius: 14px;
}
.login-wrap { max-width: 460px; margin: 4vh auto 0 auto; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# STATO DI SESSIONE
# ----------------------------------------------------------------------------
def init_state():
    defaults = {
        "user": None,
        "current_step": 0,
        "trace_path": None,
        "trace_sig": None,
        "scale": "1:1",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def logout():
    path = st.session_state.get("trace_path")
    if path and Path(path).exists():
        try:
            Path(path).unlink()
        except OSError:
            pass
    for key in ["user", "current_step", "trace_path", "trace_sig", "scale"]:
        if key in st.session_state:
            del st.session_state[key]


# ----------------------------------------------------------------------------
# SCHERMATA DI LOGIN
# ----------------------------------------------------------------------------
def login_page():
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero" style="text-align:center;">
            <h1>📐 CAD Assistant</h1>
            <p>Proiezioni Ortogonali</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Accedi")
    if submitted:
        user = authenticate(username, password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Credenziali non valide.")
    st.markdown("</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# GESTIONE UTENTI (SOLO SVILUPPATORE)
# ----------------------------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")


def user_management_page():
    user = st.session_state.user
    if not user or user["role"] != ROLE_DEV:
        st.error("Accesso negato.")
        return

    st.markdown(
        """
        <div class="hero">
            <h1>👥 Gestione Utenti</h1>
            <p>Crea e gestisci gli account con ruolo <b>studente</b>.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_new, tab_list = st.tabs(["➕ Nuovo studente", "📋 Elenco studenti"])

    with tab_new:
        with st.form("new_student_form", clear_on_submit=True):
            new_user = st.text_input("Username studente")
            new_pwd = st.text_input("Password", type="password")
            new_pwd2 = st.text_input("Conferma password", type="password")
            create = st.form_submit_button("Crea account studente")
        if create:
            if not USERNAME_RE.match(new_user or ""):
                st.error("Username non valido: 3-30 caratteri (lettere, numeri, . _ -).")
            elif len(new_pwd) < 6:
                st.error("La password deve avere almeno 6 caratteri.")
            elif new_pwd != new_pwd2:
                st.error("Le password non coincidono.")
            else:
                try:
                    create_user(new_user.strip(), new_pwd, ROLE_STUDENT)
                    st.success(f"Account studente «{new_user.strip()}» creato.")
                except sqlite3.IntegrityError:
                    st.error("Esiste già un utente con questo username.")

    with tab_list:
        students = list_students()
        if not students:
            st.info("Nessuno studente registrato.")
        for s in students:
            with st.expander(f"🎓 {s['username']}  ·  creato il {s['created_at']}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    pwd = st.text_input(
                        "Nuova password",
                        type="password",
                        key=f"pwd_{s['id']}",
                    )
                    if st.button("Aggiorna password", key=f"upd_{s['id']}"):
                        if len(pwd) < 6:
                            st.error("Minimo 6 caratteri.")
                        else:
                            reset_student_password(s["id"], pwd)
                            st.success("Password aggiornata.")
                with c2:
                    st.write("")
                    st.write("")
                    if st.button("Elimina", key=f"del_{s['id']}"):
                        delete_student(s["id"])
                        st.rerun()


# ----------------------------------------------------------------------------
# GUIDA PASSO-PASSO
# ----------------------------------------------------------------------------
def scale_factor(scale: str) -> float:
    """'1:2' -> 0.5 ; '2:1' -> 2.0 (misura disegno = misura reale * fattore)."""
    a, b = scale.split(":")
    return float(a) / float(b)


def build_steps(scale: str):
    f = scale_factor(scale)
    if scale == "1:1":
        kind = "scala naturale: le misure sul foglio coincidono con quelle reali"
    elif f < 1:
        kind = "scala di riduzione: le misure sul foglio sono più piccole di quelle reali"
    else:
        kind = "scala di ingrandimento: le misure sul foglio sono più grandi di quelle reali"

    return [
        {
            "title": "Analisi della traccia",
            "items": [
                "Osserva la traccia e individua la forma generale del solido o del pezzo.",
                "Identifica fori, smussi, raccordi, gole e sporgenze.",
                "Annota tutte le quote note e individua quelle che mancano.",
                "Stabilisci quali elementi saranno visibili e quali nascosti nelle diverse viste.",
            ],
            "tip": "Una buona lettura della traccia evita errori nelle fasi successive.",
        },
        {
            "title": "Scala e formato del foglio",
            "items": [
                f"Scala scelta: <b>{scale}</b> — {kind}.",
                f"Formula: misura da disegnare = misura reale × <b>{f:g}</b>.",
                "Scegli il formato (A4, A3…) in modo che le tre viste entrino con margini adeguati.",
                "Traccia il riquadro (margini) e predisponi lo spazio per il cartiglio.",
            ],
            "tip": "Le quote scritte restano sempre quelle reali, indipendentemente dalla scala.",
        },
        {
            "title": "Scelta della vista frontale",
            "items": [
                "La vista frontale (prospetto) è quella che descrive meglio la forma del pezzo.",
                "Scegli la posizione di lavoro o d'uso più naturale del pezzo.",
                "Mostra il maggior numero di particolari in vista (meno linee tratteggiate).",
                "Il numero di viste deve essere il minimo necessario per definire completamente l'oggetto.",
            ],
            "tip": "Il pezzo deve essere definito completamente con il minor numero di viste.",
        },
        {
            "title": "Disposizione delle viste (metodo europeo)",
            "items": [
                "Vista frontale in alto a sinistra del foglio.",
                "Pianta (vista dall'alto) <b>sotto</b> la vista frontale.",
                "Vista laterale sinistra <b>a destra</b> della vista frontale.",
                "Lascia tra le viste uno spazio sufficiente per le quote.",
            ],
            "tip": "Nel metodo europeo (primo diedro) l'oggetto si trova fra l'osservatore e il piano di proiezione.",
        },
        {
            "title": "Assi e linee di costruzione",
            "items": [
                "Traccia con linea sottile gli assi di simmetria (linea a tratto e punto).",
                "Disegna le linee di costruzione leggere per gli ingombri massimi.",
                "Prepara la bisettrice a 45° per riportare le misure tra pianta e vista laterale.",
                "Usa matita dura (H/2H) per le linee di costruzione.",
            ],
            "tip": "Le linee di costruzione devono essere leggere: andranno rinforzate solo dove serve.",
        },
        {
            "title": "Proiezione della vista frontale",
            "items": [
                "Riporta larghezza e altezza reali applicando la scala scelta.",
                "Disegna il contorno esterno, poi i particolari interni (fori, smussi).",
                "Evidenzia con linee di richiamo i punti notevoli da proiettare.",
                "Verifica le proporzioni confrontando con la traccia.",
            ],
            "tip": "Lavora dal generale al particolare.",
        },
        {
            "title": "Proiezione della pianta",
            "items": [
                "Proietta verso il basso, con linee verticali, i punti della vista frontale.",
                "Riporta le profondità reali moltiplicate per il fattore di scala.",
                "Disegna contorni e particolari visibili dall'alto.",
                "Controlla che larghezze della pianta e del prospetto coincidano.",
            ],
            "tip": "Le larghezze devono corrispondere perfettamente nelle due viste.",
        },
        {
            "title": "Proiezione della vista laterale",
            "items": [
                "Proietta orizzontalmente le altezze dalla vista frontale.",
                "Riporta le profondità dalla pianta usando la bisettrice a 45°.",
                "Disegna contorni e particolari della vista laterale sinistra.",
                "Controlla che altezze e profondità siano coerenti con le altre viste.",
            ],
            "tip": "La bisettrice a 45° è lo strumento più rapido per trasferire le profondità.",
        },
        {
            "title": "Tipi di linea e parti nascoste",
            "items": [
                "Contorni e spigoli in vista: linea continua grossa.",
                "Spigoli nascosti: linea tratteggiata sottile.",
                "Assi e centri: linea a tratto e punto sottile.",
                "Rinforza i contorni definitivi e cancella le costruzioni superflue.",
            ],
            "tip": "Rispetta le norme UNI/ISO sui tipi e gli spessori di linea.",
        },
        {
            "title": "Quotatura",
            "items": [
                "Quota ogni elemento una sola volta, nella vista dove è più chiaro.",
                "Linee di misura sottili, frecce ben formate, numeri leggibili.",
                "Scrivi le quote reali (non quelle scalate).",
                "Evita quote ridondanti e non quotare sulle linee nascoste.",
            ],
            "tip": "Le quote devono permettere di realizzare il pezzo senza fare misurazioni sul disegno.",
        },
        {
            "title": "Cartiglio e verifica finale",
            "items": [
                "Compila il cartiglio: titolo, scala, data, nome, classe, metodo di proiezione.",
                f"Indica nel cartiglio la scala <b>{scale}</b> e il simbolo del metodo europeo.",
                "Controlla coerenza tra le viste, quote complete, linee corrette.",
                "Ripulisci il foglio e consegna l'elaborato.",
            ],
            "tip": "Una verifica finale accurata fa la differenza nella valutazione.",
        },
    ]


def go_prev():
    if st.session_state.current_step > 0:
        st.session_state.current_step -= 1


def go_next(total: int):
    if st.session_state.current_step < total - 1:
        st.session_state.current_step += 1


def save_upload(uploaded) -> None:
    """Salva il file su disco con getbuffer() e memorizza solo il percorso."""
    size_mb = uploaded.size / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        st.error(f"File troppo grande ({size_mb:.1f} MB). Limite: {MAX_UPLOAD_MB} MB.")
        return

    ext = Path(uploaded.name).suffix.lower()
    if ext.lstrip(".") not in ALLOWED_EXT:
        st.error("Formato non supportato.")
        return

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(dest, "wb") as f:
        f.write(uploaded.getbuffer())

    # Verifica che sia davvero un'immagine valida (senza caricarla tutta in memoria)
    try:
        with Image.open(dest) as img:
            img.verify()
    except Exception:
        dest.unlink(missing_ok=True)
        st.error("Il file caricato non è un'immagine valida.")
        return

    # Elimina la traccia precedente
    old = st.session_state.get("trace_path")
    if old and Path(old).exists():
        try:
            Path(old).unlink()
        except OSError:
            pass

    st.session_state.trace_path = str(dest)
    st.session_state.trace_sig = f"{uploaded.name}-{uploaded.size}"
    st.session_state.current_step = 0


def remove_trace():
    old = st.session_state.get("trace_path")
    if old and Path(old).exists():
        try:
            Path(old).unlink()
        except OSError:
            pass
    st.session_state.trace_path = None
    st.session_state.trace_sig = None
    st.session_state.current_step = 0


def assistant_page():
    st.markdown(
        """
        <div class="hero">
            <h1>📐 CAD Assistant — Proiezioni Ortogonali</h1>
            <p>Sistema educativo di disegno tecnico: carica la foto della traccia,
            scegli la scala di rappresentazione e segui la guida interattiva
            passo-passo per costruire correttamente le proiezioni ortogonali
            (vista frontale, pianta e vista laterale) con il metodo europeo.</p>
            <span class="author">Creato da: ENRICO BOTTONE</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Caricamento traccia e scala -------------------------------------
    col_up, col_scale = st.columns([2, 1])
    with col_up:
        st.markdown("#### 🖼️ Traccia dell'esercizio")
        uploaded = st.file_uploader(
            "Carica la foto della traccia (jpg, png, webp)",
            type=ALLOWED_EXT,
            key="trace_uploader",
        )
        if uploaded is not None:
            sig = f"{uploaded.name}-{uploaded.size}"
            if sig != st.session_state.trace_sig:
                save_upload(uploaded)
        if st.session_state.trace_path:
            if st.button("Rimuovi traccia"):
                remove_trace()
                st.rerun()

    with col_scale:
        st.markdown("#### 📏 Scala di rappresentazione")
        st.selectbox(
            "Seleziona la scala",
            SCALES,
            key="scale",
        )
        f = scale_factor(st.session_state.scale)
        st.markdown(
            f"""
            <div class="card">
                Fattore di scala: <b>{f:g}</b><br>
                <small>misura disegno = misura reale × {f:g}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
        real = st.number_input(
            "Misura reale (mm)", min_value=0.0, value=100.0, step=1.0
        )
        st.markdown(
            f"Da tracciare sul foglio: **{real * f:g} mm**"
        )

    st.divider()

    # --- Guida passo-passo -----------------------------------------------
    st.markdown("### 🧭 Guida passo-passo")

    steps = build_steps(st.session_state.scale)
    total = len(steps)
    # Protezione se il numero di passi cambiasse
    st.session_state.current_step = max(0, min(st.session_state.current_step, total - 1))
    idx = st.session_state.current_step
    step = steps[idx]

    left, right = st.columns([1, 1])

    with left:
        st.markdown("#### Riferimento: traccia caricata")
        path = st.session_state.trace_path
        if path and Path(path).exists():
            st.image(path, caption="Traccia di riferimento")
        else:
            st.info("Carica la foto della traccia per vederla qui come riferimento costante.")

    with right:
        st.progress((idx + 1) / total, text=f"Passo {idx + 1} di {total}")
        items_html = "".join(f"<li>{it}</li>" for it in step["items"])
        st.markdown(
            f"""
            <div class="card">
                <span class="step-badge">PASSO {idx + 1} / {total}</span>
                <h3>{step['title']}</h3>
                <ul>{items_html}</ul>
                <div class="tip">💡 {step['tip']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        b1, b2, _ = st.columns([1, 1, 2])
        with b1:
            st.button(
                "⬅ Indietro",
                key="btn_prev",
                on_click=go_prev,
                disabled=(idx == 0),
            )
        with b2:
            st.button(
                "Avanti ➡",
                key="btn_next",
                on_click=go_next,
                args=(total,),
                disabled=(idx == total - 1),
            )
        if idx == total - 1:
            st.success("Hai completato tutti i passaggi. Ottimo lavoro!")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    init_db()
    init_state()
    inject_css()

    user = st.session_state.user
    if not user:
        login_page()
        return

    with st.sidebar:
        st.markdown("## 📐 CAD Assistant")
        st.markdown(f"**Utente:** {user['username']}")
        st.caption(f"Ruolo: {user['role']}")
        st.divider()

        pages = ["Assistente CAD"]
        if user["role"] == ROLE_DEV:
            pages.append("Gestione Utenti")
        page = st.radio("Navigazione", pages, label_visibility="collapsed")

        st.divider()
        if st.button("Esci"):
            logout()
            st.rerun()
        st.caption("Creato da: ENRICO BOTTONE")

    if page == "Gestione Utenti" and user["role"] == ROLE_DEV:
        user_management_page()
    else:
        assistant_page()


main()
