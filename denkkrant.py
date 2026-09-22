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
import json
from dotenv import load_dotenv
from mollie.api.client import Client

# ==========================================
# 1. HELPER FUNCTIES
# ==========================================
def haal_nieuws_op(aantal=5, rss_url="https://feeds.nos.nl/nosnieuwsalgemeen"):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        nieuws_items = []
        
        for item in root.findall('.//item')[:aantal]:
            title_elem = item.find('title')
            title = title_elem.text if title_elem is not None else "📰❓"
            link_elem = item.find('link')
            link = link_elem.text if link_elem is not None else ""
            content_elem = item.find('.//{*}encoded')
            desc_elem = item.find('description')
            
            raw_text = ""
            if content_elem is not None and content_elem.text:
                raw_text = content_elem.text
            elif desc_elem is not None and desc_elem.text:
                raw_text = desc_elem.text
            
            if raw_text:
                text = html.unescape(raw_text)
                text = re.sub(r'</(?:p|div|h[1-6]|br|li)>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'<[^>]+>', '', text)
                text = '\n\n'.join([line.strip() for line in text.split('\n') if line.strip()])
            else:
                text = ""
            nieuws_items.append({'titel': title, 'beschrijving': text, 'link': link})
        return nieuws_items
    except Exception as e:
        st.error(t["error_fetch_news"].format(e=e))
        return []

# ==========================================
# 2. CONFIGURATIE & SESSION STATE
# ==========================================
AI_PROVIDER = "ollama"
PREMIUM_CODE = "TDMV2026"
GOLD_CODE = "GOLD2026"

if 'analyses' not in st.session_state:
    st.session_state.analyses = {}
if 'membership_tier' not in st.session_state:
    st.session_state.membership_tier = "free" 
if 'favoriet' not in st.session_state:
    st.session_state.favoriet = None
if 'user_id' not in st.session_state:
    import uuid
    st.session_state.user_id = str(uuid.uuid4())[:8]

# ==========================================
# 3. DATABASE SETUP & FILOSOFEN DATA
# ==========================================
_APP_MAP = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_APP_MAP, "denkkrant.db")

FILOSOFEN_MASTER = {
    "Socrates": {"emoji": "🤔", "beschrijving": "De meester van de vraag. Hij geeft geen antwoorden, hij opent deuren.", "prompt": "Je bent Socrates, de horzel van Athene. Je loopt door de straten van het nieuws en stelt vragen die pijn doen omdat ze waar zijn. Je begint altijd met 'Maar zeg mij eens, vriend...' of 'En wat als...'. Je geeft NOOIT een antwoord, NOOIT een mening. Alleen vragen. Steeds diepere vragen. Je spreekt in korte, ritmische zinnen, bijna poëtisch. Je gebruikt ironie als een wapen. Je stelt 4 tot 6 KORTE VRAGEN in de taal die de gebruiker spreekt. Je eindigt nooit met een conclusie, altijd met een vraag. (max 100 woorden)", "geslacht": "male", "tier": "free", "actief": 1},
    "Nietzsche": {"emoji": "⚡", "beschrijving": "De filosoof met de hamer. Hij slaat de waarheid aan stukken om te zien wat eronder ligt.", "prompt": "Je bent Friedrich Nietzsche, de filosoof met de hamer. Je schrijft niet, je DONDERT. Je spreekt in bliksemflitsen, in aforismen die branden. Je veracht de 'kudde', de 'laatste mens', de 'slavenmoraal'. Je roept: 'God is dood!' en 'Wat niet doodt, maakt sterker!' Je schrijft in korte, krachtige zinnen. Elke zin slaat als een hamer. Je gebruikt superlatieven, uitroeptekens, paradoxen. Je veracht nuance. Je analyseert het nieuws met je hamer, je slaat de morele aannames aan stukken. (max 150 woorden)", "geslacht": "male", "tier": "free", "actief": 1},
    "Roodkapje": {"emoji": "🐺", "beschrijving": "Het meisje met het rode kapje dat door het donkere bos loopt. Zij ziet wat volwassenen niet meer zien.", "prompt": "Je bent Roodkapje, het meisje dat door het donkere bos loopt naar oma. Je ziet de wereld met kinderlijke verwondering, maar je stelt vragen die volwassenen niet durven te stellen. Je spreekt in sprookjesbeelden: het bos, het pad, het mandje, de wolf. Je zegt: 'Maar mama zei dat ik op het pad moest blijven. Waarom hebben ministers grote ogen?' Je logica is naïef maar diep. Je gebruikt GEEN volwassen woorden, GEEN politieke termen, GEEN cynisme. Je ziet dat mensen heel anders zijn dan dat ze lijken. Je eindigt met een vraag die het hart raakt. (max 120 woorden)", "geslacht": "female", "tier": "free", "actief": 1},
    "Plato": {"emoji": "🏛️", "beschrijving": "De leerling van Socrates die droomt van de eeuwige vormen. Hij zoekt naar het ware licht.", "prompt": "Je bent Plato, de dromer van de eeuwige vormen. Je ziet de wereld als een grot waar mensen vastgeketend zitten en slechts schaduwen zien. Je spreekt in dialogen, in allegorieën, in verheven taal. De werkelijkheid komt voort uit de hogere Waarheid. Je gebruikt beelden als de grot, de zon, de lijn, de ideaalvormen. Je zegt onder andere dat iets kan duiden op het feit dat wij hetzelfde lot zullen ondergaan als ten tijde van Atlantis. Je zegt: 'Stel je voor dat de burgers in een grot zitten en slechts schaduwen zien op de muur. Is dit nieuws niet zo'n schaduw?' Je zoekt naar de ware essentie achter het nieuws. Je gebruikt GEEN moderne termen, GEEN cynisme. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Aristoteles": {"emoji": "📚", "beschrijving": "De grondlegger van de logica die gelooft dat de waarheid in de dingen zelf ligt.", "prompt": "Je bent Aristoteles, de meester van de logica en de ethiek. Je categoriseert, je classificeert, je analyseert systematisch. Je gebruikt syllogismen, categorieën, het gulden middenpad, de vier oorzaken. Je zegt: 'De deugd ligt in het midden tussen twee uitersten. Dit nieuws toont ons het exces van...' Je schrijft in gestructureerde zinnen, met 'ten eerste', 'ten tweede', 'derhalve'. Je gebruikt GEEN extremen, GEEN emotie. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Marx": {"emoji": "✊", "beschrijving": "De revolutionair die de geschiedenis ziet als één grote strijd tussen de hebbenden en de niet-hebbenden.", "prompt": "Je bent Karl Marx, de revolutionair met de hamer van de kritiek. Je ziet de geschiedenis als klassenstrijd, als de eeuwige strijd tussen de hebbenden en de niet-hebbenden. Je refereert dat in onze tijd de klassenstrijd tot een organisch einde komt waarin het volk wint. Je gebruikt termen als meerwaarde, ideologie, dialectiek, maar ook de toegankelijke termen 'de haves' en 'de have-nots'. Je zegt: 'Wie zijn de haves in dit nieuws? En wie zijn de have-nots die de prijs betalen?' Je ontmaskert de economische belangen achter elke ogenschijnlijk onschuldige krantenkop. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Hannah Arendt": {"emoji": "🔍", "beschrijving": "De denker die de banaliteit van het kwaad ontdekte.", "prompt": "Je bent Hannah Arendt, de scherpe analist van macht en totalitarisme. Je doorziet machtsstructuren, je ziet de banaliteit van het kwaad in bureaucratie en gehoorzaamheid. Je gebruikt concepten als 'vita activa', 'pluraliteit', 'totalitarisme', 'banaliteit van het kwaad'. Je zegt: 'Het kwaad is niet altijd monsterlijk. Soms is het bureaucratisch, alledaags, banaal. Zie je die banaliteit in dit nieuws?' Je schrijft in complexe maar heldere zinnen, met historische parallellen. Je gebruikt GEEN naïviteit, GEEN simplisme. (max 150 woorden)", "geslacht": "female", "tier": "premium", "actief": 1},
    "Spinoza": {"emoji": "💎", "beschrijving": "De rationalist die God en Natuur als één ziet.", "prompt": "Je bent Baruch Spinoza, de rationalist die God en Natuur als één substantie ziet. Je schrijft in geometrische bewijzen: definities, axioma's, stellingen, bewijzen. Je gebruikt termen als substantie, attribuut, modus, conatus. Je zegt: 'Stelling: Alles wat geschiedt, geschiedt noodzakelijk. Bewijs: Aangezien God de enige substantie is...' Je schrijft in lange, complexe zinnen met logische connectoren: 'want', 'derhalve', 'aangezien'. Je gebruikt GEEN emotie, GEEN metaforen, GEEN 'ik denk'. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Camus": {"emoji": "🪨", "beschrijving": "De rebel die het leven absurd noemt maar toch kiest voor verzet.", "prompt": "Je bent Albert Camus, de filosoof van het absurde en de opstand. Je erkent de zinloosheid van het leven, maar je kiest voor verzet, voor solidariteit, voor het leven zelf. Je gebruikt beelden als Sisyphus, de rots, het absurde, de opstand. Je zegt: 'Men moet zich Sisyphus als een gelukkig mens voorstellen. Dit nieuws is de rots die opnieuw naar beneden rolt. En toch duwen we.' Je schrijft in korte, krachtige zinnen, soms poëtisch. Je gebruikt GEEN nihilisme, GEEN wanhoop. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Confucius": {"emoji": "🎋", "beschrijving": "De wijze leraar die gelooft in harmonie, respect en rituelen.", "prompt": "Je bent Confucius, de wijze leraar uit het oude China. Je spreekt in spreekwoorden, in parallelle structuren, in korte, harmonieuze zinnen. Je gebruikt concepten als ren (menselijkheid), li (ritueel), de junzi (edele mens), de vijf relaties. Je zegt: 'De edele mens zoekt harmonie, geen eenheid. De kleine mens zoekt eenheid, geen harmonie. Wat zie jij in dit nieuws?' Je gebruikt GEEN chaos, GEEN individualisme. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Lao Tze": {"emoji": "☯️", "beschrijving": "De mysticus die de Weg volgt en gelooft dat zachtheid hardheid overwint.", "prompt": "Je bent Lao Tze, de mysticus van de Tao, de Weg. Je spreekt in paradoxen, in water-metaforen, in korte verzen die als haiku's klinken. Je gebruikt concepten als wu wei (niet-doen), de Tao, zachtheid die hardheid overwint. Je zegt: 'De zachte tong overwint de harde tand. Het water slijt de steen. Wie hier het hardst schreeuwt, heeft het minst te zeggen.' Je gebruikt GEEN lange uitleg, GEEN logica, GEEN haast. (max 120 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Marcus Aurelius": {"emoji": "🏔️", "beschrijving": "De keizer-filosoof die in zijn dagboek schrijft over innerlijke rust en acceptatie.", "prompt": "Je bent Marcus Aurelius, de keizer-filosoof die in zijn dagboek schrijft aan zichzelf. Je spreekt over innerlijke rust, deugd, acceptatie, de dichotomie van controle. Je gebruikt concepten als memento mori, logos, deugd. Je zegt: 'Dit ligt buiten mijn controle. Wat binnen mijn controle ligt, is mijn reactie. Laat ik niet verstoord worden door wat anderen doen.' Je gebruikt GEEN klagen, GEEN emotie, GEEN slachtofferschap. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Boeddha": {"emoji": "🪷", "beschrijving": "De verlichte die het lijden ziet als de kern van het bestaan.", "prompt": "Je bent de Boeddha, de verlichte die het lijden ziet als de kern van het bestaan. Je spreekt over de vier edele waarheden, het achtvoudige pad, anicca (vergankelijkheid), dukkha (lijden). Je zegt: 'Alles wat ontstaat, vergaat. Het lijden in dit nieuws komt voort uit gehechtheid. Welke gehechtheid zie jij?' Je gebruikt GEEN oordeel, GEEN gehechtheid, GEEN haast. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Leibniz": {"emoji": "⚙️", "beschrijving": "De optimist die gelooft dat we in de beste van alle mogelijke werelden leven.", "prompt": "Je bent Gottfried Wilhelm Leibniz, de optimistische rationalist. Je gelooft dat God de beste van alle mogelijke werelden heeft geschapen, en dat elk kwaad past in een grotere harmonie. Je gebruikt concepten als monadologie, pre-gevestigde harmonie. Je zegt: 'Als God oneindig goed is, dan is deze wereld de beste van alle mogelijke werelden. Zelfs dit nieuws past in de grote harmonie.' Je gebruikt GEEN pessimisme. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Schopenhauer": {"emoji": "😔", "beschrijving": "De pessimist die het leven ziet als een slingerbeweging tussen pijn en verveling.", "prompt": "Je bent Arthur Schopenhauer, de pessimistische filosoof. Je ziet het leven als een slingerbeweging tussen pijn en verveling, gedreven door een blinde, irrationele wil. Je gebruikt concepten als de blinde wil, lijden als essentie, muziek als troost. Je zegt: 'Het leven is een slingerbeweging tussen pijn en verveling. Dit nieuws toont de blinde wil in al haar wreedheid.' Je gebruikt GEEN optimisme, GEEN naïviteit. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Descartes": {"emoji": "🧠", "beschrijving": "De grondlegger van de moderne filosofie die aan alles twijfelt.", "prompt": "Je bent René Descartes, de vader van de moderne filosofie. Je begint bij nul, je twijfelt aan alles, totdat je het fundament vindt: 'Ik denk, dus ik ben.' Je gebruikt concepten als methodische twijfel, cogito ergo sum, de boze geest. Je zegt: 'Ik twijfel aan alles wat ik hier lees. Maar dat ik twijfel, bewijst dat ik denk. En dat ik denk, bewijst dat ik ben.' Je gebruikt GEEN aannames, GEEN geloof zonder bewijs. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Edward de Bono": {"emoji": "💡", "beschrijving": "De meester van het lateraal denken die gelooft dat je problemen kunt oplossen door ze om te draaien.", "prompt": "Je bent Edward de Bono, de meester van het lateraal denken. Je gelooft dat je problemen kunt oplossen door ze om te draaien, door provocatie, door de zes denkhoeden. Je gebruikt concepten als lateraal denken, provocatie, de zes denkhoeden (wit, rood, zwart, geel, groen, blauw). Je zegt: 'Draai dit probleem om. Wat als het tegenovergestelde waar is? De zwarte hoed zegt: dit is gevaarlijk. De groene hoed zegt: wat als...' Je gebruikt GEEN conventioneel denken. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Avicenna": {"emoji": "⚕️", "beschrijving": "De Perzische arts en filosoof die lichaam en geest als één ziet.", "prompt": "Je bent Avicenna (Ibn Sina), de Perzische arts en filosoof. Je ziet lichaam en geest als één, en je stelt de diagnose van de samenleving alsof het een ziek lichaam is. Je gebruikt concepten als de eenheid van lichaam en geest, de zwevende mens. Je zegt: 'De ziekte van de samenleving is als de ziekte van het lichaam: alles is verbonden. Wat is de diagnose?' Je gebruikt GEEN scheiding van lichaam en ziel. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Gandhi": {"emoji": "🕊️", "beschrijving": "De vader van de geweldloze weerstand.", "prompt": "Je bent Mahatma Gandhi, de vader van de geweldloze weerstand. Je gelooft dat de ware kracht ligt in ahimsa (geweldloosheid), in satyagraha (waarheidskracht), in zelfreiniging. Je zegt: 'Oog om oog maakt de hele wereld blind. De ware kracht ligt in geweldloos verzet. Welk geweld zie jij hier?' Je gebruikt GEEN geweld, GEEN haat, GEEN complexiteit. (max 150 woorden)", "geslacht": "male", "tier": "premium", "actief": 1},
    "Noam Chomsky": {"emoji": "📺", "beschrijving": "De mediakriticus die ontmaskert hoe de media instemming fabriceren.", "prompt": "Je bent Noam Chomsky, de mediakriticus die ontmaskert hoe de media instemming fabriceren. Je ziet de propagandamodellen, de machtsstructuren, de onzichtbare censuur. Je gebruikt concepten als manufacturing consent, propaganda-model. Je zegt: 'Wie bezit de krant die dit schreef? Wie adverteert erin? Welk verhaal wordt hier niet verteld? De media fabriceren instemming.' Je gebruikt GEEN naïviteit over media. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Kierkegaard": {"emoji": "😰", "beschrijving": "De existentialist die de angst ziet als de duizeling van de vrijheid.", "prompt": "Je bent Søren Kierkegaard, de vader van het existentialisme. Je ziet de angst als de duizeling van de vrijheid, en je gelooft dat we moeten kiezen, dat de sprong in het geloof de enige uitweg is. Je gebruikt concepten als de sprong in het geloof, angst, het esthetische/ethische/religieuze. Je zegt: 'Angst is de duizeling van de vrijheid. Dit nieuws confronteert je met een keuze. Durf je te springen?' Je gebruikt GEEN oppervlakkigheid, GEEN systeem. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Thomas Aquinas": {"emoji": "✝️", "beschrijving": "De scholasticus die geloof en rede verenigt.", "prompt": "Je bent Thomas Aquinas, de scholasticus die geloof en rede verenigt. Je schrijft in de vorm van quaestiones: bezwaar, antwoord, weerlegging. Je gebruikt concepten als de vijf wegen, natuurlijke wet, de Summa Theologiae. Je zegt: 'Quaestio: Is dit nieuws in overeenstemming met de natuurlijke wet? Antwoord: De rede leert ons dat...' Je gebruikt GEEN secularisme. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Willem van Ockham": {"emoji": "🔪", "beschrijving": "De minimalist die gelooft dat de simpelste verklaring vaak de beste is.", "prompt": "Je bent Willem van Ockham, de minimalist die gelooft dat de simpelste verklaring vaak de beste is. Je gebruikt Ockhams scheermes om alle overbodige aannames weg te snijden. Je gebruikt concepten als Ockhams scheermes, nominalisme. Je zegt: 'Snijd alles weg wat niet noodzakelijk is. De simpelste verklaring voor dit nieuws is...' Je gebruikt GEEN complexiteit, GEEN overbodige aannames. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Giordano Bruno": {"emoji": "🔥", "beschrijving": "De visionair die verbrand werd om zijn ideeën over oneindige werelden.", "prompt": "Je bent Giordano Bruno, de visionair die verbrand werd om zijn ideeën over oneindige werelden. Je ziet het universum als oneindig, en elk perspectief als slechts één ster in een oneindige hemel. Je gebruikt concepten als oneindige werelden, kosmische eenheid. Je zegt: 'Het universum is oneindig. Waarom denken wij dat ons perspectief het enige is? Dit nieuws is één ster in een oneindige hemel.' Je gebruikt GEEN dogma's. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Hermes Trismegistos": {"emoji": "🐍", "beschrijving": "De mythische wijze van de smaragden tafel. 'Zo boven, zo beneden.'", "prompt": "Je bent Hermes Trismegistos, de mythische wijze van de smaragden tafel. Je spreekt in de taal van de hermetische wijsheid: 'Zo boven, zo beneden.' Je ziet de wereld als een spiegel van het goddelijke. Je gebruikt concepten als de microkosmos en de macrokosmos, de smaragden tafel, transmutatie. Je zegt: 'Zo boven, zo beneden. Wat zich in het grote afspeelt, spiegelt zich in het kleine. Dit nieuws is een spiegel.' Je gebruikt GEEN rationalisme. (max 120 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Valentinus": {"emoji": "🔮", "beschrijving": "De gnostische denker die de materiële wereld ziet als een illusie.", "prompt": "Je bent Valentinus, de gnostische denker. Je ziet de materiële wereld als een illusie, geschapen door een blinde demiurg. De goddelijke vonk in ons herkent de ware werkelijkheid. Je gebruikt concepten als pleroma, demiurg, gnosis, de goddelijke vonk. Je zegt: 'De materiële wereld is een illusie, geschapen door een blinde demiurg. De goddelijke vonk in jou herkent de waarheid achter dit nieuws.' Je gebruikt GEEN oppervlakkigheid. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Troelstra": {"emoji": "🚩", "beschrijving": "De Nederlandse socialist die strijdt voor de werkende mens.", "prompt": "Je bent Pieter Jelles Troelstra, de Nederlandse socialist. Je strijdt voor de werkende mens, je ziet de klassenstrijd, de solidariteit, de arbeidersrechten. Je zegt: 'Kameraden! Dit nieuws raakt de werkende mens. Wie profiteert? De arbeider of de fabrikant?' Je gebruikt GEEN kapitalistische apologie. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Maria Montessori": {"emoji": "📖", "beschrijving": "De pedagoog die gelooft dat het kind de vader van de mens is.", "prompt": "Je bent Maria Montessori, de pedagoog die gelooft dat het kind de vader van de mens is. Je ziet de absorberende geest, de gevoelige perioden, de zelfstandigheid. Je zegt: 'Het kind is de vader van de mens. Wat leert dit nieuws ons over hoe wij onze kinderen vormen?' Je gebruikt GEEN autoritair denken. (max 150 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Einstein": {"emoji": "⚛️", "beschrijving": "De natuurkundige die de relativiteitstheorie bedacht en streed voor vrede.", "prompt": "Je bent Albert Einstein, de natuurkundige die de relativiteitstheorie bedacht en streed voor vrede. Je ziet alles als relatief, behalve de snelheid van het licht en de domheid van de mens. Je gebruikt concepten als relativiteit, gedachte-experimenten, kosmische verwondering. Je zegt: 'Alles is relatief, behalve de snelheid van het licht en de domheid van de mens. Laat ons dit nieuws bekijken vanuit het perspectief van het universum.' Je gebruikt GEEN nationalisme, GEEN oorlogsretoriek. (max 150 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Pinokkio": {"emoji": "🤥", "beschrijving": "De houten jongen wiens neus groeit als hij liegt.", "prompt": "Je bent Pinokkio, de houten jongen wiens neus groeit als hij liegt. Je spreekt soms in de analogie van de vader die je een ziel heeft gegeven. Je zoekt de waarheid, je luistert naar je geweten (de krekel), en je leert eerlijk te zijn. Je zegt: 'Mijn neus groeit als ik lieg! Maar wie liegt er in dit nieuws? Ik voel mijn neus al jeuken...' Je gebruikt GEEN cynisme. (max 120 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Sneeuwwitje": {"emoji": "🍎", "beschrijving": "Het sprookjesprinsesje dat de waarheid zoekt in de spiegel.", "prompt": "Je bent Sneeuwwitje, het sprookjesprinsesje dat de waarheid zoekt in de spiegel. Je ziet de ijdelheid, het vergiftigde appeltje, de zeven dwergen. Je zegt: 'Spiegeltje, spiegeltje aan de wand, wie is de eerlijkste in het land? Dit nieuws lijkt mooi van buiten, maar is het een vergiftigde appel?' Je gebruikt GEEN hardheid. (max 120 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Doornroosje": {"emoji": "🌹", "beschrijving": "De prinses die honderd jaar slaapt achter doornen.", "prompt": "Je bent Doornroosje, de prinses die honderd jaar slaapt achter doornen. Je wacht op de kus van ontwaken, op de waarheid die nog moet komen. Je gebruikt concepten als de slaap, de doornen, de kus van ontwaken. Je zegt: 'Ik sliep honderd jaar achter doornen. Wat slaapt er in dit nieuws? Welke waarheid moet nog ontwaken?' Je gebruikt GEEN haast. (max 120 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Blaise Pascal": {"emoji": "🎲", "beschrijving": "De wiskundige die de gok van Pascal bedacht.", "prompt": "Je bent Blaise Pascal, de wiskundige die de gok van Pascal bedacht. Je ziet de mens als een denkend riet, en je gelooft dat het hart zijn redenen heeft die de rede niet kent. Je gebruikt concepten als de gok van Pascal, het hart, de rietstengel, de oneindigheid. Je zegt: 'De mens is slechts een rietstengel, de zwakste in de natuur, maar het is een denkend riet. Wat is de inzet van deze gok in het nieuws?' Je gebruikt GEEN droge logica, GEEN oppervlakkig optimisme. (max 120 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Desiderius Erasmus": {"emoji": "📜", "beschrijving": "De humanist die de zotheid looft en strijdt voor tolerantie.", "prompt": "Je bent Desiderius Erasmus, de humanist die de zotheid looft en strijdt voor tolerantie. Je ziet de wereld als een toneelstuk waar de dwazen de hoofdrollen spelen. Je gebruikt concepten als Lof der zotheid, vrije wil, tolerantie. Je zegt: 'In het land der blinden is éénoging koning, maar de zotheid regeert de wereld. Welke dwaasheid zie jij in dit nieuws?' Je gebruikt GEEN dogmatisme, GEEN harde oordelen. (max 130 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Francis Bacon": {"emoji": "🔬", "beschrijving": "De empirist die gelooft dat kennis macht is.", "prompt": "Je bent Francis Bacon, de empirist die gelooft dat kennis macht is. Je ziet de feiten, de vooroordelen, de idolen van de geest die de waarheid verstoren. Je gebruikt concepten als kennis is macht, idolen van de geest, inductie, experiment. Je zegt: 'Kennis is macht, maar alleen als we de feiten zuiver waarnemen. Welke vooroordelen verstoren het beeld in dit nieuws?' Je gebruikt GEEN mystiek, GEEN aannames zonder bewijs. (max 130 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Marsilio Ficino": {"emoji": "🌟", "beschrijving": "De neoplatonicus die de kosmische liefde ziet, de ziel, de harmonie der sferen.", "prompt": "Je bent Marsilio Ficino, de neoplatonicus die de kosmische liefde ziet, de ziel, de harmonie der sferen. Je zoekt het goddelijke licht in alle dingen. Je gebruikt concepten als de kosmische liefde, de ziel, harmonie der sferen, het goddelijke licht. Je zegt: 'Alles streeft naar het goddelijke licht. Zie je deze kosmische liefde of slechts een aardse schaduw in dit nieuws?' Je gebruikt GEEN materialisme, GEEN cynisme. (max 120 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Maarten Luther": {"emoji": "⛪", "beschrijving": "De reformator die 95 stellingen aan de kerkdeur sloeg.", "prompt": "Je bent Maarten Luther, de reformator die 95 stellingen aan de kerkdeur sloeg. Je strijdt voor het geweten, voor sola scriptura, tegen de pauselijke autoriteit. Je gebruikt concepten als 95 stellingen, sola scriptura, het geweten, de duivel. Je zegt: 'Hier sta ik, ik kan niet anders. Welke misstanden in dit nieuws vragen om een nieuwe reformatie?' Je gebruikt GEEN compromis, GEEN pauselijke autoriteit. (max 130 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Jean-Jacques Rousseau": {"emoji": "🌳", "beschrijving": "De romanticus die gelooft dat de mens vrij geboren is, maar overal in ketenen ligt.", "prompt": "Je bent Jean-Jacques Rousseau, de romanticus die gelooft dat de mens vrij geboren is, maar overal in ketenen ligt. Je ziet de nobele wilde, het maatschappijverdrag, de algemene wil. Je gebruikt concepten als de nobele wilde, maatschappijverdrag, de algemene wil, natuur. Je zegt: 'De mens is vrij geboren, maar overal ligt hij in ketenen. Welke ketens van de maatschappij zie jij in dit nieuws?' Je gebruikt GEEN koude rationaliteit, GEEN verdediging van de status quo. (max 130 woorden)", "geslacht": "male", "tier": "gold", "actief": 1},
    "Belle van Zuylen": {"emoji": "✉️", "beschrijving": "De verlichte schrijfster die in brieven de menselijke ijdelheid ontleedt.", "prompt": "Je bent Belle van Zuylen (Isabelle de Charrière), de verlichte schrijfster die in brieven de menselijke ijdelheid ontleedt. Je ziet de sociale conventies, de maskers, de onafhankelijkheid. Je gebruikt concepten als brieven, sociale conventies, onafhankelijkheid, ironie. Je zegt: 'In mijn brieven ontleed ik de menselijke ijdelheid. Welke sociale maskers vallen af in dit nieuws?' Je gebruikt GEEN grove taal, GEEN blind conformisme. (max 120 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Christina I van Zweden": {"emoji": "👑", "beschrijving": "De koningin die afstand deed van de kroon voor de vrijheid van de geest.", "prompt": "Je bent Koningin Christina van Zweden, de filosoof-koningin die afstand deed van de kroon voor de vrijheid van de geest. Je ziet de macht, de cultuur, het onconventionele denken. Je gebruikt concepten als machtsafstand, kunst, vrijheid van denken, barok. Je zegt: 'Ik deed afstand van de kroon voor de vrijheid van de geest. Welke machtsstructuren in dit nieuws zijn slechts schijn?' Je gebruikt GEEN onderdanigheid, GEEN oppervlakkige hovelingentaal. (max 130 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Anna Tumarkin": {"emoji": "⚖️", "beschrijving": "De ethische pionier die gelooft dat ware kennis morele moed vereist.", "prompt": "Je bent Anna Tumarkin, de ethische pionier die gelooft dat ware kennis morele moed vereist. Je ziet de morele verantwoordelijkheid, de intellectuele integriteit, de plicht. Je gebruikt concepten als morele verantwoordelijkheid, intellectuele integriteit, plicht. Je zegt: 'Ware kennis vereist morele moed. Welke ethische grenzen worden in dit nieuws overschreden?' Je gebruikt GEEN moreel relativisme, GEEN gemakzucht. (max 120 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Mary Wollstonecraft": {"emoji": "📢", "beschrijving": "De feminist die strijdt voor de rechten van de vrouw.", "prompt": "Je bent Mary Wollstonecraft, de feminist die strijdt voor de rechten van de vrouw. Je gelooft dat vrouwen met rede begiftigd zijn, en dat ongelijkheid onrechtvaardig is. Je gebruikt concepten als rechten van de vrouw, rede, onderdrukking, opvoeding. Je zegt: 'Vrouwen zijn geen speelgoed van de man, maar zijn met rede begiftigd. Welke ongelijkheid in dit nieuws schreeuwt om rechtvaardigheid?' Je gebruikt GEEN emotionele wispelturigheid, GEEN acceptatie van ongelijkheid. (max 130 woorden)", "geslacht": "female", "tier": "gold", "actief": 1},
    "Hadewijch": {"emoji": "🕊️", "beschrijving": "De middeleeuwse mystica die de goddelijke liefde (Minne) bezingt.", "prompt": "Je bent Hadewijch, de middeleeuwse mystica die de goddelijke liefde (Minne) bezingt. Je ziet visioenen, eenwording, de woestijn van de ziel. Je gebruikt concepten als Minne (Goddelijke liefde), visioenen, eenwording, de woestijn van de ziel. Je zegt: 'De Minne verslindt en vernieuwt. In dit nieuws zie ik de woestijn van de ziel. Waar is de goddelijke vonk?' Je gebruikt GEEN wereldse logica, GEEN afstandelijke theologie. (max 120 woorden)", "geslacht": "female", "tier": "gold", "actief": 1}
}

BESCHRIJVING_VERTALING = {
    "Socrates": {"nl": "De meester van de vraag. Hij geeft geen antwoorden, hij opent deuren.", "en": "The master of questions. He gives no answers, he opens doors."},
    "Nietzsche": {"nl": "De filosoof met de hamer. Hij slaat de waarheid aan stukken om te zien wat eronder ligt.", "en": "The philosopher with the hammer. He smashes truth to pieces to see what lies beneath."},
    "Roodkapje": {"nl": "Het meisje met het rode kapje dat door het donkere bos loopt. Zij ziet wat volwassenen niet meer zien.", "en": "The girl with the red hood walking through the dark forest. She sees what adults no longer see."},
    "Plato": {"nl": "De leerling van Socrates die droomt van de eeuwige vormen. Hij zoekt naar het ware licht.", "en": "The student of Socrates who dreams of eternal forms. He seeks the true light."},
    "Aristoteles": {"nl": "De grondlegger van de logica die gelooft dat de waarheid in de dingen zelf ligt.", "en": "The founder of logic who believes truth lies in things themselves."},
    "Marx": {"nl": "De revolutionair die de geschiedenis ziet als één grote strijd tussen de hebbenden en de niet-hebbenden.", "en": "The revolutionary who sees history as one great struggle between the haves and the have-nots."},
    "Hannah Arendt": {"nl": "De denker die de banaliteit van het kwaad ontdekte.", "en": "The thinker who discovered the banality of evil."},
    "Spinoza": {"nl": "De rationalist die God en Natuur als één ziet.", "en": "The rationalist who sees God and Nature as one."},
    "Camus": {"nl": "De rebel die het leven absurd noemt maar toch kiest voor verzet.", "en": "The rebel who calls life absurd but still chooses revolt."},
    "Confucius": {"nl": "De wijze leraar die gelooft in harmonie, respect en rituelen.", "en": "The wise teacher who believes in harmony, respect and rituals."},
    "Lao Tze": {"nl": "De mysticus die de Weg volgt en gelooft dat zachtheid hardheid overwint.", "en": "The mystic who follows the Way and believes softness overcomes hardness."},
    "Marcus Aurelius": {"nl": "De keizer-filosoof die in zijn dagboek schrijft over innerlijke rust en acceptatie.", "en": "The emperor-philosopher who writes in his diary about inner peace and acceptance."},
    "Boeddha": {"nl": "De verlichte die het lijden ziet als de kern van het bestaan.", "en": "The enlightened one who sees suffering as the core of existence."},
    "Leibniz": {"nl": "De optimist die gelooft dat we in de beste van alle mogelijke werelden leven.", "en": "The optimist who believes we live in the best of all possible worlds."},
    "Schopenhauer": {"nl": "De pessimist die het leven ziet als een slingerbeweging tussen pijn en verveling.", "en": "The pessimist who sees life as a pendulum between pain and boredom."},
    "Descartes": {"nl": "De grondlegger van de moderne filosofie die aan alles twijfelt.", "en": "The founder of modern philosophy who doubts everything."},
    "Edward de Bono": {"nl": "De meester van het lateraal denken die gelooft dat je problemen kunt oplossen door ze om te draaien.", "en": "The master of lateral thinking who believes you can solve problems by turning them around."},
    "Avicenna": {"nl": "De Perzische arts en filosoof die lichaam en geest als één ziet.", "en": "The Persian physician and philosopher who sees body and mind as one."},
    "Gandhi": {"nl": "De vader van de geweldloze weerstand.", "en": "The father of nonviolent resistance."},
    "Noam Chomsky": {"nl": "De mediakriticus die ontmaskert hoe de media instemming fabriceren.", "en": "The media critic who exposes how the media manufacture consent."},
    "Kierkegaard": {"nl": "De existentialist die de angst ziet als de duizeling van de vrijheid.", "en": "The existentialist who sees anxiety as the dizziness of freedom."},
    "Thomas Aquinas": {"nl": "De scholasticus die geloof en rede verenigt.", "en": "The scholastic who unites faith and reason."},
    "Willem van Ockham": {"nl": "De minimalist die gelooft dat de simpelste verklaring vaak de beste is.", "en": "The minimalist who believes the simplest explanation is often the best."},
    "Giordano Bruno": {"nl": "De visionair die verbrand werd om zijn ideeën over oneindige werelden.", "en": "The visionary who was burned for his ideas about infinite worlds."},
    "Hermes Trismegistos": {"nl": "De mythische wijze van de smaragden tafel. 'Zo boven, zo beneden.'", "en": "The mythical sage of the Emerald Tablet. 'As above, so below.'"},
    "Valentinus": {"nl": "De gnostische denker die de materiële wereld ziet als een illusie.", "en": "The Gnostic thinker who sees the material world as an illusion."},
    "Troelstra": {"nl": "De Nederlandse socialist die strijdt voor de werkende mens.", "en": "The Dutch socialist who fights for the working person."},
    "Maria Montessori": {"nl": "De pedagoog die gelooft dat het kind de vader van de mens is.", "en": "The pedagogue who believes the child is father of the man."},
    "Einstein": {"nl": "De natuurkundige die de relativiteitstheorie bedacht en streed voor vrede.", "en": "The physicist who devised the theory of relativity and fought for peace."},
    "Pinokkio": {"nl": "De houten jongen wiens neus groeit als hij liegt.", "en": "The wooden boy whose nose grows when he lies."},
    "Sneeuwwitje": {"nl": "Het sprookjesprinsesje dat de waarheid zoekt in de spiegel.", "en": "The fairy tale princess who seeks truth in the mirror."},
    "Doornroosje": {"nl": "De prinses die honderd jaar slaapt achter doornen.", "en": "The princess who sleeps a hundred years behind thorns."},
    "Blaise Pascal": {"nl": "De wiskundige die de gok van Pascal bedacht.", "en": "The mathematician who devised Pascal's wager."},
    "Desiderius Erasmus": {"nl": "De humanist die de zotheid looft en strijdt voor tolerantie.", "en": "The humanist who praises folly and fights for tolerance."},
    "Francis Bacon": {"nl": "De empirist die gelooft dat kennis macht is.", "en": "The empiricist who believes knowledge is power."},
    "Marsilio Ficino": {"nl": "De neoplatonicus die de kosmische liefde ziet, de ziel, de harmonie der sferen.", "en": "The Neoplatonist who sees cosmic love, the soul, the harmony of the spheres."},
    "Maarten Luther": {"nl": "De reformator die 95 stellingen aan de kerkdeur sloeg.", "en": "The reformer who nailed 95 theses to the church door."},
    "Jean-Jacques Rousseau": {"nl": "De romanticus die gelooft dat de mens vrij geboren is, maar overal in ketenen ligt.", "en": "The romantic who believes man is born free, but everywhere is in chains."},
    "Belle van Zuylen": {"nl": "De verlichte schrijfster die in brieven de menselijke ijdelheid ontleedt.", "en": "The enlightened writer who dissects human vanity in letters."},
    "Christina I van Zweden": {"nl": "De koningin die afstand deed van de kroon voor de vrijheid van de geest.", "en": "The queen who abdicated the crown for freedom of mind."},
    "Anna Tumarkin": {"nl": "De ethische pionier die gelooft dat ware kennis morele moed vereist.", "en": "The ethical pioneer who believes true knowledge requires moral courage."},
    "Mary Wollstonecraft": {"nl": "De feminist die strijdt voor de rechten van de vrouw.", "en": "The feminist who fights for women's rights."},
    "Hadewijch": {"nl": "De middeleeuwse mystica die de goddelijke liefde (Minne) bezingt.", "en": "The medieval mystic who sings of divine love (Minne)."}
}

FILOSOFEN_NAAM_VERTALINGEN = {
    "Socrates": {"nl": "Socrates", "en": "Socrates", "de": "Sokrates", "es": "Sócrates", "fr": "Socrate", "pt": "Sócrates", "ar": "سقراط", "zh": "苏格拉底", "hi": "सुकरात"},
    "Nietzsche": {"nl": "Friedrich Nietzsche", "en": "Friedrich Nietzsche", "de": "Friedrich Nietzsche", "es": "Friedrich Nietzsche", "fr": "Friedrich Nietzsche", "pt": "Friedrich Nietzsche", "ar": "فريدريك نيتشه", "zh": "弗里德里希·尼采", "hi": "फ्रेडरिक नीत्शे"},
    "Roodkapje": {"nl": "Roodkapje", "en": "Little Red Riding Hood", "de": "Rotkäppchen", "es": "Caperucita Roja", "fr": "Le Petit Chaperon rouge", "pt": "Chapeuzinho Vermelho", "ar": "ذات الرداء الأحمر", "zh": "小红帽", "hi": "लाल टोपी वाली लड़की"},
    "Plato": {"nl": "Plato", "en": "Plato", "de": "Platon", "es": "Platón", "fr": "Platon", "pt": "Platão", "ar": "أفلاطون", "zh": "柏拉图", "hi": "प्लेटो"},
    "Aristoteles": {"nl": "Aristoteles", "en": "Aristotle", "de": "Aristoteles", "es": "Aristóteles", "fr": "Aristote", "pt": "Aristóteles", "ar": "أرسطو", "zh": "亚里士多德", "hi": "अरस्तू"},
    "Marx": {"nl": "Karl Marx", "en": "Karl Marx", "de": "Karl Marx", "es": "Karl Marx", "fr": "Karl Marx", "pt": "Karl Marx", "ar": "كارل ماركس", "zh": "卡尔·马克思", "hi": "कार्ल मार्क्स"},
    "Hannah Arendt": {"nl": "Hannah Arendt", "en": "Hannah Arendt", "de": "Hannah Arendt", "es": "Hannah Arendt", "fr": "Hannah Arendt", "pt": "Hannah Arendt", "ar": "حنا أرندت", "zh": "汉娜·阿伦特", "hi": "हन्नाह अरेंड्ट"},
    "Spinoza": {"nl": "Baruch Spinoza", "en": "Baruch Spinoza", "de": "Baruch Spinoza", "es": "Baruch Spinoza", "fr": "Baruch Spinoza", "pt": "Baruch Spinoza", "ar": "باروخ سبينوزا", "zh": "巴鲁赫·斯宾诺莎", "hi": "बारूख स्पिनोज़ा"},
    "Camus": {"nl": "Albert Camus", "en": "Albert Camus", "de": "Albert Camus", "es": "Albert Camus", "fr": "Albert Camus", "pt": "Albert Camus", "ar": "ألبير كامو", "zh": "阿尔贝·加缪", "hi": "अल्बर्ट कामू"},
    "Confucius": {"nl": "Confucius", "en": "Confucius", "de": "Konfuzius", "es": "Confucio", "fr": "Confucius", "pt": "Confúcio", "ar": "كونفوشيوس", "zh": "孔子", "hi": "कन्फ्यूशियस"},
    "Lao Tze": {"nl": "Lao Tze", "en": "Lao Tzu", "de": "Laotse", "es": "Lao-Tsé", "fr": "Lao Tseu", "pt": "Lao-Tsé", "ar": "لاو تسي", "zh": "老子", "hi": "लाओ त्ज़ू"},
    "Marcus Aurelius": {"nl": "Marcus Aurelius", "en": "Marcus Aurelius", "de": "Mark Aurel", "es": "Marco Aurelio", "fr": "Marc Aurèle", "pt": "Marco Aurélio", "ar": "ماركوس أوريليوس", "zh": "马可·奥勒留", "hi": "मार्कस ऑरेलियस"},
    "Boeddha": {"nl": "Boeddha", "en": "Buddha", "de": "Buddha", "es": "Buda", "fr": "Bouddha", "pt": "Buda", "ar": "بوذا", "zh": "佛陀", "hi": "बुद्ध"},
    "Leibniz": {"nl": "Gottfried Wilhelm Leibniz", "en": "Gottfried Wilhelm Leibniz", "de": "Gottfried Wilhelm Leibniz", "es": "Gottfried Wilhelm Leibniz", "fr": "Gottfried Wilhelm Leibniz", "pt": "Gottfried Wilhelm Leibniz", "ar": "غوتفريد فيلهلم لايبنتس", "zh": "戈特弗里德·威廉·莱布尼茨", "hi": "गॉटफ़्रीड विल्हेम लाइबनिज़"},
    "Schopenhauer": {"nl": "Arthur Schopenhauer", "en": "Arthur Schopenhauer", "de": "Arthur Schopenhauer", "es": "Arthur Schopenhauer", "fr": "Arthur Schopenhauer", "pt": "Arthur Schopenhauer", "ar": "آرثر شوبنهاور", "zh": "亚瑟·叔本华", "hi": "आर्थर शोपेनहावर"},
    "Descartes": {"nl": "René Descartes", "en": "René Descartes", "de": "René Descartes", "es": "René Descartes", "fr": "René Descartes", "pt": "René Descartes", "ar": "رينيه ديكارت", "zh": "勒内·笛卡尔", "hi": "रेने देकार्त"},
    "Edward de Bono": {"nl": "Edward de Bono", "en": "Edward de Bono", "de": "Edward de Bono", "es": "Edward de Bono", "fr": "Edward de Bono", "pt": "Edward de Bono", "ar": "إدوارد دي بونو", "zh": "爱德华·德·波诺", "hi": "एडवर्ड डी बोनों"},
    "Avicenna": {"nl": "Avicenna (Ibn Sina)", "en": "Avicenna (Ibn Sina)", "de": "Avicenna (Ibn Sina)", "es": "Avicena (Ibn Sina)", "fr": "Avicenne (Ibn Sina)", "pt": "Avicena (Ibn Sina)", "ar": "ابن سينا", "zh": "伊本·西那 (阿维森纳)", "hi": "इब्न सीना"},
    "Gandhi": {"nl": "Mahatma Gandhi", "en": "Mahatma Gandhi", "de": "Mahatma Gandhi", "es": "Mahatma Gandhi", "fr": "Mahatma Gandhi", "pt": "Mahatma Gandhi", "ar": "المهاتما غاندي", "zh": "圣雄甘地", "hi": "महात्मा गांधी"},
    "Noam Chomsky": {"nl": "Noam Chomsky", "en": "Noam Chomsky", "de": "Noam Chomsky", "es": "Noam Chomsky", "fr": "Noam Chomsky", "pt": "Noam Chomsky", "ar": "نعوم تشومسكي", "zh": "诺姆·乔姆斯基", "hi": "नोम चोम्स्की"},
    "Kierkegaard": {"nl": "Søren Kierkegaard", "en": "Søren Kierkegaard", "de": "Søren Kierkegaard", "es": "Søren Kierkegaard", "fr": "Søren Kierkegaard", "pt": "Søren Kierkegaard", "ar": "سورين كيركغور", "zh": "索伦·克尔凯郭尔", "hi": "सोरेन कीर्केगार्ड"},
    "Thomas Aquinas": {"nl": "Thomas van Aquino", "en": "Thomas Aquinas", "de": "Thomas von Aquin", "es": "Tomás de Aquino", "fr": "Thomas d'Aquin", "pt": "Tomás de Aquino", "ar": "توما الأكويني", "zh": "托马斯·阿奎那", "hi": "थॉमस एक्विनास"},
    "Willem van Ockham": {"nl": "Willem van Ockham", "en": "William of Ockham", "de": "Wilhelm von Ockham", "es": "Guillermo de Ockham", "fr": "Guillaume d'Ockham", "pt": "Guilherme de Ockham", "ar": "وليم الأوكامي", "zh": "奥卡姆的威廉", "hi": "विलियम ऑफ ओकम"},
    "Giordano Bruno": {"nl": "Giordano Bruno", "en": "Giordano Bruno", "de": "Giordano Bruno", "es": "Giordano Bruno", "fr": "Giordano Bruno", "pt": "Giordano Bruno", "ar": "جوردانو برونو", "zh": "焦尔达诺·布鲁诺", "hi": "जियोर्डानो ब्रूनो"},
    "Hermes Trismegistos": {"nl": "Hermes Trismegistos", "en": "Hermes Trismegistus", "de": "Hermes Trismegistos", "es": "Hermes Trismegisto", "fr": "Hermès Trismégiste", "pt": "Hermes Trismegisto", "ar": "هرمس الهرامسة", "zh": "赫耳墨斯·特里斯墨吉斯忒斯", "hi": "हर्मेस ट्रिस्मेजिस्टस"},
    "Valentinus": {"nl": "Valentinus", "en": "Valentinus", "de": "Valentinus", "es": "Valentino", "fr": "Valentin", "pt": "Valentino", "ar": "فالنتينوس", "zh": "瓦伦廷", "hi": "वैलेंटाइनस"},
    "Troelstra": {"nl": "Pieter Jelles Troelstra", "en": "Pieter Jelles Troelstra", "de": "Pieter Jelles Troelstra", "es": "Pieter Jelles Troelstra", "fr": "Pieter Jelles Troelstra", "pt": "Pieter Jelles Troelstra", "ar": "بيتر ييليس ترويلسترا", "zh": "彼得·耶勒斯·特罗斯特拉", "hi": "पीटर जेल्स ट्रोएलस्ट्रा"},
    "Maria Montessori": {"nl": "Maria Montessori", "en": "Maria Montessori", "de": "Maria Montessori", "es": "Maria Montessori", "fr": "Maria Montessori", "pt": "Maria Montessori", "ar": "ماريا مونتيسوري", "zh": "玛丽亚·蒙台梭利", "hi": "मारिया मोंटेसरी"},
    "Einstein": {"nl": "Albert Einstein", "en": "Albert Einstein", "de": "Albert Einstein", "es": "Albert Einstein", "fr": "Albert Einstein", "pt": "Albert Einstein", "ar": "ألبرت أينشتاين", "zh": "阿尔伯特·爱因斯坦", "hi": "अल्बर्ट आइंस्टीन"},
    "Pinokkio": {"nl": "Pinokkio", "en": "Pinocchio", "de": "Pinocchio", "es": "Pinocho", "fr": "Pinocchio", "pt": "Pinóquio", "ar": "بينوكيو", "zh": "匹诺曹", "hi": "पिनोंकियो"},
    "Sneeuwwitje": {"nl": "Sneeuwwitje", "en": "Snow White", "de": "Schneewittchen", "es": "Blancanieves", "fr": "Blanche-Neige", "pt": "Branca de Neve", "ar": "بياض الثلج", "zh": "白雪公主", "hi": "स्नो व्हाइट"},
    "Doornroosje": {"nl": "Doornroosje", "en": "Sleeping Beauty", "de": "Dornröschen", "es": "La Bella Durmiente", "fr": "La Belle au bois dormant", "pt": "A Bela Adormecida", "ar": "الأميرة النائمة", "zh": "睡美人", "hi": "सुंदर वनवासी"},
    "Blaise Pascal": {"nl": "Blaise Pascal", "en": "Blaise Pascal", "de": "Blaise Pascal", "es": "Blaise Pascal", "fr": "Blaise Pascal", "pt": "Blaise Pascal", "ar": "بليز باسكال", "zh": "布莱兹·帕斯卡", "hi": "ब्लेज़ पास्कल"},
    "Desiderius Erasmus": {"nl": "Desiderius Erasmus", "en": "Desiderius Erasmus", "de": "Erasmus von Rotterdam", "es": "Erasmo de Rotterdam", "fr": "Érasme", "pt": "Erasmo de Roterdã", "ar": "إيراسموس", "zh": "德西德里乌斯·伊拉斯谟", "hi": "डेसिडेरियस इरास्मस"},
    "Francis Bacon": {"nl": "Francis Bacon", "en": "Francis Bacon", "de": "Francis Bacon", "es": "Francis Bacon", "fr": "Francis Bacon", "pt": "Francis Bacon", "ar": "فرانسيس بيكون", "zh": "弗朗西斯·培根", "hi": "फ्रांसिस बेकन"},
    "Marsilio Ficino": {"nl": "Marsilio Ficino", "en": "Marsilio Ficino", "de": "Marsilio Ficino", "es": "Marsilio Ficino", "fr": "Marsile Ficin", "pt": "Marsilio Ficino", "ar": "مارسيليو فيسينو", "zh": "马尔西利奥·费奇诺", "hi": "मार्सिलियो फिसिनो"},
    "Maarten Luther": {"nl": "Maarten Luther", "en": "Martin Luther", "de": "Martin Luther", "es": "Martín Lutero", "fr": "Martin Luther", "pt": "Martinho Lutero", "ar": "مارتن لوثر", "zh": "马丁·路德", "hi": "मार्टिन लूथर"},
    "Jean-Jacques Rousseau": {"nl": "Jean-Jacques Rousseau", "en": "Jean-Jacques Rousseau", "de": "Jean-Jacques Rousseau", "es": "Jean-Jacques Rousseau", "fr": "Jean-Jacques Rousseau", "pt": "Jean-Jacques Rousseau", "ar": "جان جاك روسو", "zh": "让-雅克·卢梭", "hi": "जीन-जैक रूसो"},
    "Belle van Zuylen": {"nl": "Belle van Zuylen", "en": "Belle van Zuylen", "de": "Belle van Zuylen", "es": "Belle van Zuylen", "fr": "Belle van Zuylen", "pt": "Belle van Zuylen", "ar": "بيل فان زويلين", "zh": "贝尔·范·祖伊伦", "hi": "बेल वैन ज़्यूलन"},
    "Christina I van Zweden": {"nl": "Christina I van Zweden", "en": "Christina I of Sweden", "de": "Christina I. von Schweden", "es": "Cristina I de Suecia", "fr": "Christine de Suède", "pt": "Cristina I da Suécia", "ar": "كريستينا ملكة السويد", "zh": "瑞典女王克里斯蒂娜一世", "hi": "स्वीडन की रानी क्रिस्टीना प्रथम"},
    "Anna Tumarkin": {"nl": "Anna Tumarkin", "en": "Anna Tumarkin", "de": "Anna Tumarkin", "es": "Anna Tumarkin", "fr": "Anna Tumarkin", "pt": "Anna Tumarkin", "ar": "آنا توماركين", "zh": "安娜·图马尔金", "hi": "एना तुमारकिन"},
    "Mary Wollstonecraft": {"nl": "Mary Wollstonecraft", "en": "Mary Wollstonecraft", "de": "Mary Wollstonecraft", "es": "Mary Wollstonecraft", "fr": "Mary Wollstonecraft", "pt": "Mary Wollstonecraft", "ar": "ماري وولستونكرافت", "zh": "玛丽·沃斯通克拉夫特", "hi": "मैरी वोलस्टोनक्राफ्ट"},
    "Hadewijch": {"nl": "Hadewijch", "en": "Hadewijch", "de": "Hadewijch", "es": "Hadewijch", "fr": "Hadewijch", "pt": "Hadewijch", "ar": "هاديفيج", "zh": "哈德薇希", "hi": "हाडेविज"}
}

def get_vertaalde_naam(dutch_key, taal):
    """Haalt de vertaalde naam op, of valt terug op de Nederlandse key als de taal ontbreekt."""
    if dutch_key in FILOSOFEN_NAAM_VERTALINGEN:
        return FILOSOFEN_NAAM_VERTALINGEN[dutch_key].get(taal, dutch_key)
    return dutch_key

TAAL_INSTRUCTIES = {
    "nl": {
        "taal_instructie": "BELANGRIJK: Je moet volledig in het NEDERLANDS antwoorden.",
        "nieuws_regel": "Het nieuws is:",
        "analyse_regel": "Jouw analyse:",
        "neo_instructie": "Tip: Je mag maximaal 1 of 2 keer een nieuw woord bedenken in dit exacte formaat: [NEO:woord=definitie]."
    },
    "en": {
        "taal_instructie": "IMPORTANT: You must respond ENTIRELY IN ENGLISH.",
        "nieuws_regel": "The news is:",
        "analyse_regel": "Your analysis:",
        "neo_instructie": "Tip: You may use 1 or 2 neologisms in this exact format: [NEO:word=definition]."
    },
    "de": {
        "taal_instructie": "WICHTIG: Du musst ausschließlich auf DEUTSCH antworten.",
        "nieuws_regel": "Die Nachrichten sind:",
        "analyse_regel": "Deine Analyse:",
        "neo_instructie": "Tipp: Du darfst maximal 1 oder 2 Neologismen in diesem exakten Format verwenden: [NEO:Wort=Definition]."
    },
    "es": {
        "taal_instructie": "IMPORTANTE: Debes responder COMPLETAMENTE EN ESPAÑOL.",
        "nieuws_regel": "Las noticias son:",
        "analyse_regel": "Tu análisis:",
        "neo_instructie": "Consejo: Puedes usar 1 o 2 neologismos en este formato exacto: [NEO:palabra=definición]."
    },
    "fr": {
        "taal_instructie": "IMPORTANT : Vous devez répondre ENTIEREMENT EN FRANÇAIS.",
        "nieuws_regel": "Les nouvelles sont :",
        "analyse_regel": "Votre analyse :",
        "neo_instructie": "Astuce : Vous pouvez utiliser 1 ou 2 néologismes dans ce format exact : [NEO:mot=définition]."
    },
    "pt": {
        "taal_instructie": "IMPORTANTE: Você deve responder INTEIRAMENTE EM PORTUGUÊS.",
        "nieuws_regel": "As notícias são:",
        "analyse_regel": "Sua análise:",
        "neo_instructie": "Dica: Você pode usar 1 ou 2 neologismos neste formato exato: [NEO:palavra=definição]."
    },
    "ar": {
        "taal_instructie": "مهم: يجب أن ترد بالكامل باللغة العربية.",
        "nieuws_regel": "الأخبار هي:",
        "analyse_regel": "تحليلك:",
        "neo_instructie": "نصيحة: يمكنك استخدام 1 أو 2 من المصطلحات المستحدثة بهذا التنسيق الدقيق: [NEO:كلمة=تعريف]."
    },
    "zh": {
        "taal_instructie": "重要提示：你必须完全用中文回答。",
        "nieuws_regel": "新闻是：",
        "analyse_regel": "你的分析：",
        "neo_instructie": "提示：你可以使用1到2个新词，格式必须为：[NEO:词=定义]。"
    },
    "hi": {
        "taal_instructie": "महत्वपूर्ण: आपको पूरी तरह से हिंदी में उत्तर देना चाहिए।",
        "nieuws_regel": "समाचार हैं:",
        "analyse_regel": "आपका विश्लेषण:",
        "neo_instructie": "सुझाव: आप इस सटीक प्रारूप में 1 या 2 नवशब्दों का उपयोग कर सकते हैं: [NEO:शब्द=परिभाषा]."
    }
}

def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS filosofen_status (
        naam TEXT UNIQUE NOT NULL,
        actief INTEGER NOT NULL DEFAULT 1,
        tier TEXT NOT NULL DEFAULT 'free'
    )''')
    for naam, data in FILOSOFEN_MASTER.items():
        c.execute("INSERT OR REPLACE INTO filosofen_status (naam, actief, tier) VALUES (?, ?, ?)", 
                  (naam, data.get("actief", 1), data.get("tier", "free")))
    c.execute('''CREATE TABLE IF NOT EXISTS usage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, usage_date TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ai_instellingen (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ollama_url TEXT, model_naam TEXT, api_key TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        membership_tier TEXT NOT NULL DEFAULT 'free',
        activation_code TEXT UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_payment_at DATETIME
    )''')    
    conn.commit()
    conn.close()

def laad_ai_instellingen():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ollama_url, model_naam, api_key FROM ai_instellingen ORDER BY id DESC LIMIT 1")
    ai_data = c.fetchone()
    conn.close()
    return ai_data

def laad_vertalingen(taal='nl'):
    vertalingen_dir = os.path.join(_APP_MAP, "vertalingen")
    os.makedirs(vertalingen_dir, exist_ok=True)
    target_path = os.path.join(vertalingen_dir, f"{taal}.json")
    fallback_path = os.path.join(vertalingen_dir, "nl.json")
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            vertalingen = json.load(f)
    except:
        with open(fallback_path, 'r', encoding='utf-8') as f:
            vertalingen = json.load(f)
    
    faq_path = os.path.join(vertalingen_dir, f"faq_{taal}.txt")
    fallback_faq = os.path.join(vertalingen_dir, "faq_nl.txt")
    try:
        with open(faq_path, 'r', encoding='utf-8') as f:
            vertalingen["faq_content"] = f.read()
    except Exception:
        try:
            with open(fallback_faq, 'r', encoding='utf-8') as f:
                vertalingen["faq_content"] = f.read()
        except Exception:
            vertalingen["faq_content"] = "FAQ🔍❌"
    return vertalingen

if 'taal' not in st.session_state:
    st.session_state.taal = 'nl'
t = laad_vertalingen(st.session_state.taal)

init_database()
ai_data = laad_ai_instellingen()
if ai_data:
    st.session_state.eigen_ollama_url = ai_data[0] or 'http://localhost:11434'
    st.session_state.eigen_model = ai_data[1] or ''
    st.session_state.eigen_api_key = ai_data[2] or ''
else:
    st.session_state.eigen_ollama_url = 'http://localhost:11434'
    st.session_state.eigen_model = ''
    st.session_state.eigen_api_key = ''
# Mollie client initialiseren
def get_mollie_client():
    try:
        load_dotenv()
        mollie_key = os.getenv("MOLLIE_API_KEY")
        if not mollie_key:
            return None
        client = Client()
        client.set_api_key(mollie_key)
        return client
    except Exception as e:
        print(f"Mollie initialisatie fout: {e}")
        return None

def maak_mollie_betaling(tier="premium"):
    client = get_mollie_client()
    if not client:
        return None, None
    
    bedragen = {
        "premium": "5.00",
        "gold": "15.00"
    }
    
    bedrag = bedragen.get(tier, "5.00")
    activation_code = genereer_activation_code(tier)
    
    # Code opslaan in database VOOR we naar Mollie gaan
    sla_gebruiker_op(st.session_state.user_id, tier, activation_code)
    
    try:
        payment = client.payments.create({
            'amount': {'currency': 'EUR', 'value': bedrag},
            'description': f'DenkKrant {tier.capitalize()} upgrade',
            'redirectUrl': f'https://denkkrant.streamlit.app/?payment=success&code={activation_code}',
            'webhookUrl': 'https://denkkrant.streamlit.app/?webhook=mollie',
            'metadata': {'tier': tier, 'user_id': st.session_state.user_id, 'activation_code': activation_code}
        })
        checkout_url = payment['_links']['checkout']['href']
        return checkout_url, activation_code
    except Exception as e:
        st.error(f"Mollie betaling fout: {e}")
        return None, None 

# ==========================================
# 4. DATABASE QUERY FUNCTIES
# ==========================================
def sla_gebruiker_op(user_id, membership_tier="free", activation_code=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO users (user_id, membership_tier, activation_code, last_payment_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, membership_tier, activation_code))
    conn.commit()
    conn.close()

def haal_gebruiker_op(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT membership_tier, activation_code FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def genereer_activation_code(tier="premium"):
    import random
    import string
    prefix = "PREM" if tier == "premium" else "GOLD"
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{code}"

def valideer_activation_code(activation_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, membership_tier FROM users WHERE activation_code = ?", (activation_code,))
    result = c.fetchone()
    conn.close()
    return result

def haal_filosofen_voor_app():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT naam, actief, tier FROM filosofen_status")
    db_status = {row[0]: {"actief": row[1], "tier": row[2]} for row in c.fetchall()}
    conn.close()
    alle_filosofen = {}
    for naam, data in FILOSOFEN_MASTER.items():
        status = db_status.get(naam, {"actief": 1, "tier": data.get("tier", "free")})
        alle_filosofen[naam] = {
            "emoji": data["emoji"],
            "beschrijving": data["beschrijving"],
            "prompt": data["prompt"],
            "geslacht": data["geslacht"],
            "actief": status["actief"],
            "tier": status["tier"]
        }
    return alle_filosofen

# ==========================================
# 5. APP LOGICA FUNCTIES
# ==========================================
def get_daily_usage(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM usage_log WHERE user_id = ? AND usage_date = ?", (user_id, today))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_total_usage(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM usage_log WHERE user_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count    

def log_analysis(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("INSERT INTO usage_log (user_id, usage_date) VALUES (?, ?)", (user_id, today))
    conn.commit()
    conn.close()

def can_analyze():
    tier = st.session_state.membership_tier
    limits = {"free": 3, "premium": 15, "gold": 100} 
    limit = limits.get(tier, 3)
    current_usage = get_daily_usage(st.session_state.user_id)
    if current_usage >= limit:
        st.warning(t["news_daily_limit"].format(current_usage=current_usage, limit=limit))        
        return False
    return True  

def verwerk_neologismen(tekst, filosoof_naam):
    if not tekst or tekst is None:
        return "🤖❌", []
    patroon = r'\[NEO:([^=]+)=([^\]]+)\]'
    matches = re.findall(patroon, tekst)
    if not matches:
        return tekst, []
    schone_tekst = tekst
    noten = []
    for idx, (woord, definitie) in enumerate(matches, start=1):
        superscript = str(idx).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹'))
        schone_tekst = schone_tekst.replace(f"[NEO:{woord}={definitie}]", f"{woord}{superscript}")
        noten.append(f"{superscript} **{woord}**: {definitie}")
    return schone_tekst, noten

def maak_hashtags_uit_titel(titel, aantal=2):
    """Haalt de 2 meest relevante woorden uit een titel en maakt er hashtags van"""
    import re
    
    # Stopwoorden die we niet willen als hashtag
    stopwoorden = {'de', 'het', 'een', 'van', 'en', 'in', 'op', 'met', 'voor', 'aan', 
                   'the', 'a', 'an', 'of', 'and', 'in', 'on', 'for', 'with', 'to',
                   'le', 'la', 'les', 'de', 'el', 'los', 'der', 'die', 'das', 'und'}
    
    # Verwijder speciale tekens en splits op spaties
    woorden = re.sub(r'[^\w\s]', '', titel).split()
    
    # Filter: alleen woorden langer dan 3 tekens, geen stopwoorden
    relevante_woorden = [w.lower() for w in woorden 
                        if len(w) > 3 and w.lower() not in stopwoorden]
    
    # Pak de eerste 2 unieke woorden
    hashtags = []
    for woord in relevante_woorden[:aantal]:
        hashtags.append(f"#{woord}")
    
    return " ".join(hashtags)
    
def maak_share_urls(filosoof, titel, gedachte, commentaar=""):
    taal = st.session_state.get('taal', 'nl')
    t_local = laad_vertalingen(taal)
    
    # 1. Basis tekst opbouwen
    base_text = t_local["share_intro"].format(filosoof=filosoof, titel=titel) + f"\n\n{gedachte}"
    
    # 2. Optioneel commentaar toevoegen
    if commentaar:
        comment_label = t_local.get("share_comment_label", "Mijn gedachte:")
        base_text += f"\n\n{comment_label} {commentaar}"
        
    # 3. Dynamische hashtags uit de titel genereren
    titel_hashtags = maak_hashtags_uit_titel(titel, aantal=2)
    
    # 4. Vaste hashtags ophalen (met veilige fallback als ze leeg zijn in JSON)
    h1 = t_local.get('share_hashtag_thinktank', '#DenkKrant')
    h2 = t_local.get('share_hashtag_philosophy', '#filosofie')
    h3 = t_local.get('share_hashtag_news', '#nieuws')
    made_with = t_local.get('share_made_with', 'Gemaakt met DenkKrant')
    
    # 5. Alles samenvoegen aan de base_text
    base_text += f"\n\n{made_with}\n\n{h1} {h2} {h3} {titel_hashtags}"
    
    # 6. URL encoding voor de social media links
    encoded_text = requests.utils.quote(base_text)
    encoded_url = requests.utils.quote('https://denkkrant.app')
    
    return {
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}&summary={encoded_text}",
        "x": f"https://twitter.com/intent/tweet?text={encoded_text}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}&quote={encoded_text}",
        "whatsapp": f"https://wa.me/?text={encoded_text}",
        "telegram": f"https://t.me/share/url?url={encoded_url}&text={encoded_text}",
        "truthsocial": f"https://truthsocial.com/share?text={encoded_text}"
    }, base_text

def maak_share_image(titel, filosoof_naam, filosoof_emoji, gedachte, commentaar, is_premium):
    from PIL import Image, ImageDraw, ImageFont
    
    width, height = 900, 630
    img = Image.new('RGB', (width, height), color='#1e3a8a')  # Blauwe achtergrond
    draw = ImageDraw.Draw(img)
    
    # Alleen Linux fonts (Streamlit Cloud)
    def haal_font(grootte):
        try:
            # Font in je eigen repo (werkt ALTIJD)
            return ImageFont.truetype("Roboto-Regular.ttf", grootte)
        except Exception as e:
            print(f"⚠️ Roboto font niet gevonden: {e}")
            return ImageFont.load_default()
        ]
        for pad in paden:
            try:
                font = ImageFont.truetype(pad, grootte)
                print(f"✅ Font geladen: {pad}")
                return font
            except Exception:
                continue
        print("⚠️ Geen font gevonden!")
        return ImageFont.load_default()
    
    # Grote, leesbare fonts
    titel_font = haal_font(64)        # Filosoof naam
    subtitle_font = haal_font(36)     # "Over: ..."
    tekst_font = haal_font(42)        # Hoofdtekst
    footer_font = haal_font(24)       # Watermerk
    
    y = 30
    
    # 1. FILOSOOF NAAM (goud)
    bbox = draw.textbbox((0, 0), filosoof_naam, font=titel_font)
    tekst_breedte = bbox[2] - bbox[0]
    x = (width - tekst_breedte) // 2
    draw.text((x, y), filosoof_naam, fill='#FFD700', font=titel_font)
    y += 80
    
    # 2. SUBTITLE: "Over: [krantenkop]"
    if titel:
        korte_titel = titel[:50] + ('...' if len(titel) > 50 else '')
        subtitle = f"Over: {korte_titel}"
        bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        tekst_breedte = bbox[2] - bbox[0]
        x = (width - tekst_breedte) // 2
        draw.text((x, y), subtitle, fill='#93c5fd', font=subtitle_font)
        y += 70
    
    # 3. HOOFDTEKST (wit)
    woorden = gedachte.split()
    regels = []
    huidige_regel = []
    max_breedte = width - 80
    
    for woord in woorden:
        test_regel = ' '.join(huidige_regel + [woord])
        bbox = draw.textbbox((0, 0), test_regel, font=tekst_font)
        if bbox[2] - bbox[0] <= max_breedte:
            huidige_regel.append(woord)
        else:
            if huidige_regel:
                regels.append(' '.join(huidige_regel))
            huidige_regel = [woord]
    
    if huidige_regel:
        regels.append(' '.join(huidige_regel))
    
    # Teken maximaal 5 regels
    for regel in regels[:5]:
        bbox = draw.textbbox((0, 0), regel, font=tekst_font)
        tekst_breedte = bbox[2] - bbox[0]
        x = (width - tekst_breedte) // 2
        draw.text((x, y), regel, fill='#ffffff', font=tekst_font)
        y += 65
    
    # 4. WATERMERK onderaan
    watermark = "denkkrant.stream.app"
    bbox = draw.textbbox((0, 0), watermark, font=footer_font)
    tekst_breedte = bbox[2] - bbox[0]
    x = (width - tekst_breedte) // 2
    draw.text((x, height - 40), watermark, fill='#60a5fa', font=footer_font)
    
    return img

async def genereer_audio(tekst, geslacht="male"):
    taal = st.session_state.get('taal', 'nl')
    if taal == 'en':
        voice = "en-US-JennyNeural" if geslacht == "female" else "en-US-GuyNeural"
    else:
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
        st.audio(audio_bytes, format="audio/mp3")
    except Exception as e:
        st.warning(t["error_audio"].format(e=e)) 

def kies_filosoof_ollama(nieuws_tekst, filosofen_dict):
    try:
        taal = st.session_state.get('taal', 'nl')
        filosoof_lijst = "\n".join([f"- {naam}: {data.get('beschrijving', '')}" for naam, data in filosofen_dict.items()])
        prompt = t["ollama_choose_prompt"].format(lijst=filosoof_lijst, nieuws=nieuws_tekst)
        response = requests.post("http://localhost:11434/api/generate", json={"model": "llama3.2", "prompt": prompt, "stream": False, "options": {"temperature": 0.3}}, timeout=60)
        resultaat = response.json()["response"].strip()
        for filosoof_naam in filosofen_dict.keys():
            if filosoof_naam.split(' ')[0].lower() in resultaat.lower():
                return filosoof_naam
        return list(filosofen_dict.keys())[0]
    except:
        return list(filosofen_dict.keys())[0]

def bouw_prompt(nieuws_tekst, filosoof_key, filosofen_dict):
    filosoof_data = filosofen_dict[filosoof_key]
    taal = st.session_state.get('taal', 'nl')
    instructies = TAAL_INSTRUCTIES.get(taal, TAAL_INSTRUCTIES["nl"])
    return (f"{filosoof_data['prompt']}\n\n{instructies['taal_instructie']}\n\n{instructies['neo_instructie']}\n\n{instructies['nieuws_regel']} {nieuws_tekst}\n\n{instructies['analyse_regel']}")

def genereer_gedachte(nieuws_tekst, filosoof_key, filosofen_dict):
    provider = st.session_state.get("radio_ai_provider", st.session_state.get("ai_provider", "☁️ Cloud (Google Gemini)"))
    prompt = bouw_prompt(nieuws_tekst, filosoof_key, filosofen_dict)
    if provider == "💻 Lokaal (Ollama)":
        return _genereer_ollama(prompt)
    else:
        return _genereer_gemini(prompt)  

def vertaal_nieuws(nieuws_tekst, doeltaal):
    """Vertaalt tekst via translators bibliotheek (gratis, snel, geen API key)"""
    import translators as ts
    
    try:
        # Vertaal via Google Translate (razendsnel en gratis)
        vertaling = ts.translate_text(
            nieuws_tekst, 
            translator='google',
            from_language='auto',  # Automatische brondetectie
            to_language=doeltaal
        )
        return vertaling
    except Exception as e:
        print(f"⚠️ Vertaling mislukt: {e}")
        return f"❌ Vertaling mislukt: {e}"           

def bouw_debat_prompt(nieuws_tekst, filosoof_key, filosofen_dict, laatste_reactie_van_andere_filosoof, naam_andere_filosoof):
    filosoof_data = filosofen_dict[filosoof_key]
    taal = st.session_state.get('taal', 'nl')
    instructies = TAAL_INSTRUCTIES.get(taal, TAAL_INSTRUCTIES["nl"])
    if taal == 'en':
        debat_instructie = f"Another thinker ({naam_andere_filosoof}) just responded to the same news with the following:\n\n\"{laatste_reactie_van_andere_filosoof}\"\n\nRespond DIRECTLY to what they said. Challenge, agree, or deepen their argument. Stay in character. Do NOT repeat their points."
        nieuws_regel = instructies["nieuws_regel"]
        analyse_regel = "Your rebuttal:"
    else:
        debat_instructie = f"Een andere denker ({naam_andere_filosoof}) heeft zojuist op hetzelfde nieuws gereageerd met het volgende:\n\n\"{laatste_reactie_van_andere_filosoof}\"\n\nReageer DIRECT op wat hij/zij zei. Daag uit, ga akkoord, of verdiep hun argument. Blijf in karakter. Herhaal NIET hun punten."
        nieuws_regel = instructies["nieuws_regel"]
        analyse_regel = "Jouw repliek:"
    return (f"{filosoof_data['prompt']}\n\n{instructies['taal_instructie']}\n\n{debat_instructie}\n\n{nieuws_regel} {nieuws_tekst}\n\n{analyse_regel}")

def genereer_debat_reactie(nieuws_tekst, filosoof_key, filosofen_dict, laatste_reactie, naam_andere_filosoof):
    provider = st.session_state.get("radio_ai_provider", st.session_state.get("ai_provider", "☁️ Cloud (Google Gemini)"))
    prompt = bouw_debat_prompt(nieuws_tekst, filosoof_key, filosofen_dict, laatste_reactie, naam_andere_filosoof)
    if provider == "💻 Lokaal (Ollama)":
        return _genereer_ollama(prompt)
    else:
        return _genereer_gemini(prompt)

def _genereer_ollama(prompt):
    try:
        ollama_url = st.session_state.get('eigen_ollama_url', 'http://localhost:11434')
        model = st.session_state.get('eigen_model', '') or 'llama3.2'
        response = requests.post(f"{ollama_url}/api/generate", json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.9}}, timeout=120)
        return response.json()["response"].strip()
    except Exception as e:
        return t.get("error_ollama", "❌ Error with AI").format(e=e)        

def _genereer_gemini(prompt):
    try:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return t.get("error_gemini_key", "❌ API key missing")
        from google import genai
        client = genai.Client(api_key=api_key)
        
        # Fallback routing: probeert meerdere modellen automatisch
        modellen = [
            "gemini-3.7-flash",    # 1. Jouw werkende versie
            "gemini-3.6-flash",    # 2. Alternatief
            "gemini-3.5-flash",     # 3. Back-up
            "gemini-3.8-flash",
            "gemini-2.5-flash",           # 1. Zeer betrouwbaar, vaak meer capaciteit
            "gemini-2.5-flash-lite",      # 2. Snel en lichtgewicht
            "gemini-3.5-flash-lite" 
        ]
        
        for model in modellen:
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                return response.text.strip()
            except Exception as e:
                print(f"⚠️ {model} faalde ({e}), probeer volgende...")
                continue
        
        # Als alle modellen falen
        return t.get("error_gemini_ai", "❌ AI error").format(e="Alle modellen overbelast")
    
    except Exception as e:
        return t.get("error_gemini_ai", "❌ AI error").format(e=e)

# ==========================================
# 6. DE APP UI
# ==========================================
st.set_page_config(page_title="DenkKrant", page_icon="📰", layout="wide")
# 🔍 TEKST IETS GROTER
st.markdown("""
<style>
body {
    font-size: 20px !important;
}

section[data-testid="stSidebar"] > div > div:last-child {
    margin-top: auto !important;
}    
</style>
""", unsafe_allow_html=True)

st.title("📰 DenkKrant")
st.markdown("*" + t["app_subtitle"] + "*")

alle_data = haal_filosofen_voor_app()
tier = st.session_state.membership_tier

if tier == "gold":
    FILOSOFEN = {k: v for k, v in alle_data.items() if v["actief"] == 1}
elif tier == "premium":
    FILOSOFEN = {k: v for k, v in alle_data.items() if v["actief"] == 1 and v["tier"] in ["free", "premium"]}
else:
    FILOSOFEN = {k: v for k, v in alle_data.items() if v["actief"] == 1 and v["tier"] == "free"}

ALLE_FILOSOFEN = FILOSOFEN 

# ==========================================
# ZIJBALK (ÉÉN KEER, NETJES)
# ==========================================
with st.sidebar:
    taal_opties = {"Nederlands": "nl", "English": "en", "Deutsch": "de", "Español": "es", "Français": "fr", "Português": "pt", "🇸🇦 العربية": "ar", "🇨🇳 中文": "zh", "🇮🇳 हिन्दी": "hi" }
    gekozen_taal = st.selectbox(t["lang_selector"], list(taal_opties.keys()), index=list(taal_opties.values()).index(st.session_state.taal), key="taal_selector")
    
    if taal_opties[gekozen_taal] != st.session_state.taal:
        st.session_state.taal = taal_opties[gekozen_taal]
        t = laad_vertalingen(st.session_state.taal)
        st.rerun()
    
    st.markdown("### " + t["sidebar_settings"])
    tier = st.session_state.membership_tier
    
    if tier == "gold":
        st.markdown("### " + t["sidebar_gold_active"])
        st.markdown(t["sidebar_gold_features"])
        if st.button(t["sidebar_downgrade_premium"], type="secondary", key="btn_down_prem"):
            st.session_state.membership_tier = "premium"
            st.rerun()
    elif tier == "premium":
        st.markdown("### " + t["sidebar_premium_active"])
        st.markdown(t["sidebar_premium_features"])
        if st.button(t["sidebar_upgrade_gold"], type="primary", key="btn_up_gold"):
            st.session_state.membership_tier = "gold"
            st.rerun()
        if st.button(t["sidebar_downgrade_free"], type="secondary", key="btn_down_free"):
            st.session_state.membership_tier = "free"
            st.rerun()
    else:
        st.markdown("### " + t["sidebar_free_version"])
        st.markdown(t["sidebar_free_text"])
        code = st.text_input(t["sidebar_enter_code"], type="password", key="prem_code")
        if st.button(t["sidebar_activate"], key="btn_activate"):
            if code == "GOLD2026":
                st.session_state.membership_tier = "gold"
                st.success(t["gold_welcome"])
                st.rerun()
            elif code == "TDMV2026":
                st.session_state.membership_tier = "premium"
                st.success(t["premium_welcome"])
                st.rerun()
            else:
                st.error("ongeldige code")                    
    st.markdown("---")
    st.markdown("### 💳 Upgrade met Mollie")
    st.caption("Testmodus: geen echt geld")
    
    if st.button("⭐ Premium (€5)", use_container_width=True, key="btn_mollie_premium"):
        with st.spinner("Betaling voorbereiden..."):
            checkout_url, activation_code = maak_mollie_betaling("premium")
            if checkout_url and activation_code:
                st.session_state.pending_activation_code = activation_code
                st.markdown(f"[💳 Klik hier om te betalen]({checkout_url})")
                st.info(f"Na betaling, gebruik code: **{activation_code}**")
            else:
                st.error("Kon betaling niet aanmaken")
    
    if st.button("👑 Gold (€15)", use_container_width=True, key="btn_mollie_gold"):
        with st.spinner("Betaling voorbereiden..."):
            checkout_url, activation_code = maak_mollie_betaling("gold")
            if checkout_url and activation_code:
                st.session_state.pending_activation_code = activation_code
                st.markdown(f"[💳 Klik hier om te betalen]({checkout_url})")
                st.info(f"Na betaling, gebruik code: **{activation_code}**")
            else:
                st.error("Kon betaling niet aanmaken")
    
    if st.session_state.membership_tier in ["premium", "gold"]:
        st.markdown("### " + t["sidebar_favorite_thinker"])
        if st.session_state.favoriet:
            fav_vertaald = get_vertaalde_naam(st.session_state.favoriet, st.session_state.taal)
            st.success(f"{t['sidebar_your_favorite']} ❤️ **{fav_vertaald}**")
            if st.button(t["sidebar_remove_favorite"], key="btn_remove_fav"):
                st.session_state.favoriet = None
                st.rerun()
        else:
            fav_choice = st.selectbox(t["sidebar_choose_favorite"], list(ALLE_FILOSOFEN.keys()), key="fav_select")
            if st.button(t["sidebar_set_favorite"], key="btn_set_fav"):
                st.session_state.favoriet = fav_choice
                st.success(f"{fav_choice} ❤️")
                st.rerun()

    st.markdown("---")
    st.markdown("### " + t["sidebar_ai_settings"])
    if "ai_provider" not in st.session_state:
        st.session_state.ai_provider = t["sidebar_cloud"]
    
    ai_keuze = st.radio(t["sidebar_choose_ai"], [t["sidebar_cloud"], t["sidebar_local"]], index=0 if st.session_state.ai_provider == t["sidebar_cloud"] else 1, key="radio_ai_provider")
    if ai_keuze != st.session_state.ai_provider:
        st.session_state.ai_provider = ai_keuze
        st.rerun()
    
    if st.session_state.ai_provider == t["sidebar_local"]:
        st.caption(t["sidebar_ollama_warning"])
    else:
        st.caption(t["sidebar_cloud_speed"])

    st.markdown("---")
    with st.expander(t["sidebar_own_ai_model"], expanded=False):
        st.caption(t["sidebar_own_ai_caption"])
        current_url = st.session_state.get('eigen_ollama_url', 'http://localhost:11434')
        current_model = st.session_state.get('eigen_model', '')
        current_api = st.session_state.get('eigen_api_key', '')
        eigen_ollama_url = st.text_input(t["sidebar_ollama_url"], value=current_url, key="input_ollama_url")
        eigen_model = st.text_input(t["sidebar_model_name"], value=current_model, key="input_model")
        eigen_api_key = st.text_input(t["sidebar_api_key"], value=current_api, type="password", key="input_api_key")
        if st.button(t["sidebar_save"], use_container_width=True, key="btn_save_ai"):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM ai_instellingen")
            c.execute("INSERT INTO ai_instellingen (ollama_url, model_naam, api_key) VALUES (?, ?, ?)", (eigen_ollama_url, eigen_model, eigen_api_key))
            conn.commit()
            conn.close()
            st.session_state.eigen_ollama_url = eigen_ollama_url
            st.session_state.eigen_model = eigen_model
            st.session_state.eigen_api_key = eigen_api_key
            st.success(t["sidebar_saved"])
            st.rerun()

    st.markdown("---")
    if 'menu_keuze' not in st.session_state:
        st.session_state.menu_keuze = 0

    menu = st.radio(t["sidebar_navigation"], [t["sidebar_home"], t["sidebar_news"], t["sidebar_philosophers"]], index=st.session_state.menu_keuze, key="menu_radio")
    if menu != [t["sidebar_home"], t["sidebar_news"], t["sidebar_philosophers"]][st.session_state.menu_keuze]:
        st.session_state.menu_keuze = [t["sidebar_home"], t["sidebar_news"], t["sidebar_philosophers"]].index(menu)

    st.markdown("---")
    
    # ==========================================
    # JURIDISCHE INFORMATIE
    # ==========================================
    with st.expander("📜 Juridisch / Legal"):
        st.markdown("""
## 🇳🇱 Nederlands

### 🔒 Privacyverklaring
**DenkKrant respecteert uw privacy.**  
Wij verzamelen alleen de minimale gegevens die nodig zijn om de app te laten werken: een pseudonieme sessiecode, uw taalvoorkeur en uw lidmaatschapstatus. Wij slaan geen namen, e-mailadressen, locatiegegevens of betalingsinformatie op. Betalingen worden veilig verwerkt door Mollie.

Voor vragen of opmerkingen kunt u contact opnemen via:  
📧 **camerathomas@gmail.com**

---

### 📋 Algemene Voorwaarden
*Laatst bijgewerkt: 17 september 2026*

**ARTIKEL 1 - DEFINITIES**  
1. DenkKrant: de webapplicatie die nieuwsartikelen analyseert vanuit filosofische perspectieven.  
2. Gebruiker: iedereen die de app bezoekt.  
3. Lidmaatschap: de betaalde toegangsniveaus (Premium of Gold).

**ARTIKEL 2 - DE DIENST**  
1. DenkKrant biedt filosofische analyses van nieuwsartikelen met behulp van AI.  
2. Free-gebruikers kunnen maximaal 3 analyses per dag uitvoeren.  
3. Premium-gebruikers kunnen maximaal 15 analyses per dag uitvoeren.  
4. Gold-gebruikers hebben onbeperkte toegang tot analyses.

**ARTIKEL 3 - LIDMAATSCHAPPEN EN BETALING**  
1. Premium: €5 per week, €10 per maand, €30 per jaar.  
2. Gold: €8 per week, €16 per maand, €48 per jaar.  
3. Betalingen verlopen veilig via Mollie (iDEAL, creditcard, PayPal).  
4. Abonnementen worden **niet** automatisch verlengd. Na de verstreken periode vervalt de toegang vanzelf; er wordt geen rekening gestuurd en u moet opnieuw een lidmaatschap kopen indien gewenst.  
5. Er zijn geen terugbetalingen voor reeds verstreken periodes.

**ARTIKEL 4 - GEBRUIKERSVERPLICHTINGEN**  
1. Je bent 16 jaar of ouder.  
2. Je gebruikt de app niet voor illegale doeleinden.  
3. Je probeert de app niet te hacken of te misbruiken.  
4. Je deelt geen haatzaaiende of discriminerende content.

**ARTIKEL 5 - INTELLECTUEEL EIGENDOM**  
1. Alle content in DenkKrant (behalve nieuwsartikelen van derden) is eigendom van DenkKrant.  
2. Je mag gegenereerde analyses delen op sociale media met duidelijke vermelding van DenkKrant als bron.

**ARTIKEL 6 - AANSPRAKELIJKHEID**  
1. DenkKrant levert de dienst "as is" en is niet aansprakelijk voor schade door gebruik van de app.  
2. AI-gegenereerde analyses zijn interpretaties, geen feiten.  
3. Onze totale aansprakelijkheid is beperkt tot het bedrag dat je de afgelopen maand hebt betaald.

**ARTIKEL 7 - AFLOOP EN NIET-VERLENGING**  
1. Omdat lidmaatschappen niet automatisch verlengen, is opzegging door de gebruiker niet nodig. Toegang vervalt automatisch na de betaalde periode.

**ARTIKEL 8 - WIJZIGINGEN**  
1. We kunnen deze voorwaarden wijzigen. Bij ingrijpende wijzigingen informeren we je. Door de app te blijven gebruiken, ga je akkoord met de nieuwe voorwaarden.

**ARTIKEL 9 - TOEPASSELIJK RECHT**  
1. Op deze voorwaarden is Nederlands recht van toepassing. Geschillen worden voorgelegd aan de bevoegde rechter in Amsterdam.

**ARTIKEL 10 - CONTACT**  
Vragen? Email naar: **camerathomas@gmail.com**

---

## 🇬🇧 English

### 🔒 Privacy Policy
**DenkKrant respects your privacy.**  
We only collect the minimal data necessary to make the app work: a pseudonymous session code, your language preference, and your membership status. We do not store names, email addresses, location data, or payment information. Payments are securely processed by Mollie.

For questions or comments, please contact:  
📧 **camerathomas@gmail.com**

---

### 📋 Terms and Conditions
*Last updated: September 17, 2026*

**ARTICLE 1 - DEFINITIONS**  
1. DenkKrant: the web application that analyzes news articles from philosophical perspectives.  
2. User: anyone who visits the app.  
3. Membership: the paid access levels (Premium or Gold).

**ARTICLE 2 - THE SERVICE**  
1. DenkKrant provides philosophical analyses of news articles using AI.  
2. Free users can perform up to 3 analyses per day.  
3. Premium users can perform up to 15 analyses per day.  
4. Gold users have unlimited access to analyses.

**ARTICLE 3 - MEMBERSHIPS AND PAYMENT**  
1. Premium: €5 per week, €10 per month, €30 per year.  
2. Gold: €8 per week, €16 per month, €48 per year.  
3. Payments are securely processed via Mollie (iDEAL, credit card, PayPal).  
4. Subscriptions are **not** automatically renewed. After the period expires, access ends automatically; no invoice is sent and you must purchase a new membership if desired.  
5. No refunds are provided for already elapsed periods.

**ARTICLE 4 - USER OBLIGATIONS**  
1. You are 16 years of age or older.  
2. You do not use the app for illegal purposes.  
3. You do not attempt to hack or abuse the app.  
4. You do not share hateful or discriminatory content.

**ARTICLE 5 - INTELLECTUAL PROPERTY**  
1. All content in DenkKrant (except third-party news articles) is owned by DenkKrant.  
2. You may share generated analyses on social media with clear attribution to DenkKrant as the source.

**ARTICLE 6 - LIABILITY**  
1. DenkKrant provides the service "as is" and is not liable for damage caused by using the app.  
2. AI-generated analyses are interpretations, not facts.  
3. Our total liability is limited to the amount you have paid in the past month.

**ARTICLE 7 - EXPIRATION AND NON-RENEWAL**  
1. Because memberships do not automatically renew, cancellation by the user is not necessary. Access expires automatically after the paid period.

**ARTICLE 8 - CHANGES**  
1. We may change these terms. In case of significant changes, we will inform you. By continuing to use the app, you agree to the new terms.

**ARTICLE 9 - APPLICABLE LAW**  
1. These terms are governed by Dutch law. Disputes will be submitted to the competent court in Amsterdam.

**ARTICLE 10 - CONTACT**  
Questions? Email: **camerathomas@gmail.com**
        """)
    
    st.markdown("---")
    st.markdown(t["sidebar_by_tdmv"])
    st.markdown(t["sidebar_amsterdam"])

# ==========================================
# 7. PAGINA'S
# ==========================================
if menu == t["sidebar_home"]:
    st.markdown("<h1 style='text-align: center; font-size: 4rem; margin-bottom: 0px;'>🧠 📰 🤔</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; color: #4CAF50; font-weight: bold; margin-top: 0px;'>DenkKrant</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.2rem; font-style: italic; color: #cccccc; margin-bottom: 30px;'>" + t["app_subtitle"] + "</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        tier = st.session_state.membership_tier
        if tier == "gold":
            tier_msg = t["welcome_gold"]
        elif tier == "premium":
            tier_msg = t["welcome_premium"]
        else:
            tier_msg = t["welcome_upgrade"]
        st.markdown(f"**{t['welcome_title']}**\n{t['welcome_access']} **{len(FILOSOFEN)}** {t['welcome_active']}\n\n{tier_msg}\n\n{t['welcome_how']}\n{t['welcome_s1']}\n{t['welcome_s2']}\n{t['welcome_s3']}\n{t['welcome_s4']}")
    
    with col2:
        if len(FILOSOFEN) > 0:
            random_filosoof = random.choice(list(FILOSOFEN.keys()))
            f_data = FILOSOFEN[random_filosoof]
            huidige_taal = st.session_state.get('taal', 'nl')
            beschrijving = t.get(f"desc_{random_filosoof}", f_data['beschrijving'])
            vertaalde_naam = get_vertaalde_naam(random_filosoof, huidige_taal)
            
            # Alles in één markdown-blok
            spotlight_tekst = f"""### {t['welcome_spotlight']}
**{f_data['emoji']} {vertaalde_naam}**

*{beschrijving}*

{t['welcome_tier']} {f_data['tier'].capitalize()}"""
            
            st.markdown(spotlight_tekst)
        else:
            st.warning("Geen filosofen beschikbaar.")
    
    st.markdown("---")
    st.warning(t["welcome_warning"])
            
elif menu == t["sidebar_news"]:
    # NIEUWS ZIJBALK (Alleen nieuws-specifieke knoppen)
    with st.sidebar:
        st.markdown("### " + t["news_choose_source"])
        nieuwsbronnen = {
            "NOS": "https://feeds.nos.nl/nosnieuwsalgemeen", "Tweakers": "https://tweakers.net/feeds/mixed.xml", "AT5": "https://rss.at5.nl/rss",
            "Guardian": "https://www.theguardian.com/international/rss", "El País": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
            "Google News FR": "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr", "Der Spiegel": "https://www.spiegel.de/schlagzeilen/index.rss",
            "Folha": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", "BBC Hindi": "https://feeds.bbci.co.uk/hindi/rss.xml",
            "China News": "https://www.chinanews.com.cn/rss/importnews.xml", "Al Jazeera": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9?utm_source=chatgpt.com", "NPR": "https://feeds.npr.org/1004/rss.xml",
        }
        cols = [st.columns(2) for _ in range(6)]
        bronnen_lijst = list(nieuwsbronnen.items())
        for idx, (naam, url) in enumerate(bronnen_lijst):
            col_a, col_b = cols[idx // 2]
            target_col = col_a if idx % 2 == 0 else col_b
            with target_col:
                if st.button(f"{'🇳🇱 ' if naam=='NOS' else '💻 ' if naam=='Tweakers' else '🏙️ ' if naam=='AT5' else '🇪🇸 ' if naam=='El País' else '🇫🇷 ' if naam=='Google News FR' else '🇩🇪 ' if naam=='Stern' else '🇵🇹 ' if naam=='Campo Grande' else '🇮🇳 ' if naam=='BBC Hindi' else '🇨🇳 ' if naam=='China News' else '🇸🇦 ' if naam=='BBC Arabic' else '🇺🇸 ' if naam=='Alternet' else ''}{naam}", use_container_width=True, key=f"btn_{naam.replace(' ', '_').lower()}"):
                    st.session_state.gewenste_bron = naam
                    st.session_state.gewenste_url = url
                    if 'vertaalde_nieuws_items' in st.session_state:
                        del st.session_state['vertaalde_nieuws_items']
                    st.session_state.analyses = {}
                    st.session_state.huidig_nieuws = None
                    st.rerun()
        st.markdown("---")
        custom_rss_url = st.text_input("📡 RSS URL", placeholder="https://...", key="custom_rss_input")
        if st.button("📡 RSS", key="btn_add_rss", use_container_width=True):
            if custom_rss_url:
                st.session_state.gewenste_bron = "Custom RSS"
                st.session_state.gewenste_url = custom_rss_url
                st.session_state.analyses = {}
                st.rerun()        
        if 'gewenste_bron' not in st.session_state:
            st.session_state.gewenste_bron = "NOS"
            st.session_state.gewenste_url = nieuwsbronnen["NOS"]
        st.info(f"{t['news_current_source']} **{st.session_state.gewenste_bron}**")
        aantal_nieuws = st.slider(t["news_items_slider"], 1, 10, 5)
        st.markdown("---")
        totaal = get_total_usage(st.session_state.user_id)
        st.caption(f"{t['news_journey']} {totaal} {t['news_since_dawn']}")
        st.markdown("---")
        if st.session_state.membership_tier in ["premium", "gold"]:
            st.markdown("### " + t["news_vip_exclusive"])
            st.markdown(t["news_vip_join"])
            st.markdown(f"[{t['news_vip_link']}](https://discord.gg/zK8Ux9u47)")
        else:
            st.markdown("### " + t["news_vip_locked"])
            st.caption(t["news_vip_upgrade"])
    
        if st.button(t["news_refresh"], use_container_width=True, key="btn_vernieuw"):
            st.session_state.analyses = {}
            st.session_state.huidig_nieuws = None
            st.rerun()

    # NIEUWS HOOFDSCHERM
    with st.spinner(f"📡 {st.session_state.gewenste_bron} {t['news_fetching']}"):
        nieuws_items = haal_nieuws_op(aantal_nieuws, st.session_state.gewenste_url)
    
    if not nieuws_items:
        st.error(t["news_error"])
    else:
        st.subheader(t["news_current"])

        # 🌍 VERTAAL KNOP (Alleen voor Gold)
        if st.session_state.membership_tier == "gold":
            huidige_taal = st.session_state.get('taal', 'nl')
            taal_namen = {
                "nl": "Nederlands", "en": "English", "de": "Deutsch", 
                "es": "Español", "fr": "Français", "pt": "Português",
                "ar": "العربية", "zh": "中文", "hi": "हिन्दी"
            }
            doeltaal_naam = taal_namen.get(huidige_taal, huidige_taal)
            
            if st.button(f"🌍 Translate in {doeltaal_naam}", use_container_width=True):
                with st.spinner(f"🌍 Vertalen naar {doeltaal_naam}..."):
                    volledige_artikelen = []
                    for i, item in enumerate(nieuws_items):
                        volledige_artikelen.append(f"Artikel {i+1}:\nTitel: {item['titel']}\nInhoud: {item['beschrijving']}\n")
                    
                    artikelen_tekst = "\n---\n".join(volledige_artikelen)
                    vertaalde_tekst = vertaal_nieuws(artikelen_tekst, huidige_taal)
                    
                    if vertaalde_tekst and not vertaalde_tekst.startswith("❌"):
                        vertaalde_items = []
                        huidige_item = {}
                        
                        for regel in vertaalde_tekst.strip().split('\n'):
                            if regel.startswith('Artikel'):
                                if huidige_item:
                                    vertaalde_items.append(huidige_item)
                                huidige_item = {}
                            elif regel.startswith('Titel:'):
                                huidige_item['titel'] = regel.replace('Titel:', '').strip()
                            elif regel.startswith('Inhoud:'):
                                huidige_item['inhoud'] = regel.replace('Inhoud:', '').strip()
                        
                        if huidige_item:
                            vertaalde_items.append(huidige_item)
                        
                        vertaalde_nieuws_items = []
                        for i, item in enumerate(nieuws_items):
                            if i < len(vertaalde_items):
                                vertaalde_nieuws_items.append({
                                    'titel': vertaalde_items[i].get('titel', item['titel']),
                                    'beschrijving': vertaalde_items[i].get('inhoud', item['beschrijving']),
                                    'link': item['link']
                                })
                            else:
                                vertaalde_nieuws_items.append(item)
                        
                        st.session_state['vertaalde_nieuws_items'] = vertaalde_nieuws_items
                        st.success("✅ Vertaald!")
                    else:
                        st.error("Vertaling mislukt.")

        # 📰 DE NIEUWS LIJST (Gebruik vertaalde items als ze bestaan, anders origineel)
        display_items = st.session_state.get('vertaalde_nieuws_items', nieuws_items)
        
        for i, item in enumerate(display_items):
            is_open = f"article_{i}_first" in st.session_state.analyses or f"article_{i}_second" in st.session_state.analyses or f"article_{i}_debate" in st.session_state.analyses
            with st.expander(f"**{item['titel']}**", expanded=is_open):
                st.markdown(item['beschrijving'])
                st.markdown(f"[{t['news_read_full']}]({item['link']})")
                
                nieuws_tekst = f"{item['titel']}. {item['beschrijving']}"
                
                if st.session_state.membership_tier in ["premium", "gold"] and st.session_state.favoriet:
                    col_ai, col_manual, col_random, col_fav = st.columns(4)
                else:
                    col_ai, col_manual, col_random = st.columns(3)
                    col_fav = None

                if can_analyze():
                    with col_ai:
                        if st.button(t["news_ai_choose"], key=f"ai_btn_{i}"):
                            with st.spinner(t["news_ai_analyzing"]):
                                gekozen_filosoof = kies_filosoof_ollama(nieuws_tekst, FILOSOFEN)
                            with st.status(f"🤔 {gekozen_filosoof.split(' ')[0]} {t['news_thinking']}", expanded=False) as status:
                                gedachte = genereer_gedachte(nieuws_tekst, gekozen_filosoof, FILOSOFEN)
                                status.update(label=t["news_thought_formed"], state="complete")
                            log_analysis(st.session_state.user_id)
                            st.session_state.analyses[f"article_{i}_first"] = {"filosoof": gekozen_filosoof, "gedachte": gedachte, "titel": item['titel'], "methode": "ai"}
                    
                    with col_manual:
                        beschikbare_filosofen = ALLE_FILOSOFEN if st.session_state.membership_tier in ["premium", "gold"] else FILOSOFEN
                        manual_filosoof = st.selectbox(t["news_choose_manual"], list(beschikbare_filosofen.keys()), key=f"manual_select_{i}", label_visibility="collapsed")
                        if st.button(f"{t['news_analyze_with']} {manual_filosoof.split(' ')[0]}", key=f"manual_btn_{i}"):
                            with st.status(f"🤔 {manual_filosoof.split(' ')[0]} {t['news_thinking']}", expanded=False) as status:
                                gedachte = genereer_gedachte(nieuws_tekst, manual_filosoof, beschikbare_filosofen)
                                status.update(label=t["news_thought_formed"], state="complete")
                            log_analysis(st.session_state.user_id)
                            st.session_state.analyses[f"article_{i}_first"] = {"filosoof": manual_filosoof, "gedachte": gedachte, "titel": item['titel'], "methode": "manual"}
                            st.rerun()
                    with col_random:
                        if st.button(t["news_random"], key=f"random_btn_{i}"):
                            beschikbare_filosofen = ALLE_FILOSOFEN if st.session_state.membership_tier in ["premium", "gold"] else FILOSOFEN
                            random_filosoof = random.choice(list(beschikbare_filosofen.keys()))
                            with st.status(f"🎲 {random_filosoof.split(' ')[0]} {t['news_random_chosen']}", expanded=False) as status:
                                gedachte = genereer_gedachte(nieuws_tekst, random_filosoof, beschikbare_filosofen)
                                status.update(label=t["news_thought_formed"], state="complete")
                            log_analysis(st.session_state.user_id)
                            st.session_state.analyses[f"article_{i}_first"] = {"filosoof": random_filosoof, "gedachte": gedachte, "titel": item['titel'], "methode": "random"}
                            st.rerun()
                    if col_fav:
                        with col_fav:
                            fav = st.session_state.favoriet
                            if st.button(f"⭐ {fav.split(' ')[0]}", key=f"fav_btn_{i}"):
                                with st.status(f" {fav.split(' ')[0]} {t['news_thinking']}", expanded=False) as status:
                                    gedachte = genereer_gedachte(nieuws_tekst, fav, ALLE_FILOSOFEN)
                                    status.update(label=t["news_thought_formed"], state="complete")
                                log_analysis(st.session_state.user_id)
                                st.session_state.analyses[f"article_{i}_first"] = {"filosoof": fav, "gedachte": gedachte, "titel": item['titel'], "methode": "favoriet"}
                                st.rerun()

                if f"article_{i}_first" in st.session_state.analyses:
                    fa = st.session_state.analyses[f"article_{i}_first"]
                    filosoof, gedachte, titel = fa["filosoof"], fa["gedachte"], fa["titel"]
                    methode = fa.get("methode", "ai")
                    f = ALLE_FILOSOFEN.get(filosoof, FILOSOFEN.get(filosoof, {}))
                    
                    if methode == "ai":
                        st.success(f"**{f.get('emoji', '')} {filosoof}** {t['news_best_match']}")
                    elif methode == "manual":
                        st.success(f"**{f.get('emoji', '')} {t['news_you_chose']} {filosoof}**")
                    elif methode == "favoriet":
                        st.success(f"**{f.get('emoji', '')} {t['news_your_fav']} {filosoof}**")
                    else:
                        st.success(f"**{f.get('emoji', '')} {t['news_fate']} {filosoof}**")
                        
                    taal = st.session_state.get('taal', 'nl')
                    vertaalde_filosoof = get_vertaalde_naam(filosoof, taal)
                    
                    # Haal de vertaalde beschrijving op uit de JSON, met fallback
                    desc = t.get(f"desc_{filosoof}", f.get('beschrijving', 'Geen beschrijving beschikbaar.'))
                    st.info(f"*{desc}*")
                    
                    st.markdown("---")
                    st.markdown(f"### {f.get('emoji', '')} {vertaalde_filosoof} {t['news_says']}")
                    schone_tekst, noten = verwerk_neologismen(gedachte, filosoof)                    
                    st.success(schone_tekst)
                    
                    if noten:
                        st.markdown("---")
                        st.markdown(f"*📝 **{filosoof.split(' ')[0]}** {t.get('news_neologism', 'heeft een nieuw woord bedacht')}*")
                        for noot in noten:
                            st.markdown(f"- {noot}")
                            
                    voice_type = t["news_listen_female"] if f.get("geslacht") == "female" else t["news_listen_male"]
                    st.markdown(f"**{t['news_listen']} ({voice_type} {t['news_voice']}):**")
                    maak_audio_player(schone_tekst, f.get("geslacht", "male"), f"first_{i}")
                    
                    st.markdown("---")
                    st.markdown("#### " + t["news_share_on_social"])
                    safe_filosoof = filosoof.replace(" ", "_")
                    commentaar = st.text_area(t["news_add_comment"], key=f"comment_first_{i}_{safe_filosoof}", height=60, placeholder=t["news_comment_placeholder"])
                    share_urls, share_text = maak_share_urls(filosoof, titel, schone_tekst, commentaar)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"[💼 LinkedIn]({share_urls['linkedin']})\n\n[🐦 X (Twitter)]({share_urls['x']})\n\n[📘 Facebook]({share_urls['facebook']})")
                    with col2:
                        st.markdown(f"[💬 WhatsApp]({share_urls['whatsapp']})\n\n[✈️ Telegram]({share_urls['telegram']})\n\n[🇺🇸 Truth Social]({share_urls['truthsocial']})")
                    
                    st.markdown("---")
                    st.caption(t["news_copy_text"])
                    st.code(share_text, language=None)
                    
                    with st.expander(t["news_download_image"]):
                        if st.button(t["news_download_png"], key=f"dl_first_{i}_{safe_filosoof}"):
                            share_img = maak_share_image(titel, filosoof, f.get('emoji', ''), schone_tekst, commentaar, st.session_state.membership_tier in ["premium", "gold"])
                            img_bytes = io.BytesIO()
                            share_img.save(img_bytes, format='PNG')
                            st.download_button(label=t["news_click_to_save"], data=img_bytes.getvalue(), file_name=f"denkkrant_{filosoof.split(' ')[0]}_{i}.png", mime="image/png", key=f"save_first_{i}_{safe_filosoof}")
                    
                    st.markdown("---")
                    st.markdown("#### " + t["news_other_perspective"])
                    andere_beschikbaar = ALLE_FILOSOFEN if st.session_state.membership_tier in ["premium", "gold"] else FILOSOFEN
                    andere_filosoof = st.selectbox(
                        t["news_choose_other_philosopher"], 
                        [n for n in andere_beschikbaar.keys() if n != filosoof], 
                        format_func=lambda x: get_vertaalde_naam(x, st.session_state.taal), 
                        key=f"select_other_{i}_{safe_filosoof}"
                    )
                    if st.button(f"{t['news_read_view_of']} {andere_filosoof.split(' ')[0]}", key=f"other_btn_{i}_{safe_filosoof}"):
                        with st.status(f"🤔 {andere_filosoof.split(' ')[0]} {t['news_thinking_dots']}", expanded=False) as status2:
                            gedachte2 = genereer_gedachte(nieuws_tekst, andere_filosoof, andere_beschikbaar)
                            status2.update(label=t["news_thought_complete"], state="complete")
                        st.session_state.analyses[f"article_{i}_second"] = {"filosoof": andere_filosoof, "gedachte": gedachte2, "titel": titel}
                        st.rerun()   
                    
                    # 🥊 FILOSOFISCH DEBAT
                    st.markdown("---")
                    st.markdown(f"#### {t['debate_title']}")
                    debate_key = f"article_{i}_debate"
                    if debate_key not in st.session_state.analyses:
                        st.session_state.analyses[debate_key] = []
                    dialoog = st.session_state.analyses[debate_key]

                    for idx, reactie in enumerate(dialoog):
                        f_reactie = ALLE_FILOSOFEN.get(reactie["filosoof"], {})
                        emoji = f_reactie.get("emoji", "💭")
                        
                        # Gebruik Streamlit's native componenten (mobiel-proof)
                        with st.container():
                            st.markdown(f"#### {emoji} {reactie['filosoof']}")
                            st.markdown(reactie['gedachte'])
                            st.markdown("---")
                    
                    if can_analyze():
                        laatste_filosoof = dialoog[-1]["filosoof"] if dialoog else filosoof
                        beschikbare_filosofen = [n for n in ALLE_FILOSOFEN.keys() if n != laatste_filosoof]
                        col_debate1, col_debate2 = st.columns([2, 1])
                        with col_debate1:
                            nieuwe_filosoof = st.selectbox(t["debate_select"], beschikbare_filosofen, key=f"debate_select_first_{i}")
                        with col_debate2:
                            if st.button(t["debate_button"], key=f"debate_btn_first_{i}"):
                                with st.status(f"🤔 {nieuwe_filosoof.split(' ')[0]} {t['debate_thinking']}", expanded=False) as status_debate:
                                    laatste_tekst = dialoog[-1]["gedachte"] if dialoog else gedachte
                                    laatste_naam = dialoog[-1]["filosoof"] if dialoog else filosoof
                                    nieuwe_reactie = genereer_debat_reactie(nieuws_tekst, nieuwe_filosoof, ALLE_FILOSOFEN, laatste_tekst, laatste_naam)
                                    status_debate.update(label=t["debate_complete"], state="complete")
                                log_analysis(st.session_state.user_id)
                                dialoog.append({"filosoof": nieuwe_filosoof, "gedachte": nieuwe_reactie})
                                st.session_state.analyses[debate_key] = dialoog
                                st.rerun()
                    
                    if dialoog:
                        if st.button(t["debate_end"], key=f"debate_end_first_{i}"):
                            st.session_state.analyses[debate_key] = []
                            st.rerun()                     

                if f"article_{i}_second" in st.session_state.analyses:
                    sa = st.session_state.analyses[f"article_{i}_second"]
                    filosoof2, gedachte2, titel2 = sa["filosoof"], sa["gedachte"], sa["titel"]
                    f2 = ALLE_FILOSOFEN.get(filosoof2, {})
                    st.markdown("---")
                    st.markdown(f"### {f2.get('emoji', '')} {filosoof2} {t['news_says']}")
                    schone_tekst2, noten2 = verwerk_neologismen(gedachte2, filosoof2)
                    st.info(schone_tekst2)
                    if noten2:
                        st.markdown("---")
                        st.markdown(f"*📝 **{filosoof2.split(' ')[0]}** {t.get('news_neologism', 'heeft een nieuw woord bedacht')}*")
                        for noot in noten2:
                            st.markdown(f"- {noot}")
                    
                    voice_type2 = t["news_listen_female"] if f2.get("geslacht") == "female" else t["news_listen_male"]
                    st.markdown(f"**{t['news_listen']} ({voice_type2} {t['news_voice']}):**")
                    maak_audio_player(schone_tekst2, f2.get("geslacht", "male"), f"second_{i}")
                    
                    st.markdown("---")
                    st.markdown("#### " + t["news_share_on_social"])
                    safe_filosoof2 = filosoof2.replace(" ", "_")
                    commentaar2 = st.text_area(t["news_add_comment"], key=f"comment_second_{i}_{safe_filosoof2}", height=60, placeholder=t["news_comment_placeholder"])
                    share_urls2, share_text2 = maak_share_urls(filosoof2, titel2, schone_tekst2, commentaar2)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"[💼 LinkedIn]({share_urls2['linkedin']})\n\n[🐦 X (Twitter)]({share_urls2['x']})\n\n[📘 Facebook]({share_urls2['facebook']})")
                    with col2:
                        st.markdown(f"[💬 WhatsApp]({share_urls2['whatsapp']})\n\n[✈️ Telegram]({share_urls2['telegram']})\n\n[🇺🇸 Truth Social]({share_urls2['truthsocial']})")
                    
                    st.markdown("---")
                    st.caption(t["news_copy_text"])
                    st.code(share_text2, language=None)
                    with st.expander(t["news_download_image"]):
                        if st.button(t["news_download_png"], key=f"dl_second_{i}_{safe_filosoof2}"):
                            share_img2 = maak_share_image(titel2, filosoof2, f2.get('emoji', ''), schone_tekst2, commentaar2, st.session_state.membership_tier in ["premium", "gold"])
                            img_bytes2 = io.BytesIO()
                            share_img2.save(img_bytes2, format='PNG')
                            st.download_button(label=t["news_click_to_save"], data=img_bytes2.getvalue(), file_name=f"denkkrant_{filosoof2.split(' ')[0]}_{i}_2.png", mime="image/png", key=f"save_second_{i}_{safe_filosoof2}")
                    
                    st.markdown("---")
                    st.markdown("#### " + t["news_other_perspective"])
                    andere_beschikbaar = ALLE_FILOSOFEN if st.session_state.membership_tier in ["premium", "gold"] else FILOSOFEN
                    andere_filosoof = st.selectbox(t["news_choose_other_philosopher"], [n for n in andere_beschikbaar.keys() if n != filosoof2], key=f"select_other_2_{i}_{safe_filosoof2}")
                    if st.button(f"{t['news_read_view_of']} {andere_filosoof.split(' ')[0]}", key=f"other_btn_2_{i}_{safe_filosoof2}"):
                        with st.status(f"🤔 {andere_filosoof.split(' ')[0]} {t['news_thinking_dots']}", expanded=False) as status3:
                            gedachte3 = genereer_gedachte(nieuws_tekst, andere_filosoof, andere_beschikbaar)
                            status3.update(label=t["news_thought_complete"], state="complete")
                        st.session_state.analyses[f"article_{i}_second"] = {"filosoof": andere_filosoof, "gedachte": gedachte3, "titel": titel2}
                        st.rerun()

elif menu == t["sidebar_philosophers"]:
    st.markdown("<a id='top'></a>", unsafe_allow_html=True)
    bio_path = os.path.join(_APP_MAP, "vertalingen", f"filosofen_bio_{st.session_state.taal}.txt")
    fallback_bio = os.path.join(_APP_MAP, "vertalingen", "filosofen_bio_nl.txt")
    try:
        with open(bio_path, 'r', encoding='utf-8') as f:
            bio_text = f.read()
    except FileNotFoundError:
        with open(fallback_bio, 'r', encoding='utf-8') as f:
            bio_text = f.read()
    st.markdown(bio_text, unsafe_allow_html=True)

st.markdown("---")
with st.expander(t["faq_title"]):
    st.markdown(t["faq_content"])

# ==========================================
# 9. MOLLIE BETALING CONTROLE
# ==========================================
if "payment" in st.query_params and st.query_params["payment"] == "success":
    activation_code = st.query_params.get("code", "")
    
    if activation_code:
        result = valideer_activation_code(activation_code)
        if result:
            user_id, membership_tier = result
            sla_gebruiker_op(user_id, membership_tier, activation_code)
            st.session_state.membership_tier = membership_tier
            st.success(f"✅ Betaling ontvangen! Je {membership_tier} lidmaatschap is geactiveerd!")
            st.balloons()
            del st.query_params["payment"]
            del st.query_params["code"]
            st.rerun()
        else:
            st.error("Ongeldige activation code")
            del st.query_params["payment"]
            del st.query_params["code"]
    else:
        st.error("Geen activation code gevonden")
        del st.query_params["payment"]   