import os
import json
from datetime import datetime

import streamlit as st

from patient_safety_guardian import (
    init_safety_guardian,
    comprehensive_medication_check,
    get_patient_records,
    add_clinical_note,
    start_safety_agent,
    generate_patient_education,
    parse_medical_order,
    list_patients,
    set_active_patient,
)

# Configuration
PAGE_TITLE = "Patient Safety Guardian"
PAGE_ICON = "⚕"  # keep it clean & professional


# =========================
#   GLOBAL UI / THEME
# =========================

def apply_custom_ui():
    """Inject custom CSS for healthcare-themed UI with light/dark adaptability."""
    st.markdown(
        """
        <style>
        /* ---------- Fonts & Base ---------- */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        :root {
            --background-color: #f8fafc;
            --text-color: #111827;
            --accent-safe: #2bb673;
            --accent-warning: #f39c12;
            --accent-danger: #e74c3c;
            --accent-primary: #3a8dde;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --background-color: #020617;
                --text-color: #e5e7eb;
            }
        }

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        .stApp {
            background-color: var(--background-color) !important;
            color: var(--text-color) !important;
        }

        /* ---------- Typography ---------- */
        h1, h2, h3, h4 {
            font-weight: 700 !important;
            letter-spacing: 0.4px;
        }

        p, li, span, label {
            font-weight: 400;
        }

        /* ---------- Cards ---------- */
        .psg-card {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 16px;
            padding: 18px 20px;
            margin-bottom: 16px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(120, 120, 120, 0.18);
            animation: fadeIn 0.3s ease-in-out both;
        }

        @media (prefers-color-scheme: dark) {
            .psg-card {
                background: rgba(15, 23, 42, 0.9);
                border-color: rgba(148, 163, 184, 0.35);
            }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* ---------- Buttons ---------- */
        button[kind="primary"] {
            background: linear-gradient(135deg, #3a8dde, #2bb673) !important;
            color: white !important;
            border-radius: 999px !important;
            border: none !important;
            font-weight: 600 !important;
            padding: 0.45rem 1.1rem !important;
        }

        button[kind="primary"]:hover {
            filter: brightness(1.03);
            transform: translateY(-1px);
            transition: all 0.18s ease-in-out;
        }

        /* ---------- Inputs ---------- */
        input, textarea, select {
            border-radius: 10px !important;
            border: 1px solid rgba(150, 150, 150, 0.32) !important;
        }

        /* ---------- Sidebar ---------- */
        section[data-testid="stSidebar"] {
            background: linear-gradient(
                180deg,
                rgba(15, 118, 180, 0.08),
                rgba(16, 185, 129, 0.06)
            );
            border-right: 1px solid rgba(148, 163, 184, 0.4);
        }

        .psg-sidebar-header {
            text-align: center;
            padding: 10px 4px 16px 4px;
        }

        .psg-sidebar-header h2 {
            margin-bottom: 2px;
            font-size: 20px;
        }

        .psg-sidebar-header p {
            margin-top: 0;
            font-size: 12px;
            opacity: 0.8;
        }

        /* ---------- Status Badge ---------- */
        .psg-risk-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .psg-risk-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }

        /* ---------- Alert Boxes ---------- */
        .psg-status-box {
            border-radius: 10px;
            padding: 10px 12px;
            margin: 6px 0 4px 0;
            font-size: 13px;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def status_box(text: str, status: str = "safe"):
    """Colored alert-style box for feedback."""
    colors = {
        "safe": "#2bb673",
        "warning": "#f39c12",
        "danger": "#e74c3c",
        "info": "#3a8dde",
    }
    color = colors.get(status, "#3a8dde")
    st.markdown(
        f"""
        <div class="psg-status-box" style="
            background: {color}18;
            border-left: 6px solid {color};
        ">
            {text}
        </div>
        """,
        unsafe_allow_html=True,
    )


def derive_risk_level(results: dict) -> str:
    """
    Heuristic to infer risk level from the risk_assessment text.

    Returns one of: 'high', 'moderate', 'low', 'unknown'
    """
    text = (results.get("risk_assessment") or "").lower()

    if any(
        phrase in text
        for phrase in [
            "high risk",
            "contraindicated",
            "do not use",
            "severe",
            "life-threatening",
        ]
    ):
        return "high"
    if any(
        phrase in text
        for phrase in [
            "moderate",
            "use with caution",
            "monitor closely",
            "increased risk",
        ]
    ):
        return "moderate"
    if text.strip():
        return "low"
    return "unknown"


def render_risk_badge(level: str):
    """Render pill-shaped risk badge based on inferred level."""
    mapping = {
        "high": ("High Risk", "#e74c3c"),
        "moderate": ("Moderate Risk", "#f39c12"),
        "low": ("Low Risk", "#2bb673"),
        "unknown": ("Risk Unknown", "#6b7280"),
    }
    label, color = mapping.get(level, mapping["unknown"])
    st.markdown(
        f"""
        <div class="psg-risk-badge" style="background:{color}18; color:{color}">
            <span class="psg-risk-dot" style="background:{color};"></span>
            {label}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
#   BACKEND / SESSION
# =========================

def load_api_key():
    """
    Load API key from environment variable or Streamlit secrets.
    Returns None if no key is found.
    """
    key = os.getenv("GOOGLE_API_KEY")
    if key:
        return key

    try:
        return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        return None


def display_error_message():
    """Display API key error message with setup instructions."""
    st.error(
        "**API Key Not Found**\n\n"
        "Please configure your API key using one of the following methods:\n\n"
        "1. Set environment variable:\n"
        "   ```bash\n"
        "   export GOOGLE_API_KEY='your-api-key'\n"
        "   ```\n\n"
        "2. Create `.streamlit/secrets.toml` with:\n"
        "   ```toml\n"
        "   GOOGLE_API_KEY = \"your-api-key\"\n"
        "   ```"
    )


def initialize_backend(api_key):
    """Initialize the Patient Safety Guardian backend."""
    try:
        init_safety_guardian(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"**Initialization Error**\n\n{str(e)}")
        return False


def init_session_state():
    """Initialize session state variables."""
    if "chat" not in st.session_state:
        st.session_state.chat = start_safety_agent()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "agent_health" not in st.session_state:
        # Simple fake health metrics for the Agent Monitoring tab
        st.session_state.agent_health = {
            "total_checks": 0,
            "last_status": "All systems operational",
        }


# =========================
#   PATIENT UTILITIES
# =========================

def render_patient_snapshot(patient):
    """Render patient information in the sidebar inside a small card."""
    st.markdown("<div class='psg-card'>", unsafe_allow_html=True)

    st.markdown("**Active Patient**")
    st.markdown(f"**Name:** {patient.get('name', 'Unknown')}")
    st.markdown(f"**Age:** {patient.get('age', 'N/A')}")
    st.markdown(f"**Patient ID:** {patient.get('patient_id', 'N/A')}")

    st.markdown("---")
    st.markdown("**Medical Conditions:**")
    conditions = patient.get("medical_conditions", [])
    if conditions:
        for cond in conditions:
            st.markdown(f"- {cond}")
    else:
        st.write("None recorded")

    st.markdown("**Current Medications:**")
    medications = patient.get("current_medications", [])
    if medications:
        for med in medications:
            line = f"- {med.get('name')}, {med.get('dosage')} {med.get('frequency')}"
            st.markdown(line)
    else:
        st.write("None recorded")

    st.markdown("**Allergies:**")
    allergies = patient.get("allergies", [])
    if allergies:
        for allergy in allergies:
            st.markdown(f"- {allergy.get('allergen')} ({allergy.get('reaction')})")
    else:
        st.write("No allergies recorded")

    st.markdown("</div>", unsafe_allow_html=True)


def render_patient_selector():
    """Render patient selection dropdown."""
    patients = list_patients()
    if not patients:
        st.error("No patients found in the 'patients/' folder.")
        st.stop()

    label_to_patient = {f"{p['name']} ({p['id']})": p for p in patients}
    labels = list(label_to_patient.keys())

    stored_label = st.session_state.get("active_patient_label")
    default_index = labels.index(stored_label) if stored_label in labels else 0

    selected_label = st.selectbox(
        "Active Patient",
        labels,
        index=default_index,
    )
    selected_patient = label_to_patient[selected_label]

    if st.session_state.get("active_patient_id") != selected_patient["id"]:
        try:
            set_active_patient(selected_patient["id"])
            st.session_state["active_patient_id"] = selected_patient["id"]
            st.session_state["active_patient_label"] = selected_label
            st.rerun()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()

    return selected_patient


def render_clinical_notes_form():
    """Render form to add clinical notes."""
    st.markdown("<div class='psg-card'>", unsafe_allow_html=True)
    st.markdown("**Add Clinical Note**")
    note_text = st.text_area("New note", key="sidebar_note", height=80)

    if st.button("Save Note"):
        if not note_text.strip():
            st.warning("Please enter a note before saving.")
        else:
            msg = add_clinical_note(note_text.strip())
            st.success(msg)
    st.markdown("</div>", unsafe_allow_html=True)


def save_uploaded_patient(uploaded_file):
    """Save uploaded patient JSON file."""
    try:
        data = json.load(uploaded_file)
        pid = data.get("patient_id")

        if not pid:
            st.warning("Uploaded JSON must contain a 'patient_id' field.")
            return False

        name = data.get("name", "Unknown")
        os.makedirs("patients", exist_ok=True)
        path = os.path.join("patients", f"{pid}.json")

        with open(path, "w") as f:
            json.dump(data, f, indent=4)

        set_active_patient(pid)
        st.session_state["active_patient_id"] = pid
        st.session_state["active_patient_label"] = f"{name} ({pid})"
        st.success(f"Successfully saved patient: {name} ({pid})")
        return True
    except Exception as e:
        st.error(f"Error reading uploaded JSON: {str(e)}")
        return False


def create_new_patient(patient_data):
    """Create a new patient record."""
    try:
        os.makedirs("patients", exist_ok=True)
        pid = patient_data["patient_id"]
        path = os.path.join("patients", f"{pid}.json")

        with open(path, "w") as f:
            json.dump(patient_data, f, indent=4)

        set_active_patient(pid)
        st.session_state["active_patient_id"] = pid
        st.session_state["active_patient_label"] = f"{patient_data['name']} ({pid})"
        st.success(f"Patient {patient_data['name']} ({pid}) created successfully")
        return True
    except Exception as e:
        st.error(f"Error creating patient: {str(e)}")
        return False


def render_patient_upload_form():
    """Render patient upload and creation forms."""
    with st.expander("Add / Upload Patient", expanded=False):
        st.markdown("**Upload Patient JSON**")
        uploaded = st.file_uploader(
            "Upload a patient JSON file",
            type="json",
            key="patient_upload",
        )

        if st.button("Save Uploaded Patient"):
            if uploaded is None:
                st.warning("Please upload a JSON file first.")
            elif save_uploaded_patient(uploaded):
                st.rerun()

        st.markdown("---")
        st.markdown("**Create New Patient Record**")

        new_pid = st.text_input("Patient ID (unique)", key="new_patient_id")
        new_name = st.text_input("Full Name", key="new_patient_name")
        new_age = st.number_input("Age", min_value=0, max_value=120, value=50)
        new_weight = st.number_input("Weight (kg)", min_value=0.0, value=70.0)
        new_height = st.number_input("Height (cm)", min_value=0.0, value=170.0)

        conditions_text = st.text_area(
            "Medical Conditions (comma separated)",
            placeholder="Hypertension, Diabetes, Atrial Fibrillation",
        )

        medications_text = st.text_area(
            "Current Medications (comma separated, names only)",
            placeholder="Warfarin, Metformin",
        )

        allergies_text = st.text_area(
            "Allergies (comma separated, names only)",
            placeholder="Penicillin, Aspirin",
        )

        bp = st.text_input("Blood Pressure", placeholder="120/80")
        heart_rate = st.number_input("Heart Rate", min_value=0, value=72)
        temperature = st.number_input("Temperature (°C)", value=36.6)

        if st.button("Create Patient Record", type="primary"):
            if not new_pid.strip() or not new_name.strip():
                st.warning("Patient ID and Name are required.")
            else:
                patient_data = {
                    "patient_id": new_pid.strip(),
                    "name": new_name.strip(),
                    "age": int(new_age),
                    "weight_kg": float(new_weight),
                    "height_cm": float(new_height),
                    "medical_conditions": [
                        c.strip()
                        for c in conditions_text.split(",")
                        if c.strip()
                    ],
                    "current_medications": [
                        {
                            "name": m.strip(),
                            "dosage": "",
                            "frequency": "",
                            "purpose": "",
                            "start_date": "",
                        }
                        for m in medications_text.split(",")
                        if m.strip()
                    ],
                    "allergies": [
                        {"allergen": a.strip(), "reaction": ""}
                        for a in allergies_text.split(",")
                        if a.strip()
                    ],
                    "recent_labs": {},
                    "vital_signs": {
                        "blood_pressure": bp,
                        "heart_rate": heart_rate,
                        "temperature": temperature,
                    },
                    "clinical_notes": [],
                    "last_visit": datetime.now().strftime("%Y-%m-%d"),
                }

                if create_new_patient(patient_data):
                    st.rerun()


# =========================
#   MAIN TABS
# =========================

def render_medication_safety_tab():
    """Render medication safety check tab with risk indicator."""
    st.markdown(
        "<div class='psg-card'><h3>Comprehensive Medication Safety Check</h3>"
        "<p style='font-size:13px; opacity:0.8;'>Analyze interactions, allergies, "
        "and evidence-based guideline alignment before prescribing.</p>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        new_med = st.text_input(
            "Medication Name",
            placeholder="e.g., Aspirin",
            help="Name of the medication you are considering starting or adjusting.",
        )
        dosage = st.text_input(
            "Dosage / Schedule",
            placeholder="e.g., 81 mg once daily",
            help="Include dose, route, and frequency when possible.",
        )

    with col2:
        st.markdown("**Risk Indicator**")
        # Default unknown badge before any run
        render_risk_badge("unknown")
        status_box(
            "Run the safety check to infer an overall risk level based on the current patient context.",
            "info",
        )

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Run Safety Check", type="primary"):
        if not new_med.strip():
            st.warning("Please enter a medication name.")
        else:
            with st.spinner("Running comprehensive safety analysis..."):
                results = comprehensive_medication_check(
                    new_med.strip(), dosage or None
                )

            if "error" in results:
                st.error(results["error"])
            else:
                st.session_state.agent_health["total_checks"] += 1

                # Show risk badge based on heuristic
                risk_level = derive_risk_level(results)
                st.markdown("<div class='psg-card'>", unsafe_allow_html=True)
                st.markdown("#### Overall Risk Summary")
                render_risk_badge(risk_level)

                if risk_level == "high":
                    status_box(
                        "High-risk profile detected. Strongly consider alternative therapy "
                        "or specialist consultation before proceeding.",
                        "danger",
                    )
                elif risk_level == "moderate":
                    status_box(
                        "Moderate risk. Use with caution and ensure monitoring and follow-up.",
                        "warning",
                    )
                elif risk_level == "low":
                    status_box(
                        "No major contraindications detected based on available information.",
                        "safe",
                    )
                else:
                    status_box(
                        "Risk could not be fully determined from the available analysis.",
                        "info",
                    )

                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<div class='psg-card'>", unsafe_allow_html=True)
                st.markdown("#### Checks Performed")
                checks = results.get("checks_performed", [])
                if checks:
                    st.write(", ".join(checks))
                else:
                    st.write("No explicit checks list returned by the agent.")

                with st.expander("Drug Interaction Analysis", expanded=True):
                    st.markdown(
                        results.get("drug_interactions", "No data available")
                    )

                with st.expander("Allergy & Cross-Reactivity"):
                    st.markdown(results.get("allergy_safety", "No data available"))

                with st.expander("Risk Assessment"):
                    st.markdown(results.get("risk_assessment", "No data available"))

                with st.expander("Guideline Compliance"):
                    st.markdown(results.get("guidelines", "No data available"))

                with st.expander("Clinical Recommendation", expanded=True):
                    st.markdown(
                        results.get("final_recommendation", "No data available")
                    )

                st.markdown("</div>", unsafe_allow_html=True)


def render_chat_tab():
    """Render interactive chat tab in a clinical note style."""
    st.markdown(
        "<div class='psg-card'><h3>Interactive Clinical Decision Support</h3>"
        "<p style='font-size:13px; opacity:0.8;'>Ask clinical questions, "
        "discuss cases, or submit medication orders for structured analysis.</p>",
        unsafe_allow_html=True,
    )

    # Display chat history
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        else:
            with st.chat_message("assistant"):
                st.markdown(content)

    user_input = st.text_area(
        "Question or Order",
        placeholder="e.g., 'Start patient on 81 mg aspirin daily' or 'Is DOAC appropriate for this AF patient with CKD?'",
        height=100,
        key="chat_input",
    )

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        send = st.button("Send Message", type="primary")
    with col2:
        parse_order_btn = st.button("Parse Order")
    with col3:
        clear_chat = st.button("Clear Chat")

    if clear_chat:
        st.session_state.messages = []
        st.session_state.chat = start_safety_agent()
        status_box("Chat history cleared and agent reset.", "info")
        st.rerun()

    if send:
        if not user_input.strip():
            st.warning("Please type a message first.")
        else:
            st.session_state.messages.append(
                {"role": "user", "content": user_input.strip()}
            )

            with st.spinner("Processing your request..."):
                try:
                    response = st.session_state.chat.send_message(
                        user_input.strip()
                    )
                    reply_text = getattr(response, "text", str(response))
                except Exception as e:
                    reply_text = f"Error: {str(e)}"

            st.session_state.messages.append(
                {"role": "assistant", "content": reply_text}
            )
            st.session_state.agent_health["last_status"] = "Responded to clinical query"
            st.rerun()

    if parse_order_btn:
        if not user_input.strip():
            st.warning("Please enter an order to parse.")
        else:
            with st.spinner("Parsing medical order..."):
                parsed = parse_medical_order(user_input.strip())

            st.markdown("<div class='psg-card'>", unsafe_allow_html=True)
            st.markdown("**Structured Order Data:**")
            st.json(parsed)
            st.markdown("</div>", unsafe_allow_html=True)


def render_education_tab():
    """Render patient education tab."""
    st.markdown(
        "<div class='psg-card'><h3>Patient Education Material Generator</h3>"
        "<p style='font-size:13px; opacity:0.8;'>Generate clear, layperson-friendly "
        "information about medications for handouts or discharge summaries.</p>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        med_name = st.text_input(
            "Medication Name",
            placeholder="e.g., Warfarin",
        )
    with col2:
        reading_level = st.selectbox(
            "Reading Level",
            ["6th grade", "8th grade", "10th grade"],
            index=1,
        )

    if st.button("Generate Patient Education", type="primary"):
        if not med_name.strip():
            st.warning("Please enter a medication name.")
        else:
            with st.spinner("Generating patient education material..."):
                text = generate_patient_education(
                    med_name.strip(), reading_level
                )

            st.markdown("### Patient Education Leaflet")
            st.markdown(text)

            st.download_button(
                label="Download as Text",
                data=text,
                file_name=f"{med_name.strip()}_patient_education.txt",
                mime="text/plain",
            )


def render_agent_monitor_tab():
    """Simple Agent Monitoring Dashboard for judges / operators."""
    st.markdown(
        "<div class='psg-card'><h3>Agent Monitoring Dashboard</h3>"
        "<p style='font-size:13px; opacity:0.8;'>High-level view of the "
        "multi-agent safety system status and recent activity.</p>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="Total Safety Checks",
            value=st.session_state.agent_health.get("total_checks", 0),
        )
    with col2:
        st.metric(
            label="Active Session",
            value="Online",
            delta=None,
        )
    with col3:
        st.metric(
            label="Last Event",
            value=st.session_state.agent_health.get("last_status", "Idle"),
        )

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='psg-card'>", unsafe_allow_html=True)
    st.markdown("#### System Notes")
    st.markdown(
        "- Safety guardian initialized at app startup.\n"
        "- Each medication safety run increments the check counter.\n"
        "- Chat interactions update the 'Last Event' status.\n\n"
        "This dashboard is intentionally lightweight and explainable for clinical and "
        "governance stakeholders."
    )
    st.markdown("</div>", unsafe_allow_html=True)


# =========================
#   SIDEBAR & MAIN
# =========================

def render_sidebar():
    """Render sidebar with patient information and controls."""
    with st.sidebar:
        st.markdown(
            """
            <div class="psg-sidebar-header">
                <h2>Patient Safety Guardian</h2>
                <p>Multi-agent clinical safety net</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_patient_selector()

        patient = get_patient_records()
        if "error" in patient:
            st.error(patient["error"])
        else:
            render_patient_snapshot(patient)
            render_clinical_notes_form()

        render_patient_upload_form()


def main():
    """Main application entry point."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    apply_custom_ui()
    init_session_state()

    st.title("Patient Safety Guardian")
    st.markdown(
        "AI-powered clinical safety net for medication safety, allergy checks, "
        "and evidence-based guideline support."
    )

    api_key = load_api_key()
    if not api_key:
        display_error_message()
        st.stop()

    if not initialize_backend(api_key):
        st.stop()

    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Medication Safety Check",
            "Clinical Chat",
            "Patient Education",
            "Agent Monitoring",
        ]
    )

    with tab1:
        render_medication_safety_tab()

    with tab2:
        render_chat_tab()

    with tab3:
        render_education_tab()

    with tab4:
        render_agent_monitor_tab()

    st.markdown("---")
    st.caption(
        "This system is designed to support clinical decision-making. "
        "All recommendations must be reviewed and confirmed by qualified "
        "healthcare professionals before acting on them."
    )


if __name__ == "__main__":
    main()
