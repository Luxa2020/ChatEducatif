import streamlit as st
from openai import OpenAI
import PyPDF2
import re
import os
import json
from datetime import datetime
import pandas as pd
from fpdf import FPDF


import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # Charge les variables depuis le fichier .env

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# --- Création dossiers data ---
os.makedirs("data/docs", exist_ok=True)
os.makedirs("data/quizzes", exist_ok=True)

# --- Fonctions utilitaires ---

def extraire_texte_pdf(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    texte = ""
    for page in reader.pages:
        texte += page.extract_text() or ""
    return texte

def generer_quiz(texte):
    prompt = f"""
Tu es un professeur. Génère 3 questions à choix multiples (QCM) à partir de ce texte de cours.
Chaque question doit avoir 4 options (a, b, c, d) et indique la bonne réponse à la fin en disant "Réponse correcte : x".

Contenu du cours :
{texte[:2000]}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def parser_quiz(texte_quiz):
    questions = []
    blocs = texte_quiz.strip().split("Réponse correcte :")

    for i in range(len(blocs)-1):
        bloc = blocs[i]
        q_match = re.search(r"(.*?)(?:a\)|a\.)", bloc, re.DOTALL)
        if not q_match:
            continue
        question = q_match.group(1).strip()

        options_match = re.findall(r"[abcd]\)[^\n]+", bloc)
        options = {}
        for opt in options_match:
            cle = opt[0].strip().lower()
            valeur = opt[2:].strip()
            options[cle] = valeur

        bonne = blocs[i+1].strip()[0].lower()
        if bonne not in options:
            bonne = list(options.keys())[0] if options else None

        questions.append({"question": question, "options": options, "correct": bonne})

    return questions

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def create_pdf(dataframe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    line_height = pdf.font_size * 2.5

    # Calcul largeur colonne en fonction du nombre de colonnes et de la largeur page utile
    epw = pdf.w - 2 * pdf.l_margin
    col_width = epw / len(dataframe.columns)

    # Header
    for col in dataframe.columns:
        pdf.cell(col_width, line_height, col, border=1)
    pdf.ln(line_height)

    # Rows
    for _, row in dataframe.iterrows():
        for item in row:
            txt = str(item)
            if len(txt) > 30:
                txt = txt[:27] + "..."
            pdf.cell(col_width, line_height, txt, border=1)
        pdf.ln(line_height)

    return pdf.output(dest='S').encode('latin1')

def tts_and_play(text):
    tts = gTTS(text, lang='fr')
    with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as fp:
        tts.save(fp.name)
        audio_bytes = open(fp.name, "rb").read()
        st.audio(audio_bytes, format='audio/mp3')

# --- Setup session state ---
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "reponses" not in st.session_state:
    st.session_state.reponses = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "doc_filename" not in st.session_state:
    st.session_state.doc_filename = None
if "quiz_filename" not in st.session_state:
    st.session_state.quiz_filename = None

# --- Navigation ---
pages = ["📚 Uploader & Générer Quiz", "🧪 Répondre au Quiz", "📊 Dashboard", "💬 Chat libre", "📜 Historique"]
choix = st.sidebar.radio("Navigation", pages)

st.title("🧠 Plateforme Quiz & Chat Interactive")

if choix == "📚 Uploader & Générer Quiz":
    st.subheader("📤 Uploader un fichier PDF de cours")
    fichier = st.file_uploader("Choisir un fichier PDF", type="pdf")

    if fichier:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"data/docs/cours_{now}.pdf"
        with open(fname, "wb") as f:
            f.write(fichier.getbuffer())
        st.success(f"Fichier sauvegardé localement sous : {fname}")
        st.session_state.doc_filename = fname

        texte = extraire_texte_pdf(fichier)
        st.text_area("Texte extrait du PDF :", texte, height=300)

        if st.button("🎯 Générer le Quiz"):
            with st.spinner("Génération du quiz..."):
                raw_quiz = generer_quiz(texte)
                quiz_parsed = parser_quiz(raw_quiz)
                st.session_state.quiz = quiz_parsed
                st.session_state.submitted = False

                quiz_fname = f"data/quizzes/quiz_{now}.json"
                save_json(quiz_fname, quiz_parsed)
                st.session_state.quiz_filename = quiz_fname

                st.success(f"Quiz généré et sauvegardé dans {quiz_fname}")
                st.code(raw_quiz)

elif choix == "🧪 Répondre au Quiz":
    st.subheader("📝 Réponds aux questions")

    if not st.session_state.quiz:
        st.warning("Aucun quiz généré. Retourne à la page d'upload.")
    else:
        for i, q in enumerate(st.session_state.quiz):
            st.markdown(f"**Q{i+1}. {q['question']}**")
            options = q['options']
            rep = st.radio(
                label="",
                options=list(options.keys()),
                format_func=lambda x: f"{x}) {options[x]}",
                key=f"q{i}"
            )
            st.session_state.reponses[i] = rep

        if st.button("✅ Soumettre les réponses"):
            st.session_state.submitted = True

elif choix == "📊 Dashboard":
    st.subheader("📊 Résultats du Quiz")

    if not st.session_state.quiz:
        st.info("Commence par générer un quiz et y répondre.")
    elif not st.session_state.submitted:
        st.info("Merci de soumettre tes réponses dans l'onglet précédent.")
    else:
        score = 0
        total = len(st.session_state.quiz)

        for i, q in enumerate(st.session_state.quiz):
            bonne = q['correct']
            user_rep = st.session_state.reponses.get(i, "")
            options = q['options']
            bonne_reponse = options.get(bonne, "Réponse inconnue")
            user_reponse_txt = options.get(user_rep, "Non choisie")

            correct_txt = f"✅ Bonne réponse : {bonne}) {bonne_reponse}"
            user_txt = f"👉 Ta réponse : {user_rep}) {user_reponse_txt}"

            if user_rep == bonne:
                st.success(f"Q{i+1}. {correct_txt} | {user_txt}")
                score += 1
            else:
                st.error(f"Q{i+1}. ❌ Mauvaise réponse.\n{correct_txt}\n{user_txt}")

        st.markdown("---")
        st.markdown(f"🎯 **Score final** : {score} / {total}")

        # Sauvegarde résultats
        results_path = "data/results.json"
        results = load_json(results_path) or []

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_entry = {
            "timestamp": now,
            "doc": st.session_state.doc_filename,
            "quiz": st.session_state.quiz_filename,
            "score": score,
            "total": total,
            "reponses": st.session_state.reponses,
        }
        results.append(result_entry)
        save_json(results_path, results)
        st.info(f"Résultats sauvegardés localement dans {results_path}")

elif choix == "💬 Chat libre":
    st.subheader("💬 Pose ta question librement à l'IA")

    question = st.text_input("Ta question ici")

    if question:
        try:
            reponse = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": question}]
            )
            texte = reponse.choices[0].message.content
            st.success("Réponse de l'IA :")
            st.write(texte)

            # Synthèse vocale
            tts_and_play(texte)

        except Exception as e:
            st.error(f"Erreur OpenAI : {e}")

elif choix == "📜 Historique":
    st.subheader("📜 Historique des résultats")

    results_path = "data/results.json"
    results = load_json(results_path)

    if not results:
        st.info("Aucun résultat sauvegardé pour le moment.")
    else:
        hist_data = []
        for entry in results:
            quiz = entry.get("quiz", "Inconnu")
            reponses = entry.get("reponses", {})
            for i, rep in reponses.items():
                try:
                    q_num = int(i) + 1
                except:
                    q_num = i
                hist_data.append({
                    "Quiz": quiz,
                    "Question N°": f"Q{q_num}",
                    "Réponse donnée": rep
                })

        if hist_data:
            df_hist = pd.DataFrame(hist_data)
            st.dataframe(df_hist)
        else:
            st.info("Aucun historique de réponses disponible.")

elif choix == "📊 Dashboard":
    st.subheader("📊 Statistiques globales du Quiz")

    results_path = "data/results.json"
    results = load_json(results_path)

    if not results:
        st.info("Aucun résultat disponible pour le moment.")
        st.stop()

    stats = {}
    for entry in results:
        quiz_file = entry.get("quiz")
        reponses = entry.get("reponses", {})
        if not quiz_file or not os.path.exists(quiz_file):
            continue
        quiz_data = load_json(quiz_file)
        if not quiz_data:
            continue

        for i, user_rep in reponses.items():
            try:
                q_idx = int(i)
            except:
                continue
            bonne = quiz_data[q_idx]["correct"]
            key = f"Q{q_idx+1}"
            if key not in stats:
                stats[key] = {"correct": 0, "wrong": 0}
            if user_rep == bonne:
                stats[key]["correct"] += 1
            else:
                stats[key]["wrong"] += 1

    if not stats:
        st.info("Pas assez de données pour générer un graphique.")
        st.stop()

    df_stats = pd.DataFrame(stats).T  # transpose pour questions en index
    st.bar_chart(df_stats)
