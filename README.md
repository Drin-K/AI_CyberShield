# **AI CyberShield**
### *Dual-Layer Cyber Defense: Phishing Detection + DNS Tunneling Detection*

---

## **Overview**
**AI CyberShield** is a prototype cybersecurity system designed to detect and prevent two major threats:

1. **Phishing Attacks** – detected through advanced email content analysis  
2. **DNS Tunneling** – identified via network traffic pattern analysis  

By integrating both detection engines, the system forms a **unified, AI-driven defense** that analyzes, correlates, and reacts in **real time**.

---

## **System Workflow**

1. **Data Input**  
   Collects information from two primary sources:  
   - Email content (subject, body) via Gmail extension  
   - DNS traffic packets for tunneling analysis  

2. **Detection**  
   - **Phishing:** Logistic Regression + TF-IDF analyze textual features.  
   - **DNS Tunneling:** Random Forest detects suspicious network behaviors (entropy, packet size, query frequency).  

3. **Intelligence Fusion**  
   Combines phishing and DNS results into a single **Risk Score (0–1)** for unified threat evaluation.  

4. **Response**  
   Displays detection results in the Gmail UI:  
   - *Safe* – No threat detected  
   - *Warning* – Potentially risky  
   - *Phishing Detected* – High-risk content  

5. **Human Action**  
   A single click on **“Send to SOC”** escalates incidents for real-time analysis by the Security Operations Center.  

6. **Learning Loop**  
   SOC feedback continuously retrains AI models, improving detection accuracy over time.

---

## **Core Components**

| Component | Technology |
|------------|-------------|
| **Phishing Detection** | Logistic Regression + TF-IDF |
| **DNS Detection** | Random Forest Classifier |
| **Backend** | Flask / FastAPI |
| **Database** | MongoDB / SQLite |
| **UI** | Gmail Extension |
| **Integration** | SOC Reporting System |

---

## **Installation & Run**

**1. Clone the repository**
```bash
git clone https://github.com/<your-username>/AI-CyberShield.git
cd AI-CyberShield
```
**2. Install dependencies**
```bash
pip install -r requirements.txt
python backend/api.py
```
**3. Run the backend server**
```bash
python backend/api.py
```
**Load the Gmail Extension**

Open your browser → Extensions → Developer Mode → Load unpacked

Select the folder /ui_extension

## **Team Members**
Bardh Tahiri

Diella Kika

Drin Kurti

Jon Jashari

Lize Syla

