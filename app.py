import os
import json
import streamlit as st
from datetime import datetime 

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
PAGE_ICON = "🏥"


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


def render_patient_snapshot(patient):
    """Render patient information in the sidebar."""
    st.markdown(f"**Name:** {patient.get('name', 'Unknown')}")
    st.markdown(f"**Age:** {patient.get('age', 'N/A')}")
    st.markdown(f"**Patient ID:** {patient.get('patient_id', 'N/A')}")

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
    st.markdown("---")
    st.markdown("**Add Clinical Note**")
    note_text = st.text_area("New note", key="sidebar_note", height=80)
    
    if st.button("Save Note"):
        if not note_text.strip():
            st.warning("Please enter a note before saving.")
        else:
            msg = add_clinical_note(note_text.strip())
            st.success(msg)


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
            placeholder="Hypertension, Diabetes, Atrial Fibrillation"
        )

        medications_text = st.text_area(
            "Current Medications (comma separated, names only)",
            placeholder="Warfarin, Metformin"
        )

        allergies_text = st.text_area(
            "Allergies (comma separated, names only)",
            placeholder="Penicillin, Aspirin"
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
                    "medical_conditions": [c.strip() for c in conditions_text.split(",") if c.strip()],
                    "current_medications": [
                        {
                            "name": m.strip(),
                            "dosage": "",
                            "frequency": "",
                            "purpose": "",
                            "start_date": ""
                        }
                        for m in medications_text.split(",") if m.strip()
                    ],
                    "allergies": [
                        {"allergen": a.strip(), "reaction": ""}
                        for a in allergies_text.split(",") if a.strip()
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


def render_medication_safety_tab():
    """Render medication safety check tab."""
    st.subheader("Comprehensive Medication Safety Check")
    st.markdown("Analyze medication interactions, allergies, and clinical guidelines")

    col1, col2 = st.columns(2)
    with col1:
        new_med = st.text_input("Medication Name", placeholder="e.g., Aspirin")
    with col2:
        dosage = st.text_input("Dosage / Schedule", placeholder="e.g., 81 mg once daily")

    if st.button("Run Safety Check", type="primary"):
        if not new_med.strip():
            st.warning("Please enter a medication name.")
        else:
            with st.spinner("Running comprehensive safety analysis..."):
                results = comprehensive_medication_check(new_med.strip(), dosage or None)

            if "error" in results:
                st.error(results["error"])
            else:
                st.success("Safety analysis complete")

                st.markdown("### Checks Performed")
                checks = results.get("checks_performed", [])
                if checks:
                    st.write(", ".join(checks))

                with st.expander("Drug Interaction Analysis", expanded=True):
                    st.markdown(results.get("drug_interactions", "No data available"))

                with st.expander("Allergy & Cross-Reactivity"):
                    st.markdown(results.get("allergy_safety", "No data available"))

                with st.expander("Risk Assessment"):
                    st.markdown(results.get("risk_assessment", "No data available"))

                with st.expander("Guideline Compliance"):
                    st.markdown(results.get("guidelines", "No data available"))

                with st.expander("Clinical Recommendation", expanded=True):
                    st.markdown(results.get("final_recommendation", "No data available"))


def render_chat_tab():
    """Render interactive chat tab."""
    st.subheader("Interactive Clinical Decision Support")
    st.markdown("Ask questions or submit medication orders for analysis")

    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.markdown(msg["content"])

    user_input = st.text_area(
        "Type your question or order",
        placeholder="e.g., 'Start patient on 81mg aspirin daily' or 'Check for contraindications'",
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
        st.success("Chat history cleared")
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
                    response = st.session_state.chat.send_message(user_input.strip())
                    reply_text = getattr(response, "text", str(response))
                except Exception as e:
                    reply_text = f"Error: {str(e)}"

            st.session_state.messages.append(
                {"role": "assistant", "content": reply_text}
            )
            st.rerun()

    if parse_order_btn:
        if not user_input.strip():
            st.warning("Please enter an order to parse.")
        else:
            with st.spinner("Parsing medical order..."):
                parsed = parse_medical_order(user_input.strip())
            
            st.markdown("**Structured Order Data:**")
            st.json(parsed)


def render_education_tab():
    """Render patient education tab."""
    st.subheader("Patient Education Material Generator")
    st.markdown("Generate easy-to-understand medication information for patients")

    col1, col2 = st.columns(2)
    with col1:
        med_name = st.text_input("Medication Name", placeholder="e.g., Warfarin")
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
                text = generate_patient_education(med_name.strip(), reading_level)
            
            st.markdown("### Patient Education Leaflet")
            st.markdown(text)
            
            st.download_button(
                label="Download as Text",
                data=text,
                file_name=f"{med_name.strip()}_patient_education.txt",
                mime="text/plain"
            )


def render_sidebar():
    """Render sidebar with patient information and controls."""
    with st.sidebar:
        st.header("Patient Information")
        
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

    st.title("Patient Safety Guardian")
    st.markdown(
        "AI-powered clinical decision support system for medication safety, "
        "allergy checks, and evidence-based guidelines"
    )

    api_key = load_api_key()
    if not api_key:
        display_error_message()
        st.stop()

    if not initialize_backend(api_key):
        st.stop()

    init_session_state()
    render_sidebar()

    tab1, tab2, tab3 = st.tabs([
        "Medication Safety Check",
        "Clinical Chat",
        "Patient Education"
    ])

    with tab1:
        render_medication_safety_tab()

    with tab2:
        render_chat_tab()

    with tab3:
        render_education_tab()

    st.markdown("---")
    st.caption(
        "This system is designed to support clinical decision-making. "
        "All recommendations should be reviewed by qualified healthcare professionals."
    )


if __name__ == "__main__":
    main()
