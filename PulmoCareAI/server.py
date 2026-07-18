"""
PulmoCare AI - Production Backend Server v1.0
Pulmonology (Chest Medicine) Health Intelligence Platform
Port: 5110
=========================================
DISCLAIMER: All AI output is for research/education only.
Not medical advice. Always consult a qualified pulmonologist.
PULMONARY EMERGENCY (severe breathlessness, blue lips/fingers,
massive coughing up blood, sudden one-sided chest pain with
breathlessness, silent chest in known asthmatic): Call 112
(India) / 999 (UK) / 911 (US) immediately.
"""

import os, sys, json, uuid, time, hashlib, logging, datetime, argparse
from pathlib import Path

try:
    from flask import Flask, request, jsonify, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("[FATAL] Flask not installed. Run REPAIR_AND_RECOVER.bat"); sys.exit(1)

try:
    import requests as req_lib; REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import fitz; FITZ_OK = True
except ImportError:
    FITZ_OK = False

try:
    from PIL import Image; PIL_OK = True
except ImportError:
    PIL_OK = False

sys.path.insert(0, str(Path(__file__).parent / "modules"))
try:
    import ai_providers; AI_PROVIDERS_OK = True
except ImportError:
    AI_PROVIDERS_OK = False

BASE_DIR    = Path(__file__).parent.resolve()
UPLOAD_DIR  = BASE_DIR / "uploads"
LOGS_DIR    = BASE_DIR / "logs"
DATA_DIR    = BASE_DIR / "data"
STATIC_DIR  = BASE_DIR / "static"
REPORTS_DIR = BASE_DIR / "reports_db"

for d in [UPLOAD_DIR, LOGS_DIR, DATA_DIR, STATIC_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── SOFTWARESAFETY: no hardcoded secrets — all keys from env or client-supplied at runtime ──
PORT    = int(os.environ.get("PULMOCARE_PORT", 5110))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_PROVIDER_KEYS = ai_providers.get_env_keys() if AI_PROVIDERS_OK else {}
VERSION = "1.0.0"

DISCLAIMER = (
    "WARNING - AI RESEARCH DISCLAIMER: All output is AI-generated from published "
    "pulmonology literature (GOLD, GINA, ATS/ERS, WHO, NICE, NTEP - National TB "
    "Elimination Programme India, PubMed). For educational research only. NOT a "
    "substitute for professional chest/pulmonology examination, diagnosis, or "
    "treatment. ALWAYS consult a qualified pulmonologist. PULMONARY EMERGENCY "
    "(severe breathlessness, blue lips/fingers, massive coughing up blood, sudden "
    "one-sided chest pain with breathlessness, silent chest in known asthmatic): "
    "Call 112 (India) / 999 (UK) / 911 (US) immediately."
)

log_file = LOGS_DIR / f"server_{datetime.date.today()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("PulmoCareAI")

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
CORS(app, origins="*")  # local single-user tool; no auth/session/cookie state to protect

_RATE_STORE = {}

def _get_client_id():
    return hashlib.sha256((request.remote_addr or "127.0.0.1").encode()).hexdigest()[:16]

def rate_limit_check():
    """SOFTWARESAFETY: route throttling on all endpoints."""
    cid = _get_client_id(); now = time.time()
    _RATE_STORE.setdefault(cid, [])
    _RATE_STORE[cid] = [t for t in _RATE_STORE[cid] if now - t < 60]
    if len(_RATE_STORE[cid]) >= 30: return False
    _RATE_STORE[cid].append(now); return True

def sanitise_api_key(key):
    """SOFTWARESAFETY: treat all client input as untrusted — validate and strip."""
    if not key or not isinstance(key, str): return ""
    key = key.strip()
    if len(key) > 512: return ""
    s = "".join(c for c in key if 0x21 <= ord(c) <= 0x7E)
    return s if len(s) >= 10 else ""

def validate_provider(p):
    """SOFTWARESAFETY: whitelist validation — reject anything not in the known set."""
    valid = {"anthropic","openai","gemini","grok","deepseek","mistral"}
    return p.lower() if p and p.lower() in valid else "anthropic"

def sanitise_text_field(val, max_len=500):
    """SOFTWARESAFETY: bound and strip all free-text client input before use in prompts/logs."""
    if not val or not isinstance(val, str): return ""
    return val.strip()[:max_len]

# ═══════════════════════════════════════════════════════════════
# PULMONOLOGY KNOWLEDGE BASE
# Sources: GOLD, GINA, ATS/ERS, WHO, NICE, NTEP (National TB
#          Elimination Programme India), PubMed
# ═══════════════════════════════════════════════════════════════
KNOWLEDGE = {
    "asthma": {
        "name": "Asthma",
        "definition": "Chronic inflammatory airway disease causing variable, reversible airflow obstruction. Symptoms: wheeze, breathlessness, chest tightness, cough (often nocturnal/early morning, or triggered by exercise/cold air/allergens). GINA (Global Initiative for Asthma) provides internationally adopted stepwise management guidance. Diagnosis: characteristic symptom pattern plus demonstrated variable airflow limitation (spirometry with reversibility testing, peak flow variability, or bronchial challenge testing if diagnosis uncertain).",
        "classification_control": "Asthma control assessed by symptom frequency, reliever use, night waking, and activity limitation (well-controlled/partly-controlled/uncontrolled per GINA). Distinguish from severity, which is retrospectively assessed by treatment step required to achieve control. Poor control despite adequate treatment should prompt review of inhaler technique, adherence, and consideration of alternative/coexisting diagnoses before escalating therapy.",
        "management": "GINA preferred approach: all adults/adolescents should receive ICS-containing therapy (inhaled corticosteroid) rather than SABA-only reliever, given evidence that SABA-only treatment increases exacerbation risk. Track 1 (preferred): as-needed low-dose ICS-formoterol at all steps, escalating to regular ICS-formoterol maintenance plus as-needed at higher steps. Track 2 (alternative): regular ICS maintenance with as-needed SABA reliever. Add-on therapy for severe/uncontrolled asthma: LABA, LTRA (montelukast), long-acting muscarinic antagonist (LAMA), or biologics (omalizumab for allergic asthma, mepolizumab/benralizumab/dupilumab for eosinophilic phenotype) guided by phenotyping. Correct inhaler technique and a written asthma action plan are essential components of management regardless of severity.",
        "acute_exacerbation": "Acute severe asthma: assess severity (moderate/severe/life-threatening) by respiratory rate, ability to speak in sentences, peak flow, oxygen saturation, and signs of exhaustion. Life-threatening features: silent chest, cyanosis, bradycardia/hypotension, exhaustion, confusion, peak flow under 33% predicted - EMERGENCY. Management: high-flow oxygen to maintain saturations, nebulised salbutamol (repeated/continuous if severe) plus ipratropium bromide, systemic corticosteroids (oral prednisolone or IV hydrocortisone) early in all but the mildest exacerbations, IV magnesium sulphate for severe/life-threatening cases not responding to initial bronchodilator therapy, escalate to intensive care if deteriorating or life-threatening features present. Never underestimate acute asthma - patients can deteriorate rapidly and it remains a preventable cause of death.",
    },
    "copd": {
        "name": "Chronic Obstructive Pulmonary Disease (COPD)",
        "definition": "GOLD definition: persistent respiratory symptoms and airflow limitation due to airway/alveolar abnormalities, usually caused by significant exposure to noxious particles or gases. Primarily tobacco smoking in high-income countries, but biomass fuel/solid cooking fuel smoke exposure is a major and often under-recognised cause in India and other LMICs, particularly affecting women who traditionally do most household cooking with biomass fuels in poorly ventilated kitchens. Diagnosis requires spirometry demonstrating post-bronchodilator FEV1/FVC below the lower limit of normal (or below 0.7 per simplified GOLD criteria).",
        "assessment_staging": "GOLD ABE assessment tool (updated from ABCD): combines symptom burden (mMRC dyspnoea scale or CAT score) with exacerbation history (Group A: low symptom burden, 0-1 moderate exacerbations without hospitalisation; Group B: high symptom burden, same exacerbation profile; Group E: 2+ moderate exacerbations or 1+ requiring hospitalisation, regardless of symptoms) to guide initial pharmacological therapy selection. Spirometric grading (GOLD 1-4, mild to very severe) based on FEV1 percent predicted provides additional prognostic information.",
        "management": "Smoking cessation is the single most important intervention to slow disease progression - should be addressed at every encounter. Bronchodilators are mainstay: long-acting muscarinic antagonists (LAMA) and/or long-acting beta-agonists (LABA), with combination LAMA/LABA often preferred over monotherapy for reducing exacerbations and improving symptoms. Inhaled corticosteroids (ICS) added to LABA/LAMA for patients with frequent exacerbations, particularly with blood eosinophil count elevation (biomarker guides ICS benefit) - ICS should generally be avoided as monotherapy in COPD given increased pneumonia risk without the same benefit seen in asthma. Pulmonary rehabilitation: strong evidence for improving symptoms, exercise capacity and quality of life, markedly underutilised globally. Long-term oxygen therapy for patients with chronic severe hypoxaemia (improves survival). Vaccination (influenza, pneumococcal, COVID-19, pertussis where indicated) reduces exacerbation risk. Roflumilast (PDE4 inhibitor) or azithromycin prophylaxis considered for selected patients with frequent exacerbations despite optimised inhaled therapy.",
        "exacerbations": "COPD exacerbation: acute worsening of respiratory symptoms (increased breathlessness, sputum volume/purulence, cough) requiring additional treatment. Management: short-acting bronchodilators (increase frequency/dose), systemic corticosteroids (short course, typically 5 days - reduces recovery time and improves lung function), antibiotics if increased sputum purulence or clinical signs of infection/severe exacerbation (choice guided by local resistance patterns), controlled oxygen therapy (target saturations typically 88-92% in those at risk of hypercapnic respiratory failure - avoid over-oxygenation), non-invasive ventilation for acute hypercapnic respiratory failure with respiratory acidosis not responding to initial medical therapy.",
    },
    "tuberculosis": {
        "name": "Tuberculosis (TB)",
        "burden_india": "India carries the world's highest TB burden, accounting for a very substantial proportion of global TB cases and deaths. The National TB Elimination Programme (NTEP, formerly RNTCP) coordinates India's TB control efforts with the ambitious goal of TB elimination, providing free diagnosis and treatment nationwide including newer rapid molecular diagnostics (CBNAAT/Truenat for rapid detection including rifampicin resistance) and daily fixed-dose combination therapy (moved from earlier intermittent regimens based on evidence of improved outcomes). Drug-resistant TB (MDR-TB, resistant to at least isoniazid and rifampicin; XDR-TB with additional resistance) represents a major ongoing public health challenge requiring specialised, prolonged treatment regimens.",
        "clinical_presentation": "Classic presentation: chronic cough (over 2-3 weeks - the key symptom prompting TB investigation per WHO/NTEP screening criteria), fever (often low-grade, evening predominance), night sweats, weight loss, haemoptysis (may occur, particularly with cavitary disease or in advanced disease). Extrapulmonary TB (lymph node, pleural, spinal/Pott's disease, meningeal, abdominal, genitourinary) accounts for a significant minority of cases and can present with more varied, site-specific symptoms - TB meningitis is a particularly serious form requiring urgent recognition and treatment given high mortality/morbidity if delayed. HIV co-infection significantly increases TB risk and alters presentation (more likely extrapulmonary/disseminated, atypical chest X-ray findings, smear-negative disease more common) - bidirectional testing (TB patients for HIV, HIV patients for TB) is standard of care.",
        "diagnosis": "Sputum smear microscopy (AFB smear): rapid, widely available, but limited sensitivity, particularly in paucibacillary or HIV-associated disease. Molecular tests (CBNAAT/GeneXpert MTB/RIF, Truenat): rapid (hours rather than weeks), simultaneously detect rifampicin resistance (surrogate marker for MDR-TB risk), now first-line initial diagnostic test per WHO/NTEP guidance where available given superior sensitivity and rapid resistance detection. Culture (solid or liquid media): gold-standard sensitivity, but slow (weeks) - remains important for drug susceptibility testing and in specific clinical scenarios. Chest X-ray: supportive but not diagnostic alone (upper lobe cavitation classic but disease can present atypically, especially in immunocompromised/HIV-positive patients). Tuberculin skin test/IGRA (interferon-gamma release assay): identify TB infection (latent or active) but cannot distinguish between them or confirm active disease - used mainly for latent TB infection screening in appropriate risk groups.",
        "treatment": "Standard drug-sensitive TB regimen (per WHO/NTEP): intensive phase 2 months of isoniazid, rifampicin, pyrazinamide, ethambutol (HRZE) daily, followed by continuation phase 4 months of isoniazid and rifampicin (HR) - daily dosing throughout now standard given superior outcomes versus older intermittent regimens. Directly observed therapy (DOT) or equivalent adherence support historically emphasised to ensure completion, now often supplemented/replaced by digital adherence technologies in many programmes. Drug-resistant TB: requires longer, more complex regimens with second-line drugs (bedaquiline, linezolid, and other agents in newer WHO-recommended shorter/all-oral regimens that have transformed MDR-TB treatment from the historically very prolonged, poorly tolerated injectable-containing regimens) under specialist supervision. Treatment success requires addressing adherence barriers, monitoring for drug toxicity (hepatotoxicity particularly with isoniazid/rifampicin/pyrazinamide - baseline and monitoring LFTs, visual acuity monitoring with ethambutol given optic neuritis risk), and nutritional support given the strong bidirectional relationship between malnutrition and TB risk/outcomes in India.",
        "latent_tb_prevention": "Latent TB infection (LTBI): asymptomatic infection without active disease, identified by IGRA or tuberculin skin test in appropriate risk groups (household contacts of active TB, immunosuppressed individuals, healthcare workers in high-burden settings). Preventive therapy (isoniazid alone for 6-9 months, or shorter rifamycin-based regimens increasingly preferred for better completion rates) significantly reduces progression to active disease in high-risk individuals. BCG vaccination provides some protection against severe childhood TB (miliary, meningeal) but has variable and generally limited efficacy against adult pulmonary TB - included in India's universal childhood immunisation programme.",
    },
    "interstitial_lung_disease": {
        "name": "Interstitial Lung Disease (ILD)",
        "overview": "Heterogeneous group of disorders causing progressive lung scarring/fibrosis or inflammation of the lung interstitium. Idiopathic pulmonary fibrosis (IPF) is the most common and generally most aggressive idiopathic form, predominantly affecting older adults, usually progressive despite treatment. Other causes: connective tissue disease-associated ILD (rheumatoid arthritis, systemic sclerosis, myositis - screening for underlying autoimmune disease important in ILD workup), hypersensitivity pneumonitis (allergic reaction to inhaled organic antigens - occupational/environmental exposure history crucial, includes exposures relevant in Indian agricultural/occupational settings such as bird fancier's lung, farmer's lung), sarcoidosis, drug-induced ILD, and pneumoconiosis (occupational lung disease from mineral dust inhalation).",
        "diagnosis": "High-resolution CT (HRCT) chest is central to diagnosis, identifying characteristic patterns (usual interstitial pneumonia/UIP pattern in IPF, ground-glass changes, and other patterns) that combined with clinical history often allow confident diagnosis without biopsy. Multidisciplinary discussion (pulmonologist, radiologist, pathologist) is considered best practice for accurate ILD diagnosis and classification given the complexity and overlap between entities. Pulmonary function tests characteristically show restrictive pattern (reduced FVC and TLC, preserved or increased FEV1/FVC ratio) with reduced diffusion capacity (DLCO). Autoimmune serology screening important even without overt connective tissue disease symptoms, as subclinical autoimmune-associated ILD is increasingly recognised.",
        "treatment": "IPF: antifibrotic agents (pirfenidone, nintedanib) slow disease progression (reduce rate of FVC decline) though do not reverse existing fibrosis - early diagnosis and treatment initiation is important given the progressive, largely irreversible nature of the disease. Connective tissue disease-associated ILD: immunosuppression (depending on underlying disease and ILD pattern) may be appropriate, contrasting with IPF where immunosuppression is generally not beneficial and historically was associated with worse outcomes in some studies. Hypersensitivity pneumonitis: antigen avoidance is key, with immunosuppression for ongoing inflammation. Pulmonary rehabilitation and oxygen therapy (for hypoxaemia) provide symptomatic benefit across ILD types. Lung transplantation remains an option for selected patients with progressive disease despite optimal medical therapy.",
        "occupational_pneumoconiosis_india": "Occupational lung diseases remain a significant concern in India given large workforces in mining, stone-cutting/quarrying, construction, and textile industries. Silicosis (from crystalline silica dust exposure - stone workers, sandblasting, mining) and coal workers' pneumoconiosis remain prevalent in certain occupational groups, often under-recognised and under-compensated given limited occupational health surveillance infrastructure in many settings. Silicosis notably also significantly increases TB risk, an important interaction relevant to affected worker populations. Prevention (dust control, protective equipment, workplace monitoring) is the primary strategy as established pneumoconiosis is generally irreversible.",
    },
    "respiratory_infections": {
        "name": "Respiratory Infections",
        "pneumonia": "Community-acquired pneumonia (CAP): CURB-65 or similar severity scores (Confusion, Urea, Respiratory rate, Blood pressure, Age ≥65) guide site-of-care decisions (outpatient vs admission vs ICU) and inform antibiotic choice/duration. Typical organisms: Streptococcus pneumoniae (most common), Haemophilus influenzae, atypical organisms (Mycoplasma, Chlamydophila, Legionella) requiring different antibiotic coverage (macrolides/fluoroquinolones for atypical cover). Empirical antibiotic choice guided by severity and local resistance patterns/antibiograms. Hospital-acquired and ventilator-associated pneumonia carry different, typically broader-spectrum, resistant organism profiles requiring different empirical approaches. Vaccination (pneumococcal, influenza) reduces incidence particularly in high-risk groups (elderly, chronic lung/heart disease, immunosuppressed).",
        "bronchitis_acute": "Acute bronchitis: usually viral, self-limiting cough illness, antibiotics generally not indicated in the absence of underlying lung disease or signs suggesting pneumonia (focal chest signs, hypoxia, systemic illness) - overuse of antibiotics for viral bronchitis is a significant driver of antimicrobial resistance and should be actively avoided per antibiotic stewardship principles.",
        "post_covid_considerations": "Post-COVID respiratory sequelae recognised in a proportion of patients following acute infection, ranging from prolonged symptomatic recovery to, in a smaller subset, organising pneumonia or fibrotic-appearing changes on imaging following severe illness - ongoing follow-up and pulmonary function/imaging assessment appropriate for those with persistent symptoms or risk factors for severe disease, though the majority of post-COVID respiratory symptoms improve over time without specific fibrotic sequelae.",
    },
    "lung_cancer": {
        "name": "Lung Cancer",
        "overview": "Leading cause of cancer death globally. Major risk factor: tobacco smoking (both active and passive/secondhand exposure), though a notable and possibly increasing proportion occurs in never-smokers, particularly relevant with certain molecular subtypes (EGFR-mutant adenocarcinoma more common in Asian never-smoking populations including India). Indoor air pollution from biomass fuel smoke and outdoor air pollution are increasingly recognised contributing factors, of particular relevance in the Indian context given high ambient and household air pollution levels in many regions.",
        "presentation_redflags": "Red flag symptoms warranting urgent chest X-ray/CT and respiratory referral: persistent cough beyond 3 weeks (especially new or changed cough in a smoker), haemoptysis (coughing up blood - always requires investigation), unexplained weight loss, persistent chest/shoulder pain, hoarseness, unexplained breathlessness, finger clubbing, unexplained or persistent chest signs, cervical/supraclavicular lymphadenopathy. Any of these, particularly in a current or former smoker over 40, should prompt prompt investigation rather than being attributed to more benign causes without appropriate imaging.",
        "diagnosis_staging": "CT chest (with contrast) is the primary staging investigation. PET-CT increasingly used for more accurate staging, particularly for assessing mediastinal lymph node involvement and detecting distant metastases before curative-intent treatment. Tissue diagnosis (bronchoscopy, CT-guided biopsy, endobronchial ultrasound-guided biopsy, or surgical biopsy depending on lesion location) essential, with molecular/biomarker testing (EGFR, ALK, ROS1, KRAS, PD-L1 and others) now standard for advanced non-small cell lung cancer to guide targeted therapy or immunotherapy selection.",
        "management_screening": "Management is highly stage- and histology-dependent: surgical resection for early-stage disease where feasible, combined chemoradiotherapy for locally advanced unresectable disease, and targeted therapy/immunotherapy/chemotherapy combinations for advanced/metastatic disease based on molecular profile and PD-L1 status. Low-dose CT screening for high-risk individuals (heavy smoking history, appropriate age range) has been shown to reduce lung cancer mortality in trials and is recommended in some countries, though implementation and eligibility criteria vary internationally and is not yet a widely established national programme in India.",
    },
    "pleural_disease": {
        "name": "Pleural Diseases",
        "pleural_effusion": "Fluid accumulation in the pleural space. Investigation: pleural fluid aspiration with Light's criteria (comparing pleural fluid to serum protein and LDH) distinguishes transudate (heart failure, cirrhosis, nephrotic syndrome - usually bilateral, treat underlying cause) from exudate (infection/parapneumonic, malignancy, TB, pulmonary embolism - broader differential requiring further pleural fluid analysis: cytology, culture, ADA for TB in endemic settings like India, ANA/rheumatoid factor if autoimmune suspected). Large or symptomatic effusions may require therapeutic drainage. Empyema (infected pleural fluid/pus) requires prompt drainage (chest drain) plus antibiotics, occasionally surgical intervention (VATS decortication) if loculated/organised.",
        "pneumothorax": "Air in the pleural space causing lung collapse. Primary spontaneous pneumothorax: typically young, tall, thin patients without underlying lung disease, often due to rupture of subpleural blebs. Secondary spontaneous pneumothorax: occurs in patients with underlying lung disease (COPD, TB-related cavitary/fibrotic changes, ILD) - generally more symptomatic and higher-risk given reduced respiratory reserve. Management depends on size and symptoms: observation for small asymptomatic primary pneumothorax, needle aspiration or chest drain insertion for larger/symptomatic pneumothoraces, surgical intervention (pleurodesis) considered for recurrent episodes. Tension pneumothorax: EMERGENCY - progressive air accumulation causing mediastinal shift and cardiovascular compromise (hypotension, tachycardia, tracheal deviation, absent breath sounds on affected side) - requires immediate needle decompression followed by chest drain insertion, must not await imaging confirmation if clinical suspicion is high given rapid life-threatening deterioration.",
    },
    "pulmonary_function_diagnostics": {
        "name": "Pulmonary Function Tests & Diagnostics",
        "spirometry": "Fundamental test of lung function. FEV1 (forced expiratory volume in 1 second) and FVC (forced vital capacity) and their ratio distinguish obstructive (reduced FEV1/FVC ratio - asthma, COPD) from restrictive (reduced FVC with preserved or increased FEV1/FVC ratio - ILD, chest wall/neuromuscular disease, obesity) patterns. Bronchodilator reversibility testing (spirometry before and after bronchodilator) supports asthma diagnosis when significant improvement demonstrated, though a negative reversibility test does not exclude asthma given its variable nature.",
        "additional_tests": "Diffusion capacity (DLCO): assesses gas transfer across the alveolar-capillary membrane, characteristically reduced in ILD, emphysema, and pulmonary vascular disease; can help distinguish chronic bronchitis-predominant from emphysema-predominant COPD phenotypes. Lung volumes (body plethysmography): confirms restrictive pattern (reduced TLC) versus obstruction with hyperinflation (increased TLC/RV in COPD). Arterial blood gas: assesses oxygenation and ventilation (hypercapnia in advanced COPD or acute severe asthma exhaustion - a particularly concerning sign of impending respiratory failure in acute severe asthma, since CO2 typically falls initially with hyperventilation before rising as the patient tires). 6-minute walk test: assesses functional exercise capacity, used in ILD and pulmonary hypertension assessment and monitoring.",
        "imaging": "Chest X-ray: first-line imaging, useful for pneumonia, pneumothorax, effusion, and gross parenchymal changes, though limited sensitivity for early or subtle interstitial disease. HRCT chest: essential for detailed assessment of interstitial lung disease, bronchiectasis, and detecting subtle parenchymal abnormalities not visible on plain film. CT pulmonary angiography (CTPA): investigation of choice for suspected pulmonary embolism where clinical probability and D-dimer testing suggest need for definitive imaging.",
    },
    "pulmonary_emergencies": {
        "name": "Pulmonary Emergencies",
        "acute_severe_asthma": "Life-threatening asthma features: silent chest, cyanosis, feeble respiratory effort, bradycardia, hypotension, exhaustion/confusion, peak flow under 33% predicted. EMERGENCY requiring immediate high-flow oxygen, continuous/repeated nebulised bronchodilators, systemic corticosteroids, IV magnesium sulphate, and escalation to critical care if not rapidly improving - a rising or normal CO2 in a patient with acute severe asthma who was previously hyperventilating is an ominous sign of impending respiratory failure, not reassurance of improvement.",
        "tension_pneumothorax": "EMERGENCY. Progressive one-sided chest pain and breathlessness with hypotension, tachycardia, tracheal deviation away from affected side, and absent breath sounds - requires IMMEDIATE needle decompression (do not wait for chest X-ray confirmation if clinically suspected in a deteriorating patient) followed by formal chest drain insertion.",
        "massive_haemoptysis": "Large-volume coughing up of blood (variably defined, but generally over 100-600mL in 24 hours or causing haemodynamic/respiratory compromise) - EMERGENCY with risk of asphyxiation from airway flooding as much as from blood loss itself. Causes in India particularly include TB (active or from bronchiectasis/aspergilloma in old TB cavities), bronchiectasis, and lung cancer. Management: position patient with the presumed bleeding side dependent/down (to protect the unaffected lung from blood aspiration) if the side is known, secure airway if compromised, urgent bronchoscopy and/or CT angiography to localise bleeding source, bronchial artery embolisation is often the definitive treatment of choice, surgery reserved for those failing embolisation or with specific anatomical lesions.",
        "acute_respiratory_distress_syndrome": "ARDS: acute, severe hypoxaemic respiratory failure with bilateral pulmonary infiltrates not fully explained by cardiac failure/fluid overload, following a precipitating insult (severe pneumonia, sepsis, aspiration, trauma, severe COVID-19). Requires intensive care management, lung-protective ventilation strategy (low tidal volume ventilation - a cornerstone evidence-based intervention shown to improve survival), prone positioning for moderate-severe cases (also evidence-based mortality benefit), and treatment of the underlying precipitating cause. High mortality condition requiring specialist critical care management.",
        "pulmonary_embolism_massive": "Massive/high-risk pulmonary embolism causing haemodynamic instability (hypotension, shock) - EMERGENCY requiring thrombolysis or catheter-directed/surgical embolectomy depending on centre capability and contraindications, in contrast to stable PE managed with anticoagulation alone. Sudden breathlessness, pleuritic chest pain, and collapse, particularly with risk factors (immobility, recent surgery, malignancy, prior VTE), should prompt urgent assessment.",
    },
    "india_pulmonology": {
        "name": "Pulmonology in India",
        "air_pollution_burden": "India experiences among the highest ambient and household air pollution levels globally, a major contributor to the substantial national burden of COPD, asthma exacerbations, and respiratory infections. Household air pollution from biomass/solid fuel cooking disproportionately affects women and children in many rural and lower-income urban households. Government initiatives (such as clean cooking fuel access programmes) aim to reduce household air pollution exposure, alongside ongoing efforts to address ambient air quality in heavily polluted urban centres, though air pollution remains a very significant modifiable driver of the national respiratory disease burden.",
        "tb_elimination_programme": "The National TB Elimination Programme (NTEP) coordinates India's TB control strategy, providing free diagnosis (including rapid molecular testing) and treatment nationwide, alongside active case-finding initiatives, nutritional support schemes for TB patients (Ni-kshay Poshan Yojana), and digital adherence support tools. India has set an ambitious national target for TB elimination ahead of the global WHO End TB Strategy timeline, though the scale of the underlying burden, drug-resistant TB, and diagnostic/treatment gaps in reaching all affected individuals (including in the private healthcare sector, which manages a substantial proportion of TB cases requiring notification integration) remain significant ongoing challenges.",
        "occupational_lung_disease": "Silicosis and other pneumoconioses remain significant occupational health concerns in India's mining, quarrying, stone-cutting, and construction sectors, often affecting workers in informal employment settings with limited occupational health monitoring or compensation access. Strengthening occupational health surveillance and dust control measures remains an important public health priority, particularly given the irreversible nature of established pneumoconiosis and its recognised interaction with increased TB risk.",
        "healthcare_access": "Significant tertiary pulmonology and critical care capacity exists in major Indian cities (AIIMS, other government medical colleges, private centres) offering advanced bronchoscopic techniques, ILD/lung cancer multidisciplinary care, and lung transplantation in select centres. Rural-urban disparity in access to spirometry, HRCT, and specialist pulmonology consultation remains a substantial challenge, contributing to diagnostic delay for conditions like ILD and lung cancer. PM-JAY (Ayushman Bharat) provides insurance coverage for eligible families for major respiratory procedures and hospitalisations.",
    },
}

def save_knowledge():
    with open(DATA_DIR / "pulmo_knowledge.json", "w", encoding="utf-8") as f:
        json.dump(KNOWLEDGE, f, indent=2, ensure_ascii=False)

def load_sessions():
    sf = DATA_DIR / "sessions.json"
    if sf.exists():
        with open(sf) as f: return json.load(f)
    return {}

def save_session(sid, data):
    sessions = load_sessions()
    sessions[sid] = {**data, "updated": datetime.datetime.now().isoformat()}
    with open(DATA_DIR / "sessions.json", "w") as f: json.dump(sessions, f, indent=2)

def is_online():
    if not REQUESTS_OK: return False
    try: req_lib.get("https://8.8.8.8", timeout=3); return True
    except: return False

def extract_pdf_text(filepath):
    if not FITZ_OK: return "[PDF extraction unavailable]"
    try:
        doc = fitz.open(str(filepath))
        text = "".join(page.get_text() for page in doc)
        doc.close(); return text[:8000]
    except Exception:
        # SOFTWARESAFETY: never leak internal exception/stack trace details to caller
        return "[PDF extraction error]"

DEFAULT_SYSTEM = (
    "You are PulmoCare AI, an expert pulmonology (chest medicine) health research "
    "assistant. Help patients understand asthma, COPD, tuberculosis, and other lung "
    "conditions from published literature. "
    "ALWAYS start with a brief AI research disclaimer. "
    "Reference GOLD, GINA, ATS/ERS, WHO, NICE, NTEP (National TB Elimination "
    "Programme India) guidelines. ALWAYS end reminding them to consult a qualified "
    "pulmonologist. For pulmonary emergencies (severe breathlessness, silent chest, "
    "massive haemoptysis, tension pneumothorax, sudden chest pain with breathlessness): "
    "advise immediate 112/999/911 or A&E attendance. For Indian patients: reference "
    "NTEP guidance, note air pollution/biomass smoke COPD risk, TB burden context, "
    "and PM-JAY where relevant."
)

def call_ai(prompt, system_prompt=None, max_tokens=2500, provider=None, api_key=None):
    if not AI_PROVIDERS_OK: return None, "ai_providers_missing"
    provider = validate_provider(provider)
    effective_key = (sanitise_api_key(api_key) or
                     DEFAULT_PROVIDER_KEYS.get(provider, "") or
                     (API_KEY if provider == "anthropic" else ""))
    if not effective_key or not REQUESTS_OK or not is_online():
        return None, "offline_or_no_key"
    text, mode = ai_providers.call_ai(
        provider, effective_key, prompt, system_prompt or DEFAULT_SYSTEM, max_tokens
    )
    if text is None:
        log.error(f"{provider} API error: {mode}")
        return None, mode
    return text, "live_ai"

def build_offline_response(topic, patient_info=None):
    topic_l = topic.lower()
    kb_key = next(
        (k for k in KNOWLEDGE
         if k.replace("_", " ") in topic_l or topic_l in k.replace("_", " ")
         or any(w in topic_l for w in k.split("_"))),
        None
    )
    lines = [
        "# PulmoCare AI Research Report",
        f"**Topic:** {topic}",
        "**Mode:** Offline Research (Embedded Pulmonology Knowledge Base)",
        "",
        "> DISCLAIMER: AI-generated educational information. NOT medical advice. "
        "ALWAYS consult a qualified pulmonologist. "
        "PULMONARY EMERGENCY: Call 112 (India) / 999 (UK) / 911 (US).",
        "", "---", ""
    ]
    if kb_key:
        kb = KNOWLEDGE[kb_key]
        lines.append(f"## {kb.get('name', topic)}\n")
        for field, value in kb.items():
            if field == "name": continue
            if isinstance(value, str):
                lines += [f"**{field.replace('_', ' ').title()}:** {value}", ""]
    else:
        lines += [f"## Research Overview: {topic}", "",
                  f"Enable live AI in Settings for detailed research on {topic}.", ""]
    lines += [
        "---",
        "## India Pulmonology Resources",
        "- NTEP: National TB Elimination Programme (tbcindia.gov.in)",
        "- AIIMS Pulmonology: aiims.edu",
        "- Ni-kshay Poshan Yojana: nutritional support for TB patients",
        "- PM-JAY: respiratory procedure insurance coverage",
        "- Emergency: 112",
        "",
        f"WARNING - {DISCLAIMER}"
    ]
    return "\n".join(lines)

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC_DIR), filename)

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": VERSION,
                    "online": is_online(), "pdf_extract": FITZ_OK,
                    "timestamp": datetime.datetime.now().isoformat()})

@app.route("/api/upload", methods=["POST"])
def upload():
    if "files" not in request.files: return jsonify({"error": "No files"}), 400
    session_id = request.form.get("session_id") or str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id; session_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for f in request.files.getlist("files"):
        if not f.filename: continue
        ext = Path(f.filename).suffix.lower()
        # SOFTWARESAFETY: never trust client filename — generate opaque server-side name
        safe = f"{uuid.uuid4().hex}{ext}"; dest = session_dir / safe; f.save(str(dest))
        extracted = extract_pdf_text(dest) if ext == ".pdf" else ""
        results.append({"original": f.filename, "saved": safe,
                        "type": "pdf" if ext == ".pdf" else ("image" if ext in [".jpg",".jpeg",".png"] else "text"),
                        "size_kb": round(dest.stat().st_size/1024, 1), "has_content": bool(extracted)})
    existing = load_sessions().get(session_id, {})
    save_session(session_id, {"session_id": session_id, "files": existing.get("files",[]) + results})
    return jsonify({"success": True, "session_id": session_id,
                    "uploaded": len(results), "files": results, "disclaimer": DISCLAIMER})

@app.route("/api/analyse", methods=["POST"])
def analyse():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    topic = sanitise_text_field(data.get("topic", "General Pulmonology"), 200)
    condition = sanitise_text_field(data.get("condition", ""), 200)
    patient_info = data.get("patient_info", {}) if isinstance(data.get("patient_info"), dict) else {}
    provider = validate_provider(data.get("provider", "anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    prompt = (
        f"Pulmonology Research Request: {topic} / {condition}\n"
        f"Patient: Age {sanitise_text_field(str(patient_info.get('age','NR')),10)}, "
        f"Symptoms: {sanitise_text_field(str(patient_info.get('symptoms','NR')),300)}, "
        f"Duration: {sanitise_text_field(str(patient_info.get('duration','NR')),100)}, "
        f"Smoking/exposure history: {sanitise_text_field(str(patient_info.get('exposure','NR')),200)}\n"
        f"Medications/History: {sanitise_text_field(str(patient_info.get('history','none')),300)}\n"
        "Cover: clinical overview, differential diagnosis, investigations, "
        "evidence-based treatment options, red flags/warning signs, "
        "India-specific context (NTEP, air pollution/TB), "
        "questions to ask the pulmonologist. Reference GOLD, GINA, ATS/ERS, NICE, NTEP."
    )
    result, mode = (call_ai(prompt, provider=provider, api_key=effective_key)
                    if (effective_key and is_online()) else (None,"offline"))
    if not result: result = build_offline_response(topic, patient_info); mode = "offline"
    return jsonify({"success": True, "mode": mode, "analysis": result,
                    "topic": topic, "disclaimer": DISCLAIMER,
                    "timestamp": datetime.datetime.now().isoformat()})

@app.route("/api/condition/<condition_name>")
def condition_detail(condition_name):
    cn = sanitise_text_field(condition_name, 100).lower().replace("-","_").replace(" ","_")
    if cn in KNOWLEDGE:
        return jsonify({"success": True, "mode": "offline_kb",
                        "condition": KNOWLEDGE[cn], "disclaimer": DISCLAIMER})
    provider = validate_provider(request.args.get("provider","anthropic"))
    effective_key = (sanitise_api_key(request.args.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    safe_name = sanitise_text_field(condition_name, 100)
    prompt = (f"Comprehensive pulmonology research on {safe_name}: "
              "definition, prevalence, pathophysiology, clinical features, diagnosis, "
              "evidence-based management, prognosis. Reference GOLD, GINA, ATS/ERS, NICE, NTEP.")
    result, mode = call_ai(prompt, provider=provider, api_key=effective_key)
    if not result: result = build_offline_response(safe_name); mode = "offline"
    return jsonify({"success": True, "mode": mode, "content": result, "disclaimer": DISCLAIMER})

@app.route("/api/pulmo/assess", methods=["POST"])
def assess_pulmo():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    symptom = sanitise_text_field(data.get("symptom",""), 300)
    duration = sanitise_text_field(data.get("duration",""), 100)
    age = sanitise_text_field(str(data.get("age","")), 10)
    exposure = sanitise_text_field(data.get("exposure",""), 200)
    history = sanitise_text_field(data.get("history",""), 300)
    provider = validate_provider(data.get("provider","anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    if not symptom:
        return jsonify({"error": "Symptom field is required"}), 400
    prompt = (
        f"Pulmonology Assessment Research:\n"
        f"Chief Symptom: {symptom}\nDuration: {duration}\n"
        f"Age: {age}\nSmoking/Exposure History: {exposure}\nHistory: {history}\n"
        "Provide: possible causes (most likely to least likely), "
        "urgency of assessment needed, red flags requiring emergency care, "
        "what the pulmonologist will likely do, questions to ask. "
        "This is educational research — must consult pulmonologist for actual diagnosis."
    )
    result, mode = call_ai(prompt, provider=provider, api_key=effective_key)
    if not result:
        result = (f"Pulmonology assessment research for: {symptom}. "
                  "Enable live AI in Settings for personalised research. "
                  "For any concerning respiratory symptom, see your pulmonologist promptly. "
                  "For emergencies (severe breathlessness, blue lips, massive haemoptysis): "
                  "112/999/911.")
        mode = "offline"
    return jsonify({"success": True, "mode": mode, "content": result, "disclaimer": DISCLAIMER})

@app.route("/api/chat/send", methods=["POST"])
def chat_send():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    message = sanitise_text_field(data.get("message",""), 1000)
    if not message: return jsonify({"error": "Empty message"}), 400
    provider = validate_provider(data.get("provider","anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    result = None
    if data.get("request_ai") and is_online() and effective_key:
        result, _ = call_ai(
            f"Pulmonology patient question: '{message}'. "
            "3-4 paragraphs, compassionate and evidence-based. "
            "Include India-specific guidance where relevant. "
            "End with pulmonologist consultation reminder. "
            "For emergencies (severe breathlessness, silent chest, massive haemoptysis, "
            "tension pneumothorax): 112/999/911 immediately.",
            max_tokens=800, provider=provider, api_key=effective_key)
    return jsonify({"success": True, "ai_response": result,
                    "disclaimer": "Not medical advice. Consult your pulmonologist."})

@app.route("/api/report/generate", methods=["POST"])
def generate_report():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    topic = sanitise_text_field(data.get("topic","General Pulmonology"), 200)
    patient = data.get("patient_info", {}) if isinstance(data.get("patient_info"), dict) else {}
    provider = validate_provider(data.get("provider","anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    content = build_offline_response(topic, patient)
    if effective_key and is_online():
        ai_content, _ = call_ai(
            f"Generate comprehensive pulmonology research report for: {topic}. "
            f"Patient: {patient}. Cover diagnosis, treatment options, follow-up, prevention.",
            max_tokens=3500, provider=provider, api_key=effective_key)
        if ai_content: content = ai_content
    # SOFTWARESAFETY: opaque, non-sequential identifier — not a predictable/enumerable integer ID
    report_id = f"report_{uuid.uuid4().hex}"
    report = {"report_id": report_id, "generated": datetime.datetime.now().isoformat(),
              "topic": topic, "patient": patient, "content": content, "disclaimer": DISCLAIMER}
    with open(REPORTS_DIR / f"{report_id}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return jsonify(report)

@app.route("/api/resolve", methods=["POST"])
def resolve_multi_ai():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    prompt = sanitise_text_field(data.get("prompt",""), 4000)
    if not prompt: return jsonify({"error": "No prompt provided"}), 400
    pairs_raw = data.get("providers",[])
    if not isinstance(pairs_raw, list) or len(pairs_raw) < 1:
        return jsonify({"error": "No providers specified"}), 400
    if not AI_PROVIDERS_OK: return jsonify({"error": "ai_providers module not available"}), 500
    pairs = []
    for p in pairs_raw[:6]:
        if not isinstance(p, dict): continue
        pid = validate_provider(p.get("provider",""))
        key = sanitise_api_key(p.get("key",""))
        if pid and key: pairs.append((pid, key))
    if not pairs: return jsonify({"error": "No valid provider+key pairs"}), 400
    results = ai_providers.call_multi_ai(pairs, prompt, DEFAULT_SYSTEM, 1500)
    successes = [r for r in results if r.get("success") and r.get("text")]
    synthesis = None
    if len(successes) >= 2:
        synth_parts = [f"=== {r.get('label',r.get('provider','AI'))} ===\n{(r.get('text') or '')[:1200]}"
                       for r in successes]
        synth_prompt = (
            "You are a pulmonology research synthesis engine. Multiple AI systems "
            "answered the same question. Question: " + prompt + "\n\n" +
            "\n\n".join(synth_parts) + "\n\n"
            "Synthesise the best, most complete, evidence-based research answer. "
            "Note any disagreements. Lead with the most clinically important finding. "
            "Remind that this is research only — consult a qualified pulmonologist."
        )
        synth_key = next((k for pr,k in pairs if pr==successes[0]["provider"]), None)
        if synth_key:
            synth_text, _ = ai_providers.call_ai(
                successes[0]["provider"], synth_key, synth_prompt,
                "You are a pulmonology research synthesis assistant.", 2000)
            synthesis = synth_text
    return jsonify({"success": True, "responses": results,
                    "synthesis": synthesis, "disclaimer": DISCLAIMER})

@app.route("/api/providers")
def list_providers():
    if not AI_PROVIDERS_OK: return jsonify({"providers": [], "error": "ai_providers module not available"})
    return jsonify({"providers": [
        {"id":k,"label":v["label"],"default_model":v["default_model"],
         "key_prefix":v["key_prefix"],"get_key_url":v["get_key_url"],
         "server_default_configured":bool(DEFAULT_PROVIDER_KEYS.get(k))}
        for k,v in ai_providers.PROVIDERS.items()], "online": is_online()})

@app.route("/api/status")
def status():
    any_key = bool(API_KEY) or any(DEFAULT_PROVIDER_KEYS.values())
    return jsonify({"server":"running","version":VERSION,"online":is_online(),
                    "mode":"live_ai" if (any_key and is_online()) else "offline_research",
                    "capabilities":{"pdf":FITZ_OK,"images":PIL_OK,
                                    "live_ai":bool(any_key and is_online()),
                                    "offline":True,"multi_provider":AI_PROVIDERS_OK,
                                    "rate_limiting":True,"aes256_frontend":True,
                                    "ambiguity_resolver":True},
                    "knowledge_base":list(KNOWLEDGE.keys()),
                    "providers":list(ai_providers.PROVIDERS.keys()) if AI_PROVIDERS_OK else [],
                    "disclaimer":DISCLAIMER})

# SOFTWARESAFETY: opaque fault management — never leak stack traces or internals to client
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    err_ref = uuid.uuid4().hex[:12]
    log.error(f"[{err_ref}] Internal server error: {e}")
    return jsonify({"error": "Internal server error", "reference": err_ref}), 500

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    save_knowledge()
    log.info("="*60)
    log.info(f"  PulmoCare AI Server v{VERSION} - Port {args.port}")
    log.info(f"  Online: {is_online()}")
    log.info(f"  URL: http://localhost:{args.port}")
    log.info(f"  Providers: {list(ai_providers.PROVIDERS.keys()) if AI_PROVIDERS_OK else 'N/A'}")
    log.info("="*60)
    app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True, use_reloader=False)
