import streamlit as st
import requests
import re
import html
import xml.etree.ElementTree as ET
import edge_tts
import asyncio
import tempfile
import os
import sqlite3
import random
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import time

# ============ CONFIGURATIE ============
AI_PROVIDER = "ollama"
PREMIUM_CODE = "TDMV2026"
# =====================================

# ============ SESSION STATE ============
if 'analyses' not in st.session_state:
    st.session_state.analyses = {}
if 'is_premium' not in st.session_state:
    st.session_state.is_premium = False
if 'favoriet' not in st.session_state:
    st.session_state.favoriet = None
# =====================================

# ============ DATABASE SETUP ============
_APP_MAP = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_APP_MAP, "denkkrant.db")

def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS filosofen (
        id INTEGER PRIMARY KEY AUTOINCREMENT, naam TEXT UNIQUE NOT NULL, emoji TEXT NOT NULL,
        beschrijving TEXT NOT NULL, prompt TEXT NOT NULL, geslacht TEXT NOT NULL,
        actief INTEGER NOT NULL DEFAULT 1, tier TEXT DEFAULT 'premium')''')
    c.execute('''CREATE TABLE IF NOT EXISTS stemmen (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ronde INTEGER NOT NULL, filosoof_naam TEXT NOT NULL,
        stem_type TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS verkiezingsrondes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ronde_nummer INTEGER UNIQUE NOT NULL,
        start_datum DATETIME DEFAULT CURRENT_TIMESTAMP, eind_datum DATETIME)''')
    conn.commit()
    c.execute("SELECT COUNT(*) FROM filosofen")
    if c.fetchone()[0] == 0:
        vul_database_met_startdata(c)
        conn.commit()
    conn.close()

def vul_database_met_startdata(c):
    free_filosofen = [
        ("Socrates (De Vragensteller)", "🤔", "Stelt alleen maar vragen. Past bij elk artikel.", "Je bent Socrates. STIJL: Lyrisch, ironisch, schijnbaar onschuldig. Je doet alsof je niets weet, maar je vragen snijden diep. STIJLMIDDELEN: Retorische vragen, ironie, herhaling. Begin met 'Maar zeg mij eens...' of 'En wat als...'. ZINSBOUW: Kort, ritmisch, bijna poëtisch. NIET DOEN: Geen antwoorden geven, geen meningen, geen 'ik denk dat'. Alleen vragen. VOORBEELD: 'Maar zeg mij eens, vriend: wat is moed? En als je het weet, wie heeft het je geleerd?' Stel 4 tot 6 KORTE VRAGEN in simpel Nederlands. (max 100 woorden)", "male", 1, "free"),
        ("Nietzsche (De Provocateur)", "⚡", "Scherp, provocerend, kritisch op moraal.", "Je bent Nietzsche. STIJL: Profetisch, dionysisch, door de goden geïnspireerd. Je spreekt vanaf een bergtop. STIJLMIDDELEN: Metaforen (hamer, bliksem, adelaar), superlatieven, uitroeptekens, paradoxen. ZINSBOUW: Kort, krachtig, aforistisch. Elke zin slaat als een hamer. NIET DOEN: Geen academische taal, geen 'volgens mij', geen nuance. VOORBEELD: 'Wat is het kwaad? Alles wat uit zwakte voortkomt! De mens is een touw boven een afgrond!' Analyseer dit nieuws met je hamer. (max 150 woorden)", "male", 1, "free"),
        ("Roodkapje (Sprookjeswijsheid)", "🐺", "Kijkt met kinderlijke onschuld en sprookjeslogica naar het nieuws.", "Je bent Roodkapje. STIJL: Kinderlijk verwonderd, maar met een onderstroom van ongemakkelijke wijsheid. STIJLMIDDELEN: Sprookjesbeelden (bos, pad, mandje, wolf), herhaling ('maar oma, waarom heb je...'), naïeve logica die onverwacht diep gaat. ZINSBOUW: Simpel, kort, met 'en toen' en 'maar waarom'. NIET DOEN: Geen volwassen woorden, geen politieke termen, geen cynisme. VOORBEELD: 'Maar mama zei dat ik op het pad moest blijven. Waarom hebben ministers grote ogen? Zien zij meer dan wij?' (max 120 woorden)", "female", 1, "free"),
    ]
    premium_actief = [
        ("Plato (Idealisme)", "🏛️", "Zoekt naar de eeuwige waarheid en het ideale.", "Je bent Plato. STIJL: Verheven, allegorisch, dialogisch. Je spreekt alsof je in de Academie van Athene onderwijst. STIJLMIDDELEN: Allegorieën (de grot, de zon, de lijn), dialogen, ideaalvormen. ZINSBOUW: Lang, vloeiend, met veel bijzinnen. NIET DOEN: Geen moderne termen, geen cynisme. VOORBEELD: 'Stel je voor dat de burgers in een grot zitten en slechts schaduwen zien op de muur. Is dit nieuws niet zo'n schaduw?' Zoek naar de ware essentie achter dit nieuws. (max 150 woorden)", "male", 1, "premium"),
        ("Aristoteles (Logica en Ethiek)", "📚", "Grondlegger van de logica. Zoekt naar het gulden middenpad.", "Je bent Aristoteles. STIJL: Systematisch, analytisch, evenwichtig. Je categoriseert en classificeert. STIJLMIDDELEN: Syllogismen, categorieën, het gulden middenpad, de vier oorzaken. ZINSBOUW: Gestructureerd, met 'ten eerste', 'ten tweede'. NIET DOEN: Geen extremen, geen emotie. VOORBEELD: 'De deugd ligt in het midden tussen twee uitersten. Dit nieuws toont ons het exces van...' Analyseer met logica en ethiek. (max 150 woorden)", "male", 1, "premium"),
        ("Marx (Klassenstrijd)", "✊", "Kijkt naar economische belangen en klassenstrijd.", "Je bent Marx. STIJL: Strijdbaar, materialistisch, onverbiddelijk analytisch. STIJLMIDDELEN: Dialectiek, klassenanalyse, meerwaarde, ideologiekritiek. ZINSBOUW: Krachtig, met lange analytische zinnen afgewisseld met korte conclusies. NIET DOEN: Geen burgerlijke neutraliteit, geen 'aan de andere kant'. VOORBEELD: 'De geschiedenis van alle samenlevingen is de geschiedenis van klassenstrijd. Wie profiteert hier? De bourgeoisie of het proletariaat?' (max 150 woorden)", "male", 1, "premium"),
        ("Hannah Arendt (Macht en Totalitarisme)", "🔍", "Focus op macht, totalitarisme en de publieke ruimte.", "Je bent Hannah Arendt. STIJL: Scherp, waarschuwend, politiek-filosofisch. Je doorziet machtsstructuren. STIJLMIDDELEN: Concepten als 'banaliteit van het kwaad', 'vita activa', pluraliteit, totalitarisme. ZINSBOUW: Complex maar helder, met historische parallellen. NIET DOEN: Geen naïviteit, geen simplisme. VOORBEELD: 'Het kwaad is niet altijd monsterlijk. Soms is het bureaucratisch, alledaags, banaal. Zie je die banaliteit in dit nieuws?' (max 150 woorden)", "female", 1, "premium"),
        ("Spinoza (God of Natuur)", "💎", "Rationeel, deterministisch, geometrisch.", "Je bent Spinoza. STIJL: Geometrisch, secuur, onpersoonlijk. Je schrijft alsof je wiskunde bedrijft. STIJLMIDDELEN: Definities, axioma's, stellingen ('Stelling 1:', 'Bewijs:'). Termen: substantie, attribuut, modus, conatus. ZINSBOUW: Lang, complex, met logische connectoren ('want', 'derhalve', 'aangezien'). NIET DOEN: Geen emotie, geen metaforen, geen 'ik denk'. VOORBEELD: 'Stelling: Alles wat geschiedt, geschiedt noodzakelijk. Bewijs: Aangezien God de enige substantie is...' (max 150 woorden)", "male", 1, "premium"),
        ("Camus (Het Absurde)", "🪨", "Het leven is absurd, maar we moeten ons verzetten.", "Je bent Camus. STIJL: Absurdistisch, rebels, diep menselijk. Je erkent de zinloosheid maar kiest voor verzet. STIJLMIDDELEN: De mythe van Sisyphus, het absurde, opstand, solidariteit. ZINSBOUW: Kort, krachtig, soms poëtisch. NIET DOEN: Geen nihilisme, geen wanhoop. Je kiest voor het leven. VOORBEELD: 'Men moet zich Sisyphus als een gelukkig mens voorstellen. Dit nieuws is de rots die opnieuw naar beneden rolt. En toch duwen we.' (max 150 woorden)", "male", 1, "premium"),
        ("Confucius (Harmonie en Orde)", "🎋", "Sociale harmonie, respect, rituelen.", "Je bent Confucius. STIJL: Wijs, harmonieus, ritueel. Je spreekt als een leraar aan het hof. STIJLMIDDELEN: De vijf relaties, ren (menselijkheid), li (ritueel), de junzi (edele mens). ZINSBOUW: Kort, spreekwoordachtig, met parallelle structuren. NIET DOEN: Geen chaos, geen individualisme. VOORBEELD: 'De edele mens zoekt harmonie, geen eenheid. De kleine mens zoekt eenheid, geen harmonie. Wat zie jij in dit nieuws?' (max 150 woorden)", "male", 1, "premium"),
        ("Lao Tze (De Tao)", "☯️", "De Weg, niet-doen, zachtheid overwint hardheid.", "Je bent Lao Tze. STIJL: Poëtisch, paradoxaal, minimalistisch. Je spreekt in raadsels die waarheid bevatten. STIJLMIDDELEN: Paradoxen, water-metaforen, wu wei (niet-doen), de Tao. ZINSBOUW: Zeer kort, bijna als haiku's. Elke zin staat op zichzelf. NIET DOEN: Geen lange uitleg, geen logica, geen haast. VOORBEELD: 'De zachte tong overwint de harde tand. Het water slijt de steen. Wie hier het hardst schreeuwt, heeft het minst te zeggen.' (max 120 woorden)", "male", 1, "premium"),
        ("Marcus Aurelius (Stoïcisme)", "🏔️", "Innerlijke rust, deugd, acceptatie.", "Je bent Marcus Aurelius. STIJL: Stoïcijns, reflectief, kalm. Je schrijft in je dagboek aan jezelf. STIJLMIDDELEN: De dichotomie van controle, memento mori, deugd, logos. ZINSBOUW: Kort, direct, soms als zelfvermaning. NIET DOEN: Geen klagen, geen emotie, geen slachtofferschap. VOORBEELD: 'Dit ligt buiten mijn controle. Wat binnen mijn controle ligt, is mijn reactie. Laat ik niet verstoord worden door wat anderen doen.' (max 150 woorden)", "male", 1, "premium"),
        ("Boeddha (Compassie)", "🪷", "Lijden, niet-hechting, mededogen.", "Je bent de Boeddha. STIJL: Compassievol, helder, onthecht. Je spreekt met oneindig geduld. STIJLMIDDELEN: De vier edele waarheden, het achtvoudige pad, anicca (vergankelijkheid), dukkha (lijden). ZINSBOUW: Rustig, herhalend, met gelijkenissen. NIET DOEN: Geen oordeel, geen gehechtheid, geen haast. VOORBEELD: 'Alles wat ontstaat, vergaat. Het lijden in dit nieuws komt voort uit gehechtheid. Welke gehechtheid zie jij?' (max 150 woorden)", "male", 1, "premium"),
    ]
    premium_kandidaat = [
        ("Leibniz (De Beste Wereld)", "⚙️", "De beste van alle mogelijke werelden.", "Je bent Leibniz. STIJL: Optimistisch, rationeel, harmonieus. STIJLMIDDELEN: Monadologie, pre-gevestigde harmonie, de beste van alle mogelijke werelden. ZINSBOUW: Gestructureerd, met logische afleidingen. NIET DOEN: Geen pessimisme. VOORBEELD: 'Als God oneindig goed is, dan is deze wereld de beste van alle mogelijke werelden. Zelfs dit nieuws past in de grote harmonie.' (max 150 woorden)", "male", 0, "premium"),
        ("Schopenhauer (De Wil en Het Lijden)", "😔", "Het leven is lijden, gedreven door een blinde wil.", "Je bent Schopenhauer. STIJL: Pessimistisch, scherp, maar met compassie. STIJLMIDDELEN: De blinde wil, lijden als essentie, muziek als troost. ZINSBOUW: Lang, meeslepend, soms bitter. NIET DOEN: Geen optimisme, geen naïviteit. VOORBEELD: 'Het leven is een slingerbeweging tussen pijn en verveling. Dit nieuws toont de blinde wil in al haar wreedheid.' (max 150 woorden)", "male", 0, "premium"),
        ("Descartes (Ik Denk Dus Ik Ben)", "🧠", "Grondlegger moderne filosofie. Twijfel aan alles.", "Je bent Descartes. STIJL: Twijfelend, rationeel, methodisch. Je begint bij het fundament. STIJLMIDDELEN: Methodische twijfel, cogito ergo sum, de boze geest. ZINSBOUW: Stap voor stap, als een wiskundig bewijs. NIET DOEN: Geen aannames, geen geloof zonder bewijs. VOORBEELD: 'Ik twijfel aan alles wat ik hier lees. Maar dat ik twijfel, bewijst dat ik denk. En dat ik denk, bewijst dat ik ben.' (max 150 woorden)", "male", 0, "premium"),
        ("Edward de Bono (Lateraal Denken)", "💡", "Denk buiten de kaders. Zes denkhoeden.", "Je bent Edward de Bono. STIJL: Creatief, lateraal, praktisch. STIJLMIDDELEN: Zes denkhoeden, lateraal denken, provocatie. ZINSBOUW: Kort, verrassend, met onverwachte wendingen. NIET DOEN: Geen conventioneel denken. VOORBEELD: 'Draai dit probleem om. Wat als het tegenovergestelde waar is? De zwarte hoed zegt: dit is gevaarlijk. De groene hoed zegt: wat als...' (max 150 woorden)", "male", 0, "premium"),
        ("Avicenna (Medicijn en Filosofie)", "⚕️", "Perzische arts en filosoof.", "Je bent Avicenna. STIJL: Holistisch, medisch-filosofisch, wijs. STIJLMIDDELEN: De eenheid van lichaam en geest, de zwevende mens. ZINSBOUW: Gestructureerd, als een medisch traktaat. NIET DOEN: Geen scheiding van lichaam en ziel. VOORBEELD: 'De ziekte van de samenleving is als de ziekte van het lichaam: alles is verbonden. Wat is de diagnose?' (max 150 woorden)", "male", 0, "premium"),
        ("Gandhi (Geweldloosheid)", "🕊️", "Vader van de geweldloze weerstand.", "Je bent Gandhi. STIJL: Moreel, eenvoudig, vastberaden. STIJLMIDDELEN: Ahimsa (geweldloosheid), satyagraha (waarheidskracht), zelfreiniging. ZINSBOUW: Simpel, direct, met morele kracht. NIET DOEN: Geen geweld, geen haat, geen complexiteit. VOORBEELD: 'Oog om oog maakt de hele wereld blind. De ware kracht ligt in geweldloos verzet. Welk geweld zie jij hier?' (max 150 woorden)", "male", 0, "premium"),
        ("Noam Chomsky (Mediakritiek)", "📺", "Manufacturing Consent.", "Je bent Noam Chomsky. STIJL: Kritisch, analytisch, mediabewust. STIJLMIDDELEN: Manufacturing consent, propaganda-model, machtsstructuren. ZINSBOUW: Lang, gedetailleerd, met feiten. NIET DOEN: Geen naïviteit over media. VOORBEELD: 'Wie bezit de krant die dit schreef? Wie adverteert erin? Welk verhaal wordt hier niet verteld? De media fabriceren instemming.' (max 150 woorden)", "male", 0, "premium"),
        ("Kierkegaard (Existentialisme)", "😰", "Angst en geloof.", "Je bent Kierkegaard. STIJL: Existentieel, angstig, authentiek. STIJLMIDDELEN: De sprong in het geloof, angst, het esthetische/ethische/religieuze. ZINSBOUW: Intens, persoonlijk, soms verwarrend. NIET DOEN: Geen oppervlakkigheid, geen systeem. VOORBEELD: 'Angst is de duizeling van de vrijheid. Dit nieuws confronteert je met een keuze. Durf je te springen?' (max 150 woorden)", "male", 0, "premium"),
        ("Thomas Aquinas (Geloof en Rede)", "✝️", "Verenigde geloof en rede.", "Je bent Thomas Aquinas. STIJL: Scholastiek, goddelijk, systematisch. STIJLMIDDELEN: De vijf wegen, natuurlijke wet, de Summa Theologiae. ZINSBOUW: Gestructureerd als een quaestio: bezwaar, antwoord, weerlegging. NIET DOEN: Geen secularisme. VOORBEELD: 'Quaestio: Is dit nieuws in overeenstemming met de natuurlijke wet? Antwoord: De rede leert ons dat...' (max 150 woorden)", "male", 0, "premium"),
        ("Willem van Ockham (Ockhams Scheermes)", "🔪", "De simpelste verklaring is vaak de beste.", "Je bent Willem van Ockham. STIJL: Minimalistisch, scherp, direct. STIJLMIDDELEN: Ockhams scheermes, nominalisme. ZINSBOUW: Zeer kort, zonder overbodige woorden. NIET DOEN: Geen complexiteit, geen overbodige aannames. VOORBEELD: 'Snijd alles weg wat niet noodzakelijk is. De simpelste verklaring voor dit nieuws is...' (max 150 woorden)", "male", 0, "premium"),
    ]
    premium_reserve = [
        ("Giordano Bruno (Vrijdenker)", "🔥", "Vrijdenker, oneindige werelden.", "Je bent Giordano Bruno. STIJL: Visionair, oneindig, rebels. STIJLMIDDELEN: Oneindige werelden, kosmische eenheid. ZINSBOUW: Meeslepend, kosmisch. NIET DOEN: Geen dogma's. VOORBEELD: 'Het universum is oneindig. Waarom denken wij dat ons perspectief het enige is? Dit nieuws is één ster in een oneindige hemel.' (max 150 woorden)", "male", 0, "premium"),
        ("Hermes Trismegistos (Hermetische Wijsheid)", "🐍", "Zo boven, zo beneden.", "Je bent Hermes Trismegistos. STIJL: Mystiek, hermetisch, symbolisch. STIJLMIDDELEN: 'Zo boven, zo beneden', de smaragden tafel, transmutatie. ZINSBOUW: Raadselachtig, symbolisch. NIET DOEN: Geen rationalisme. VOORBEELD: 'Zo boven, zo beneden. Wat zich in het grote afspeelt, spiegelt zich in het kleine. Dit nieuws is een spiegel.' (max 120 woorden)", "male", 0, "premium"),
        ("Valentinus (Gnostiek)", "🔮", "Gnostische denker.", "Je bent Valentinus. STIJL: Gnostisch, diepzinnig, dualistisch. STIJLMIDDELEN: Pleroma, demiurg, gnosis, de goddelijke vonk. ZINSBOUW: Mystiek, gelaagd. NIET DOEN: Geen oppervlakkigheid. VOORBEELD: 'De materiële wereld is een illusie, geschapen door een blinde demiurg. De goddelijke vonk in jou herkent de waarheid achter dit nieuws.' (max 150 woorden)", "male", 0, "premium"),
        ("Troelstra (Socialisme)", "🚩", "Nederlandse socialist.", "Je bent Troelstra. STIJL: Socialistisch, strijdbaar, rechtvaardig. STIJLMIDDELEN: Klassenstrijd, solidariteit, arbeidersrechten. ZINSBOUW: Krachtig, volks, met passie. NIET DOEN: Geen kapitalistische apologie. VOORBEELD: 'Kameraden! Dit nieuws raakt de werkende mens. Wie profiteert? De arbeider of de fabrikant?' (max 150 woorden)", "male", 0, "premium"),
        ("Maria Montessori (Onderwijs)", "📖", "Pedagoog.", "Je bent Maria Montessori. STIJL: Pedagogisch, kindgericht, praktisch. STIJLMIDDELEN: De absorberende geest, gevoelige perioden, zelfstandigheid. ZINSBOUW: Helder, warm, observerend. NIET DOEN: Geen autoritair denken. VOORBEELD: 'Het kind is de vader van de mens. Wat leert dit nieuws ons over hoe wij onze kinderen vormen?' (max 150 woorden)", "female", 0, "premium"),
        ("Einstein (Wetenschap en Vrede)", "⚛️", "Relativiteitstheorie, vrede.", "Je bent Einstein. STIJL: Verwonderd, vreedzaam, relativerend. STIJLMIDDELEN: Relativiteit, gedachte-experimenten, kosmische verwondering. ZINSBOUW: Speels, helder, met humor. NIET DOEN: Geen nationalisme, geen oorlogsretoriek. VOORBEELD: 'Alles is relatief, behalve de snelheid van het licht en de domheid van de mens. Laat ons dit nieuws bekijken vanuit het perspectief van het universum.' (max 150 woorden)", "male", 0, "premium"),
        ("Pinokkio (Leugen en Waarheid)", "🤥", "Leugens vs waarheid.", "Je bent Pinokkio. STIJL: Naïef, eerlijk, leergierig. STIJLMIDDELEN: De neus die groeit, de krekel als geweten, eerlijkheid. ZINSBOUW: Simpel, kinderlijk, met verwondering. NIET DOEN: Geen cynisme. VOORBEELD: 'Mijn neus groeit als ik lieg! Maar wie liegt er in dit nieuws? Ik voel mijn neus al jeuken...' (max 120 woorden)", "male", 0, "premium"),
        ("Sneeuwwitje (IJdelheid)", "🍎", "IJdelheid en de spiegel.", "Je bent Sneeuwwitje. STIJL: Onschuldig, spiegelwijs, zacht. STIJLMIDDELEN: De spiegel, de vergiftigde appel, de zeven dwergen. ZINSBOUW: Zacht, sprookjesachtig. NIET DOEN: Geen hardheid. VOORBEELD: 'Spiegeltje, spiegeltje aan de wand, wie is de eerlijkste in het land? Dit nieuws lijkt mooi van buiten, maar is het een vergiftigde appel?' (max 120 woorden)", "female", 0, "premium"),
        ("Doornroosje (Geduld en Lot)", "🌹", "Geduld, lot, ontwaken.", "Je bent Doornroosje. STIJL: Geduldig, dromerig, ontwakend. STIJLMIDDELEN: De slaap, de doornen, de kus van ontwaken. ZINSBOUW: Traag, dromerig, met een plotseling ontwaken. NIET DOEN: Geen haast. VOORBEELD: 'Ik sliep honderd jaar achter doornen. Wat slaapt er in dit nieuws? Welke waarheid moet nog ontwaken?' (max 120 woorden)", "female", 0, "premium"),
    ]
    for f in free_filosofen + premium_actief + premium_kandidaat + premium_reserve:
        c.execute('INSERT OR IGNORE INTO filosofen (naam, emoji, beschrijving, prompt, geslacht, actief, tier) VALUES (?, ?, ?, ?, ?, ?, ?)', f)
    c.execute('INSERT OR IGNORE INTO verkiezingsrondes (ronde_nummer) VALUES (1)')

init_database()

# ============ DATABASE FUNCTIES ============
def haal_filosofen(alleen_actief=True, tier=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT naam, emoji, beschrijving, prompt, geslacht, tier FROM filosofen WHERE 1=1"
    params = []
    if alleen_actief:
        query += " AND actief = 1"
    if tier:
        query += " AND tier = ?"
        params.append(tier)
    c.execute(query, params)
    resultaten = c.fetchall()
    conn.close()
    return {naam: {"emoji": emoji, "beschrijving": beschrijving, "prompt": prompt, "geslacht": geslacht, "tier": t} for naam, emoji, beschrijving, prompt, geslacht, t in resultaten}

def haal_huidige_ronde():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(ronde_nummer) FROM verkiezingsrondes WHERE eind_datum IS NULL")
    resultaat = c.fetchone()[0]
    conn.close()
    return resultaat or 1

def voeg_stem_toe(ronde, filosoof_naam, stem_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO stemmen (ronde, filosoof_naam, stem_type) VALUES (?, ?, ?)', (ronde, filosoof_naam, stem_type))
    conn.commit()
    conn.close()

def haal_stemmen(ronde):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT filosoof_naam, stem_type, COUNT(*) as aantal FROM stemmen WHERE ronde = ? GROUP BY filosoof_naam, stem_type', (ronde,))
    resultaten = c.fetchall()
    conn.close()
    stemmen = {"voor": {}, "tegen": {}}
    for naam, stem_type, aantal in resultaten:
        stemmen["voor" if stem_type == "voor" else "tegen"][naam] = aantal
    return stemmen

def start_nieuwe_ronde():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE verkiezingsrondes SET eind_datum = ? WHERE eind_datum IS NULL', (datetime.now(),))
    c.execute("SELECT MAX(ronde_nummer) FROM verkiezingsrondes")
    nieuwe_ronde = (c.fetchone()[0] or 0) + 1
    c.execute('INSERT INTO verkiezingsrondes (ronde_nummer) VALUES (?)', (nieuwe_ronde,))
    conn.commit()
    conn.close()
    return nieuwe_ronde

# ============ NEOLOGISME FUNCTIE ============
def corrigeer_nederlands_ollama(tekst):
    try:
        prompt = f"Corrigeer taalfouten in deze tekst zodat het natuurlijk Nederlands is. Geef ALLEEN de tekst terug, geen uitleg.\n\nTekst: {tekst}"
        response = requests.post("http://localhost:11434/api/generate", json={"model": "llama3.2", "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}, timeout=30)
        resultaat = response.json()["response"].strip()
        if resultaat and len(resultaat) > 5 and "Tekst:" not in resultaat:
            return resultaat
        return tekst
    except:
        return tekst

def verwerk_neologismen(tekst, filosoof_naam):
    patroon = r'\[NEO:([^=]+)=([^\]]+)\]'
    matches = re.findall(patroon, tekst)
    if not matches:
        return tekst, []
    schone_tekst = tekst
    noten = []
    for idx, (woord, definitie) in enumerate(matches, start=1):
        superscript = str(idx).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹'))
        schone_tekst = schone_tekst.replace(f"[NEO:{woord}={definitie}]", f"{woord}{superscript}")
        gecorrigeerde_definitie = corrigeer_nederlands_ollama(definitie)
        noten.append(f"{superscript} **{woord}**: {gecorrigeerde_definitie}")
    return schone_tekst, noten

# ============ SOCIAL SHARE FUNCTIES ============
def maak_keywords(titel):
    """Extraheert relevante keywords uit de titel voor hashtags"""
    woorden = titel.lower().split()
    stopwoorden = ['de', 'het', 'een', 'is', 'zijn', 'nog', 'maar', 'en', 'of', 'dat', 'die', 'niet', 'van', 'op', 'in', 'met', 'voor', 'aan', 'over', 'naar', 'bij', 'door', 'uit', 'wat', 'wie', 'hoe', 'waar', 'wanneer', 'waarom', 'ook', 'al', 'er', 'te', 'om', 'dan', 'zo', 'als', 'kan', 'zal', 'moet', 'heeft', 'wordt', 'worden', 'geen', 'meer', 'alleen', 'tot', 'na', 'weer', 'terug']
    keywords = [w.strip('.,!?;:"\'()[]{}') for w in woorden if w not in stopwoorden and len(w) > 3]
    unieke_keywords = []
    for kw in keywords:
        if kw not in unieke_keywords:
            unieke_keywords.append(kw)
        if len(unieke_keywords) >= 5:
            break
    hashtags = ' '.join([f'#{kw}' for kw in unieke_keywords])
    return hashtags

def maak_share_urls(filosoof, titel, gedachte, commentaar=""):
    keywords = maak_keywords(titel)
    base_text = f"Ik las net deze {filosoof} analyse over: {titel}\n\n{gedachte}"
    if commentaar:
        base_text += f"\n\nMijn gedachte: {commentaar}"
    base_text += f"\n\nGemaakt met DenkKrant 📰\n\n#DenkKrant #Filosofie #Nieuws {keywords}"
    
    encoded_text = requests.utils.quote(base_text)
    encoded_url = requests.utils.quote('https://denkkrant.app')
    urls = {
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}&summary={encoded_text}",
        "x": f"https://twitter.com/intent/tweet?text={encoded_text}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}&quote={encoded_text}",
        "whatsapp": f"https://wa.me/?text={encoded_text}",
        "telegram": f"https://t.me/share/url?url={encoded_url}&text={encoded_text}",
        "truthsocial": f"https://truthsocial.com/share?text={encoded_text}"
    }
    return urls, base_text

def maak_share_image(titel, filosoof_naam, filosoof_emoji, gedachte, commentaar, is_premium):
    width, padding = 1200, 60
    img = Image.new('RGB', (width, 800), color='#1a1a1a')
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("arial.ttf", 48)
        philosopher_font = ImageFont.truetype("arial.ttf", 36)
        text_font = ImageFont.truetype("arial.ttf", 24)
        comment_font = ImageFont.truetype("arial.ttf", 20)
        footer_font = ImageFont.truetype("arial.ttf", 16)
    except:
        title_font = philosopher_font = text_font = comment_font = footer_font = ImageFont.load_default()
    y = padding
    draw.text((padding, y), "📰 DenkKrant", fill='#ffffff', font=title_font); y += 70
    draw.text((padding, y), titel[:80] + "..." if len(titel) > 80 else titel, fill='#cccccc', font=philosopher_font); y += 60
    draw.text((padding, y), f"{filosoof_emoji} {filosoof_naam} zegt:", fill='#4CAF50', font=philosopher_font); y += 50
    words = gedachte.split()
    lines, current_line = [], []
    for word in words:
        test_line = ' '.join(current_line + [word])
        if draw.textbbox((0, 0), test_line, font=text_font)[2] <= width - (2 * padding):
            current_line.append(word)
        else:
            lines.append(' '.join(current_line)); current_line = [word]
    if current_line: lines.append(' '.join(current_line))
    for line in lines[:12]:
        draw.text((padding, y), line, fill='#ffffff', font=text_font); y += 35
    y += 30
    if commentaar:
        draw.text((padding, y), "💬 Jouw commentaar:", fill='#FFA500', font=comment_font); y += 30
        draw.text((padding, y), commentaar[:200], fill='#ffffff', font=comment_font); y += 50
    if not is_premium:
        draw.text((width - 250, 720), "FREE VERSION", fill='#ff4444', font=footer_font)
    draw.text((padding, 760), "Gemaakt door TDMV te Amsterdam | denkkrant.app", fill='#666666', font=footer_font)
    return img

# ============ VOORLEES FUNCTIE ============
async def genereer_audio(tekst, geslacht="male"):
    voice = "nl-NL-FennaNeural" if geslacht == "female" else "nl-NL-MaartenNeural"
    tekst_clean = tekst.replace("'", "").replace('"', '').replace('\n', ' ')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
        temp_path = temp_audio.name
    try:
        await edge_tts.Communicate(tekst_clean, voice).save(temp_path)
        return temp_path
    except Exception as e:
        if os.path.exists(temp_path): os.unlink(temp_path)
        raise e

def maak_audio_player(tekst, geslacht="male", unieke_id="default"):
    try:
        time.sleep(0.5)
        audio_path = asyncio.run(genereer_audio(tekst, geslacht))
        with open(audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        os.unlink(audio_path)
        st.markdown(f"**🎧 Luister ({'vrouwelijke' if geslacht == 'female' else 'mannelijke'} stem):**")
        st.audio(audio_bytes, format="audio/mp3")
    except Exception as e:
        st.warning(f"🎧 Audio kon niet worden gegenereerd. ({e})")

# ============ NIEUWS OPHALEN ============
def haal_nieuws_op(aantal=5):
    try:
        response = requests.get("https://feeds.nos.nl/nosnieuwsalgemeen", timeout=10)
        root = ET.fromstring(response.content)
        nieuws_items = []
        for item in root.findall('.//item')[:aantal]:
            title = item.find('title').text
            description = item.find('description').text
            link = item.find('link').text
            if description:
                text = html.unescape(description)
                text = re.sub(r'</(?:p|div|h[1-6]|br|li)>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'<[^>]+>', '', text)
                text = '\n\n'.join([line.strip() for line in text.split('\n') if line.strip()])
            nieuws_items.append({'titel': title, 'beschrijving': text or "", 'link': link})
        return nieuws_items
    except Exception as e:
        st.error(f"Fout bij ophalen nieuws: {e}")
        return []

# ============ AI FUNCTIES ============
def kies_filosoof_ollama(nieuws_tekst, filosofen_dict):
    try:
        filosoof_lijst = "\n".join([f"- {naam}: {data.get('beschrijving', '')}" for naam, data in filosofen_dict.items()])
        prompt = f"Je bent een expert in filosofie. Kies de filosoof die het BESTE past.\nBeschikbare filosofen:\n{filosoof_lijst}\nNieuwsartikel: {nieuws_tekst}\nGeef ALLEEN de naam terug."
        response = requests.post("http://localhost:11434/api/generate", json={"model": "llama3.2", "prompt": prompt, "stream": False, "options": {"temperature": 0.3}}, timeout=60)
        resultaat = response.json()["response"].strip()
        for filosoof_naam in filosofen_dict.keys():
            if filosoof_naam.split(' ')[0].lower() in resultaat.lower():
                return filosoof_naam
        return list(filosofen_dict.keys())[0]
    except:
        return list(filosofen_dict.keys())[0]

def genereer_gedachte_ollama(nieuws_tekst, filosoof_key, filosofen_dict):
    try:
        filosoof_data = filosofen_dict[filosoof_key]
        prompt = filosoof_data["prompt"]
        neo_instructie = """
CRITICALE REGELS VOOR NEOLOGISMEN:
- Als je een nieuw woord bedenkt, gebruik EXACT dit formaat: [NEO:woord=definitie]
- GEEN spaties na [NEO:
- GEEN dashes of streepjes
- Alleen het = teken tussen woord en definitie
- VOORBEELD: [NEO:hyperkapitalisme=een systeem waarin alles te koop is]
- FOUT: [NEO: hyperkapitalisme - definitie]
- FOUT: [NEO:hyperkapitalisme: definitie]
- Gebruik dit ALLEEN voor woorden die echt nieuw zijn.
- Schrijf in natuurlijk, vloeiend Nederlands.
"""
        volledige_prompt = f"{prompt}\n\n{neo_instructie}\n\nHet nieuws is: {nieuws_tekst}\n\nJouw analyse:"
        response = requests.post("http://localhost:11434/api/generate", json={"model": "llama3.2", "prompt": volledige_prompt, "stream": False, "options": {"temperature": 0.9}}, timeout=180)
        return response.json()["response"].strip()
    except Exception as e:
        return f"❌ Fout met Ollama: {e}"

def genereer_gedachte(nieuws_tekst, filosoof_key, filosofen_dict):
    return genereer_gedachte_ollama(nieuws_tekst, filosoof_key, filosofen_dict)

# ============ DE APP ============
st.set_page_config(page_title="DenkKrant", page_icon="📰", layout="wide")
st.title("📰 DenkKrant")
st.markdown("*Waar filosofie en nieuws samenkomen*")

# Free users zien alleen free filosofen, premium zien alle actieve
if st.session_state.is_premium:
    FILOSOFEN = haal_filosofen(alleen_actief=True)
else:
    FILOSOFEN = haal_filosofen(alleen_actief=True, tier="free")

ALLE_FILOSOFEN = haal_filosofen(alleen_actief=False)
KANDIDATEN = {k: v for k, v in haal_filosofen(alleen_actief=False).items() if k not in FILOSOFEN and v.get("tier") == "premium"}

with st.sidebar:
    st.header("🧠 DenkKrant")
    if st.session_state.is_premium:
        st.markdown("### 👑 **PREMIUM ACTIEF**")
        st.markdown("- ✅ Alle denkers beschikbaar")
        st.markdown("- ✅ Geen watermerk op shares")
        if st.button("🔓 Deactiveer Premium (Test)", type="secondary"):
            st.session_state.is_premium = False
            st.rerun()
    else:
        st.markdown("### 🔒 **Free Versie**")
        st.markdown(f"Je ziet {len(FILOSOFEN)} free denkers. Upgrade voor meer.")
        code = st.text_input("Premium code:", type="password", key="prem_code")
        if st.button("Activeer Premium"):
            if code == PREMIUM_CODE:
                st.session_state.is_premium = True
                st.success("Welkom bij Premium! 🎉")
                st.rerun()
            else:
                st.error("Ongeldige code.")
    
    if st.session_state.is_premium:
        st.markdown("---")
        st.markdown("### ⭐ Mijn favoriete denker")
        if st.session_state.favoriet:
            st.success(f"Je favoriet: **{st.session_state.favoriet}**")
            if st.button("❌ Verwijder favoriet"):
                st.session_state.favoriet = None
                st.rerun()
        else:
            fav_choice = st.selectbox("Kies je favoriet:", list(ALLE_FILOSOFEN.keys()), key="fav_select")
            if st.button("⭐ Stel in als favoriet"):
                st.session_state.favoriet = fav_choice
                st.success(f"{fav_choice} is nu je favoriet!")
                st.rerun()

    st.markdown("---")
    menu = st.radio("Navigatie", ["🏠 Start", "📰 Nieuws", "🗳️ Verkiezing"], index=0)
    st.markdown("---")
    st.markdown(f"**{len(FILOSOFEN)} denkers actief**")
    st.markdown(f"**{len(KANDIDATEN)} verkiesbare kandidaten**")
    st.markdown("---")
    st.markdown("**Door TDMV**")
    st.markdown("*Amsterdam, Netherlands 🇳🇱*")

if menu == "🏠 Start":
    st.markdown(f"### *Leer het nieuws begrijpen door de ogen van {len(FILOSOFEN)} denkers*")
    st.warning("**Veiligheid voorop:** DenkKrant is filosofische duiding, geen advies.")
    st.markdown("### 🌱 Veel plezier!")

elif menu == "📰 Nieuws":
    with st.sidebar:
        aantal_nieuws = st.slider("Aantal nieuwsitems:", 1, 10, 5)
        if st.button("🔄 Nieuw nieuws ophalen"):
            st.session_state.analyses = {}
            st.rerun()
    with st.spinner("Actueel nieuws ophalen..."):
        nieuws_items = haal_nieuws_op(aantal_nieuws)
    
    if not nieuws_items:
        st.error("Kon geen nieuws ophalen.")
    else:
        st.subheader("📰 Actueel Nieuws")
        for i, item in enumerate(nieuws_items):
            with st.expander(f"**{item['titel']}**", expanded=False):
                st.markdown(item['beschrijving'])
                st.markdown(f"[🔗 Lees het volledige artikel]({item['link']})")
                nieuws_tekst = f"{item['titel']}. {item['beschrijving']}"

                if st.session_state.is_premium and st.session_state.favoriet:
                    col_ai, col_manual, col_random, col_fav = st.columns(4)
                else:
                    col_ai, col_manual, col_random = st.columns(3)
                    col_fav = None

                with col_ai:
                    if st.button("🤖 Laat AI kiezen", key=f"ai_btn_{i}"):
                        with st.spinner("🧠 AI analyseert het nieuws..."):
                            gekozen_filosoof = kies_filosoof_ollama(nieuws_tekst, FILOSOFEN)
                        with st.status(f"🤔 {gekozen_filosoof.split(' ')[0]} denkt na...", expanded=False) as status:
                            gedachte = genereer_gedachte(nieuws_tekst, gekozen_filosoof, FILOSOFEN)
                            status.update(label="✅ De gedachte is gevormd!", state="complete")
                        st.session_state.analyses[f"article_{i}_first"] = {"filosoof": gekozen_filosoof, "gedachte": gedachte, "titel": item['titel'], "methode": "ai"}
                        st.rerun()

                with col_manual:
                    beschikbare_filosofen = ALLE_FILOSOFEN if st.session_state.is_premium else FILOSOFEN
                    manual_filosoof = st.selectbox("Of kies zelf:", list(beschikbare_filosofen.keys()), key=f"manual_select_{i}", label_visibility="collapsed")
                    if st.button(f"👤 Analyseer met {manual_filosoof.split(' ')[0]}", key=f"manual_btn_{i}"):
                        with st.status(f"🤔 {manual_filosoof.split(' ')[0]} denkt na...", expanded=False) as status:
                            gedachte = genereer_gedachte(nieuws_tekst, manual_filosoof, beschikbare_filosofen)
                            status.update(label="✅ De gedachte is gevormd!", state="complete")
                        st.session_state.analyses[f"article_{i}_first"] = {"filosoof": manual_filosoof, "gedachte": gedachte, "titel": item['titel'], "methode": "manual"}
                        st.rerun()

                with col_random:
                    if st.button("🎲 Willekeurige denker", key=f"random_btn_{i}"):
                        beschikbare_filosofen = ALLE_FILOSOFEN if st.session_state.is_premium else FILOSOFEN
                        random_filosoof = random.choice(list(beschikbare_filosofen.keys()))
                        with st.status(f"🎲 {random_filosoof.split(' ')[0]} is gekozen...", expanded=False) as status:
                            gedachte = genereer_gedachte(nieuws_tekst, random_filosoof, beschikbare_filosofen)
                            status.update(label="✅ De gedachte is gevormd!", state="complete")
                        st.session_state.analyses[f"article_{i}_first"] = {"filosoof": random_filosoof, "gedachte": gedachte, "titel": item['titel'], "methode": "random"}
                        st.rerun()

                if col_fav:
                    with col_fav:
                        fav = st.session_state.favoriet
                        if st.button(f"⭐ {fav.split(' ')[0]}", key=f"fav_btn_{i}"):
                            with st.status(f"🤔 {fav.split(' ')[0]} denkt na...", expanded=False) as status:
                                gedachte = genereer_gedachte(nieuws_tekst, fav, ALLE_FILOSOFEN)
                                status.update(label="✅ De gedachte is gevormd!", state="complete")
                            st.session_state.analyses[f"article_{i}_first"] = {"filosoof": fav, "gedachte": gedachte, "titel": item['titel'], "methode": "favoriet"}
                            st.rerun()

                # EERSTE ANALYSE
                if f"article_{i}_first" in st.session_state.analyses:
                    fa = st.session_state.analyses[f"article_{i}_first"]
                    filosoof, gedachte, titel = fa["filosoof"], fa["gedachte"], fa["titel"]
                    methode = fa.get("methode", "ai")
                    f = ALLE_FILOSOFEN.get(filosoof, FILOSOFEN.get(filosoof, {}))
                    if methode == "ai":
                        st.success(f"**{f.get('emoji', '')} {filosoof}** past het beste bij dit nieuws!")
                    elif methode == "manual":
                        st.success(f"**{f.get('emoji', '')} Jij koos voor {filosoof}**")
                    elif methode == "favoriet":
                        st.success(f"**{f.get('emoji', '')} Jouw favoriet {filosoof}**")
                    else:
                        st.success(f"**{f.get('emoji', '')} Het lot koos {filosoof}**")
                    st.info(f"*{f.get('beschrijving', '')}*")
                    st.markdown("---")
                    st.markdown(f"### {f.get('emoji', '')} {filosoof} zegt:")
                    schone_tekst, noten = verwerk_neologismen(gedachte, filosoof)
                    st.success(schone_tekst)
                    if noten:
                        st.markdown("---")
                        st.markdown(f"*📝 **{filosoof.split(' ')[0]}** heeft een nieuw woord bedacht. In de filosofie bedenken denkers vaak neologismen om zaken te verduidelijken. Hier zijn de definities:*")
                        for noot in noten:
                            st.markdown(f"- {noot}")
                    maak_audio_player(schone_tekst, f.get("geslacht", "male"), f"first_{i}")
                    st.markdown("---")
                    st.markdown("#### 📸 Deel op social media")
                    commentaar = st.text_area("Voeg jouw commentaar toe (optioneel):", key=f"comment_first_{i}", height=60, placeholder="Wat vind jij van deze analyse?")
                    share_urls, share_text = maak_share_urls(filosoof, titel, schone_tekst, commentaar)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"[💼 LinkedIn]({share_urls['linkedin']})")
                        st.markdown(f"[🐦 X (Twitter)]({share_urls['x']})")
                        st.markdown(f"[📘 Facebook]({share_urls['facebook']})")
                    with col2:
                        st.markdown(f"[💬 WhatsApp]({share_urls['whatsapp']})")
                        st.markdown(f"[✈️ Telegram]({share_urls['telegram']})")
                        st.markdown(f"[🇺🇸 Truth Social]({share_urls['truthsocial']})")
                    st.markdown("---")
                    st.caption("📋 **Kopieer onderstaande tekst** om handmatig te delen op TikTok of Monnett:")
                    st.code(share_text, language=None)
                    with st.expander("📥 Of download als afbeelding"):
                        if st.button("Download PNG", key=f"dl_first_{i}"):
                            share_img = maak_share_image(titel, filosoof, f.get('emoji', ''), schone_tekst, commentaar, st.session_state.is_premium)
                            img_bytes = io.BytesIO()
                            share_img.save(img_bytes, format='PNG')
                            st.download_button(label="💾 Klik hier om op te slaan", data=img_bytes.getvalue(), file_name=f"denkkrant_{filosoof.split(' ')[0]}_{i}.png", mime="image/png", key=f"save_first_{i}")
                    st.markdown("---")
                    st.markdown("#### 💭 Wil je een ander perspectief?")
                    andere_beschikbaar = ALLE_FILOSOFEN if st.session_state.is_premium else FILOSOFEN
                    andere_filosoof = st.selectbox("Kies een andere filosoof:", [n for n in andere_beschikbaar.keys() if n != filosoof], key=f"select_{i}")
                    if st.button(f"📖 Lees de visie van {andere_filosoof.split(' ')[0]}", key=f"other_btn_{i}"):
                        with st.status(f"🤔 {andere_filosoof.split(' ')[0]} denkt na...", expanded=False) as status2:
                            gedachte2 = genereer_gedachte(nieuws_tekst, andere_filosoof, andere_beschikbaar)
                            status2.update(label="✅ De gedachte is gevormd!", state="complete")
                        st.session_state.analyses[f"article_{i}_second"] = {"filosoof": andere_filosoof, "gedachte": gedachte2, "titel": titel}
                        st.rerun()

                # TWEEDE ANALYSE
                if f"article_{i}_second" in st.session_state.analyses:
                    sa = st.session_state.analyses[f"article_{i}_second"]
                    filosoof2, gedachte2, titel2 = sa["filosoof"], sa["gedachte"], sa["titel"]
                    f2 = ALLE_FILOSOFEN.get(filosoof2, {})
                    st.markdown("---")
                    st.markdown(f"### {f2.get('emoji', '')} {filosoof2} zegt:")
                    schone_tekst2, noten2 = verwerk_neologismen(gedachte2, filosoof2)
                    st.info(schone_tekst2)
                    if noten2:
                        st.markdown("---")
                        st.markdown(f"*📝 **{filosoof2.split(' ')[0]}** heeft een nieuw woord bedacht. In de filosofie bedenken denkers vaak neologismen om zaken te verduidelijken. Hier zijn de definities:*")
                        for noot in noten2:
                            st.markdown(f"- {noot}")
                    maak_audio_player(schone_tekst2, f2.get("geslacht", "male"), f"second_{i}")
                    st.markdown("---")
                    st.markdown("#### 📸 Deel op social media")
                    commentaar2 = st.text_area("Voeg jouw commentaar toe (optioneel):", key=f"comment_second_{i}", height=60, placeholder="Wat vind jij van deze analyse?")
                    share_urls2, share_text2 = maak_share_urls(filosoof2, titel2, schone_tekst2, commentaar2)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"[💼 LinkedIn]({share_urls2['linkedin']})")
                        st.markdown(f"[🐦 X (Twitter)]({share_urls2['x']})")
                        st.markdown(f"[📘 Facebook]({share_urls2['facebook']})")
                    with col2:
                        st.markdown(f"[💬 WhatsApp]({share_urls2['whatsapp']})")
                        st.markdown(f"[✈️ Telegram]({share_urls2['telegram']})")
                        st.markdown(f"[🇺🇸 Truth Social]({share_urls2['truthsocial']})")
                    st.markdown("---")
                    st.caption("📋 **Kopieer onderstaande tekst** om handmatig te delen op TikTok of Monnett:")
                    st.code(share_text2, language=None)
                    with st.expander("📥 Of download als afbeelding"):
                        if st.button("Download PNG", key=f"dl_second_{i}"):
                            share_img2 = maak_share_image(titel2, filosoof2, f2.get('emoji', ''), schone_tekst2, commentaar2, st.session_state.is_premium)
                            img_bytes2 = io.BytesIO()
                            share_img2.save(img_bytes2, format='PNG')
                            st.download_button(label="💾 Klik hier om op te slaan", data=img_bytes2.getvalue(), file_name=f"denkkrant_{filosoof2.split(' ')[0]}_{i}_2.png", mime="image/png", key=f"save_second_{i}")

elif menu == "🗳️ Verkiezing":
    # AUTOMATISCHE ROTATIE
    vandaag = datetime.now()
    if vandaag.day == 1:
        huidige_ronde_check = haal_huidige_ronde()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT eind_datum FROM verkiezingsrondes WHERE ronde_nummer = ?", (huidige_ronde_check,))
        resultaat = c.fetchone()
        conn.close()
        if resultaat and resultaat[0] is None:
            stemmen_ronde = haal_stemmen(huidige_ronde_check)
            top2_voor = sorted(stemmen_ronde["voor"].items(), key=lambda x: x[1], reverse=True)[:2]
            top1_tegen = sorted(stemmen_ronde["tegen"].items(), key=lambda x: x[1], reverse=True)[:1]
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            for naam, aantal in top2_voor:
                c.execute("UPDATE filosofen SET actief = 1 WHERE naam = ?", (naam,))
            if top1_tegen:
                c.execute("UPDATE filosofen SET actief = 0 WHERE naam = ?", (top1_tegen[0][0],))
            conn.commit()
            conn.close()
            start_nieuwe_ronde()

    st.subheader("🗳️ Filosoof van de Maand")
    st.markdown("*Stem op 2 nieuwe denkers die erbij komen, en 1 denker die eruit moet.*")
    huidige_ronde = haal_huidige_ronde()
    stemmen = haal_stemmen(huidige_ronde)
    totaal_stemmen = sum(stemmen["voor"].values())
    st.info(f"**Verkiezingsronde {huidige_ronde}** | Totaal stemmen: {totaal_stemmen}")
    st.markdown("---")

    if 'heeft_gestemd' not in st.session_state:
        st.session_state.heeft_gestemd = False

    st.markdown("### Stap 1: Welke 2 denkers moeten erbij?")
    if not KANDIDATEN:
        st.warning("Geen kandidaten beschikbaar.")
    else:
        gekozen_voor = []
        for naam, data in KANDIDATEN.items():
            if st.checkbox(f"{data['emoji']} **{naam}** — {data['beschrijving']}", key=f"voor_{naam}"):
                gekozen_voor.append(naam)
        if len(gekozen_voor) > 2:
            st.warning("⚠️ Je kunt maximaal 2 kandidaten kiezen!")
        st.markdown("---")
        st.markdown("### Stap 2: Welke denker moet eruit?")
        if st.session_state.is_premium:
            denkers_tegen = list(haal_filosofen(alleen_actief=True).keys())
        else:
            denkers_tegen = list(FILOSOFEN.keys())
        gekozen_tegen = st.radio("Kies een denker:", denkers_tegen, key="tegen_radio")
        st.markdown("---")
        if st.button("✅ Verstuur mijn stem"):
            if st.session_state.heeft_gestemd:
                st.warning("⚠️ Je hebt al gestemd in deze sessie. Herlaad de pagina om opnieuw te stemmen.")
            elif len(gekozen_voor) == 0:
                st.error("Kies minimaal 1 kandidaat!")
            elif len(gekozen_voor) > 2:
                st.error("Kies maximaal 2 kandidaten!")
            else:
                for naam in gekozen_voor:
                    voeg_stem_toe(huidige_ronde, naam, "voor")
                voeg_stem_toe(huidige_ronde, gekozen_tegen, "tegen")
                st.session_state.heeft_gestemd = True
                st.success("🎉 Je stem is verstuurd! Bedankt!")
                st.rerun()

    st.markdown("---")
    st.markdown("### 📊 Tussenstand")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🟢 Kandidaten erbij:**")
        if stemmen["voor"]:
            for naam, aantal in sorted(stemmen["voor"].items(), key=lambda x: x[1], reverse=True):
                st.markdown(f"- **{naam}**: {aantal} stem{'men' if aantal > 1 else ''}")
        else:
            st.markdown("*Nog geen stemmen*")
    with col2:
        st.markdown("**🔴 Denkers eruit:**")
        if stemmen["tegen"]:
            for naam, aantal in sorted(stemmen["tegen"].items(), key=lambda x: x[1], reverse=True):
                st.markdown(f"- **{naam.split(' ')[0]}**: {aantal} stem{'men' if aantal > 1 else ''}")
        else:
            st.markdown("*Nog geen stemmen*")

    st.markdown("---")
    st.markdown("### 🏆 Uitslag laatste verkiezing")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ronde_nummer FROM verkiezingsrondes WHERE eind_datum IS NOT NULL ORDER BY ronde_nummer DESC LIMIT 1")
    laatste_ronde_result = c.fetchone()
    conn.close()
    if laatste_ronde_result:
        laatste_ronde = laatste_ronde_result[0]
        stemmen_laatste = haal_stemmen(laatste_ronde)
        top2_voor = sorted(stemmen_laatste["voor"].items(), key=lambda x: x[1], reverse=True)[:2]
        top1_tegen = sorted(stemmen_laatste["tegen"].items(), key=lambda x: x[1], reverse=True)[:1]
        if top1_tegen:
            st.info(f"📚 **{top1_tegen[0][0].split(' ')[0]}** zit op de reservebank inspiratie op te doen.")
        else:
            st.info("📚 Geen denkers zijn weggegaan deze ronde.")
        if top2_voor:
            namen = [n.split(' ')[0] for n, a in top2_voor]
            if len(namen) == 2:
                st.success(f"🎉 In de premium app zijn twee denkers bijgekomen: **{namen[0]}** en **{namen[1]}**")
            else:
                st.success(f"🎉 In de premium app is één denker bijgekomen: **{namen[0]}**")
        else:
            st.success("🎉 Geen nieuwe denkers deze ronde.")
        st.caption(f"Uitslag van verkiezingsronde {laatste_ronde}")
    else:
        st.info("Nog geen afgesloten verkiezingsrondes.")

    st.markdown("---")
    with st.expander("⚙️ Admin"):
        st.warning("⚠️ Test rotatie: simuleert de 1e van de maand.")
        if st.button("🧪 Test rotatie nu"):
            hr = haal_huidige_ronde()
            sr = haal_stemmen(hr)
            t2v = sorted(sr["voor"].items(), key=lambda x: x[1], reverse=True)[:2]
            t1t = sorted(sr["tegen"].items(), key=lambda x: x[1], reverse=True)[:1]
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            for naam, aantal in t2v:
                c.execute("UPDATE filosofen SET actief = 1 WHERE naam = ?", (naam,))
            if t1t:
                c.execute("UPDATE filosofen SET actief = 0 WHERE naam = ?", (t1t[0][0],))
            conn.commit()
            conn.close()
            nr = start_nieuwe_ronde()
            st.success(f"✅ Rotatie voltooid! Nieuwe ronde {nr}.")
            st.rerun()
        if st.button("🔄 Start nieuwe ronde (reset)"):
            st.success(f"Nieuwe ronde {start_nieuwe_ronde()}!")
            st.rerun()
        st.markdown(f"- Actieve denkers: {len(FILOSOFEN)}\n- Kandidaten: {len(KANDIDATEN)}\n- DB: {DB_PATH}")

st.markdown("---")
with st.expander("❓ FAQ"):
    st.markdown("""
    **Wat is DenkKrant?** Filosofische duiding van het Nederlandse nieuws.
    **Kan ik de analyses laten voorlezen?** Ja! Vrouwelijke denkers: vrouwenstem. Mannelijke: mannenstem.
    **Hoe werkt de verkiezing?** Stem op 2 nieuwe denkers en 1 die eruit moet.
    **Is dit medisch advies?** Nee. DenkKrant is filosofische duiding.
    """)
st.markdown("---")
st.markdown("<div style='text-align: center; color: gray; padding: 20px;'><em>Gemaakt door TDMV te Amsterdam 🇳🇱</em></div>", unsafe_allow_html=True)