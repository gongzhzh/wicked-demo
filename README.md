# WICKED
WICKED is a creativity-supporting chatbot that's devoted to helping testers be more creative when designing testing scenarios during exploratory testing sessions. 

**Status:** Internal draft (not submitted). Cycle 1 complete; Cycle 2 ongoing.

**Abstract:**  
We build a multi-agent LLM chatbot to support creativity in exploratory testing by encouraging divergent and critical thinking. Two agents (Brainstormer and Assumption Buster) use creativity-support communication patterns. Scripted dialogue assessments show that targeted system instructions and web retrieval improve both the strength and consistency of these behaviors versus a baseline. Human-centric evaluation is next. This repository contains the experimental application's code and data used in the research evaluation.


🔁 Reproduction: see [`cycle 1/`](experiment/cycle-1/README.md)

# Installation
## Prerequisites
Python 3.11+
### 1. Clone the repository:
```
cd wicked-demo
```

### 2. Create a virtual environment

```
uv venv 
```

### 3. Activate the virtual environment

```
venv\Scripts\Activate
(or on Mac): source venv/bin/activate
```

### 4. Install libraries

```
uv pip install -r requirements.txt
```

### 5. Configuration
Rename the .env.example file to .env


### 6. Executing the scripts

- Open a terminal in VS Code

- Execute the following commands:
```
streamlit run testing_assistant.py
```

## Preview
<img width="1178" height="788" alt="image" src="https://github.com/user-attachments/assets/cc275098-93ec-4db6-b65b-b8e9d27a2785" />



