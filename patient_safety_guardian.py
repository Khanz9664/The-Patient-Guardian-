#!/usr/bin/env python
# coding: utf-8

"""
Patient Safety Guardian backend module.

- Provides functions for:
  - Patient record access and updating
  - Drug interaction checks
  - Allergy checks
  - Risk assessment
  - Guideline checks
  - Patient education
  - Differential diagnosis
  - Safety intervention logging
  - Comprehensive medication safety check
  - Interactive safety agent chat

- Designed to be imported and used from a Streamlit app (or any other frontend).
- No hard-coded API keys. Use init_safety_guardian(api_key=...) or set GOOGLE_API_KEY env var.
"""

# ===================================================================
# SECTION 0: IMPORTANT LIBRARIES IMPORTS
# ===================================================================
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import re

# ===================================================================
# SECTION 1: CONFIGURATION & INITIALIZATION HELPERS
# ===================================================================

# Global model handles (initialized by init_safety_guardian)
main_agent = None
pharmacology_agent = None
allergy_agent = None
diagnostic_agent = None
agent_with_tools = None

# Directory to store per-patient JSON files
PATIENTS_DIR = "patients"
os.makedirs(PATIENTS_DIR, exist_ok=True)

# This will store the path to the currently active patient's JSON file
ACTIVE_PATIENT_FILE: Optional[str] = None


def make_json_serializable(obj):
    """
    Try several fallbacks to convert common SDK/protobuf objects into JSON-serializable
    Python primitives.
    """
    # 1) Try protobuf's MessageToDict (best for proto messages)
    try:
        from google.protobuf.json_format import MessageToDict
        return MessageToDict(obj)
    except Exception:
        pass

    # 2) If object has a to_dict() method
    try:
        if hasattr(obj, "to_dict"):
            return make_json_serializable(obj.to_dict())
    except Exception:
        pass

    # 3) Basic Python primitives
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [make_json_serializable(v) for v in obj]

    # 4) If object has __dict__ (dataclass / simple object)
    if hasattr(obj, "__dict__"):
        return make_json_serializable(vars(obj))

    # 5) Fallback to string
    return str(obj)


def init_safety_guardian(api_key: Optional[str] = None) -> None:
    """
    Initialize Google Generative AI models and tool-enabled agent.

    Call this once at application startup.

    Args:
        api_key: Optional explicit API key.
                 If not provided, reads GOOGLE_API_KEY from environment.

    Raises:
        RuntimeError if no API key is found or configuration fails.
    """
    global main_agent, pharmacology_agent, allergy_agent, diagnostic_agent, agent_with_tools

    # Resolve API key
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set.\n"
            "Set it as an environment variable, or pass api_key to init_safety_guardian()."
        )

    # Configure genai
    genai.configure(api_key=key)

    # Create model instances
    main_agent = genai.GenerativeModel("gemini-2.5-pro")
    pharmacology_agent = genai.GenerativeModel("gemini-2.5-pro")
    allergy_agent = genai.GenerativeModel("gemini-2.5-pro")
    diagnostic_agent = genai.GenerativeModel("gemini-2.5-pro")

    # Tool-enabled agent
    agent_with_tools = genai.GenerativeModel(
        "gemini-2.5-pro",
        tools=[
            get_patient_records,
            add_clinical_note,
            check_drug_interactions_ai,
            check_allergy_safety,
            assess_patient_risk,
            generate_differential_diagnosis,
            check_treatment_guidelines,
            generate_patient_education,
        ],
    )


def _ensure_initialized() -> None:
    """
    Ensure that the safety guardian models have been initialized.

    If not initialized, this will:
      - Use GOOGLE_API_KEY from environment.
      - Call init_safety_guardian().

    You can also explicitly call init_safety_guardian(api_key=...) in your app
    before using any functions to control which key is used.
    """
    global main_agent, pharmacology_agent, allergy_agent, diagnostic_agent, agent_with_tools

    if (
        main_agent is None
        or pharmacology_agent is None
        or allergy_agent is None
        or diagnostic_agent is None
        or agent_with_tools is None
    ):
        init_safety_guardian()


# ==================================================================
# SECTION 2: ENHANCED PATIENT DATABASE WITH MORE FIELDS
# ==================================================================

patient_database = {
    "patient_id": "P-90210",
    "name": "Robert Smith",
    "age": 65,
    "weight_kg": 82,
    "height_cm": 175,
    "medical_conditions": [
        "Atrial Fibrillation",
        "Hypertension",
        "Type 2 Diabetes",
    ],
    "current_medications": [
        {
            "name": "Warfarin",
            "dosage": "5mg",
            "frequency": "Once daily",
            "purpose": "Anticoagulation for AFib",
            "start_date": "2023-06-15",
        },
        {
            "name": "Lisinopril",
            "dosage": "10mg",
            "frequency": "Once daily",
            "purpose": "Blood pressure control",
            "start_date": "2022-03-20",
        },
        {
            "name": "Metformin",
            "dosage": "500mg",
            "frequency": "Twice daily",
            "purpose": "Blood sugar control",
            "start_date": "2021-11-10",
        },
    ],
    "allergies": [
        {"allergen": "Penicillin", "reaction": "Rash and swelling"},
    ],
    "recent_labs": {
        "date": "2024-10-15",
        "INR": 2.3,
        "creatinine": 1.1,
        "HbA1c": 6.8,
    },
    "vital_signs": {
        "blood_pressure": "138/82",
        "heart_rate": 72,
        "temperature": 36.8,
    },
    "clinical_notes": [
        {
            "date": "2024-10-15",
            "note": "Patient reports good medication compliance. No bleeding episodes. INR therapeutic.",
        }
    ],
    "last_visit": "2024-10-15",
}

# Save default patient into patients/ directory and make it the active patient
default_patient_file = os.path.join(PATIENTS_DIR, f"{patient_database['patient_id']}.json")
with open(default_patient_file, "w") as f:
    json.dump(patient_database, f, indent=4)

ACTIVE_PATIENT_FILE = default_patient_file


# ===================================================================
# SECTION 3: CORE MEMORY FUNCTIONS (MULTI-PATIENT)
# ===================================================================

def get_patient_records() -> Dict:
    """
    Retrieves the current active patient's complete medical records.
    """
    global ACTIVE_PATIENT_FILE

    if ACTIVE_PATIENT_FILE is None:
        return {"error": "No active patient is selected."}

    try:
        with open(ACTIVE_PATIENT_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": f"Active patient file not found: {ACTIVE_PATIENT_FILE}"}
    except Exception as e:
        return {"error": f"Error reading patient records: {e}"}


def list_patients() -> List[Dict]:
    """
    List all available patients from the patients/ directory.

    Returns:
        List of dicts with keys: id, name, file
    """
    patients: List[Dict] = []

    if not os.path.isdir(PATIENTS_DIR):
        return patients

    for fname in os.listdir(PATIENTS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(PATIENTS_DIR, fname)
        try:
            with open(path, "r") as f:
                data = json.load(f)
            patients.append(
                {
                    "id": data.get("patient_id", os.path.splitext(fname)[0]),
                    "name": data.get("name", "Unknown"),
                    "file": path,
                }
            )
        except Exception:
            # Skip malformed files
            continue

    return patients


def set_active_patient(patient_id: str) -> str:
    """
    Set which patient is 'active' for all safety checks.

    Args:
        patient_id: The patient's ID (must match filename <id>.json)

    Returns:
        The full path to the active patient file.

    Raises:
        FileNotFoundError if patient file does not exist.
    """
    global ACTIVE_PATIENT_FILE

    candidate = os.path.join(PATIENTS_DIR, f"{patient_id}.json")
    if not os.path.exists(candidate):
        raise FileNotFoundError(f"No patient file found for ID {patient_id}: {candidate}")

    ACTIVE_PATIENT_FILE = candidate
    return ACTIVE_PATIENT_FILE


def add_clinical_note(note: str) -> str:
    """
    Adds a new clinical note to the active patient record with timestamp.
    Args:
        note: The clinical observation or note to add
    Returns: Confirmation message
    """
    global ACTIVE_PATIENT_FILE

    if ACTIVE_PATIENT_FILE is None:
        return "Error adding note: no active patient is selected."

    try:
        records = get_patient_records()
        if "clinical_notes" not in records:
            records["clinical_notes"] = []

        new_note = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": note,
        }

        records["clinical_notes"].append(new_note)

        with open(ACTIVE_PATIENT_FILE, "w") as f:
            json.dump(records, f, indent=4)

        return f"Clinical note added successfully at {new_note['date']}"
    except Exception as e:
        return f"Error adding note: {str(e)}"


# ===================================================================
# SECTION 5: ENHANCED DRUG INTERACTION CHECKER
# ===================================================================

def check_drug_interactions_ai(new_medication: str) -> str:
    """
    Uses Gemini AI to comprehensively check drug interactions.

    Args:
        new_medication: The drug being considered

    Returns:
        Detailed interaction analysis text
    """
    _ensure_initialized()

    patient_data = get_patient_records()
    if "error" in patient_data:
        return f"Error retrieving patient records: {patient_data['error']}"

    current_meds = [med["name"] for med in patient_data.get("current_medications", [])]
    conditions = patient_data.get("medical_conditions", [])

    prompt = f"""
    MEDICATION SAFETY ANALYSIS

    NEW MEDICATION: {new_medication}

    CURRENT MEDICATIONS: {', '.join(current_meds)}

    MEDICAL CONDITIONS: {', '.join(conditions)}

    PATIENT AGE: {patient_data.get('age', 'Unknown')} years

    RECENT LABS: INR={patient_data.get('recent_labs', {}).get('INR', 'N/A')},
                 Creatinine={patient_data.get('recent_labs', {}).get('creatinine', 'N/A')}

    Perform a comprehensive analysis:

    1. INTERACTION SEVERITY: Rate as CRITICAL/HIGH/MODERATE/LOW/NONE

    2. SPECIFIC INTERACTIONS: List each interaction with:
       - Drug pair involved
       - Mechanism of interaction
       - Clinical consequence

    3. CONTRAINDICATIONS: Based on patient conditions

    4. RECOMMENDATIONS:
       - Proceed/Do not proceed
       - Dose adjustments if needed
       - Monitoring parameters
       - Timing considerations

    5. ALTERNATIVES: If unsafe, suggest safer alternatives

    Format your response clearly with headers.
    """

    try:
        response = pharmacology_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error in drug interaction check: {str(e)}"


# ===================================================================
# SECTION 6: ALLERGY CROSS-REACTIVITY CHECKER
# ===================================================================

def check_allergy_safety(new_medication: str) -> str:
    """
    Checks for direct allergies and cross-reactivity patterns.

    Args:
        new_medication: Drug being considered

    Returns:
        Allergy risk assessment text
    """
    _ensure_initialized()

    patient_data = get_patient_records()
    if "error" in patient_data:
        return f"Error retrieving patient records: {patient_data['error']}"

    patient_allergies = patient_data.get("allergies", [])
    allergy_list = [a["allergen"] for a in patient_allergies]

    prompt = f"""
    ALLERGY SAFETY SCREENING

    NEW MEDICATION: {new_medication}

    KNOWN ALLERGIES: {', '.join(allergy_list) if allergy_list else 'None recorded'}

    Analyze:
    1. Is there a DIRECT match?
    2. Is there CROSS-REACTIVITY risk? (e.g., Penicillin → Cephalosporins)
    3. What is the RISK LEVEL: CONTRAINDICATED/HIGH/MODERATE/LOW/SAFE
    4. If risk exists, explain the mechanism
    5. Suggest alternatives if contraindicated

    Be specific about drug classes and chemical structures.
    """

    try:
        response = allergy_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error in allergy check: {str(e)}"


# ===================================================================
# SECTION 7: NATURAL LANGUAGE ORDER PARSER
# ===================================================================

def parse_medical_order(natural_language_order: str) -> Dict:
    """
    Converts natural language medical orders into structured data.
    Example: "Start Robert on 81mg aspirin daily for cardiac protection"
    Returns: Structured medication order as dict or an error dict.
    """
    _ensure_initialized()

    prompt = f"""
Parse this medical order into structured JSON format:

ORDER: "{natural_language_order}"

Extract and return ONLY valid JSON (no markdown, no explanation):
{{
  "patient_name": "name if mentioned or null",
  "medication": "drug name",
  "dosage": "amount with unit",
  "frequency": "how often",
  "route": "oral/IV/etc or null",
  "indication": "reason/purpose",
  "duration": "how long or null"
}}

If information is missing, use null. Do not include any additional keys.
Return only JSON.
"""

    try:
        response = main_agent.generate_content(prompt)
        text = getattr(response, "text", None)
        if text is None:
            return {
                "error": "Could not parse order: AI model returned no text.",
                "raw_response": str(response),
            }

        # Remove markdown code fences if present
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

        # Try to parse JSON directly
        try:
            parsed = json.loads(text)
            return parsed
        except Exception:
            # Sometimes model returns extra commentary; extract first {...} block
            m = re.search(r"(\{[\s\S]*?\})", text)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception as e:
                    return {"error": f"Could not parse JSON block: {e}", "raw": text}
            return {"error": "Could not parse order: invalid JSON", "raw": text}
    except Exception as e:
        return {"error": f"Could not parse order: {e}"}


# ===================================================================
# SECTION 8: RISK ASSESSMENT ENGINE
# ===================================================================

def assess_patient_risk(proposed_treatment: str) -> str:
    """
    Predicts potential complications and risk factors.

    Args:
        proposed_treatment: Treatment plan being considered

    Returns:
        Comprehensive risk assessment text
    """
    _ensure_initialized()

    patient_data = get_patient_records()
    if "error" in patient_data:
        return f"Error retrieving patient records: {patient_data['error']}"

    prompt = f"""
    PATIENT RISK ASSESSMENT

    PATIENT PROFILE:
    {json.dumps(patient_data, indent=2)}

    PROPOSED TREATMENT: {proposed_treatment}

    Provide a comprehensive risk analysis:

    1. TOP 5 RISK FACTORS (ranked by severity)

    2. PROBABILITY OF ADVERSE EVENTS
       - Minor complications: ___%
       - Major complications: ___%
       - Life-threatening events: ___%

    3. EARLY WARNING SIGNS to monitor:
       - List specific symptoms
       - When to seek immediate care

    4. PREVENTIVE MEASURES:
       - What to do before starting
       - Ongoing monitoring plan
       - Patient education points

    5. CONTRAINDICATIONS:
       - Absolute contraindications
       - Relative contraindications

    6. RISK-BENEFIT ANALYSIS:
       - Benefits of treatment
       - Risks of treatment
       - Risks of NOT treating
       - Overall recommendation

    Be specific and evidence-based.
    """

    try:
        response = main_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error in risk assessment: {str(e)}"


# ===================================================================
# SECTION 9: DIFFERENTIAL DIAGNOSIS GENERATOR
# ===================================================================

def generate_differential_diagnosis(symptoms: str) -> str:
    """
    Generates differential diagnosis based on presentation.

    Args:
        symptoms: Chief complaint and symptoms

    Returns:
        Ranked differential diagnosis with recommendations text
    """
    _ensure_initialized()

    patient_history = get_patient_records()
    if "error" in patient_history:
        return f"Error retrieving patient records: {patient_history['error']}"

    prompt = f"""
    DIFFERENTIAL DIAGNOSIS ANALYSIS

    CHIEF COMPLAINT: {symptoms}

    PATIENT HISTORY:
    - Age: {patient_history.get('age')}
    - Medical Conditions: {', '.join(patient_history.get('medical_conditions', []))}
    - Current Medications: {', '.join([m['name'] for m in patient_history.get('current_medications', [])])}

    Provide:

    1. DIFFERENTIAL DIAGNOSES (ranked by likelihood):
       a) Most likely diagnosis (with % probability)
       b) Second most likely
       c) Third most likely
       d) Other considerations

    2. MUST-NOT-MISS DIAGNOSES:
       - Life-threatening conditions to rule out
       - Time-sensitive diagnoses

    3. RECOMMENDED DIAGNOSTIC WORKUP:
       - Initial tests (labs, imaging)
       - Physical examination findings to check
       - Specialist referrals if needed

    4. RED FLAGS requiring immediate attention

    5. INITIAL MANAGEMENT while awaiting workup

    Think like a clinician. Consider both common and dangerous causes.
    """

    try:
        response = diagnostic_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error generating differential: {str(e)}"


# ===================================================================
# SECTION 10: CLINICAL GUIDELINES CHECKER
# ===================================================================

def check_treatment_guidelines(condition: str, proposed_treatment: str) -> str:
    """
    Verifies treatment aligns with evidence-based clinical guidelines.

    Args:
        condition: Medical condition being treated
        proposed_treatment: Treatment plan

    Returns:
        Guidelines comparison and recommendations text
    """
    _ensure_initialized()

    prompt = f"""
    CLINICAL GUIDELINES REVIEW

    CONDITION: {condition}
    PROPOSED TREATMENT: {proposed_treatment}

    Analyze against standard clinical guidelines (AHA/ACC/WHO/ADA/etc):

    1. GUIDELINE ALIGNMENT:
       - Is this first-line therapy? Yes/No
       - Guideline recommendation class (I, IIA, IIB, III)
       - Evidence level (A, B, C)

    2. STANDARD OF CARE:
       - What do current guidelines recommend?
       - Any recent guideline updates?

    3. CONTRAINDICATIONS per guidelines

    4. MONITORING REQUIREMENTS per protocol

    5. ALTERNATIVE APPROACHES:
       - Other guideline-recommended options
       - When to consider alternatives

    6. QUALITY METRICS:
       - Relevant quality indicators
       - Documentation requirements

    Cite specific guidelines when possible.
    """

    try:
        response = main_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error checking guidelines: {str(e)}"


# ===================================================================
# SECTION 11: PATIENT EDUCATION GENERATOR
# ===================================================================

def generate_patient_education(medication: str, reading_level: str = "8th grade") -> str:
    """
    Creates patient-friendly medication information.

    Args:
        medication: Drug name
        reading_level: Target reading level

    Returns:
        Patient education material text
    """
    _ensure_initialized()

    prompt = f"""
    Create patient education material about {medication}.

    TARGET READING LEVEL: {reading_level}

    Include these sections in simple language:

    1. WHAT IS THIS MEDICINE?
       - What it does in simple terms
       - Why your doctor prescribed it

    2. HOW TO TAKE IT:
       - When to take it
       - With or without food
       - What to do if you miss a dose

    3. WHAT TO EXPECT:
       - When it starts working
       - How you'll know it's working

    4. POSSIBLE SIDE EFFECTS:
       - Common (not worrying)
       - Serious (call doctor)
       - Emergency (call 911)

    5. IMPORTANT WARNINGS:
       - What NOT to do
       - Foods/drinks to avoid
       - Other medicines that don't mix

    6. WHEN TO CALL YOUR DOCTOR

    7. STORAGE AND HANDLING

    Use:
    - Short sentences (max 15 words)
    - Bullet points
    - No medical jargon
    - Action-oriented language
    - Positive tone

    Make it something a patient would actually read and understand.
    """

    try:
        response = main_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error generating education material: {str(e)}"


# ===================================================================
# SECTION 12: SAFETY INTERVENTION LOGGER
# ===================================================================

intervention_log: List[Dict] = []


def log_safety_intervention(intervention_type: str, details: Dict) -> str:
    """
    Logs all safety interventions for quality improvement.

    Args:
        intervention_type: Type of intervention (drug_interaction, allergy, etc)
        details: Details of the intervention

    Returns:
        Confirmation and analysis text
    """
    _ensure_initialized()

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": intervention_type,
        "details": details,
    }

    intervention_log.append(log_entry)

    prompt = f"""
    Analyze this safety intervention:

    TYPE: {intervention_type}
    DETAILS: {json.dumps(make_json_serializable(details), indent=2)}

    Provide:
    1. ERROR TYPE CATEGORY: (Prescribing/Dispensing/Administration/Monitoring)
    2. SEVERITY if not caught: (Near miss/Minor/Moderate/Major/Catastrophic)
    3. ROOT CAUSE: What led to this near-miss?
    4. PREVENTABILITY: Was this preventable? How?
    5. SYSTEM IMPROVEMENT: What process change could prevent this?

    Be constructive and focus on systems, not individuals.
    """

    try:
        response = main_agent.generate_content(prompt)
        analysis_text = getattr(response, "text", str(response))
        log_entry["analysis"] = analysis_text

        # Save to file
        with open("safety_interventions.json", "w") as f:
            json.dump(intervention_log, f, indent=4)

        return f"Intervention logged successfully. Analysis:\n\n{analysis_text}"
    except Exception as e:
        return f"Error logging intervention: {str(e)}"


# ===================================================================
# SECTION 13: COMPREHENSIVE MEDICATION SAFETY CHECK
# ===================================================================

def generate_final_recommendation(check_results: Dict) -> str:
    """
    Synthesizes all safety checks into a final recommendation text.
    """
    _ensure_initialized()

    prompt = f"""
    Based on these comprehensive safety checks, provide a FINAL RECOMMENDATION:

    DRUG INTERACTIONS:
    {check_results.get('drug_interactions', 'Not checked')}

    ALLERGY SAFETY:
    {check_results.get('allergy_safety', 'Not checked')}

    RISK ASSESSMENT:
    {check_results.get('risk_assessment', 'Not checked')}

    GUIDELINES:
    {check_results.get('guidelines', 'Not checked')}

    Provide a clear, actionable recommendation:

    1. DECISION: APPROVE / APPROVE WITH MODIFICATIONS / DO NOT APPROVE

    2. RATIONALE: (2-3 sentences)

    3. IF APPROVED:
       - Key monitoring parameters
       - Patient counseling points
       - Follow-up timeline

    4. IF NOT APPROVED:
       - Primary reason
       - Safer alternatives
       - What would need to change

    Be decisive but thorough.
    """

    try:
        response = main_agent.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Error generating recommendation: {str(e)}"


def comprehensive_medication_check(new_medication: str, dosage: Optional[str] = None) -> Dict:
    """
    Performs all safety checks in one comprehensive analysis.

    Args:
        new_medication: Medication to check
        dosage: Proposed dosage (optional)

    Returns:
        Dictionary containing the complete safety analysis with all checks.
    """
    _ensure_initialized()

    results: Dict = {
        "medication": new_medication,
        "dosage": dosage,
        "timestamp": datetime.now().isoformat(),
        "checks_performed": [],
    }

    patient_data = get_patient_records()
    if "error" in patient_data:
        results["error"] = "Could not retrieve patient records"
        return results

    # Step 1: Drug interactions
    interaction_check = check_drug_interactions_ai(new_medication)
    results["drug_interactions"] = interaction_check
    results["checks_performed"].append("Drug Interactions")

    # Step 2: Allergy safety
    allergy_check = check_allergy_safety(new_medication)
    results["allergy_safety"] = allergy_check
    results["checks_performed"].append("Allergy Safety")

    # Step 3: Risk assessment
    risk_assessment = assess_patient_risk(f"{new_medication} {dosage if dosage else ''}")
    results["risk_assessment"] = risk_assessment
    results["checks_performed"].append("Risk Assessment")

    # Step 4: Guidelines
    primary_condition = patient_data.get("medical_conditions", ["Unknown"])[0]
    guidelines_check = check_treatment_guidelines(primary_condition, new_medication)
    results["guidelines"] = guidelines_check
    results["checks_performed"].append("Guidelines Review")

    # Step 5: Final recommendation
    final_recommendation = generate_final_recommendation(results)
    results["final_recommendation"] = final_recommendation

    return results


# ===================================================================
# SECTION 14: INTERACTIVE AGENT SYSTEM
# ===================================================================

class DummyChat:
    """
    Fallback chat object used when the real model cannot be called
    (e.g., quota exceeded). It returns a friendly static message.
    """
    def __init__(self, error_msg: str):
        self.error_msg = error_msg

    def send_message(self, content):
        class R:
            pass

        r = R()
        r.text = (
            "The live Patient Safety Guardian backend (Gemini API) "
            "is currently unavailable.\n\n"
            f"Backend error:\n{self.error_msg}\n\n"
            "You’ve likely hit the current quota/limit for this API key. "
            "Once quota is available again, responses will work normally."
        )
        return r


def start_safety_agent():
    """
    Starts an interactive chat session with the safety agent.

    Returns:
        A chat session object (with send_message(...) method).
        If the backend quota is exhausted or initialization fails,
        returns a DummyChat instead so the app does not crash.
    """
    _ensure_initialized()

    try:
        chat = agent_with_tools.start_chat(enable_automatic_function_calling=True)

        # System prompt to prime the agent
        system_prompt = """
        You are the Patient Safety Guardian - a senior clinical safety agent.
        YOUR MISSION: To protect patients by checking orders, drug interactions, allergies,
        and offering safer alternatives. Always prioritize patient safety and evidence-based care.
        """
        chat.send_message(system_prompt)
        return chat

    except ResourceExhausted as e:
        # Specific quota error: return dummy chat
        print(f"[PatientSafetyGuardian] Quota exhausted: {e}")
        return DummyChat(str(e))

    except Exception as e:
        # Any other error: also fall back to dummy chat
        print(f"[PatientSafetyGuardian] Failed to start safety agent: {e}")
        return DummyChat(str(e))

