# The-Patient-Guardian-
Patient Safety Guardian is an AI-powered clinical decision support system built as a capstone for Agents Intensive Competition. It helps clinicians reduce medical errors by analyzing prescriptions, detecting drug interactions, assessing risks, generating patient education, and enabling real-time safety checks through an agentic AI interface.

# Folder Structure
```bash
The Patient Guardian/
├── patient_safety_guardian.py # Core Python file for managing patient data and safety protocols
├── app.py # Application entry point for running the app
├── .streamlit/
│ └── secrets.toml # Contains sensitive information such as the Gemini API Key
├── patients/
│ ├── patient_id1.json # Patient data file for patient with ID 1
│ ├── patient_id2.json # Patient data file for patient with ID 2
│ └── ... # Additional patient data files for each patient
```

### Description of Files and Directories

- **`patient_safety_guardian.py`**: This file contains the main logic and functions related to patient safety. It includes handling patient data, medication management, and other safety protocols.
  
- **`app.py`**: This is the entry point for the application, used to run the app and interact with the user interface. It imports from the `patient_safety_guardian.py` file.

- **`.streamlit/secrets.toml`**: A configuration file that securely stores sensitive information, such as API keys (e.g., Gemini API Key), used by the app.

- **`patients/`**: This directory contains JSON files for each patient, where patient-specific data (such as medical conditions, medications, lab results, etc.) are stored. Each file is named after the patient's unique `patient_id`, e.g., `patient_id1.json`, `patient_id2.json`, etc.

---

## Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone [<repository_url>](https://github.com/Khanz9664/The-Patient-Guardian-.git)
   cd The-Patient-Guardian
   ```
2. **Install dependencies**:
  Make sure you have the necessary Python libraries installed:
  ```bash
  pip install -r requirements.txt
  ```

3. **Configure secrets**:
  In .streamlit/secrets.toml, add your Gemini API Key:
  [gemini]
  ```bash
  api_key = "your_api_key_here"
  ```

4. **Run the application**:
  To start the app, run:
  ```bash
  streamlit run app.py
  ```

---

### Note on Patient Data
Patient data is stored in individual JSON files under the patients/ directory. Each file contains information specific to the patient, such as:

patient_id
name
age
medical_conditions
medications
allergies
Recent lab results
Vital signs
Clinical notes


```Ensure that sensitive patient information is handled according to the appropriate data protection and privacy standards.```

---

### Key Sections:

- **Folder Structure**: Visualizes the project structure, making it easy for others to understand how the project is organized.
- **File Descriptions**: Provides a brief explanation of each file’s role in the project.
- **Setup Instructions**: Clear steps on how to get the project up and running.
- **Note on Patient Data**: Emphasizes the importance of handling sensitive data responsibly.
