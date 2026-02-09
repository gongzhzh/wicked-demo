# wicked-demo
WICKED is a creativity-supporting chatbot that's devoted to helping testers be more innovative when designing testing scenarios during exploratory testing sessions. 

# Abstract
Exploratory Testing is a common and highly valued practice that  leverages the tester’s expertise, intuition, and their creativity to reveal unforeseen defects. Thus, creativity has always been considered one of the most essential problem-solving skills for an exploratory tester. Countless tools and models that help improve human creativity have been proposed in the past; however, the topic of how to support exploratory testers' creativity with tools has not been studied enough. In this study, we propose and evaluate an LLM-based chatbot that aims to support testers' creativity by stimulating divergent thinking and critical thinking during consultation chatting dialogues. The chatbot is driven by a multi-agent LLM-based system, which consists of two main agents: the Brainstormer and the Assumption Buster. Those agents communicate with testers using creativity-support patterns. To examine the magnitude and consistency, we conducted two scripted dialogue assessment sessions. The results show that using targeted system instructions and web-based retrieval tools meaningfully strengthens the chatbot’s ability (in both magnitude and consistency) to exhibit the intended creativity-supportive communication behaviors compared to a baseline. We also planned an assessment to further evaluate the assistant from a human-centric perspective for next-step work. Our study can contribute to researchers in AI for software engineering and creativity support tools. Additionally, our findings can help practitioners who aim to build LLM-driven tools that help support exploratory testers' creativity.

## Prerequisites
Python 3.11+
## Installation
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


## Executing the scripts

- Open a terminal in VS Code

- Execute the following commands:
```
streamlit run testing_assistant.py
```

## Preview
<img width="1178" height="788" alt="image" src="https://github.com/user-attachments/assets/cc275098-93ec-4db6-b65b-b8e9d27a2785" />



