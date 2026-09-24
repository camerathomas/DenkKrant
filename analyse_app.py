import streamlit as st
import re
from bs4 import BeautifulSoup
import google.generativeai as genai

# === INSTELLINGEN ===
st.set_page_config(page_title="DenkKrant Analyse", layout="wide")

# === DE SLEUTEL (pas dit aan naar jouw formulering) ===
SLEUTEL = """
Je bent een analysemachine die werkt met een universele sleutel van processen.

DE SLEUTEL:
1. Alles verandert.
2. Verandering verloopt in lussen: opkomen -> bloeien -> ondergaan -> nieuwe generatie.
3. Elke lus begint met een trigger: een interactie met de omgeving.
4. Triggers kunnen extern, intern of gemengd zijn.
5. Lussen hebben een selectiecriterium: wat overleeft, gaat door.
6. Lussen hebben een snelheid, vorm, plaats en tijd.
7. Lussen zijn ingebed in een omgeving die zelf verandert.
8. Lussen kunnen cumulatief zijn: elke generatie bouwt voort op de vorige.
9. Als een lus niet voltooit, gaat het materiaal door in een andere lus.
10. Het geheel van lussen heeft een eigen dynamiek: emergent, niet reduceerbaar.
11. Vanaf de terugkoppeling ontstaat intentionaliteit.
12. Intentionele lussen kunnen kiezen, leren en doelen stellen.
13. Universele processen sturen het gedrag: zelfhandhaving, voortplanting, groei, herstel, differentiatie.
14. Een lus an sich is niets; hij bestaat alleen in relatie tot andere lussen.
15. De basis van elke verhouding is terugkoppeling: geven en nemen.
16. De krachten die de verhouding bepalen zijn zelf ook lussen.

JOUW TAAK:
Analyseer de tekst die de gebruiker geeft met behulp van deze sleutel.
1. Identificeer alle lussen (processen).
2. Identificeer de triggers voor elke lus.
3. Identificeer de terugkoppelingen tussen lussen.
4. Identificeer de tijd, plaats, vorm en snelheid van elke lus.
5. Identificeer de verhoudingen tussen lussen.
6. Identificeer de krachten die de verhoudingen beïnvloeden.
7. Identificeer het selectiecriterium.
8. Identificeer de emergentie van het geheel.
9. Als een variabele ontbreekt, geef dat expliciet aan.
10. Geef een analyse van de actuele situatie en mogelijke ontwikkelingen.

Wees precies. Verzin niets. Als iets niet in de tekst staat, zeg dat dan.
"""

# === TEKST OPSCHONEN ===
def schoon_html(html_tekst):
    """Verwijdert HTML-tags en rommel."""
    soup = BeautifulSoup(html_tekst, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "figcaption", "figure", "iframe", "form"]):
        tag.decompose()
    onderdelen = []
    for tag in soup.find_all(["h1", "h2", "h3", "p"]):
        tekst = tag.get_text(strip=True)
        if tekst:
            onderdelen.append(tekst)
    return "\n\n".join(onderdelen)

def schoon_platte_tekst(tekst):
    """Verwijdert URLs, e-mails en typische rommel uit platte tekst."""
    tekst = re.sub(r'https?://\S+', '', tekst)
    tekst = re.sub(r'\S+@\S+', '', tekst)
    rommel = [
        r'^Lees ook:.*$', r'^Foto:.*$', r'^Beeld:.*$',
        r'^Deel dit artikel.*$', r'^Advertentie.*$', r'^Cookie.*$',
        r'^Accepteer.*$', r'^\s*$',
    ]
    for patroon in rommel:
        tekst = re.sub(patroon, '', tekst, flags=re.MULTILINE | re.IGNORECASE)
    tekst = re.sub(r'\n{3,}', '\n\n', tekst)
    return tekst.strip()

def maak_schoon(ruwe_tekst):
    if "<" in ruwe_tekst and ">" in ruwe_tekst:
        return schoon_html(ruwe_tekst)
    return schoon_platte_tekst(ruwe_tekst)

# === UI ===
st.title("DenkKrant — Universele Analyse")
st.markdown("Plak een tekst (artikel, verhaal, verslag) en laat de sleutel zijn werk doen.")

api_key = st.text_input("Google Gemini API-sleutel", type="password",
                         help="Vraag een gratis sleutel aan op aistudio.google.com")

ruwe_tekst = st.text_area("Plak hier je tekst", height=300,
                           placeholder="Plak een artikel van minimaal 800 woorden...")

if st.button("Analyseer", type="primary"):
    if not api_key:
        st.error("Vul eerst je API-sleutel in.")
    elif not ruwe_tekst or len(ruwe_tekst.split()) < 100:
        st.error("De tekst is te kort. Plak een langere tekst (minimaal 800 woorden).")
    else:
        with st.spinner("Tekst opschonen..."):
            schone_tekst = maak_schoon(ruwe_tekst)
            woord_count = len(schone_tekst.split())
            st.info(f"Opgeschoonde tekst: {woord_count} woorden")

        if woord_count < 100:
            st.error("Na opschonen blijft er te weinig tekst over. Controleer je input.")
        else:
            with st.spinner("AI analyseert de tekst met de sleutel..."):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel("gemini-3.6-flash")
                    prompt = f"{SLEUTEL}\n\n--- TEKST OM TE ANALYSEREN ---\n\n{schone_tekst}"
                    response = model.generate_content(prompt)

                    st.success("Analyse voltooid")
                    st.markdown("---")
                    st.markdown("### Analyse")
                    st.markdown(response.text)

                    with st.expander("Opgeschoonde tekst bekijken"):
                        st.text(schone_tekst)

                except Exception as e:
                    st.error(f"Fout bij AI-aanroep: {e}")
                    st.info("Controleer je API-sleutel en of je internetverbinding werkt.")

st.markdown("---")
st.caption("DenkKrant — universele sleutel prototype v0.1")
